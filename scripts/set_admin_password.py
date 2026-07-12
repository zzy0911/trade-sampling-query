from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from trade_query.database import Database, hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="修改现有数据库的管理员密码")
    parser.add_argument("--database", type=Path, default=Path("data/trade_query.db"))
    args = parser.parse_args()
    password = getpass.getpass("新管理员密码：")
    confirmation = getpass.getpass("再次输入：")
    if len(password) < 10:
        raise SystemExit("密码至少需要 10 个字符")
    if password != confirmation:
        raise SystemExit("两次输入不一致")
    database = Database(args.database)
    database.initialize()
    database.set_setting("admin_password_hash", hash_password(password))
    print("管理员密码已更新")


if __name__ == "__main__":
    main()
