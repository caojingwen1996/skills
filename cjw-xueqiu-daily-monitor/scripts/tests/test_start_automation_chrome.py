from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class StartAutomationChromeScriptTests(unittest.TestCase):
    def test_script_exists_and_uses_fixed_profile_and_port(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "start_automation_chrome.sh"
        text = script_path.read_text(encoding="utf-8")

        self.assertIn(".xueqiu-chrome-profile", text)
        self.assertIn('DEFAULT_DEBUG_PORT="9333"', text)
        self.assertIn("/json/version", text)
        self.assertIn("already running", text)
        self.assertIn("open", text)
        self.assertIn("-na", text)

    def test_script_supports_dry_run_for_fixed_launch_command(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "start_automation_chrome.sh"
        with tempfile.TemporaryDirectory() as tmpdir:
            chrome_path = Path(tmpdir) / "chrome"
            chrome_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            chrome_path.chmod(0o755)

            result = subprocess.run(
                ["bash", str(script_path)],
                cwd=PROJECT_ROOT,
                env={
                    **os.environ,
                    "DRY_RUN": "1",
                    "CHROME_PATH": str(chrome_path),
                },
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--remote-debugging-port=9333", result.stdout)
        self.assertIn(".xueqiu-chrome-profile", result.stdout)

    def test_script_uses_open_na_for_macos_app_bundle_dry_run(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "start_automation_chrome.sh"

        result = subprocess.run(
            ["bash", str(script_path)],
            cwd=PROJECT_ROOT,
            env={
                **os.environ,
                "DRY_RUN": "1",
                "CHROME_PATH": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            },
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("open -na", result.stdout)
        self.assertIn("/Applications/Google\\ Chrome.app", result.stdout)
        self.assertIn("--remote-debugging-port=9333", result.stdout)


if __name__ == "__main__":
    unittest.main()
