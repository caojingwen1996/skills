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
      "  --capture-scope SCOPE  daily | all-visible; defaults to daily",
      "  --comment-scope SCOPE  none | author-only | all; defaults to none",
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

function extractPublishedMarkerValue(rawText) {
  const normalized = String(rawText || "")
    .replace(/年/g, "-")
    .replace(/月/g, "-")
    .replace(/日/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return "";

  const patterns = [
    /发布于\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)/,
    /发布于\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})/,
    /发布于\s*((?:今天|昨天|昨日)\s*\d{1,2}:\d{2})/,
    /发布于\s*(\d+\s*(?:分钟前|小时前))/,
    /发布于\s*(\d{1,2}:\d{2}(?::\d{2})?)/,
  ];

  for (const pattern of patterns) {
    const match = normalized.match(pattern);
    if (match?.[1]) return match[1];
  }
  return "";
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

  const publishedMarkerValue = extractPublishedMarkerValue(normalized);
  if (publishedMarkerValue) {
    return inferPostDate(publishedMarkerValue, targetDate, now);
  }

  let match = normalized.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+\d{1,2}:\d{2}(?::\d{2})?/);
  if (match) {
    return formatDateParts(
      Number.parseInt(match[1], 10),
      Number.parseInt(match[2], 10),
      Number.parseInt(match[3], 10)
    );
  }

  match = normalized.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
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
  const rawPublishedAt = String(candidate?.published_at || "").trim();
  const markerPublishedAt = rawPublishedAt
    ? ""
    : extractPublishedMarkerValue(String(candidate?.content_snippet || "").trim());
  const candidatePublishedAt = rawPublishedAt || markerPublishedAt;
  const inferredDate = inferPostDate(candidatePublishedAt, targetDate, now);
  return inferredDate === targetDate;
}

const VERIFICATION_PAYLOAD_PATTERN =
  /(访问验证|请按住滑块|拖动到最右边|为了更好的访问体验|即可继续访问网页|别离开)/;
const LOGIN_PAYLOAD_PATTERN =
  /(登录雪球|登录后(?:即可|可)?(?:查看|继续|发帖|评论|互动)|请先登录|立即登录|注册登录|账号密码登录|手机验证码登录)/;
const VERIFICATION_MODES = new Set(["manual", "auto-then-manual", "auto-only"]);
const CAPTURE_SCOPES = new Set(["daily", "all-visible"]);
const COMMENT_SCOPES = new Set(["none", "author-only", "all"]);

export function isXueqiuPostUrl(value) {
  return /^https?:\/\/xueqiu\.com\/\d+\/\d+(?:[?#].*)?$/.test(String(value || ""));
}

export function shouldKeepCandidateForCaptureScope(candidate, targetDate, captureScope, now = new Date()) {
  if (captureScope === "all-visible") return true;
  return shouldKeepCandidateForTargetDate(candidate, targetDate, now);
}

function normalizeComment(value) {
  const authorName = String(value?.author_name || "").trim();
  const content = String(value?.content || "").trim();
  const publishedAt = String(value?.published_at || "").trim();
  if (!content) return null;
  return {
    author_name: authorName,
    published_at: publishedAt,
    content,
  };
}

export function filterCommentsForScope(comments, commentScope, authorName) {
  if (commentScope === "none") return [];
  const normalizedAuthor = String(authorName || "").trim();
  return (comments || [])
    .map((comment) => normalizeComment(comment))
    .filter(Boolean)
    .filter((comment) => {
      if (commentScope === "all") return true;
      return Boolean(normalizedAuthor) && (
        comment.author_name === normalizedAuthor ||
        comment.author_name.startsWith(normalizedAuthor) ||
        comment.content.startsWith(normalizedAuthor)
      );
    });
}

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
    captureScope: "daily",
    commentScope: "none",
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
      case "--capture-scope":
        args.captureScope = argv[++index] ?? "";
        break;
      case "--comment-scope":
        args.commentScope = argv[++index] ?? "";
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
  if (!CAPTURE_SCOPES.has(args.captureScope)) {
    throw new Error("--capture-scope must be one of: daily, all-visible");
  }
  if (!COMMENT_SCOPES.has(args.commentScope)) {
    throw new Error("--comment-scope must be one of: none, author-only, all");
  }
  if (!VERIFICATION_MODES.has(args.verificationMode)) {
    throw new Error("--verification-mode must be one of: manual, auto-then-manual, auto-only");
  }

  return args;
}

export function parseArgsForTesting(argv) {
  return parseArgs(argv);
}

export function resolveProfileDirForTesting(metaUrl, explicitProfileDir) {
  const scriptDir = path.dirname(fileURLToPath(metaUrl));
  return path.resolve(explicitProfileDir || path.join(scriptDir, ".xueqiu-chrome-profile"));
}

async function isChromeDebugPortUsable(port) {
  try {
    await waitForChromeDebugPort(port, 1_000);
    return true;
  } catch {
    return false;
  }
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

async function scrollDetailForComments(cdp, sessionId, commentScope) {
  if (commentScope === "none") return;
  await evaluateJson(
    cdp,
    sessionId,
    `
      (async () => {
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        for (let i = 0; i < 4; i += 1) {
          window.scrollTo(0, document.body.scrollHeight);
          await sleep(500);
        }
      })()
    `,
    true
  );
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

function clamp(value, minValue, maxValue) {
  return Math.min(Math.max(value, minValue), maxValue);
}

function parseRgbColor(value) {
  const match = String(value || "").match(/rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  if (!match) return null;
  return {
    r: Number.parseInt(match[1], 10),
    g: Number.parseInt(match[2], 10),
    b: Number.parseInt(match[3], 10),
  };
}

function isLikelyOrangeColor(value) {
  const parsed = parseRgbColor(value);
  if (!parsed) return false;
  return parsed.r >= 210 && parsed.g >= 80 && parsed.g <= 190 && parsed.b <= 110;
}

function isLikelyGrayTrackColor(value) {
  const parsed = parseRgbColor(value);
  if (!parsed) return false;
  const spread = Math.max(parsed.r, parsed.g, parsed.b) - Math.min(parsed.r, parsed.g, parsed.b);
  return spread <= 18 && parsed.r >= 210 && parsed.r <= 245;
}

function normalizeRectCandidate(candidate) {
  const width = Number(candidate?.width);
  const height = Number(candidate?.height);
  const left = Number(candidate?.left);
  const top = Number(candidate?.top);
  if (![width, height, left, top].every(Number.isFinite) || width <= 0 || height <= 0) {
    return null;
  }

  return {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    text: String(candidate?.text || "").trim(),
    background: String(candidate?.background || "").trim(),
  };
}

export function buildVisualVerificationGeometry({ clipLeft, clipTop, orangeBox, trackBox }) {
  const orangeWidth = Number(orangeBox?.right) - Number(orangeBox?.left);
  const orangeCenterY = (Number(orangeBox?.top) + Number(orangeBox?.bottom)) / 2;
  return {
    handleX: Math.round(Number(clipLeft) + Number(orangeBox?.left) + orangeWidth / 2),
    handleY: Math.round(Number(clipTop) + orangeCenterY),
    endX: Math.round(Number(clipLeft) + Number(trackBox?.right) - orangeWidth / 2 - 2),
    endY: Math.round(Number(clipTop) + orangeCenterY),
  };
}

export function selectBestVerificationWidget(candidates) {
  const normalized = (candidates || []).map((candidate) => normalizeRectCandidate(candidate)).filter(Boolean);
  if (normalized.length === 0) return null;

  const handles = normalized.filter((candidate) => {
    const aspectRatio = Math.max(candidate.width, candidate.height) / Math.min(candidate.width, candidate.height);
    return (
      candidate.width >= 24 &&
      candidate.width <= 120 &&
      candidate.height >= 24 &&
      candidate.height <= 120 &&
      aspectRatio <= 1.8
    );
  });
  const tracks = normalized.filter((candidate) => (
    candidate.width >= 140 &&
    candidate.height >= 28 &&
    candidate.height <= 90
  ));

  let bestPair = null;
  let bestScore = Number.NEGATIVE_INFINITY;

  for (const handle of handles) {
    for (const track of tracks) {
      if (track === handle) continue;
      if (track.right <= handle.right + 40) continue;
      if (track.left > handle.left + 20) continue;
      if (track.top > handle.bottom || track.bottom < handle.top) continue;

      const handleCenterY = handle.top + handle.height / 2;
      const trackCenterY = track.top + track.height / 2;
      const verticalDelta = Math.abs(handleCenterY - trackCenterY);
      if (verticalDelta > Math.max(18, track.height * 0.5)) continue;

      const overlapTop = Math.max(handle.top, track.top);
      const overlapBottom = Math.min(handle.bottom, track.bottom);
      const overlapHeight = Math.max(0, overlapBottom - overlapTop);
      const overlapRatio = overlapHeight / Math.max(1, Math.min(handle.height, track.height));

      let score = overlapRatio * 120;
      score -= verticalDelta * 1.5;
      score -= Math.abs(track.left - handle.left) * 0.6;
      score += Math.max(0, track.width - handle.width) * 0.08;
      if (isLikelyOrangeColor(handle.background)) score += 60;
      if (isLikelyGrayTrackColor(track.background)) score += 30;
      if (VERIFICATION_PAYLOAD_PATTERN.test(track.text)) score += 15;
      if (handle.text) score -= 20;

      if (score > bestScore) {
        bestScore = score;
        bestPair = { handle, track };
      }
    }
  }

  if (!bestPair || bestScore < 40) return null;

  return {
    handleX: bestPair.handle.left + bestPair.handle.width / 2,
    handleY: bestPair.handle.top + bestPair.handle.height / 2,
    endX: bestPair.track.right - bestPair.handle.width / 2 - 2,
    endY: bestPair.handle.top + bestPair.handle.height / 2,
  };
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

function buildHomepageExtractionScript(maxPosts, captureScope = "daily") {
  const scrollRounds = captureScope === "all-visible" ? 5 : 5;
  return `
    (async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      for (let i = 0; i < ${JSON.stringify(scrollRounds)}; i += 1) {
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(600);
      }

      const postUrlPattern = /^https?:\\/\\/xueqiu\\.com\\/\\d+\\/\\d+(?:\\?.*)?$/;
      const inferPublishedAt = (text) => {
        const source = String(text || "");
        const publishedMarkerPatterns = [
          /发布于\\s*(\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?)/,
          /发布于\\s*(\\d{4}[-/]\\d{1,2}[-/]\\d{1,2})/,
          /发布于\\s*((?:今天|昨天|昨日)\\s*\\d{1,2}:\\d{2})/,
          /发布于\\s*(\\d+\\s*(?:分钟前|小时前))/,
          /发布于\\s*(\\d{1,2}:\\d{2}(?::\\d{2})?)/,
        ];
        for (const pattern of publishedMarkerPatterns) {
          const matched = source.match(pattern);
          if (matched?.[1]) return matched[1];
        }
        const patterns = [
          /\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?/,
          /\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}/,
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

function buildDetailExtractionScript(commentScope = "none") {
  return `
    (() => {
      const commentScope = ${JSON.stringify(commentScope)};
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
          /\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}/,
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

      const extractComments = () => {
        if (commentScope === "none") return [];
        const commentNodes = Array.from(document.querySelectorAll(
          "[class*='comment'], [class*='reply'], [class*='Comment'], [class*='Reply']"
        ));
        const seen = new Set();
        const comments = [];
        for (const node of commentNodes) {
          const text = (node.innerText || "").trim();
          if (!text || text.length < 2 || seen.has(text)) continue;
          seen.add(text);
          const lines = text.split(/\\n+/).map((item) => item.trim()).filter(Boolean);
          const commentAuthor = Array.from(node.querySelectorAll(
            "a, [class*='user'], [class*='author'], [class*='name'], [class*='User'], [class*='Author'], [class*='Name']"
          ))
            .map((item) => (item.innerText || "").trim())
            .find(Boolean) || lines[0] || "";
          comments.push({
            author_name: commentAuthor,
            published_at: inferPublishedAt(text),
            content: text,
          });
        }
        return comments;
      };

      return {
        title: String(candidateTitle).trim(),
        published_at: inferPublishedAt(bodyText),
        author_name: author,
        content: bodyText,
        url: location.href,
        comments: extractComments(),
      };
    })()
  `;
}

function buildVerificationInspectionPayloadScript() {
  return `
    (() => {
      const textPattern = /璁块棶楠岃瘉|璇锋寜浣忔粦鍧梶鎷栧姩鍒版渶鍙宠竟|涓轰簡鏇村ソ鐨勮闂綋楠寍鍗冲彲缁х画璁块棶缃戦〉|鍒寮€|婊戝潡|楠岃瘉/;
      const elements = Array.from(document.querySelectorAll("div, span, button, section"));
      const hintNode = elements.find((node) => textPattern.test((node.innerText || "").replace(/\\s+/g, "")));
      if (!hintNode) return null;

      const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
      const container = hintNode.closest("section, article, main, div") || hintNode.parentElement || document.body;
      const nodes = Array.from((container || document.body).querySelectorAll("div, span, button, a"));
      const candidates = nodes
        .map((node) => {
          const rect = node.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) return null;
          const style = window.getComputedStyle(node);
          return {
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height,
            text: (node.innerText || "").trim(),
            background: style.backgroundColor || ""
          };
        })
        .filter(Boolean);

      const regionRect = (container || hintNode).getBoundingClientRect();
      return {
        candidates,
        region: {
          left: Math.max(0, regionRect.left - 40),
          top: Math.max(0, regionRect.top - 40),
          width: Math.min(viewportWidth, regionRect.width + 120),
          height: Math.min(viewportHeight, Math.max(160, regionRect.height + 160))
        },
        viewport: {
          width: viewportWidth,
          height: viewportHeight
        }
      };
    })()
  `;
}

function buildVisualVerificationAnalysisScript(dataUrl) {
  return `
    (async () => {
      const image = new Image();
      const loadImage = new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = () => reject(new Error("visual verification image load failed"));
      });
      image.src = ${JSON.stringify(dataUrl)};
      await loadImage;

      const canvas = document.createElement("canvas");
      canvas.width = image.width;
      canvas.height = image.height;
      const context = canvas.getContext("2d");
      context.drawImage(image, 0, 0);

      const { data, width, height } = context.getImageData(0, 0, canvas.width, canvas.height);
      const isOrange = (offset) => {
        const r = data[offset];
        const g = data[offset + 1];
        const b = data[offset + 2];
        const a = data[offset + 3];
        return a >= 180 && r >= 210 && g >= 80 && g <= 190 && b <= 110;
      };
      const isGrayTrack = (offset) => {
        const r = data[offset];
        const g = data[offset + 1];
        const b = data[offset + 2];
        const a = data[offset + 3];
        const spread = Math.max(r, g, b) - Math.min(r, g, b);
        return a >= 180 && spread <= 18 && r >= 210 && r <= 245;
      };

      const orangeBox = { left: width, top: height, right: -1, bottom: -1 };
      for (let y = 0; y < height; y += 1) {
        for (let x = 0; x < width; x += 1) {
          const offset = (y * width + x) * 4;
          if (!isOrange(offset)) continue;
          if (x < orangeBox.left) orangeBox.left = x;
          if (y < orangeBox.top) orangeBox.top = y;
          if (x > orangeBox.right) orangeBox.right = x;
          if (y > orangeBox.bottom) orangeBox.bottom = y;
        }
      }

      if (orangeBox.right < orangeBox.left || orangeBox.bottom < orangeBox.top) return null;

      const searchTop = Math.max(0, orangeBox.top - 8);
      const searchBottom = Math.min(height - 1, orangeBox.bottom + 8);
      const trackBox = { left: width, top: height, right: -1, bottom: -1 };
      for (let y = searchTop; y <= searchBottom; y += 1) {
        for (let x = 0; x < width; x += 1) {
          const offset = (y * width + x) * 4;
          if (!isGrayTrack(offset)) continue;
          if (x < trackBox.left) trackBox.left = x;
          if (y < trackBox.top) trackBox.top = y;
          if (x > trackBox.right) trackBox.right = x;
          if (y > trackBox.bottom) trackBox.bottom = y;
        }
      }

      if (trackBox.right < trackBox.left || trackBox.bottom < trackBox.top) return null;
      return { orangeBox, trackBox };
    })()
  `;
}

function buildVerificationClip(region, viewport) {
  if (!region || !viewport) return null;
  const left = clamp(Math.floor(Number(region.left) || 0), 0, Math.max(0, Number(viewport.width) || 0));
  const top = clamp(Math.floor(Number(region.top) || 0), 0, Math.max(0, Number(viewport.height) || 0));
  const width = clamp(Math.ceil(Number(region.width) || 0), 60, Math.max(60, (Number(viewport.width) || 0) - left));
  const height = clamp(Math.ceil(Number(region.height) || 0), 60, Math.max(60, (Number(viewport.height) || 0) - top));
  if (width <= 0 || height <= 0) return null;
  return { left, top, width, height };
}

function buildClickNextColumnPageScript() {
  return `
    (() => {
      const controls = Array.from(document.querySelectorAll("a, button, [role='button']"));
      const next = controls.find((node) => (node.innerText || node.textContent || "").trim() === "下一页");
      if (!next) return { clicked: false, reason: "missing" };
      const text = (next.innerText || next.textContent || "").trim();
      const className = String(next.className || "");
      const disabled = next.disabled ||
        next.getAttribute("aria-disabled") === "true" ||
        /disabled|inactive/.test(className);
      if (disabled) return { clicked: false, reason: "disabled", text };
      next.scrollIntoView({ block: "center" });
      next.click();
      return { clicked: true, text };
    })()
  `;
}

async function extractHomepageCandidates(cdp, sessionId, args) {
  const seenUrls = new Set();
  const allCandidates = [];
  const maxPages = args.captureScope === "all-visible" ? 20 : 1;

  for (let pageIndex = 0; pageIndex < maxPages && allCandidates.length < args.maxPosts; pageIndex += 1) {
    const remaining = args.maxPosts - allCandidates.length;
    const pageCandidates = await evaluateJson(
      cdp,
      sessionId,
      buildHomepageExtractionScript(remaining, args.captureScope),
      true
    );
    let added = 0;
    for (const candidate of pageCandidates ?? []) {
      const url = String(candidate?.url || "").trim();
      if (!url || seenUrls.has(url)) continue;
      seenUrls.add(url);
      allCandidates.push(candidate);
      added += 1;
      if (allCandidates.length >= args.maxPosts) break;
    }

    if (args.captureScope !== "all-visible" || allCandidates.length >= args.maxPosts) break;

    const clickResult = await evaluateJson(cdp, sessionId, buildClickNextColumnPageScript(), false);
    if (!clickResult?.clicked) break;
    await sleep(1_500);

    if (added === 0) {
      const afterClickCandidates = await evaluateJson(
        cdp,
        sessionId,
        buildHomepageExtractionScript(remaining, args.captureScope),
        true
      );
      const hasNewAfterClick = (afterClickCandidates ?? []).some((candidate) => {
        const url = String(candidate?.url || "").trim();
        return url && !seenUrls.has(url);
      });
      if (!hasNewAfterClick) break;
    }
  }

  return allCandidates;
}

function normalizePost(candidate, detail, fallbackAuthor, commentScope = "none") {
  const url = detail.url || candidate.url;
  const title = detail.title || candidate.title || url;
  const publishedAt = detail.published_at || candidate.published_at || "";
  const content = detail.content || candidate.content_snippet || "";
  const authorName = String(detail.author_name || candidate.author_name || fallbackAuthor || "").trim();
  return {
    title: String(title).trim(),
    published_at: String(publishedAt).trim(),
    url: String(url).trim(),
    content: String(content).trim(),
    author_name: authorName,
    author_comments: filterCommentsForScope(detail.comments, commentScope, authorName || fallbackAuthor),
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
  const payload = await evaluateJson(cdp, sessionId, buildVerificationInspectionPayloadScript(), false);
  if (!payload) return null;

  return {
    widget: selectBestVerificationWidget(payload.candidates || []),
    clip: buildVerificationClip(payload.region, payload.viewport),
  };
}

async function attemptVisualVerification(cdp, sessionId, clip) {
  if (!clip) return null;
  const screenshot = await cdp.send(
    "Page.captureScreenshot",
    {
      format: "png",
      clip: {
        x: clip.left,
        y: clip.top,
        width: clip.width,
        height: clip.height,
        scale: 1,
      },
      fromSurface: true,
      optimizeForSpeed: true,
    },
    { sessionId }
  );
  const data = String(screenshot?.data || "").trim();
  if (!data) return null;

  const visual = await evaluateJson(
    cdp,
    sessionId,
    buildVisualVerificationAnalysisScript(`data:image/png;base64,${data}`),
    true
  );
  if (!visual?.orangeBox || !visual?.trackBox) return null;

  return buildVisualVerificationGeometry({
    clipLeft: clip.left,
    clipTop: clip.top,
    orangeBox: visual.orangeBox,
    trackBox: visual.trackBox,
  });
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
    let clip = null;
    try {
      await waitForDocumentReady(cdp, sessionId, 5_000);
      const inspection = await inspectVerificationWidget(cdp, sessionId);
      widget = inspection?.widget || null;
      clip = inspection?.clip || null;
    } catch {
      widget = null;
      clip = null;
    }

    if (!widget) {
      try {
        widget = await attemptVisualVerification(cdp, sessionId, clip);
      } catch (error) {
        process.stderr.write(
          `[extract_xueqiu_posts] visual verification fallback failed: ${
            error instanceof Error ? error.message : String(error)
          }\n`
        );
      }
    }

    if (!widget) {
      process.stderr.write("[extract_xueqiu_posts] automatic slider verification could not locate a stable widget or visual track\n");
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
  const profileDir = resolveProfileDirForTesting(import.meta.url, args.profileDir);

  let launchedChrome = null;
  let debugPort = await findExistingChromeDebugPort({ profileDir, timeoutMs: 3_000 });
  if (!debugPort && await isChromeDebugPortUsable(args.debugPort)) {
    debugPort = args.debugPort;
  }
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
        win32: [
          path.join(process.env.PROGRAMFILES ?? "", "Google/Chrome/Application/chrome.exe"),
          path.join(process.env["PROGRAMFILES(X86)"] ?? "", "Google/Chrome/Application/chrome.exe"),
          path.join(process.env.LOCALAPPDATA ?? "", "Google/Chrome/Application/chrome.exe"),
          path.join(process.env.PROGRAMFILES ?? "", "Microsoft/Edge/Application/msedge.exe"),
          path.join(process.env["PROGRAMFILES(X86)"] ?? "", "Microsoft/Edge/Application/msedge.exe"),
          path.join(process.env.LOCALAPPDATA ?? "", "Microsoft/Edge/Application/msedge.exe"),
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

    const candidates = await extractHomepageCandidates(cdp, homepage.sessionId, args);

    const posts = [];
    for (const candidate of (candidates ?? []).filter((item) =>
      shouldKeepCandidateForCaptureScope(item, targetDate, args.captureScope)
    )) {
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
        await scrollDetailForComments(cdp, detailSession.sessionId, args.commentScope);

        let detail = await evaluateJson(cdp, detailSession.sessionId, buildDetailExtractionScript(args.commentScope), false);
        let normalized = normalizePost(candidate, detail, args.authorName, args.commentScope);
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
          await scrollDetailForComments(cdp, detailSession.sessionId, args.commentScope);
          detail = await evaluateJson(cdp, detailSession.sessionId, buildDetailExtractionScript(args.commentScope), false);
          normalized = normalizePost(candidate, detail, args.authorName, args.commentScope);
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
