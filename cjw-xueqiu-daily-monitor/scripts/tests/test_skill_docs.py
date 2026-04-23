from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_text(*parts: str) -> str:
    return (PROJECT_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


class SkillDocumentationTests(unittest.TestCase):
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
        vendor_entry = PROJECT_ROOT / "scripts" / "vendor" / "baoyu-chrome-cdp" / "src" / "index.mjs"

        self.assertTrue(extract_script.exists(), extract_script)
        self.assertTrue(vendor_entry.exists(), vendor_entry)

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

        self.assertIn("/Users/cjw/dev/Obsidian/{skill_name}", extend_text)
        for text in (skill_text, workflow_text, output_layout_text, file_layout_text):
            self.assertIn("EXTEND.md", text)
            self.assertNotIn("/Users/cjw/dev/projects/skills_output", text)


if __name__ == "__main__":
    unittest.main()
