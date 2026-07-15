from __future__ import annotations

import tempfile
import unittest
from email.parser import BytesParser
from email.policy import default
from pathlib import Path

from openpyxl import Workbook

from trade_query.database import Database, hash_password, verify_password
from trade_query.importer import extract_quarter, industry_info, normalize_code, read_workbook
from trade_query.server import decode_multipart_text


class CoreTests(unittest.TestCase):
    def test_frontend_avoids_array_at_for_legacy_browsers(self) -> None:
        static_dir = Path(__file__).resolve().parent.parent / "static"
        for script in static_dir.glob("*.js"):
            self.assertNotIn(".at(", script.read_text(encoding="utf-8"), script.name)

    def test_industry_mapping(self) -> None:
        self.assertEqual(industry_info(5123), ("批发业", "销售额"))
        self.assertEqual(industry_info("5299"), ("零售业", "销售额"))
        self.assertEqual(industry_info(6129), ("住宿业", "营业额"))
        self.assertEqual(industry_info("6291"), ("餐饮业", "营业额"))
        self.assertIsNone(industry_info("7010"))

    def test_normalize_long_code(self) -> None:
        self.assertEqual(normalize_code(320111003010510000), "320111003010510000")
        self.assertEqual(normalize_code(3.2011100400261e17), "320111004002610000")
        self.assertEqual(normalize_code("91320191MA1Y53AC7W"), "91320191MA1Y53AC7W")

    def test_quarter_parsing(self) -> None:
        self.assertEqual(extract_quarter("第1季度"), 1)
        self.assertEqual(extract_quarter("第二季度"), 2)
        self.assertIsNone(extract_quarter("汇总"))

    def test_previous_value_comes_from_the_same_quarter_sheet(self) -> None:
        headers = [
            "处理地名称",
            "单位代码",
            "单位名称",
            "行业代码",
            "商品销售额（批发和零售业单位填报）;本季度",
            "商品销售额（批发和零售业单位填报）;上年同期",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "测试2026.xlsx"
            workbook = Workbook()
            first_quarter = workbook.active
            first_quarter.title = "第1季度"
            first_quarter.append(headers)
            first_quarter.append(["街道", "001", "测试单位", "5219", 100, 10])
            second_quarter = workbook.create_sheet("第2季度")
            second_quarter.append(headers)
            second_quarter.append(["街道", "001", "测试单位", "5219", 220, 40])
            workbook.save(path)
            workbook.close()

            records = read_workbook(path, "测试区域", 2026)
            second_record = next(record for record in records if record["quarter"] == 2)
            self.assertEqual(second_record["current_value"], 220)
            self.assertEqual(second_record["previous_value"], 40)
            self.assertAlmostEqual(second_record["yoy_rate"], 450)

    def test_password_hash(self) -> None:
        encoded = hash_password("correct-password")
        self.assertTrue(verify_password("correct-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))

    def test_browser_formdata_chinese_field(self) -> None:
        boundary = "test-boundary"
        body = (
            f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="district"\r\n\r\n'
        ).encode() + "江北新区".encode("utf-8") + f"\r\n--{boundary}--\r\n".encode()
        message = BytesParser(policy=default).parsebytes(body)
        part = next(message.iter_parts())
        self.assertEqual(decode_multipart_text(part), "江北新区")

    def test_database_aggregate_and_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            database.initialize()
            now = "2026-01-01T00:00:00+00:00"
            with database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO records(
                        district, year, quarter, subregion, unit_code, unit_name,
                        industry_code, industry_name, metric_kind, current_value,
                        previous_value, yoy_rate, explanation, source_file, created_at, updated_at
                    ) VALUES('江北新区', 2026, 1, '沿江街道', '001', '测试单位',
                             '5219', '零售业', '销售额', 120, 100, 20, NULL, 'test.xlsx', ?, ?)
                    """,
                    (now, now),
                )
            trend = database.trend("all", "all")
            self.assertEqual(len(trend), 1)
            self.assertAlmostEqual(trend[0]["yoy_rate"], 20)
            record = database.records("all", "all", 2026, 1)[0]
            updated = database.update_record(
                record["id"], {"current_value": 90, "previous_value": 100, "explanation": "修订"}
            )
            self.assertAlmostEqual(updated["yoy_rate"], -10)
            self.assertEqual(updated["explanation"], "修订")

    def test_records_mark_units_replaced_since_previous_quarter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.db")
            database.initialize()
            now = "2026-01-01T00:00:00+00:00"
            rows = [
                (2025, 4, "001", "延续单位"),
                (2026, 1, "001", "延续单位"),
                (2026, 1, "002", "新替换单位"),
            ]
            with database.connect() as connection:
                connection.executemany(
                    """
                    INSERT INTO records(
                        district, year, quarter, subregion, unit_code, unit_name,
                        industry_code, industry_name, metric_kind, current_value,
                        previous_value, yoy_rate, explanation, source_file, created_at, updated_at
                    ) VALUES('测试区域', ?, ?, '测试街道', ?, ?,
                             '5219', '零售业', '销售额', 120, 100, 20, NULL, 'test.xlsx', ?, ?)
                    """,
                    [(year, quarter, code, name, now, now) for year, quarter, code, name in rows],
                )

            records = database.records("测试区域", "all", 2026, 1)
            replacement_flags = {record["unit_name"]: record["is_new_unit"] for record in records}
            self.assertEqual(replacement_flags["延续单位"], 0)
            self.assertEqual(replacement_flags["新替换单位"], 1)


if __name__ == "__main__":
    unittest.main()
