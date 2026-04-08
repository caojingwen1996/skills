from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ContentTaskTests(unittest.TestCase):
    def test_content_task_source_no_longer_contains_browser_workflow(self) -> None:
        text = (PROJECT_ROOT / "scripts" / "content_task.py").read_text(encoding="utf-8")

        self.assertNotIn("launch_persistent_browser", text)
        self.assertNotIn("ensure_login", text)
        self.assertNotIn("safe_open(", text)
        self.assertNotIn("scan_posts_on_homepage", text)
        self.assertNotIn("extract_post_content", text)

    def test_process_extracted_posts_saves_target_day_and_skips_duplicates(self) -> None:
        from scripts.content_task import process_extracted_posts

        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "output"
            input_file = Path(tmpdir) / "posts.json"
            input_file.write_text(
                json.dumps(
                    [
                        {
                            "title": "第一条",
                            "published_at": "2026-04-07 09:30:00",
                            "url": "https://xueqiu.com/u/9838764557/status/1001",
                            "content": "正文一",
                            "author_name": "闵行一霸",
                        },
                        {
                            "title": "第二条",
                            "published_at": "2026-04-06 09:30:00",
                            "url": "https://xueqiu.com/u/9838764557/status/1002",
                            "content": "正文二",
                            "author_name": "闵行一霸",
                        },
                        {
                            "title": "第一条重复",
                            "published_at": "2026-04-07 09:45:00",
                            "url": "https://xueqiu.com/u/9838764557/status/1001",
                            "content": "正文一重复",
                            "author_name": "闵行一霸",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            args = Namespace(
                input_file=str(input_file),
                author_name="闵行一霸",
                account_url="https://xueqiu.com/u/9838764557",
                date="2026-04-07",
                output_dir=str(output_root),
            )

            summary = process_extracted_posts(args)

            result_dir = output_root / "20260407" / "闵行一霸"
            files = sorted(path.name for path in result_dir.glob("*.txt"))

            self.assertEqual(summary.candidate_count, 3)
            self.assertEqual(summary.matched_count, 2)
            self.assertEqual(summary.success_count, 1)
            self.assertEqual(summary.skipped_count, 2)
            self.assertEqual(summary.failure_count, 0)
            self.assertEqual(len(files), 1)
            self.assertTrue((result_dir / files[0]).read_text(encoding="utf-8").startswith("标题：第一条"))


if __name__ == "__main__":
    unittest.main()
