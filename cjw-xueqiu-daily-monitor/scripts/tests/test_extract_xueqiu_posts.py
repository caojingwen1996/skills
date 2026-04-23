from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ExtractXueqiuPostsScriptTests(unittest.TestCase):
    def test_help_succeeds(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs"

        result = subprocess.run(
            ["node", str(script_path), "--help"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--account-url", result.stdout)
        self.assertIn("--date", result.stdout)

    def test_vendor_js_entry_contains_cdp_exports(self) -> None:
        vendor_path = PROJECT_ROOT / "scripts" / "vendor" / "baoyu-chrome-cdp" / "src" / "index.mjs"
        text = vendor_path.read_text(encoding="utf-8")

        self.assertIn("export class CdpConnection", text)
        self.assertIn("export async function openPageSession", text)
        self.assertIn("findChromeExecutable", text)

    def run_node_module_json(self, script: str) -> dict[str, object]:
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_target_date_filter_helpers(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs").as_uri()
        payload = self.run_node_module_json(
            f"""
import {{ inferPostDate, shouldKeepCandidateForTargetDate }} from {json.dumps(script_path)};
console.log(JSON.stringify({{
  exact: inferPostDate("2026-04-11 19:05", "2026-04-11"),
  keepTarget: shouldKeepCandidateForTargetDate({{ published_at: "2026-04-11 19:05" }}, "2026-04-11"),
  dropOther: shouldKeepCandidateForTargetDate({{ published_at: "2026-04-10 17:35" }}, "2026-04-11"),
  keepUnknown: shouldKeepCandidateForTargetDate({{ published_at: "" }}, "2026-04-11"),
}}));
"""
        )

        self.assertEqual(payload["exact"], "2026-04-11")
        self.assertTrue(payload["keepTarget"])
        self.assertFalse(payload["dropOther"])
        self.assertTrue(payload["keepUnknown"])

    def test_manual_action_payload_detection(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs").as_uri()
        payload = self.run_node_module_json(
            f"""
import {{ classifyManualActionPayload }} from {json.dumps(script_path)};
console.log(JSON.stringify({{
  verification: classifyManualActionPayload({{
    title: "访问验证",
    author_name: "访问验证",
    content: "别离开，为了更好的访问体验，请按住滑块，拖动到最右边"
  }}),
  login: classifyManualActionPayload({{
    title: "登录雪球",
    author_name: "雪球",
    content: "登录后即可查看全文，发帖、评论、互动更方便"
  }}),
  normal: classifyManualActionPayload({{
    title: "正常帖子",
    author_name: "买股票的老木匠",
    content: "这里是正常正文"
  }})
}}));
"""
        )

        self.assertEqual(payload["verification"], "verification")
        self.assertEqual(payload["login"], "login")
        self.assertFalse(payload["normal"])

    def test_manual_action_guidance_message_mentions_wait_and_resume(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs").as_uri()
        payload = self.run_node_module_json(
            f"""
import {{ formatManualActionGuidance }} from {json.dumps(script_path)};
console.log(JSON.stringify({{
  verification: formatManualActionGuidance("verification"),
  login: formatManualActionGuidance("login")
}}));
"""
        )

        self.assertIn("Manual action required", payload["verification"])
        self.assertIn("complete the Xueqiu verification in the automation Chrome window", payload["verification"])
        self.assertIn("wait", payload["verification"])
        self.assertIn("Manual action required", payload["login"])
        self.assertIn("log in to Xueqiu in the automation Chrome window", payload["login"])
        self.assertIn("wait", payload["login"])

    def test_manual_action_cleanup_plan_keeps_browser_open(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs").as_uri()
        payload = self.run_node_module_json(
            f"""
import {{ buildCleanupPlan }} from {json.dumps(script_path)};
console.log(JSON.stringify({{
  blocked: buildCleanupPlan({{ manualActionBlocked: true, launchedChrome: true }}),
  normal: buildCleanupPlan({{ manualActionBlocked: false, launchedChrome: true }})
}}));
"""
        )

        self.assertFalse(payload["blocked"]["closeDetailTarget"])
        self.assertFalse(payload["blocked"]["closeHomepageTarget"])
        self.assertFalse(payload["blocked"]["terminateLaunchedChrome"])
        self.assertTrue(payload["normal"]["closeDetailTarget"])
        self.assertTrue(payload["normal"]["closeHomepageTarget"])
        self.assertTrue(payload["normal"]["terminateLaunchedChrome"])

    def test_verification_mode_defaults_to_auto_then_manual(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs").as_uri()
        payload = self.run_node_module_json(
            f"""
import {{ parseArgsForTesting }} from {json.dumps(script_path)};
console.log(JSON.stringify(parseArgsForTesting([
  "--account-url", "https://xueqiu.com/u/1",
  "--date", "2026-04-23"
])));
"""
        )

        self.assertEqual(payload["verificationMode"], "auto-then-manual")

    def test_verification_mode_rejects_invalid_value(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs").as_uri()
        result = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                f"""
import {{ parseArgsForTesting }} from {json.dumps(script_path)};
parseArgsForTesting([
  "--account-url", "https://xueqiu.com/u/1",
  "--date", "2026-04-23",
  "--verification-mode", "bad"
]);
""",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verification-mode", result.stderr)

    def test_should_fallback_to_manual_wait(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs").as_uri()
        payload = self.run_node_module_json(
            f"""
import {{ shouldFallbackToManualWait }} from {json.dumps(script_path)};
console.log(JSON.stringify({{
  manual: shouldFallbackToManualWait("manual", false),
  autoThenManual: shouldFallbackToManualWait("auto-then-manual", false),
  autoOnly: shouldFallbackToManualWait("auto-only", false)
}}));
"""
        )

        self.assertTrue(payload["manual"])
        self.assertTrue(payload["autoThenManual"])
        self.assertFalse(payload["autoOnly"])

    def test_build_human_like_drag_path_properties(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_xueqiu_posts.mjs").as_uri()
        payload = self.run_node_module_json(
            f"""
import {{ buildHumanLikeDragPath }} from {json.dumps(script_path)};
const path = buildHumanLikeDragPath({{
  startX: 10,
  startY: 20,
  endX: 120,
  endY: 20,
  steps: 12
}});
console.log(JSON.stringify({{
  points: path.length,
  first: path[0],
  last: path[path.length - 1],
  hasBacktrack: path.some((point, index) => index > 0 && point.x < path[index - 1].x)
}}));
"""
        )

        self.assertGreaterEqual(payload["points"], 12)
        self.assertEqual(payload["first"]["x"], 10)
        self.assertEqual(payload["first"]["y"], 20)
        self.assertEqual(payload["last"]["x"], 120)
        self.assertEqual(payload["last"]["y"], 20)
        self.assertTrue(payload["hasBacktrack"])


if __name__ == "__main__":
    unittest.main()
