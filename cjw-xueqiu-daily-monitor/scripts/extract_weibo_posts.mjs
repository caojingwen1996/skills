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
      "Usage: node scripts/extract_weibo_posts.mjs --account-url URL --date YYYY-MM-DD [options]",
      "",
      "Options:",
      "  --account-url URL      Weibo homepage URL in https://weibo.com/u/... format",
      "  --date YYYY-MM-DD      Target date used for later filtering",
      "  --author-name NAME     Optional author name override",
      "  --output-file PATH     Optional JSON output path; defaults to stdout",
      "  --profile-dir PATH     Chrome profile dir; defaults to scripts/.xueqiu-chrome-profile",
      "  --debug-port PORT      Remote debugging port; defaults to 9333",
      "  --max-posts N          Maximum detail pages to extract; defaults to 30",
      "  --headless             Launch Chrome in headless mode when starting a new instance",
      "  --help                 Show this help",
      "",
    ].join("\n")
  );
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
  if (!/^https?:\/\/weibo\.com\/u\/\d+/.test(args.accountUrl)) {
    throw new Error("--account-url must be a Weibo homepage URL in https://weibo.com/u/... format");
  }
  if (!args.date || !/^\d{4}-\d{2}-\d{2}$/.test(args.date)) throw new Error("--date must be YYYY-MM-DD");
  if (!Number.isInteger(args.debugPort) || args.debugPort <= 0) throw new Error("--debug-port must be a positive integer");
  if (!Number.isInteger(args.maxPosts) || args.maxPosts <= 0) throw new Error("--max-posts must be a positive integer");
  return args;
}

function resolveProfileDir(metaUrl, explicitProfileDir) {
  const scriptDir = path.dirname(fileURLToPath(metaUrl));
  return path.resolve(explicitProfileDir || path.join(scriptDir, ".xueqiu-chrome-profile"));
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

function buildAccessInspectionScript() {
  return `
    (() => {
      const text = (document.body?.innerText || "").trim();
      return {
        title: document.title || "",
        href: location.href,
        text,
        loginRequired: /前方有点拥堵，请登录后使用|登录后使用|登录查看更多|请登录/.test(text),
      };
    })()
  `;
}

function buildHomepageExtractionScript(maxPosts) {
  return `
    (async () => {
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      for (let i = 0; i < 6; i += 1) {
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(700);
      }

      const normalizeUrl = (value) => {
        try {
          return new URL(value, location.href).href;
        } catch {
          return "";
        }
      };

      const inferPublishedAt = (text) => {
        const source = String(text || "");
        const patterns = [
          /\\d{4}-\\d{1,2}-\\d{1,2}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?/,
          /\\d{4}\\/\\d{1,2}\\/\\d{1,2}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?/,
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

      const authorFallback = Array.from(document.querySelectorAll("h1, [class*='name'], [class*='Nick']"))
        .map((node) => (node.innerText || "").trim())
        .find(Boolean) || "";

      const anchors = Array.from(document.querySelectorAll("a[href]"));
      const seen = new Set();
      const results = [];
      for (const anchor of anchors) {
        const href = normalizeUrl(anchor.getAttribute("href"));
        if (!/weibo\\.com\\/(?:u\\/)?\\d+\\/[A-Za-z0-9]+/.test(href) && !/weibo\\.com\\/detail\\/[A-Za-z0-9]+/.test(href)) {
          continue;
        }
        if (seen.has(href)) continue;
        seen.add(href);
        const container = anchor.closest("article, div, li") || anchor;
        const text = (container.innerText || anchor.innerText || "").trim();
        if (!text) continue;
        const lines = text.split(/\\n+/).map((item) => item.trim()).filter(Boolean);
        results.push({
          url: href,
          title: lines[0] || href,
          published_at: inferPublishedAt(text),
          content_snippet: text,
          author_name: authorFallback,
          platform: "weibo",
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
      const inferPublishedAt = (text) => {
        const source = String(text || "");
        const patterns = [
          /\\d{4}-\\d{1,2}-\\d{1,2}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?/,
          /\\d{4}\\/\\d{1,2}\\/\\d{1,2}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?/,
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

      const title = [
        document.querySelector("h1")?.innerText,
        document.querySelector("[class*='detail'] [class*='text']")?.innerText,
        document.title,
        bodyText.split(/\\n+/).find(Boolean),
      ].find((value) => value && String(value).trim()) || "";

      const author = Array.from(document.querySelectorAll("h1, [class*='name'], [class*='Nick']"))
        .map((node) => (node.innerText || "").trim())
        .find(Boolean) || "";

      return {
        title: String(title).trim(),
        published_at: inferPublishedAt(bodyText),
        author_name: author,
        content: bodyText,
        url: location.href,
        platform: "weibo",
      };
    })()
  `;
}

function normalizePost(candidate, detail, fallbackAuthor) {
  return {
    title: String(detail.title || candidate.title || candidate.url).trim(),
    published_at: String(detail.published_at || candidate.published_at || "").trim(),
    url: String(detail.url || candidate.url || "").trim(),
    content: String(detail.content || candidate.content_snippet || "").trim(),
    author_name: String(detail.author_name || candidate.author_name || fallbackAuthor || "").trim(),
    platform: "weibo",
  };
}

async function isChromeDebugPortUsable(port) {
  try {
    await waitForChromeDebugPort(port, 1_000);
    return true;
  } catch {
    return false;
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const profileDir = resolveProfileDir(import.meta.url, args.profileDir);

  let launchedChrome = null;
  let debugPort = await findExistingChromeDebugPort({ profileDir, timeoutMs: 3_000 });
  if (!debugPort && await isChromeDebugPortUsable(args.debugPort)) {
    debugPort = args.debugPort;
  }

  if (!debugPort) {
    debugPort = args.debugPort;
    const chromePath = findChromeExecutable({
      candidates: {
        win32: [
          path.join(process.env.PROGRAMFILES ?? "", "Google/Chrome/Application/chrome.exe"),
          path.join(process.env["PROGRAMFILES(X86)"] ?? "", "Google/Chrome/Application/chrome.exe"),
          path.join(process.env.LOCALAPPDATA ?? "", "Google/Chrome/Application/chrome.exe"),
          path.join(process.env.PROGRAMFILES ?? "", "Microsoft/Edge/Application/msedge.exe"),
          path.join(process.env["PROGRAMFILES(X86)"] ?? "", "Microsoft/Edge/Application/msedge.exe"),
          path.join(process.env.LOCALAPPDATA ?? "", "Microsoft/Edge/Application/msedge.exe"),
        ],
        darwin: [
          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Chromium.app/Contents/MacOS/Chromium",
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
    await sleep(3_000);

    const accessState = await evaluateJson(cdp, homepage.sessionId, buildAccessInspectionScript(), false);
    if (accessState?.loginRequired) {
      throw new Error(`Weibo login required for ${args.accountUrl}: ${String(accessState.text || "").slice(0, 120)}`);
    }

    const candidates = await evaluateJson(cdp, homepage.sessionId, buildHomepageExtractionScript(args.maxPosts), true);
    const posts = [];

    for (const candidate of candidates ?? []) {
      let detailSession = null;
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
        await sleep(1_500);

        const detail = await evaluateJson(cdp, detailSession.sessionId, buildDetailExtractionScript(), false);
        const normalized = normalizePost(candidate, detail, args.authorName);
        if (normalized.url && normalized.content) {
          posts.push(normalized);
        }
      } catch (error) {
        process.stderr.write(
          `[extract_weibo_posts] failed to extract ${candidate.url}: ${
            error instanceof Error ? error.message : String(error)
          }\n`
        );
      } finally {
        if (detailSession?.targetId) {
          try {
            await cdp.send("Target.closeTarget", { targetId: detailSession.targetId });
          } catch {
            // ignore
          }
        }
      }
    }

    const payload = JSON.stringify(posts, null, 2);
    if (args.outputFile) {
      const fs = await import("node:fs/promises");
      await fs.writeFile(args.outputFile, payload, "utf-8");
    } else {
      process.stdout.write(`${payload}\n`);
    }
  } finally {
    cdp.close();
    if (launchedChrome) {
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
