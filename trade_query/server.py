from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .database import Database
from .importer import import_workbook


IS_FROZEN = bool(getattr(sys, "frozen", False))
APP_ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent.parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT)) if IS_FROZEN else APP_ROOT
STATIC_DIR = RESOURCE_ROOT / "static"
DATA_DIR = Path(os.environ.get("DATA_DIR", APP_ROOT / "data"))
DB = Database(os.environ.get("DATABASE_PATH", DATA_DIR / "trade_query.db"))
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class AppHandler(BaseHTTPRequestHandler):
    server_version = "TradeQuery/0.1"

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._get_api(parsed.path, parse_qs(parsed.query))
            else:
                self._serve_page(parsed.path)
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._handle_error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/login":
                self._login()
            elif parsed.path == "/api/logout":
                self._logout()
            elif parsed.path == "/api/admin/import":
                self._require_admin()
                self._import()
            else:
                self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    def do_PUT(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            match = re.fullmatch(r"/api/admin/records/(\d+)", parsed.path)
            if not match:
                self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                return
            self._require_admin()
            payload = self._read_json()
            record = DB.update_record(int(match.group(1)), payload)
            self._json({"record": record})
        except Exception as exc:
            self._handle_error(exc)

    def _get_api(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/options":
            self._json(DB.options())
            return
        if path == "/api/trend":
            district = first(query, "district", "all")
            industry = first(query, "industry", "all")
            self._json({"items": DB.trend(district, industry)})
            return
        if path == "/api/summary":
            district, industry, year, quarter = query_filters(query)
            self._json({"items": DB.summary(district, industry, year, quarter)})
            return
        if path == "/api/records":
            district, industry, year, quarter = query_filters(query)
            self._json(
                {
                    "items": DB.records(
                        district,
                        industry,
                        year,
                        quarter,
                        search=first(query, "search", ""),
                    )
                }
            )
            return
        if path == "/api/admin/session":
            self._json({"authenticated": self._is_admin()})
            return
        if path == "/api/admin/batches":
            self._require_admin()
            self._json({"items": DB.recent_batches()})
            return
        self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

    def _serve_page(self, path: str) -> None:
        pages = {
            "/": "index.html",
            "/history": "history.html",
            "/admin": "admin.html",
        }
        if path in pages:
            self._serve_file(STATIC_DIR / pages[path])
            return
        if path.startswith("/static/"):
            relative = path.removeprefix("/static/")
            target = (STATIC_DIR / relative).resolve()
            if STATIC_DIR.resolve() not in target.parents:
                self._json({"error": "非法路径"}, HTTPStatus.BAD_REQUEST)
                return
            self._serve_file(target)
            return
        self._serve_file(STATIC_DIR / "404.html", HTTPStatus.NOT_FOUND)

    def _serve_file(self, path: Path, status: HTTPStatus = HTTPStatus.OK) -> None:
        if not path.is_file():
            self._json({"error": "文件不存在"}, HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
            mime += "; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def _login(self) -> None:
        payload = self._read_json()
        if not DB.verify_admin(str(payload.get("username", "")), str(payload.get("password", ""))):
            self._json({"error": "账户或密码有误！"}, HTTPStatus.UNAUTHORIZED)
            return
        token = create_session_token()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header(
            "Set-Cookie",
            f"trade_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800",
        )
        body = json.dumps({"authenticated": True}, ensure_ascii=False).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _logout(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header(
            "Set-Cookie",
            "trade_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
        )
        body = b'{"authenticated":false}'
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _import(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("导入请求必须使用 multipart/form-data")
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            raise ValueError("文件为空或超过 20MB 限制")
        message = BytesParser(policy=default).parsebytes(
            (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode()
            + self.rfile.read(length)
        )
        fields: dict[str, str] = {}
        file_bytes: bytes | None = None
        filename = ""
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            part_filename = part.get_filename()
            if part_filename:
                filename = Path(part_filename).name
                file_bytes = part.get_payload(decode=True)
            elif name:
                fields[name] = decode_multipart_text(part).strip()
        if not file_bytes or not filename.lower().endswith(".xlsx"):
            raise ValueError("请选择 .xlsx 文件")
        district = fields.get("district", "").strip()
        year = int(fields["year"]) if fields.get("year") else None
        upload_dir = DATA_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff（）()_.-]", "_", filename)
        batch_dir = upload_dir / uuid.uuid4().hex[:10]
        batch_dir.mkdir(parents=True, exist_ok=True)
        stored_path = batch_dir / safe_name
        stored_path.write_bytes(file_bytes)
        result = import_workbook(DB, stored_path, district, year)
        result["source_file"] = filename
        self._json({"result": result}, HTTPStatus.CREATED)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("请求正文无效")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _is_admin(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("trade_session")
        return bool(morsel and verify_session_token(morsel.value))

    def _require_admin(self) -> None:
        if not self._is_admin():
            raise PermissionError("请先登录管理员账户")

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, PermissionError):
            status = HTTPStatus.UNAUTHORIZED
        elif isinstance(exc, (ValueError, KeyError, json.JSONDecodeError)):
            status = HTTPStatus.BAD_REQUEST
        else:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            traceback.print_exc()
        if not self.wfile.closed:
            try:
                self._json({"error": str(exc)}, status)
            except (BrokenPipeError, ConnectionResetError):
                pass


def first(query: dict[str, list[str]], key: str, default_value: str) -> str:
    values = query.get(key)
    return values[0] if values else default_value


def decode_multipart_text(part: Any) -> str:
    """Decode browser FormData text fields as UTF-8 when MIME omits charset."""
    payload = part.get_payload(decode=True)
    if payload is None:
        return str(part.get_payload())
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def query_filters(query: dict[str, list[str]]) -> tuple[str, str, int, int]:
    district = first(query, "district", "all")
    industry = first(query, "industry", "all")
    try:
        year = int(first(query, "year", "0"))
        quarter = int(first(query, "quarter", "0"))
    except ValueError as exc:
        raise ValueError("年份或季度格式不正确") from exc
    if not (2000 <= year <= 2100 and 1 <= quarter <= 4):
        raise ValueError("请选择有效的年份和季度")
    return district, industry, year, quarter


def _secret() -> bytes:
    value = DB.get_setting("session_secret")
    if value is None:
        raise RuntimeError("系统尚未初始化")
    return value.encode()


def create_session_token() -> str:
    payload = f"admin:{int(time.time()) + 28_800}".encode()
    signature = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + b"." + signature).decode().rstrip("=")


def verify_session_token(token: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        payload, signature = raw.rsplit(b".", 1)
        expected = hmac.new(_secret(), payload, hashlib.sha256).digest()
        role, expires = payload.decode().split(":", 1)
        return role == "admin" and int(expires) >= int(time.time()) and hmac.compare_digest(signature, expected)
    except (ValueError, TypeError, UnicodeDecodeError):
        return False


def run() -> None:
    DB.initialize()
    host = os.environ.get("SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SERVER_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"“四下”贸易抽样调查数据查询已启动：http://127.0.0.1:{port}")
    print("局域网访问请使用：http://本机IP:%d" % port)
    open_browser_setting = os.environ.get("OPEN_BROWSER")
    should_open_browser = IS_FROZEN if open_browser_setting is None else open_browser_setting == "1"
    if should_open_browser:
        timer = threading.Timer(0.8, webbrowser.open, args=(f"http://127.0.0.1:{port}",))
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()
