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

    def test_process_extracted_posts_saves_markdown_and_skips_duplicates(self) -> None:
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
                            "author_name": "测试作者",
                            "platform": "xueqiu",
                        },
                        {
                            "title": "非目标日期",
                            "published_at": "2026-04-06 09:30:00",
                            "url": "https://xueqiu.com/u/9838764557/status/1002",
                            "content": "正文二",
                            "author_name": "测试作者",
                            "platform": "xueqiu",
                        },
                        {
                            "title": "重复内容",
                            "published_at": "2026-04-07 09:45:00",
                            "url": "https://xueqiu.com/u/9838764557/status/1001",
                            "content": "正文一重复",
                            "author_name": "测试作者",
                            "platform": "xueqiu",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            args = Namespace(
                input_file=str(input_file),
                author_name="测试作者",
                account_url="https://xueqiu.com/u/9838764557",
                date="2026-04-07",
                output_dir=str(output_root),
            )

            summary = process_extracted_posts(args)

            result_dir = output_root / "20260407" / "测试作者"
            files = sorted(path.name for path in result_dir.glob("*.md"))

            self.assertEqual(summary.candidate_count, 3)
            self.assertEqual(summary.matched_count, 2)
            self.assertEqual(summary.success_count, 1)
            self.assertEqual(summary.skipped_count, 2)
            self.assertEqual(summary.failure_count, 0)
            self.assertEqual(len(files), 1)

            saved_text = (result_dir / files[0]).read_text(encoding="utf-8")
            self.assertTrue(saved_text.startswith("标题：第一条"))
            self.assertIn("平台：xueqiu", saved_text)
            self.assertIn("\n\n正文：\n正文一", saved_text)

    def test_author_root_date_layout_groups_by_post_date_and_saves_author_comments(self) -> None:
        from scripts.content_task import process_extracted_posts

        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "测试作者"
            input_file = Path(tmpdir) / "posts.json"
            input_file.write_text(
                json.dumps(
                    [
                        {
                            "title": "五月二十五日文章",
                            "published_at": "2026-05-25 09:30:00",
                            "url": "https://weibo.com/7796318711/1001",
                            "content": "正文一",
                            "author_name": "测试作者",
                            "platform": "weibo",
                            "author_comments": [
                                {
                                    "author_name": "测试作者",
                                    "published_at": "2026-05-25 10:00:00",
                                    "content": "作者评论一",
                                }
                            ],
                        },
                        {
                            "title": "五月二十四日文章",
                            "published_at": "2026-05-24 13:00:00",
                            "url": "https://weibo.com/7796318711/1002",
                            "content": "正文二",
                            "author_name": "测试作者",
                            "platform": "weibo",
                            "author_comments": [],
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            args = Namespace(
                input_file=str(input_file),
                author_name="测试作者",
                account_url="https://weibo.com/u/7796318711",
                date="2026-05-25",
                output_dir=str(output_root),
                date_source="post",
                date_filter="off",
                layout="author-root-date",
            )

            summary = process_extracted_posts(args)

            first_day = output_root / "20260525"
            second_day = output_root / "20260524"
            first_files = sorted(first_day.glob("*.md"))
            second_files = sorted(second_day.glob("*.md"))

            self.assertEqual(summary.candidate_count, 2)
            self.assertEqual(summary.matched_count, 2)
            self.assertEqual(summary.success_count, 2)
            self.assertEqual(summary.failure_count, 0)
            self.assertEqual(len(first_files), 1)
            self.assertEqual(len(second_files), 1)
            self.assertTrue((first_day / "state.json").exists())
            self.assertTrue((second_day / "state.json").exists())
            self.assertTrue((first_day / "processing").exists())

            saved_text = first_files[0].read_text(encoding="utf-8")
            self.assertIn("平台：weibo", saved_text)
            self.assertIn("作者评论：", saved_text)
            self.assertIn("作者评论一", saved_text)


if __name__ == "__main__":
    unittest.main()
