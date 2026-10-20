"""边界自测用例：交付前跑一遍，覆盖正常路径与常见脏输入。"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kit import api_sync, rename_batch, sheet_ops  # noqa: E402


class TestExtractDate(unittest.TestCase):
    def test_compact_date(self):
        self.assertEqual(rename_batch.extract_date("IMG_20240715_093012.jpg")[0], "2024-07-15")

    def test_dash_date(self):
        self.assertEqual(rename_batch.extract_date("扫描件2024-08-12.pdf")[0], "2024-08-12")

    def test_cn_date(self):
        self.assertEqual(rename_batch.extract_date("对账单2024年9月3日.xlsx")[0], "2024-09-03")

    def test_invalid_date_falls_back(self):
        # 2024-13-45 是假日期，必须继续往下找，最终落回 mtime
        date, source = rename_batch.extract_date("2024-13-45.jpg", mtime=1700000000)
        self.assertIn(source, ("mtime", "unknown"))
        self.assertNotEqual(date, "2024-13-45")

    def test_no_date_uses_mtime(self):
        date, source = rename_batch.extract_date("photo.jpg", mtime=1700000000)
        self.assertEqual(source, "mtime")
        self.assertTrue(date.startswith("2023-11"))


class TestRenamePlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for i, name in enumerate(["b_20240102.jpg", "a_20240101.jpg", "c.jpg"]):
            (self.dir / name).write_bytes(b"x" * (i + 1))

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_count_and_template(self):
        plan = rename_batch.build_plan(self.dir, template="{date}_{seq:03d}{ext}", sort_by="name")
        self.assertEqual(len(plan), 3)
        self.assertEqual(plan[0]["new_name"], "2024-01-01_001.jpg")
        self.assertEqual(plan[1]["new_name"], "2024-01-02_002.jpg")

    def test_pattern_filter(self):
        plan = rename_batch.build_plan(self.dir, pattern="*.jpg", sort_by="name")
        self.assertEqual(len(plan), 3)
        plan = rename_batch.build_plan(self.dir, pattern="*.png", sort_by="name")
        self.assertEqual(len(plan), 0)

    def test_conflict_detected_when_template_has_no_seq(self):
        plan = rename_batch.build_plan(self.dir, template="fixed{ext}", sort_by="name")
        problems = rename_batch.check_plan(plan, self.dir)
        self.assertTrue(any("重名冲突" in p for p in problems))

    def test_apply_is_idempotent_and_reports(self):
        plan = rename_batch.build_plan(self.dir, template="{date}_{seq:03d}{ext}", sort_by="name")
        self.assertEqual(rename_batch.check_plan(plan, self.dir), [])
        stats = rename_batch.apply_plan(plan, self.dir)
        self.assertEqual(stats["renamed"], 3)
        again = rename_batch.apply_plan(plan, self.dir)
        self.assertEqual(again["renamed"], 0)  # 源文件已不存在，不会二次改坏

    def test_missing_dir_raises(self):
        with self.assertRaises(NotADirectoryError):
            rename_batch.build_plan(self.dir / "not-exist")


class TestSheetOps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _csv(self, name, header, rows):
        path = self.dir / name
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        return path

    def test_merge_aligns_different_headers(self):
        a = self._csv("a.csv", ["id", "region", "备注"], [["1", "华东", "含运费"]])
        b = self._csv("b.csv", ["id", "region", "channel"], [["2", "华南", "官网"]])
        out = self.dir / "m.csv"
        stats = sheet_ops.merge_csv([a, b], out)
        self.assertEqual(stats["rows_out"], 2)
        self.assertIn("来源文件", stats and csv_header(out))
        _, rows = sheet_ops.read_csv(out)
        self.assertEqual(rows[0]["备注"], "含运费")
        self.assertEqual(rows[1]["备注"], "")  # 缺失列补空

    def test_merge_dedupe(self):
        a = self._csv("a.csv", ["id", "v"], [["1", "x"], ["2", "y"]])
        b = self._csv("b.csv", ["id", "v"], [["1", "x"], ["3", "z"]])
        stats = sheet_ops.merge_csv([a, b], self.dir / "m.csv", dedupe_key="id")
        self.assertEqual(stats["deduped"], 1)
        self.assertEqual(stats["rows_out"], 3)

    def test_merge_empty_input(self):
        with self.assertRaises(ValueError):
            sheet_ops.merge_csv([], self.dir / "m.csv")

    def test_split_by_column(self):
        src = self._csv("s.csv", ["id", "region"], [["1", "华东"], ["2", "华南"], ["3", "华东"], ["4", ""]])
        res = sheet_ops.split_csv(src, self.dir / "parts", by_column="region")
        self.assertEqual(res["groups"], 3)  # 华东 / 华南 / 空值分组
        self.assertTrue((self.dir / "parts" / "part_华东.csv").exists())

    def test_split_bad_column(self):
        src = self._csv("s.csv", ["id"], [["1"]])
        with self.assertRaises(KeyError):
            sheet_ops.split_csv(src, self.dir / "parts", by_column="nope")


class TestApiSync(unittest.TestCase):
    def test_retry_succeeds_and_row_count_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "o.csv"
            with api_sync.MockServer(total=57, fail_first_hit=True) as server:
                stats = api_sync.sync_orders(server.base_url, out, page_size=20, max_retries=4)
            self.assertEqual(stats["rows"], 57)
            self.assertEqual(stats["pages"], 3)
            self.assertGreaterEqual(stats["retries"], 3)  # 每页首次都会抖动
            self.assertTrue(out.exists())

    def test_gives_up_after_max_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                # 端口上没有服务，必然连不上
                api_sync.sync_orders("http://127.0.0.1:1", Path(tmp) / "o.csv", max_retries=1, timeout=0.3)


def csv_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig") as fh:
        return next(csv.reader(fh))


if __name__ == "__main__":
    unittest.main(verbosity=2)
