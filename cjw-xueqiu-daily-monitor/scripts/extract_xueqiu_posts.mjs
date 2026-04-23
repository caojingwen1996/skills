#!/usr/bin/env node

import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import {
  CdpConnection,
  findChromeExecutable,
  findExistingChromeDebugPort,
  launchChrome,
  openPageSession,
  sleep,
  waitForChromeDebugPort,
} from "./vendor/baoyu-chrome-cdp/src/index.mjs";

function printHelp() {
  process.stdout.write(
    [
      "Usage: node scripts/extract_xueqiu_posts.mjs --account-url URL --date YYYY-MM-DD [options]",
      "",
      "Options:",
      "  --account-url URL      Xueqiu homepage URL",
      "  --date YYYY-MM-DD      Target date used for later filtering",
      "  --author-name NAME     Optional author name override",
      "  --output-file PATH     Optional JSON output path; defaults to stdout",
      "  --profile-dir PATH     Chrome profile dir; defaults to scripts/.xueqiu-chrome-profile",
      "  --debug-port PORT      Remote debugging port; defaults to 9333",
      "  --max-posts N          Maximum detail pages to extract; defaults to 30",
      "  --verification-mode MODE  manual | auto-then-manual | auto-only; defaults to auto-then-manual",
      "  --headless             Launch Chrome in headless mode when starting a new instance",
      "  --help                 Show this help",
      "",
    ].join("\n")
  );
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatDateParts(year, month, day) {
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

function parseIsoDate(dateText) {
  const match = String(dateText || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  return {
    year: Number.parseInt(match[1], 10),
    month: Number.parseInt(match[2], 10),
    day: Number.parseInt(match[3], 10),
  };
}

export function inferPostDate(rawText, targetDate, now = new Date()) {
  const normalized = String(rawText || "")
    .replace(/年/g, "-")
    .replace(/月/g, "-")
    .replace(/日/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return null;

  const targetParts = parseIsoDate(targetDate);
  if (!targetParts) {
    throw new Error(`Invalid target date: ${targetDate}`);
  }

  let match = normalized.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+\d{1,2}:\d{2}(?::\d{2})?/);
  if (match) {
    return formatDateParts(
      Number.parseInt(match[1], 10),
      Number.parseInt(match[2], 10),
      Number.parseInt(match[3], 10)
    );
  }

  match = normalized.match(/(\d{1,2})[-/](\d{1,2})\s+\d{1,2}:\d{2}(?::\d{2})?/);
  if (match) {
    return formatDateParts(targetParts.year, Number.parseInt(match[1], 10), Number.parseInt(match[2], 10));
  }

  if (/今天\s*\d{1,2}:\d{2}/.test(normalized)) {
    return formatDateParts(now.getFullYear(), now.getMonth() + 1, now.getDate());
  }
  if (/(昨天|昨日)\s*\d{1,2}:\d{2}/.test(normalized)) {
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    return formatDateParts(yesterday.getFullYear(), yesterday.getMonth() + 1, yesterday.getDate());
  }

  match = normalized.match(/(\d+)\s*分钟前/);
  if (match) {
    const parsed = new Date(now.getTime() - Number.parseInt(match[1], 10) * 60 * 1000);
    return formatDateParts(parsed.getFullYear(), parsed.getMonth() + 1, parsed.getDate());
  }

  match = normalized.match(/(\d+)\s*小时前/);
  if (match) {
    const parsed = new Date(now.getTime() - Number.parseInt(match[1], 10) * 60 * 60 * 1000);
    return formatDateParts(parsed.getFullYear(), parsed.getMonth() + 1, parsed.getDate());
  }

  if (/\b\d{1,2}:\d{2}(?::\d{2})?\b/.test(normalized)) {
    return targetDate;
  }

  return null;
}

export function shouldKeepCandidateForTargetDate(candidate, targetDate, now = new Date()) {
  const rawPublishedAt = String(candidate?.published_at || candidate?.content_snippet || "").trim();
  const inferredDate = inferPostDate(rawPublishedAt, targetDate, now);
  return !inferredDate || inferredDate === targetDate;
}

const VERIFICATION_PAYLOAD_PATTERN =
  /(访问验证|请按住滑块|拖动到最右边|为了更好的访问体验|即可继续访问网页|别离开)/;
const LOGIN_PAYLOAD_PATTERN =
  /(登录雪球|登录后(?:即可|可)?(?:查看|继续|发帖|评论|互动)|请先登录|立即登录|注册登录|账号密码登录|手机验证码登录)/;
const VERIFICATION_MODES = new Set(["manual", "auto-then-manual", "auto-only"]);

export function classifyManualActionPayload(payload) {
  const text = [
    String(payload?.title || ""),
    String(payload?.author_name || ""),
    String(payload?.content || ""),
  ].join("\n");
  if (VERIFICATION_PAYLOAD_PATTERN.test(text)) {
    return "verification";
  }
  if (LOGIN_PAYLOAD_PATTERN.test(text)) {
    return "login";
  }
  return false;
}

export function isVerificationPayload(payload) {
  return classifyManualActionPayload(payload) === "verification";
}

export function formatVerificationGuidance() {
  return (
    "Manual action required: complete the Xueqiu verification in the automation Chrome window, " +
    "then rerun the same-day task."
  );
}

export function formatManualActionGuidance(reason) {
  if (reason === "login") {
    return (
      "Manual action required: log in to Xueqiu in the automation Chrome window, " +
      "then wait for the page to recover and extraction will continue automatically."
    );
  }

  return (
    "Manual action required: complete the Xueqiu verification in the automation Chrome window, " +
    "then wait for the page to recover and extraction will continue automatically."
  );
}

export function buildCleanupPlan({ manualActionBlocked, verificationBlocked, launchedChrome }) {
  const shouldPreserveBrowser = Boolean(
    manualActionBlocked ?? verificationBlocked
  );
  return {
    closeDetailTarget: !shouldPreserveBrowser,
    closeHomepageTarget: !shouldPreserveBrowser,
    terminateLaunchedChrome: Boolean(launchedChrome) && !shouldPreserveBrowser,
  };
}

function parseArgs(argv) {
  const args = {
    accountUrl: "",
    date: "",
    authorName: "",
    outputFile: "",
    profileDir: "",
    debugPort: Number.parseInt(process.env.XUEQIU_CHROME_DEBUG_PORT ?? "9333", 10),
    maxPosts: 30,
    verificationMode: "auto-then-manual",
    headless: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    switch (value) {
      case "--account-url":
        args.accountUrl = argv[++index] ?? "";
        break;
      case "--date":
        args.date = argv[++index] ?? "";
        break;
      case "--author-name":
        args.authorName = argv[++index] ?? "";
        break;
      case "--output-file":
        args.outputFile = argv[++index] ?? "";
        break;
      case "--profile-dir":
        args.profileDir = argv[++index] ?? "";
        break;
      case "--debug-port":
        args.debugPort = Number.parseInt(argv[++index] ?? "", 10);
        break;
      case "--max-posts":
        args.maxPosts = Number.parseInt(argv[++index] ?? "", 10);
        break;
      case "--verification-mode":
        args.verificationMode = argv[++index] ?? "";
        break;
      case "--headless":
        args.headless = true;
        break;
      case "--help":
      case "-h":
        printHelp();
        process.exit(0);
        break;
      default:
        throw new Error(`Unknown argument: ${value}`);
    }
  }

  if (!args.accountUrl) throw new Error("--account-url is required");
  if (!args.date) throw new Error("--date is required");
  if (!parseIsoDate(args.date)) throw new Error("--date must be YYYY-MM-DD");
  if (!Number.isInteger(args.debugPort) || args.debugPort <= 0) {
    throw new Error("--debug-port must be a positive integer");
  }
  if (!Number.isInteger(args.maxPosts) || args.maxPosts <= 0) {
    throw new Error("--max-posts must be a positive integer");
  }
  if (!VERIFICATION_MODES.has(args.verificationMode)) {
    throw new Error("--verification-mode must be one of: manual, auto-then-manual, auto-only");
  }

  return args;
}

export function parseArgsForTesting(argv) {
  return parseArgs(argv);
}

export function shouldFallbackToManualWait(mode, autoVerificationSucceeded) {
  if (mode === "manual") return true;
  if (mode === "auto-then-manual") return !autoVerificationSucceeded;
  return false;
}

async function evaluateJson(cdp, sessionId, expression, awaitPromise = true) {
  const result = await cdp.send(
    "Runtime.evaluate",
    {
      expression,
      awaitPromise,
      returnByValue: true,
    },
    { sessionId }
  );

  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || "Runtime.evaluate failed");
  }
  return result.result?.value;
}

async function waitForDocumentReady(cdp, sessionId, timeoutMs = 20_000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const state = await evaluateJson(cdp, sessionId, "document.readyState");
    if (state === "interactive" || state === "complete") return;
    await sleep(200);
  }
  throw new Error("Timed out waiting for document.readyState");
}

export function buildHumanLikeDragPath({
  startX,
  startY,
  endX,
  endY,
  steps = 18,
}) {
  const points = [{ x: startX, y: startY, delayMs: 12 }];
  const baseSteps = Math.max(steps, 8);

  for (let index = 1; index < baseSteps - 2; index += 1) {
    const progress = index / (baseSteps - 2);
    const eased =
      progress < 0.65
        ? 0.9 * (1 - Math.pow(1 - progress / 0.65, 2))
        : 0.9 + ((progress - 0.65) / 0.35) * 0.08;
    const jitterY = index % 2 === 0 ? 0.8 : -0.8;
    points.push({
      x: Math.round((startX + (endX - startX) * eased) * 100) / 100,
      y: Math.round((startY + (endY - startY) * progress + jitterY) * 100) / 100,
      delayMs: index > baseSteps - 6 ? 24 : 16,
    });
  }

  const overshootX = Math.max(startX, endX + Math.min(4, Math.max(1, Math.abs(endX - startX) * 0.02)));
  const backtrackX = Math.max(startX, endX - Math.min(3, Math.max(1, Math.abs(endX - startX) * 0.015)));
  points.push({ x: overshootX, y: endY + 0.4, delayMs: 28 });
  points.push({ x: backtrackX, y: endY, delayMs: 30 });
  points.push({ x: endX, y: endY, delayMs: 32 });

  return points;
}

function buildVerificationWidgetInspectionScript() {
  return `
    (() => {
      const textPattern = /访问验证|请按住滑块|拖动到最右边|为了更好的访问体验|即可继续访问网页|别离开|滑块|验证/;
      const elements = Array.from(document.querySelectorAll("div, span, button, section"));
      const hintNode = elements.find((node) => textPattern.test((node.innerText || "").replace(/\\s+/g, "")));
      if (!hintNode) return null;

      const container = hintNode.closest("section, article, main, div") || hintNode.parentElement || document.body;
      const nodes = Array.from(container.querySelectorAll("div, span, button"));
      const boxes = nodes
        .map((node) => ({ node, rect: node.getBoundingClientRect(), text: (node.innerText || "").trim() }))
        .filter(({ rect }) => rect.width > 0 && rect.height > 0);

      const handleCandidate = boxes
        .filter(({ rect, text }) =>
          rect.width >= 20 &&
          rect.width <= 120 &&
          rect.height >= 20 &&
          rect.height <= 120 &&
          !textPattern.test(text)
        )
        .sort((left, right) => (right.rect.width * right.rect.height) - (left.rect.width * left.rect.height))[0];

      if (!handleCandidate) return null;

      const trackCandidate = boxes
        .filter(({ rect, node }) =>
          node !== handleCandidate.node &&
          rect.width > handleCandidate.rect.width * 2 &&
          rect.height >= handleCandidate.rect.height * 0.6 &&
          rect.left <= handleCandidate.rect.left + 8 &&
          rect.right >= handleCandidate.rect.right - 8
        )
        .sort((left, right) => (right.rect.width - left.rect.width))[0];

      if (!trackCandidate) return null;

      return {
        handleX: handleCandidate.rect.left + handleCandidate.rect.width / 2,
        handleY: handleCandidate.rect.top + handleCandidate.rect.height / 2,
        endX: trackCandidate.rect.right - handleCandidate.rect.width / 2 - 2,
        endY: handleCandidate.rect.top + handleCandidate.rect.height / 2,
      };
    })()
  `;
}

function buildHomepageExtractionScript(maxPosts) {
  return `
    (async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      for (let i = 0; i < 5; i += 1) {
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(600);
      }

      const postUrlPattern = /^https?:\\/\\/xueqiu\\.com\\/\\d+\\/\\d+(?:\\?.*)?$/;
      const inferPublishedAt = (text) => {
        const source = String(text || "");
        const patterns = [
          /\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?/,
          /(?:今天|昨天|昨日)\\s*\\d{1,2}:\\d{2}/,
          /\\d+\\s*(?:分钟前|小时前)/,
          /\\b\\d{1,2}:\\d{2}(?::\\d{2})?\\b/,
        ];
        for (const pattern of patterns) {
          const matched = source.match(pattern);
          if (matched) return matched[0];
        }
        return "";
      };

      const pickContainer = (node) => {
        if (!node) return null;
        return node.closest("article, .timeline__item, .card, .feed__item, .status__item, li") || node;
      };

      const authorFallback = Array.from(document.querySelectorAll("h1, .user-name, .profile__name"))
        .map((node) => (node.innerText || "").trim())
        .find(Boolean) || "";

      const seen = new Set();
      const results = [];
      const anchors = Array.from(document.querySelectorAll("a[href]"));
      for (const anchor of anchors) {
        const href = new URL(anchor.getAttribute("href"), location.href).href;
        if (!postUrlPattern.test(href)) continue;
        if (seen.has(href)) continue;
        seen.add(href);

        const container = pickContainer(anchor);
        const text = (container?.innerText || anchor.innerText || "").trim();
        if (!text) continue;

        const lines = text.split(/\\n+/).map((item) => item.trim()).filter(Boolean);
        const title = lines[0] || href;
        results.push({
          url: href,
          title,
          published_at: inferPublishedAt(text),
          content_snippet: text,
          author_name: authorFallback,
        });
        if (results.length >= ${JSON.stringify(maxPosts)}) break;
      }

      return results;
    })()
  `;
}

function buildDetailExtractionScript() {
  return `
    (() => {
      const bodyText = (document.body?.innerText || "").trim();
      const candidateTitle = [
        document.querySelector("h1")?.innerText,
        document.title,
        bodyText.split(/\\n+/).find(Boolean),
      ].find((value) => value && String(value).trim()) || "";

      const inferPublishedAt = (text) => {
        const source = String(text || "");
        const patterns = [
          /\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?/,
          /(?:今天|昨天|昨日)\\s*\\d{1,2}:\\d{2}/,
          /\\d+\\s*(?:分钟前|小时前)/,
          /\\b\\d{1,2}:\\d{2}(?::\\d{2})?\\b/,
        ];
        for (const pattern of patterns) {
          const matched = source.match(pattern);
          if (matched) return matched[0];
        }
        return "";
      };

      const author = Array.from(document.querySelectorAll("h1, .user-name, .profile__name, .name"))
        .map((node) => (node.innerText || "").trim())
        .find(Boolean) || "";

      return {
        title: String(candidateTitle).trim(),
        published_at: inferPublishedAt(bodyText),
        author_name: author,
        content: bodyText,
        url: location.href,
      };
    })()
  `;
}

function normalizePost(candidate, detail, fallbackAuthor) {
  const url = detail.url || candidate.url;
  const title = detail.title || candidate.title || url;
  const publishedAt = detail.published_at || candidate.published_at || "";
  const content = detail.content || candidate.content_snippet || "";
  return {
    title: String(title).trim(),
    published_at: String(publishedAt).trim(),
    url: String(url).trim(),
    content: String(content).trim(),
    author_name: String(detail.author_name || candidate.author_name || fallbackAuthor || "").trim(),
  };
}

async function inspectCurrentPage(cdp, sessionId) {
  const detail = await evaluateJson(cdp, sessionId, buildDetailExtractionScript(), false);
  return {
    title: String(detail?.title || "").trim(),
    published_at: String(detail?.published_at || "").trim(),
    url: String(detail?.url || "").trim(),
    content: String(detail?.content || "").trim(),
    author_name: String(detail?.author_name || "").trim(),
  };
}

async function inspectVerificationWidget(cdp, sessionId) {
  const widget = await evaluateJson(cdp, sessionId, buildVerificationWidgetInspectionScript(), false);
  if (!widget) return null;

  return {
    handleX: Number(widget.handleX),
    handleY: Number(widget.handleY),
    endX: Number(widget.endX),
    endY: Number(widget.endY),
  };
}

async function dispatchMouseDragPath(cdp, sessionId, dragPath) {
  const [firstPoint, ...restPoints] = dragPath;
  if (!firstPoint) {
    throw new Error("Drag path must contain at least one point.");
  }

  await cdp.send(
    "Input.dispatchMouseEvent",
    {
      type: "mouseMoved",
      x: firstPoint.x,
      y: firstPoint.y,
      button: "left",
    },
    { sessionId }
  );
  await cdp.send(
    "Input.dispatchMouseEvent",
    {
      type: "mousePressed",
      x: firstPoint.x,
      y: firstPoint.y,
      button: "left",
      clickCount: 1,
    },
    { sessionId }
  );

  for (const point of restPoints) {
    await sleep(point.delayMs ?? 16);
    await cdp.send(
      "Input.dispatchMouseEvent",
      {
        type: "mouseMoved",
        x: point.x,
        y: point.y,
        button: "left",
      },
      { sessionId }
    );
  }

  const lastPoint = dragPath[dragPath.length - 1];
  await cdp.send(
    "Input.dispatchMouseEvent",
    {
      type: "mouseReleased",
      x: lastPoint.x,
      y: lastPoint.y,
      button: "left",
      clickCount: 1,
    },
    { sessionId }
  );
}

async function attemptAutoVerification(cdp, sessionId, maxAttempts = 2) {
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    process.stderr.write(`[extract_xueqiu_posts] attempting automatic slider verification (${attempt}/${maxAttempts})\n`);

    let widget = null;
    try {
      await waitForDocumentReady(cdp, sessionId, 5_000);
      widget = await inspectVerificationWidget(cdp, sessionId);
    } catch {
      widget = null;
    }

    if (!widget) {
      process.stderr.write("[extract_xueqiu_posts] automatic slider verification could not locate a stable widget\n");
      continue;
    }

    const dragPath = buildHumanLikeDragPath({
      startX: widget.handleX,
      startY: widget.handleY,
      endX: widget.endX,
      endY: widget.endY,
    });

    try {
      await dispatchMouseDragPath(cdp, sessionId, dragPath);
      await sleep(1_500);
      await waitForDocumentReady(cdp, sessionId, 5_000);
      const payload = await inspectCurrentPage(cdp, sessionId);
      if (!classifyManualActionPayload(payload)) {
        process.stderr.write("[extract_xueqiu_posts] automatic slider verification succeeded\n");
        return true;
      }
    } catch (error) {
      process.stderr.write(
        `[extract_xueqiu_posts] automatic slider verification attempt failed: ${
          error instanceof Error ? error.message : String(error)
        }\n`
      );
    }
  }

  process.stderr.write("[extract_xueqiu_posts] automatic slider verification did not clear the page\n");
  return false;
}

async function resolveManualAction(cdp, sessionId, reason, verificationMode) {
  if (reason === "verification" && verificationMode !== "manual") {
    const autoVerificationSucceeded = await attemptAutoVerification(cdp, sessionId);
    if (autoVerificationSucceeded) {
      return;
    }
    if (!shouldFallbackToManualWait(verificationMode, autoVerificationSucceeded)) {
      throw new Error("Automatic Xueqiu verification failed without manual fallback.");
    }
    process.stderr.write("[extract_xueqiu_posts] automatic verification failed, falling back to manual recovery\n");
  }

  await waitForManualActionCompletion(cdp, sessionId, reason);
}

async function waitForManualActionCompletion(cdp, sessionId, reason, timeoutMs = 300_000, pollMs = 3_000) {
  process.stderr.write(`[extract_xueqiu_posts] ${formatManualActionGuidance(reason)}\n`);

  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    await sleep(pollMs);
    try {
      await waitForDocumentReady(cdp, sessionId, 5_000);
      const payload = await inspectCurrentPage(cdp, sessionId);
      if (!classifyManualActionPayload(payload)) {
        process.stderr.write("[extract_xueqiu_posts] manual action resolved, resuming extraction\n");
        return;
      }
    } catch {
      // Keep polling until timeout; the browser may still be navigating.
    }
  }

  throw new Error(
    `Timed out waiting for Xueqiu ${reason === "login" ? "login" : "verification"} to complete in the automation Chrome window.`
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const targetDate = args.date;
  const scriptDir = path.dirname(new URL(import.meta.url).pathname);
  const profileDir = path.resolve(args.profileDir || path.join(scriptDir, ".xueqiu-chrome-profile"));

  let launchedChrome = null;
  let debugPort = await findExistingChromeDebugPort({ profileDir, timeoutMs: 3_000 });
  if (!debugPort) {
    debugPort = args.debugPort;
    const chromePath = findChromeExecutable({
      candidates: {
        darwin: [
          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Chromium.app/Contents/MacOS/Chromium",
          path.join(process.env.HOME ?? "", "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
          path.join(process.env.HOME ?? "", "Applications/Chromium.app/Contents/MacOS/Chromium"),
        ],
        default: [
          "/usr/bin/google-chrome",
          "/usr/bin/google-chrome-stable",
          "/usr/bin/chromium",
          "/usr/bin/chromium-browser",
        ],
      },
      envNames: ["CHROME_PATH"],
    });
    if (!chromePath) {
      throw new Error("Unable to find Chrome or Chromium executable.");
    }

    launchedChrome = await launchChrome({
      chromePath,
      profileDir,
      port: debugPort,
      url: args.accountUrl,
      headless: args.headless,
      extraArgs: ["--disable-popup-blocking"],
    });
  }

  const wsUrl = await waitForChromeDebugPort(debugPort, 20_000, { includeLastError: true });
  const cdp = await CdpConnection.connect(wsUrl, 10_000);
  let manualActionBlocked = false;

  try {
    const homepage = await openPageSession({
      cdp,
      reusing: true,
      url: args.accountUrl,
      matchTarget: (target) => target.url === args.accountUrl,
      enablePage: true,
      enableRuntime: true,
      activateTarget: true,
    });

    await cdp.send("Page.navigate", { url: args.accountUrl }, { sessionId: homepage.sessionId });
    await waitForDocumentReady(cdp, homepage.sessionId);
    await sleep(2_000);

    const homepagePayload = await inspectCurrentPage(cdp, homepage.sessionId);
    const homepageManualAction = classifyManualActionPayload(homepagePayload);
    if (homepageManualAction) {
      manualActionBlocked = true;
      await resolveManualAction(cdp, homepage.sessionId, homepageManualAction, args.verificationMode);
      await cdp.send("Page.navigate", { url: args.accountUrl }, { sessionId: homepage.sessionId });
      await waitForDocumentReady(cdp, homepage.sessionId);
      await sleep(2_000);
    }

    const candidates = await evaluateJson(
      cdp,
      homepage.sessionId,
      buildHomepageExtractionScript(args.maxPosts),
      true
    );

    const posts = [];
    for (const candidate of (candidates ?? []).filter((item) => shouldKeepCandidateForTargetDate(item, targetDate))) {
      let detailSession = null;
      let closeDetailTarget = true;
      try {
        detailSession = await openPageSession({
          cdp,
          reusing: true,
          url: candidate.url,
          matchTarget: (target) => target.url === candidate.url,
          enablePage: true,
          enableRuntime: true,
          activateTarget: true,
        });

        await cdp.send("Page.navigate", { url: candidate.url }, { sessionId: detailSession.sessionId });
        await waitForDocumentReady(cdp, detailSession.sessionId);
        await sleep(1_000);

        let detail = await evaluateJson(cdp, detailSession.sessionId, buildDetailExtractionScript(), false);
        let normalized = normalizePost(candidate, detail, args.authorName);
        const manualActionReason = classifyManualActionPayload(normalized);
        if (manualActionReason) {
          manualActionBlocked = true;
          closeDetailTarget = false;
          process.stderr.write(
            `[extract_xueqiu_posts] ${manualActionReason} page detected for ${candidate.url}\n`
          );
          await resolveManualAction(cdp, detailSession.sessionId, manualActionReason, args.verificationMode);
          await cdp.send("Page.navigate", { url: candidate.url }, { sessionId: detailSession.sessionId });
          await waitForDocumentReady(cdp, detailSession.sessionId);
          await sleep(1_000);
          detail = await evaluateJson(cdp, detailSession.sessionId, buildDetailExtractionScript(), false);
          normalized = normalizePost(candidate, detail, args.authorName);
          if (classifyManualActionPayload(normalized)) {
            throw new Error(`Manual action completed but ${candidate.url} is still blocked.`);
          }
        }
        if (normalized.url && normalized.content) {
          posts.push(normalized);
        }
      } catch (error) {
        process.stderr.write(
          `[extract_xueqiu_posts] failed to extract ${candidate.url}: ${
            error instanceof Error ? error.message : String(error)
          }\n`
        );
      } finally {
        if (detailSession?.targetId && closeDetailTarget) {
          try {
            await cdp.send("Target.closeTarget", { targetId: detailSession.targetId });
          } catch {
            // ignore close errors
          }
        }
      }
    }

    const payload = JSON.stringify(posts, null, 2);
    if (args.outputFile) {
      await import("node:fs/promises").then((fs) => fs.writeFile(args.outputFile, payload, "utf-8"));
    } else {
      process.stdout.write(`${payload}\n`);
    }

    const cleanupPlan = buildCleanupPlan({
      manualActionBlocked,
      launchedChrome: Boolean(launchedChrome),
    });

    if (cleanupPlan.closeHomepageTarget) {
      await cdp.send("Target.closeTarget", { targetId: homepage.targetId });
    }
  } finally {
    cdp.close();
    const cleanupPlan = buildCleanupPlan({
      manualActionBlocked,
      launchedChrome: Boolean(launchedChrome),
    });
    if (cleanupPlan.terminateLaunchedChrome) {
      try {
        launchedChrome.kill("SIGTERM");
      } catch {
        // ignore
      }
    }
  }
}

const currentModulePath = fileURLToPath(import.meta.url);
const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";

if (invokedPath === currentModulePath) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exit(1);
  });
}
