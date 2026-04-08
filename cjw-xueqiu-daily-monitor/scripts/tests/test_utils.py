from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class UtilsTests(unittest.TestCase):
    def test_utils_source_no_longer_contains_browser_workflow(self) -> None:
        text = (PROJECT_ROOT / "scripts" / "utils.py").read_text(encoding="utf-8")

        self.assertNotIn("playwright.sync_api", text)
        self.assertNotIn("launch_persistent_browser", text)
        self.assertNotIn("ensure_login", text)
        self.assertNotIn("discover_debugging_url", text)
        self.assertNotIn("safe_open(", text)
        self.assertNotIn("safe_click(", text)
        self.assertNotIn("close_browser(", text)

    def test_sanitize_filename_replaces_illegal_characters(self) -> None:
        from scripts.utils import sanitize_filename

        self.assertEqual(sanitize_filename('  a<>:"/\\\\|?*b  '), "a_b")

    def test_read_preferred_output_root_and_resolve_output_root(self) -> None:
        from scripts.utils import read_preferred_output_root, resolve_output_root

        with tempfile.TemporaryDirectory() as tmpdir:
            configured_root = str((Path(tmpdir) / "skills_output").resolve())
            extend_file = Path(tmpdir) / "EXTEND.md"
            extend_file.write_text(
                f"# Config\n\n- preferred output root: `{configured_root}`\n",
                encoding="utf-8",
            )

            self.assertEqual(read_preferred_output_root(extend_file), configured_root)
            self.assertEqual(resolve_output_root(None, extend_file=extend_file), Path(configured_root))


if __name__ == "__main__":
    unittest.main()
