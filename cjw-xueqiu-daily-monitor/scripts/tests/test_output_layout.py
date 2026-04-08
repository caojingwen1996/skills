from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from datetime import date
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


class OutputLayoutTests(unittest.TestCase):
    def test_content_task_builds_date_scoped_author_directory(self) -> None:
        from scripts.content_task import build_result_paths

        output_root = Path("/tmp/xueqiu-output")
        result_dir, log_file = build_result_paths(output_root, "闵行一霸 - 雪球", date(2026, 4, 6))

        self.assertEqual(result_dir, output_root / "20260406" / "闵行一霸_-_雪球")
        self.assertEqual(log_file, output_root / "20260406" / "闵行一霸_-_雪球" / "task.log")

    def test_output_root_defaults_to_extend_configuration(self) -> None:
        from scripts.utils import resolve_output_root

        with tempfile.TemporaryDirectory() as tmpdir:
            configured_root = (Path(tmpdir) / "skills_output").resolve()
            extend_file = Path(tmpdir) / "EXTEND.md"
            extend_file.write_text(
                f"# Config\n\n- preferred output root: `{configured_root}`\n",
                encoding="utf-8",
            )

            resolved = resolve_output_root(None, extend_file=extend_file)

            self.assertEqual(resolved, configured_root)

    def test_task_store_init_writes_state_inside_date_scoped_author_directory(self) -> None:
        from scripts.task_store import init_command, load_state

        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = (Path(tmpdir) / "output").resolve()
            args = Namespace(
                output_root=str(output_root),
                start_time="2026-04-06 09:30:00",
                account="闵行一霸",
                chrome_profile="/tmp/chrome-profile",
                resume_existing=False,
            )

            exit_code = init_command(args)

            self.assertEqual(exit_code, 0)
            state_file = output_root / "20260406" / "闵行一霸" / "state.json"
            self.assertTrue(state_file.exists())

            state = load_state(state_file)
            self.assertEqual(state["result_dir"], str(output_root / "20260406" / "闵行一霸"))
            self.assertEqual(state["log_file"], str(output_root / "20260406" / "闵行一霸" / "task.log"))
            self.assertEqual(state["state_file"], str(state_file))

if __name__ == "__main__":
    unittest.main()
