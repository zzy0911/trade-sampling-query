from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    district TEXT NOT NULL,
    year INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    imported_rows INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    district TEXT NOT NULL,
    year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    subregion TEXT NOT NULL,
    unit_code TEXT NOT NULL,
    unit_name TEXT NOT NULL,
    industry_code TEXT NOT NULL,
    industry_name TEXT NOT NULL,
    metric_kind TEXT NOT NULL CHECK (metric_kind IN ('销售额', '营业额')),
    current_value REAL,
    previous_value REAL,
    yoy_rate REAL,
    explanation TEXT,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (district, year, quarter, unit_code, unit_name)
);

CREATE INDEX IF NOT EXISTS idx_records_filter
ON records (district, year, quarter, industry_name);

CREATE INDEX IF NOT EXISTS idx_records_unit
ON records (unit_name, unit_code);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            if self.get_setting("admin_password_hash", connection) is None:
                password = os.environ.get("ADMIN_PASSWORD", "admin123")
                self.set_setting("admin_password_hash", hash_password(password), connection)
            if self.get_setting("session_secret", connection) is None:
                self.set_setting("session_secret", secrets.token_hex(32), connection)

    def get_setting(
        self, key: str, connection: sqlite3.Connection | None = None
    ) -> str | None:
        if connection is not None:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return None if row is None else str(row["value"])
        with self.connect() as own_connection:
            return self.get_setting(key, own_connection)

    def set_setting(
        self, key: str, value: str, connection: sqlite3.Connection | None = None
    ) -> None:
        if connection is not None:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            return
        with self.connect() as own_connection:
            self.set_setting(key, value, own_connection)

    def verify_admin(self, username: str, password: str) -> bool:
        if username != os.environ.get("ADMIN_USERNAME", "admin"):
            return False
        stored = self.get_setting("admin_password_hash")
        return stored is not None and verify_password(password, stored)

    def options(self) -> dict[str, list[Any]]:
        with self.connect() as connection:
            districts = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT district FROM records ORDER BY district"
                )
            ]
            years = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT year FROM records ORDER BY year"
                )
            ]
            quarters = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT quarter FROM records ORDER BY quarter"
                )
            ]
        return {
            "districts": districts,
            "years": years,
            "industries": ["批发业", "零售业", "住宿业", "餐饮业"],
            "quarters": quarters or [1, 2, 3, 4],
        }

    @staticmethod
    def _filters(
        district: str | None = None,
        industry: str | None = None,
        year: int | None = None,
        quarter: int | None = None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if district and district != "all":
            clauses.append("district = ?")
            params.append(district)
        if industry and industry != "all":
            clauses.append("industry_name = ?")
            params.append(industry)
        if year is not None:
            clauses.append("year = ?")
            params.append(year)
        if quarter is not None:
            clauses.append("quarter = ?")
            params.append(quarter)
        return (" AND ".join(clauses) if clauses else "1 = 1"), params

    def trend(self, district: str, industry: str) -> list[dict[str, Any]]:
        where, params = self._filters(district=district, industry=industry)
        sql = f"""
            SELECT year, quarter,
                   SUM(current_value) AS current_value,
                   SUM(previous_value) AS previous_value,
                   COUNT(*) AS sample_count
            FROM records
            WHERE {where}
            GROUP BY year, quarter
            ORDER BY year, quarter
        """
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            current = row["current_value"]
            previous = row["previous_value"]
            yoy = None
            if previous not in (None, 0) and current is not None:
                yoy = (current - previous) / previous * 100
            result.append(
                {
                    "year": row["year"],
                    "quarter": row["quarter"],
                    "current_value": current,
                    "previous_value": previous,
                    "yoy_rate": yoy,
                    "sample_count": row["sample_count"],
                }
            )
        return result

    def summary(
        self, district: str, industry: str, year: int, quarter: int
    ) -> list[dict[str, Any]]:
        where, params = self._filters(district, industry, year, quarter)
        sql = f"""
            SELECT industry_name,
                   SUM(current_value) AS current_value,
                   SUM(previous_value) AS previous_value,
                   COUNT(*) AS sample_count
            FROM records
            WHERE {where}
            GROUP BY industry_name
            ORDER BY CASE industry_name
                WHEN '批发业' THEN 1 WHEN '零售业' THEN 2
                WHEN '住宿业' THEN 3 WHEN '餐饮业' THEN 4 ELSE 9 END
        """
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            previous = row["previous_value"]
            current = row["current_value"]
            yoy = (
                (current - previous) / previous * 100
                if previous not in (None, 0) and current is not None
                else None
            )
            result.append({**dict(row), "yoy_rate": yoy})
        return result

    def records(
        self,
        district: str,
        industry: str,
        year: int,
        quarter: int,
        search: str = "",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        where, params = self._filters(district, industry, year, quarter)
        previous_year = year if quarter > 1 else year - 1
        previous_quarter = quarter - 1 if quarter > 1 else 4
        if search:
            where += " AND (unit_name LIKE ? OR unit_code LIKE ? OR subregion LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term])
        query_params = [
            previous_year,
            previous_quarter,
            previous_year,
            previous_quarter,
            *params,
            min(max(limit, 1), 2000),
        ]
        sql = f"""
            SELECT id, district, year, quarter, subregion, unit_code, unit_name,
                   industry_code, industry_name, metric_kind, current_value,
                   previous_value, yoy_rate, explanation,
                   CASE
                       WHEN EXISTS (
                           SELECT 1 FROM records AS previous_any
                           WHERE previous_any.district = records.district
                             AND previous_any.year = ? AND previous_any.quarter = ?
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM records AS previous_unit
                           WHERE previous_unit.district = records.district
                             AND previous_unit.year = ? AND previous_unit.quarter = ?
                             AND previous_unit.unit_code = records.unit_code
                             AND previous_unit.unit_name = records.unit_name
                       )
                       THEN 1 ELSE 0
                   END AS is_new_unit
            FROM records
            WHERE {where}
            ORDER BY industry_name, subregion, unit_name
            LIMIT ?
        """
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, query_params)]

    def update_record(self, record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = numeric_or_none(payload.get("current_value"))
        previous = numeric_or_none(payload.get("previous_value"))
        yoy = None if previous in (None, 0) or current is None else (current - previous) / previous * 100
        explanation = clean_text(payload.get("explanation")) or None
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE records
                SET current_value = ?, previous_value = ?, yoy_rate = ?,
                    explanation = ?, updated_at = ?
                WHERE id = ?
                """,
                (current, previous, yoy, explanation, utc_now(), record_id),
            )
            row = connection.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            raise KeyError("记录不存在")
        return dict(row)

    def recent_batches(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM import_batches ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]


def clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def numeric_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("数值无效")
    return number


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (TypeError, ValueError):
        return False
