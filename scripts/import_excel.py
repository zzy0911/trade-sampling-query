from __future__ import annotations

import argparse
from pathlib import Path

from trade_query.database import Database
from trade_query.importer import DuplicateSourceFileError, import_workbook


def main() -> None:
    parser = argparse.ArgumentParser(description="导入“四下”贸易季度 Excel 数据")
    parser.add_argument("file", type=Path, help="Excel 文件路径")
    parser.add_argument("--district", required=True, help="区域名称，如江北新区")
    parser.add_argument("--year", type=int, help="年份；省略时从文件名识别")
    parser.add_argument("--database", type=Path, default=Path("data/trade_query.db"))
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="确认删除并替换数据库中同名文件的全部现存数据",
    )
    args = parser.parse_args()

    database = Database(args.database)
    database.initialize()
    try:
        result = import_workbook(
            database, args.file, args.district, args.year, overwrite=args.overwrite
        )
    except DuplicateSourceFileError as exc:
        parser.error(f"{exc}；确认后请添加 --overwrite")
    print(
        f"导入完成：{result['district']} {result['year']}年，"
        f"共 {result['imported_rows']} 条记录"
    )


if __name__ == "__main__":
    main()
