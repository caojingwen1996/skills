# Xueqiu Auto Slider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auto-attempted Xueqiu slider verification with safe fallback to the existing manual recovery flow.

**Architecture:** Extend `scripts/extract_xueqiu_posts.mjs` with a verification mode flag, slider widget inspection helpers, and CDP mouse-drag automation. Keep the current wait-and-resume behavior as the fallback path and update docs/tests to match the new contract.

**Tech Stack:** Node.js ESM, Chrome DevTools Protocol, Python `unittest`

---

### Task 1: Add failing tests for verification mode and auto-verification helpers

**Files:**
- Modify: `scripts/tests/test_extract_xueqiu_posts.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest scripts.tests.test_extract_xueqiu_posts.ExtractXueqiuPostsScriptTests.test_verification_mode_defaults_to_auto_then_manual`
Expected: FAIL because `parseArgsForTesting` does not exist yet

- [ ] **Step 3: Add more failing tests for validation and fallback rules**

```python
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
```

- [ ] **Step 4: Run the focused test file and confirm RED**

Run: `python3 -m unittest scripts.tests.test_extract_xueqiu_posts -v`
Expected: FAIL with missing export or missing helper errors

- [ ] **Step 5: Commit**

```bash
git add scripts/tests/test_extract_xueqiu_posts.py
git commit -m "test: add verification mode coverage"
```

### Task 2: Implement verification mode parsing and fallback helpers

**Files:**
- Modify: `scripts/extract_xueqiu_posts.mjs`
- Test: `scripts/tests/test_extract_xueqiu_posts.py`

- [ ] **Step 1: Write minimal implementation**

```javascript
const VERIFICATION_MODES = new Set(["manual", "auto-then-manual", "auto-only"]);

// inside parseArgs defaults
verificationMode: "auto-then-manual",

case "--verification-mode":
  args.verificationMode = argv[++index] ?? "";
  break;

if (!VERIFICATION_MODES.has(args.verificationMode)) {
  throw new Error("--verification-mode must be one of: manual, auto-then-manual, auto-only");
}

export function parseArgsForTesting(argv) {
  return parseArgs(argv);
}

export function shouldFallbackToManualWait(mode, autoVerificationSucceeded) {
  if (mode === "manual") return true;
  if (mode === "auto-then-manual") return !autoVerificationSucceeded;
  return false;
}
```

- [ ] **Step 2: Run tests to verify GREEN**

Run: `python3 -m unittest scripts.tests.test_extract_xueqiu_posts -v`
Expected: PASS for the new verification mode tests

- [ ] **Step 3: Refactor names and help text if needed while keeping tests green**

```javascript
"  --verification-mode MODE  manual | auto-then-manual | auto-only; defaults to auto-then-manual",
```

- [ ] **Step 4: Re-run focused tests**

Run: `python3 -m unittest scripts.tests.test_extract_xueqiu_posts -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_xueqiu_posts.mjs scripts/tests/test_extract_xueqiu_posts.py
git commit -m "feat: add verification mode controls"
```

### Task 3: Add failing tests for drag path generation

**Files:**
- Modify: `scripts/tests/test_extract_xueqiu_posts.py`

- [ ] **Step 1: Write the failing test**

```python
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
        self.assertTrue(payload["hasBacktrack"])
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `python3 -m unittest scripts.tests.test_extract_xueqiu_posts.ExtractXueqiuPostsScriptTests.test_build_human_like_drag_path_properties`
Expected: FAIL because `buildHumanLikeDragPath` does not exist

- [ ] **Step 3: Commit**

```bash
git add scripts/tests/test_extract_xueqiu_posts.py
git commit -m "test: cover drag path generation"
```

### Task 4: Implement drag path generation and widget inspection helpers

**Files:**
- Modify: `scripts/extract_xueqiu_posts.mjs`
- Test: `scripts/tests/test_extract_xueqiu_posts.py`

- [ ] **Step 1: Add helper exports for path generation**

```javascript
export function buildHumanLikeDragPath({ startX, startY, endX, endY, steps = 18 }) {
  const points = [];
  const totalX = endX - startX;
  const totalY = endY - startY;

  for (let index = 0; index < steps; index += 1) {
    const progress = index / (steps - 1);
    const eased = progress < 0.7
      ? 1 - Math.pow(1 - progress / 0.7, 2)
      : 0.85 + ((progress - 0.7) / 0.3) * 0.15;
    const jitterY = index === steps - 1 ? 0 : ((index % 2 === 0 ? 1 : -1) * 0.8);
    points.push({
      x: Math.round((startX + totalX * eased) * 100) / 100,
      y: Math.round((startY + totalY * progress + jitterY) * 100) / 100,
      delayMs: index < steps - 1 ? (index > steps - 4 ? 24 : 16) : 20,
    });
  }

  const beforeLast = points[points.length - 2];
  if (beforeLast && beforeLast.x <= endX) {
    beforeLast.x = Math.max(startX, endX - 3);
  }

  points.push({ x: endX, y: endY, delayMs: 30 });
  return points;
}
```

- [ ] **Step 2: Add DOM inspection script builder**

```javascript
function buildVerificationWidgetInspectionScript() {
  return `
    (() => {
      const selectors = [
        "[class*='slider']",
        "[class*='captcha']",
        "[class*='verify']",
        "[class*='nc_']"
      ];
      const nodes = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));
      const handle = nodes.find((node) => {
        const text = (node.innerText || "").trim();
        return /滑块|拖动|验证/.test(text) || node.getBoundingClientRect().width < 120;
      });
      if (!handle) return null;
      const rect = handle.getBoundingClientRect();
      const track = handle.parentElement?.getBoundingClientRect() || rect;
      return {
        handleX: rect.left + rect.width / 2,
        handleY: rect.top + rect.height / 2,
        trackLeft: track.left,
        trackRight: track.right,
        trackY: track.top + track.height / 2,
      };
    })()
  `;
}
```

- [ ] **Step 3: Run focused tests to verify GREEN**

Run: `python3 -m unittest scripts.tests.test_extract_xueqiu_posts -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/extract_xueqiu_posts.mjs scripts/tests/test_extract_xueqiu_posts.py
git commit -m "feat: add slider drag helpers"
```

### Task 5: Add failing tests for documentation contract

**Files:**
- Modify: `scripts/tests/test_skill_docs.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_docs_describe_auto_verification_with_manual_fallback(self) -> None:
        skill_text = read_text("SKILL.md")
        workflow_text = read_text("references", "workflow.md")
        error_policy_text = read_text("references", "error-policy.md")

        for text in (workflow_text, error_policy_text):
            self.assertIn("自动尝试", text)
            self.assertIn("人工", text)

        self.assertIn("登录", workflow_text)
        self.assertIn("验证", workflow_text)
        self.assertIn("回退", error_policy_text)
```

- [ ] **Step 2: Run focused docs test to verify RED**

Run: `python3 -m unittest scripts.tests.test_skill_docs.SkillDocumentationTests.test_docs_describe_auto_verification_with_manual_fallback`
Expected: FAIL because docs do not mention the new contract yet

- [ ] **Step 3: Commit**

```bash
git add scripts/tests/test_skill_docs.py
git commit -m "test: cover auto verification docs contract"
```

### Task 6: Implement auto-verification flow and update docs

**Files:**
- Modify: `scripts/extract_xueqiu_posts.mjs`
- Modify: `references/workflow.md`
- Modify: `references/error-policy.md`
- Modify: `SKILL.md`
- Test: `scripts/tests/test_extract_xueqiu_posts.py`
- Test: `scripts/tests/test_skill_docs.py`

- [ ] **Step 1: Add CDP drag dispatcher and auto-verification wrapper**

```javascript
async function dispatchMouseDragPath(cdp, sessionId, path) {
  const [first, ...rest] = path;
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: first.x,
    y: first.y,
    button: "left",
  }, { sessionId });
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: first.x,
    y: first.y,
    button: "left",
    clickCount: 1,
  }, { sessionId });
  for (const point of rest) {
    await sleep(point.delayMs);
    await cdp.send("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: point.x,
      y: point.y,
      button: "left",
    }, { sessionId });
  }
  const last = path[path.length - 1];
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: last.x,
    y: last.y,
    button: "left",
    clickCount: 1,
  }, { sessionId });
}
```

- [ ] **Step 2: Wire automatic verification into the existing manual wait flow**

```javascript
async function resolveVerificationIfNeeded(cdp, sessionId, reason, verificationMode) {
  if (reason !== "verification") {
    await waitForManualActionCompletion(cdp, sessionId, reason);
    return;
  }

  if (verificationMode !== "manual") {
    const autoSucceeded = await attemptAutoVerification(cdp, sessionId);
    if (autoSucceeded) return;
    if (!shouldFallbackToManualWait(verificationMode, autoSucceeded)) {
      throw new Error("Automatic Xueqiu verification failed without manual fallback.");
    }
  }

  await waitForManualActionCompletion(cdp, sessionId, reason);
}
```

- [ ] **Step 3: Update docs to match**

```markdown
- 验证页：脚本应先自动尝试滑块验证；若自动尝试失败，则提示操作者在自动化 Chrome 窗口内继续处理
- 登录页：仍由操作者在自动化 Chrome 窗口内完成登录
```

- [ ] **Step 4: Run the focused test suites**

Run: `python3 -m unittest scripts.tests.test_extract_xueqiu_posts scripts.tests.test_skill_docs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_xueqiu_posts.mjs references/workflow.md references/error-policy.md SKILL.md scripts/tests/test_extract_xueqiu_posts.py scripts/tests/test_skill_docs.py
git commit -m "feat: auto-attempt xueqiu slider verification"
```

### Task 7: Final verification

**Files:**
- Modify: none

- [ ] **Step 1: Run the full relevant verification**

Run: `python3 -m unittest scripts.tests.test_extract_xueqiu_posts scripts.tests.test_skill_docs scripts.tests.test_start_automation_chrome -v`
Expected: PASS

- [ ] **Step 2: Review the diff for unrelated changes**

Run: `git diff -- scripts/extract_xueqiu_posts.mjs references/workflow.md references/error-policy.md SKILL.md scripts/tests/test_extract_xueqiu_posts.py scripts/tests/test_skill_docs.py`
Expected: Only auto-verification related changes

- [ ] **Step 3: Commit**

```bash
git add scripts/extract_xueqiu_posts.mjs references/workflow.md references/error-policy.md SKILL.md scripts/tests/test_extract_xueqiu_posts.py scripts/tests/test_skill_docs.py
git commit -m "chore: finalize xueqiu auto verification changes"
```

