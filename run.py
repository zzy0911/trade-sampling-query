from __future__ import annotations

import argparse
import getpass

from trade_query.database import hash_password
from trade_query.server import DB, run


def set_admin_password() -> None:
    DB.initialize()
    password = getpass.getpass("新管理员密码：")
    confirmation = getpass.getpass("再次输入：")
    if len(password) < 10:
        raise SystemExit("密码至少需要 10 个字符")
    if password != confirmation:
        raise SystemExit("两次输入不一致")
    DB.set_setting("admin_password_hash", hash_password(password))
    print("管理员密码已更新")


def main() -> None:
    parser = argparse.ArgumentParser(description="“四下”贸易抽样调查数据查询")
    parser.add_argument("--set-admin-password", action="store_true", help="修改管理员密码")
    args = parser.parse_args()
    if args.set_admin_password:
        set_admin_password()
    else:
        run()


if __name__ == "__main__":
    main()
