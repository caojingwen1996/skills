from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SAMPLE_POST = """标题：昨天 20:15· 来自iPhone
内容ID：381128136
发布时间：2026-03-25 20:15:00
发布日期：2026-03-25
原始链接：https://xueqiu.com/9838764557/381128136
作者名称：闵行一霸 - 雪球
抓取时间：2026-03-26 16:02:34

正文：
很客观。今天的下跌非常惊心动魄。很多人在这种场景下其实都很手足无措。
$泡泡玛特(09992)$
"""

SAMPLE_EXTEND = """# Xueqiu Daily Monitor Extend

## Accounts

- [enabled] name: 闵行一霸
  url: https://xueqiu.com/u/9838764557
  note: 泡泡玛特、美团、港股成长股
"""


class DailySummaryTests(unittest.TestCase):
    def test_generates_processing_and_final_markdown(self) -> None:
        from scripts.daily_summary import generate_daily_summary

        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "output"
            raw_dir = output_root / "闵行一霸_-_雪球_20260325"
            raw_dir.mkdir(parents=True)
            (raw_dir / "201500_sample.txt").write_text(SAMPLE_POST, encoding="utf-8")
            extend_file = Path(tmpdir) / "EXTEND.md"
            extend_file.write_text(SAMPLE_EXTEND, encoding="utf-8")

            result = generate_daily_summary("2026-03-25", output_root=output_root, extend_file=extend_file)

            self.assertTrue((output_root / "processing" / "20260325" / "raw_index").exists())
            self.assertTrue((output_root / "processing" / "20260325" / "normalized").exists())
            self.assertTrue((output_root / "processing" / "20260325" / "extracted").exists())
            self.assertTrue((output_root / "processing" / "20260325" / "post_analysis").exists())
            self.assertTrue((output_root / "processing" / "20260325" / "author_daily").exists())
            self.assertTrue((output_root / "processing" / "20260325" / "market_daily").exists())
            self.assertTrue((output_root / "summaries" / "20260325" / "闵行一霸_-_雪球.md").exists())
            self.assertTrue((output_root / "summaries" / "20260325" / "daily_summary.md").exists())
            self.assertEqual(result["author_count"], 1)

            author_md = (output_root / "summaries" / "20260325" / "闵行一霸_-_雪球.md").read_text(encoding="utf-8")
            self.assertIn("## 1. 核心内容", author_md)
            self.assertIn("## 2. 背景语境", author_md)
            self.assertIn("## 3. Spec相关", author_md)
            self.assertIn("账号主页：https://xueqiu.com/u/9838764557", author_md)

            market_md = (output_root / "summaries" / "20260325" / "daily_summary.md").read_text(encoding="utf-8")
            self.assertIn("缺失/异常博主：无", market_md)


if __name__ == "__main__":
    unittest.main()
