from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_text(*parts: str) -> str:
    return (PROJECT_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


class SkillDocumentationTests(unittest.TestCase):
    def test_daily_brief_format_reference_exists_and_mentions_demo_sections(self) -> None:
        brief_format_text = read_text("references", "daily-brief-format.md")

        self.assertIn("daily_brief.md", brief_format_text)
        self.assertIn("数据来源：", brief_format_text)
        self.assertIn("覆盖时段：", brief_format_text)
        self.assertIn("生成时间：", brief_format_text)
        self.assertIn("一句话主线", brief_format_text)
        self.assertIn("核心矛盾", brief_format_text)
        self.assertIn("现象层", brief_format_text)
        self.assertIn("归因层", brief_format_text)
        self.assertIn("传导机制", brief_format_text)
        self.assertIn("外推结论", brief_format_text)
        self.assertIn("应对策略", brief_format_text)
        self.assertIn("反证清单", brief_format_text)
        self.assertIn("今日待跟踪问题", brief_format_text)

    def test_summary_sections_are_consistent_across_docs(self) -> None:
        skill_text = read_text("SKILL.md")
        extend_text = read_text("EXTEND.md")
        workflow_text = read_text("references", "workflow.md")
        summary_text = read_text("references", "summary-format.md")

        for text in (skill_text, extend_text, workflow_text, summary_text):
            self.assertIn("总观点", text)
            self.assertIn("分观点", text)

        for text in (skill_text, extend_text):
            self.assertNotIn("核心内容", text)
            self.assertNotIn("背景语境", text)
            self.assertNotIn("Spec相关", text)

    def test_capture_flow_uses_repo_local_browser_access_and_not_web_access(self) -> None:
        skill_text = read_text("SKILL.md")
        workflow_text = read_text("references", "workflow.md")

        for text in (skill_text, workflow_text):
            self.assertNotIn("web-access", text)
            self.assertIn("extract_xueqiu_posts.mjs", text)

        self.assertNotIn("scripts/content_task.py", skill_text)
        self.assertIn("scripts/content_task.py", workflow_text)

    def test_repo_local_browser_access_files_exist(self) -> None:
        extract_script = PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs"
        weibo_script = PROJECT_ROOT / "scripts" / "extract_weibo_posts.mjs"
        wechat_script = PROJECT_ROOT / "scripts" / "extract_wechat_articles.mjs"
        vendor_entry = PROJECT_ROOT / "scripts" / "vendor" / "baoyu-chrome-cdp" / "src" / "index.mjs"

        self.assertTrue(extract_script.exists(), extract_script)
        self.assertTrue(weibo_script.exists(), weibo_script)
        self.assertTrue(wechat_script.exists(), wechat_script)
        self.assertTrue(vendor_entry.exists(), vendor_entry)

    def test_docs_describe_weibo_accounts_and_markdown_raw_files(self) -> None:
        skill_text = read_text("SKILL.md")
        extend_text = read_text("EXTEND.md")
        workflow_text = read_text("references", "workflow.md")
        file_layout_text = read_text("references", "file-layout.md")

        self.assertIn("Weibo Accounts", extend_text)
        self.assertIn("weibo.com/u/", extend_text)
        for text in (skill_text, workflow_text):
            self.assertIn("extract_weibo_posts.mjs", text)
            self.assertIn("微博", text)

        self.assertIn(".md", file_layout_text)
        self.assertIn("平台", file_layout_text)

    def test_docs_describe_wechat_article_link_and_history_url_capture_scope(self) -> None:
        skill_text = read_text("SKILL.md")
        extend_text = read_text("EXTEND.md")
        workflow_text = read_text("references", "workflow.md")

        for text in (skill_text, extend_text, workflow_text):
            self.assertIn("微信公众号", text)
            self.assertIn("extract_wechat_articles.mjs", text)
            self.assertIn("文章链接", text)
            self.assertIn("--history-url", text)

        self.assertIn("公众号主页/历史消息", workflow_text)
        self.assertNotIn("不支持公众号主页自动发现", workflow_text)

    def test_workflow_contains_local_command_reference_without_usage_doc(self) -> None:
        skill_text = read_text("SKILL.md")
        workflow_text = read_text("references", "workflow.md")

        self.assertNotIn("usage.md", skill_text)
        self.assertNotIn("usage.md", workflow_text)
        self.assertIn("scripts/task_store.py init", workflow_text)
        self.assertIn("scripts/content_task.py", workflow_text)

    def test_processing_directory_is_described_under_author_directory(self) -> None:
        skill_text = read_text("SKILL.md")
        extend_text = read_text("EXTEND.md")
        output_layout_text = read_text("references", "output-layout.md")

        expected = "{yyyymmdd}/{author}/processing/"
        for text in (skill_text, extend_text, output_layout_text):
            self.assertIn(expected, text)

        self.assertNotIn("{yyyymmdd}/processing/", output_layout_text)

    def test_docs_describe_day_level_daily_brief_output(self) -> None:
        skill_text = read_text("SKILL.md")
        workflow_text = read_text("references", "workflow.md")
        output_layout_text = read_text("references", "output-layout.md")

        for text in (skill_text, workflow_text, output_layout_text):
            self.assertIn("daily_brief.md", text)
            self.assertIn("{yyyymmdd}/daily_brief.md", text)

        self.assertIn("demo.md", workflow_text)
        self.assertIn("今日简报", workflow_text)

    def test_dedicated_automation_chrome_is_prepared_before_capture(self) -> None:
        skill_text = read_text("SKILL.md")
        workflow_text = read_text("references", "workflow.md")

        for text in (skill_text, workflow_text):
            self.assertIn("1.3", text)
            self.assertIn("自动化专用 Chrome 实例", text)
            self.assertIn("复用第 1.3 步", text)
            self.assertIn("start_automation_chrome.sh", text)

    def test_output_root_is_defined_by_extend(self) -> None:
        skill_text = read_text("SKILL.md")
        extend_text = read_text("EXTEND.md")
        workflow_text = read_text("references", "workflow.md")
        output_layout_text = read_text("references", "output-layout.md")
        file_layout_text = read_text("references", "file-layout.md")

        self.assertIn("preferred output root", extend_text)
        for text in (skill_text, workflow_text, output_layout_text, file_layout_text):
            self.assertIn("EXTEND.md", text)
            self.assertNotIn("/Users/cjw/dev/projects/skills_output", text)

    def test_docs_describe_auto_verification_with_manual_fallback(self) -> None:
        skill_text = read_text("SKILL.md")
        workflow_text = read_text("references", "workflow.md")
        error_policy_text = read_text("references", "error-policy.md")

        for text in (skill_text, workflow_text, error_policy_text):
            self.assertIn("自动", text)
            self.assertIn("人工", text)

        self.assertIn("登录", workflow_text)
        self.assertIn("验证", workflow_text)
        self.assertIn("回退", error_policy_text)


if __name__ == "__main__":
    unittest.main()
