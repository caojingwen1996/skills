#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

function printHelp() {
  process.stdout.write(
    [
      "Usage: node scripts/extract_wechat_articles.mjs --article-url URL [--article-url URL ...] [options]",
      "",
      "Options:",
      "  --article-url URL      WeChat article URL, repeatable",
      "  --history-url URL      WeChat history/home page URL used to discover article links",
      "  --input-file PATH      Text or JSON file containing article URLs",
      "  --output-file PATH     Optional JSON output path; defaults to stdout",
      "  --author-name NAME     Optional author name fallback",
      "  --html-file PATH       Parse this local HTML file instead of fetching; intended for offline checks",
      "  --history-html-file PATH  Parse this local history HTML file instead of fetching --history-url",
      "  --date YYYY-MM-DD      Keep only articles published on this date",
      "  --help                 Show this help",
      "",
    ].join("\n")
  );
}

function parseArgs(argv) {
  const args = {
    articleUrls: [],
    historyUrl: "",
    inputFile: "",
    outputFile: "",
    authorName: "",
    htmlFile: "",
    historyHtmlFile: "",
    date: "",
  };

  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--help") {
      args.help = true;
    } else if (value === "--article-url") {
      args.articleUrls.push(requireValue(argv, index, value));
      index += 1;
    } else if (value === "--history-url") {
      args.historyUrl = requireValue(argv, index, value);
      index += 1;
    } else if (value === "--input-file") {
      args.inputFile = requireValue(argv, index, value);
      index += 1;
    } else if (value === "--output-file") {
      args.outputFile = requireValue(argv, index, value);
      index += 1;
    } else if (value === "--author-name") {
      args.authorName = requireValue(argv, index, value);
      index += 1;
    } else if (value === "--html-file") {
      args.htmlFile = requireValue(argv, index, value);
      index += 1;
    } else if (value === "--history-html-file") {
      args.historyHtmlFile = requireValue(argv, index, value);
      index += 1;
    } else if (value === "--date") {
      args.date = requireValue(argv, index, value);
      index += 1;
    } else {
      throw new Error(`Unknown option: ${value}`);
    }
  }

  return args;
}

function requireValue(argv, index, optionName) {
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${optionName} requires a value`);
  }
  return value;
}

export function isWechatArticleUrl(value) {
  let parsed;
  try {
    parsed = new URL(String(value || ""));
  } catch {
    return false;
  }
  if (parsed.hostname !== "mp.weixin.qq.com") return false;
  return parsed.pathname === "/s" || parsed.pathname.startsWith("/s/");
}

function normalizeWechatArticleUrl(value, baseUrl) {
  const raw = normalizeWhitespace(value).replace(/\\u0026/g, "&");
  const candidates = [raw];
  try {
    candidates.push(decodeURIComponent(raw));
  } catch {
    // Keep the raw candidate when percent decoding fails.
  }

  for (const candidate of candidates) {
    try {
      const parsed = new URL(candidate, baseUrl || "https://mp.weixin.qq.com/");
      if (isWechatArticleUrl(parsed.href)) {
        parsed.hash = "";
        return parsed.href;
      }
    } catch {
      // Try the next candidate.
    }
  }
  return "";
}

export function extractWechatArticleUrlsFromHistoryHtml(html, baseUrl = "https://mp.weixin.qq.com/") {
  const text = String(html || "");
  const found = [];
  const patterns = [
    /\bhref\s*=\s*["']([^"']+)["']/gi,
    /https?:\/\/mp\.weixin\.qq\.com\/s(?:\/|%2F|\?)[^"'<>\s\\]+/gi,
    /https?%3A%2F%2Fmp\.weixin\.qq\.com%2Fs(?:%2F|%3F)[^"'<>\s\\]+/gi,
    /\/s\/[^"'<>\s\\]+/gi,
  ];

  for (const pattern of patterns) {
    for (const match of text.matchAll(pattern)) {
      const value = match[1] || match[0];
      const normalized = normalizeWechatArticleUrl(value, baseUrl);
      if (normalized) found.push(normalized);
    }
  }

  return [...new Set(found)];
}

function decodeHtmlEntities(value) {
  const named = {
    amp: "&",
    gt: ">",
    lt: "<",
    nbsp: " ",
    quot: '"',
    apos: "'",
  };
  return String(value || "").replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (match, entity) => {
    const lower = entity.toLowerCase();
    if (lower.startsWith("#x")) {
      return String.fromCodePoint(Number.parseInt(lower.slice(2), 16));
    }
    if (lower.startsWith("#")) {
      return String.fromCodePoint(Number.parseInt(lower.slice(1), 10));
    }
    return named[lower] ?? match;
  });
}

function normalizeWhitespace(value) {
  return decodeHtmlEntities(value)
    .replace(/\u00a0/g, " ")
    .replace(/[ \t\r\f\v]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function stripTags(html) {
  return normalizeWhitespace(
    String(html || "")
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "")
      .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, "")
      .replace(/<(?:p|div|section|article|h[1-6]|blockquote|li|br)\b[^>]*>/gi, "\n")
      .replace(/<\/(?:p|div|section|article|h[1-6]|blockquote|li)>/gi, "\n")
      .replace(/<[^>]+>/g, "")
      .replace(/[ \t]*\n[ \t]*/g, "\n")
  );
}

function extractElementById(html, id) {
  const pattern = new RegExp(
    `<([a-zA-Z][\\w:-]*)\\b(?=[^>]*\\bid\\s*=\\s*["']${escapeRegExp(id)}["'])[^>]*>([\\s\\S]*?)<\\/\\1>`,
    "i"
  );
  const match = String(html || "").match(pattern);
  return match ? stripTags(match[2]) : "";
}

function extractJsVar(html, name) {
  const pattern = new RegExp(`\\bvar\\s+${escapeRegExp(name)}\\s*=\\s*(['"])([\\s\\S]*?)\\1\\s*;`, "i");
  const match = String(html || "").match(pattern);
  if (!match) return "";
  return normalizeWhitespace(unescapeJsString(match[2]));
}

function unescapeJsString(value) {
  return String(value || "")
    .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(Number.parseInt(hex, 16)))
    .replace(/\\x([0-9a-fA-F]{2})/g, (_, hex) => String.fromCharCode(Number.parseInt(hex, 16)))
    .replace(/\\(['"\\])/g, "$1");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizePublishTime(value) {
  const text = normalizeWhitespace(value).replace(/年|月/g, "-").replace(/日/g, " ");
  let match = text.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?/);
  if (match) {
    return formatDateTime(match);
  }
  match = text.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (match) {
    return formatDateTime([...match, "00", "00", "00"]);
  }
  return text;
}

function extractPublishTimeFromMetadata(html) {
  const text = String(html || "");
  const patterns = [
    /["']publish_time["']\s*:\s*(\d{9,12})/,
    /publish_time%22%3A(\d{9,12})/i,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) {
      return formatUnixTimestamp(Number.parseInt(match[1], 10));
    }
  }
  return "";
}

function formatUnixTimestamp(value) {
  if (!Number.isFinite(value)) return "";
  const milliseconds = value > 9_999_999_999 ? value : value * 1000;
  const parsed = new Date(milliseconds);
  if (Number.isNaN(parsed.getTime())) return "";
  return [
    parsed.getFullYear(),
    "-",
    pad2(parsed.getMonth() + 1),
    "-",
    pad2(parsed.getDate()),
    " ",
    pad2(parsed.getHours()),
    ":",
    pad2(parsed.getMinutes()),
    ":",
    pad2(parsed.getSeconds()),
  ].join("");
}

function formatDateTime(match) {
  const [, year, month, day, hour = "00", minute = "00", second = "00"] = match;
  return `${year}-${pad2(month)}-${pad2(day)} ${pad2(hour)}:${pad2(minute)}:${pad2(second)}`;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

export function extractContentIdFromWechatUrl(value) {
  const parsed = new URL(value);
  const slashId = parsed.pathname.match(/^\/s\/([^/?#]+)/);
  if (slashId) return slashId[1];
  const sn = parsed.searchParams.get("sn");
  if (sn) return sn;
  const mid = parsed.searchParams.get("mid");
  const idx = parsed.searchParams.get("idx");
  if (mid && idx) return `${mid}_${idx}`;
  return parsed.href;
}

export function extractWechatArticleFromHtml(html, url, options = {}) {
  const title = extractElementById(html, "activity-name") || extractJsVar(html, "msg_title");
  const authorName = extractElementById(html, "js_name") || extractJsVar(html, "nickname") || options.authorName || "";
  const publishedAt = normalizePublishTime(extractElementById(html, "publish_time")) || extractPublishTimeFromMetadata(html);
  const content = extractElementById(html, "js_content");
  const sourceUrl = extractJsVar(html, "msg_source_url");

  return {
    content_id: extractContentIdFromWechatUrl(url),
    title,
    published_at: publishedAt,
    url,
    author_name: authorName,
    content,
    author_comments: [],
    source_url: sourceUrl,
    fetched_at: new Date().toISOString(),
    source_platform: "wechat",
  };
}

async function readInputUrls(args) {
  const urls = [...args.articleUrls];
  if (args.historyUrl) {
    const html = args.historyHtmlFile ? await fs.readFile(args.historyHtmlFile, "utf-8") : await fetchWechatHtml(args.historyUrl);
    urls.push(...extractWechatArticleUrlsFromHistoryHtml(html, args.historyUrl));
  }
  if (args.inputFile) {
    const text = await fs.readFile(args.inputFile, "utf-8");
    const trimmed = text.trim();
    if (trimmed.startsWith("[")) {
      for (const item of JSON.parse(trimmed)) {
        if (typeof item === "string") urls.push(item);
        else if (item?.url) urls.push(String(item.url));
      }
    } else {
      for (const line of text.split(/\r?\n/)) {
        const cleaned = line.trim();
        if (cleaned && !cleaned.startsWith("#")) urls.push(cleaned);
      }
    }
  }
  return [...new Set(urls)].filter(isWechatArticleUrl);
}

async function fetchWechatHtml(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
      Referer: "https://mp.weixin.qq.com/",
    },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ${response.statusText}`);
  }
  return await response.text();
}

async function extractArticles(args) {
  const urls = await readInputUrls(args);
  if (!urls.length) {
    throw new Error("No valid WeChat article URLs were provided.");
  }

  const localHtml = args.htmlFile ? await fs.readFile(args.htmlFile, "utf-8") : "";
  const articles = [];
  for (const url of urls) {
    try {
      const html = localHtml || await fetchWechatHtml(url);
      const article = extractWechatArticleFromHtml(html, url, { authorName: args.authorName });
      if (!article.title || !article.content) {
        throw new Error("Article title or content was not found.");
      }
      if (args.date && !String(article.published_at || "").startsWith(args.date)) {
        continue;
      }
      articles.push(article);
    } catch (error) {
      process.stderr.write(
        `[extract_wechat_articles] failed to extract ${url}: ${
          error instanceof Error ? error.message : String(error)
        }\n`
      );
    }
  }
  return articles;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    printHelp();
    return 0;
  }

  const articles = await extractArticles(args);
  const payload = JSON.stringify(articles, null, 2);
  if (args.outputFile) {
    await fs.mkdir(path.dirname(args.outputFile), { recursive: true });
    await fs.writeFile(args.outputFile, `${payload}\n`, "utf-8");
  } else {
    process.stdout.write(`${payload}\n`);
  }
  return articles.length > 0 ? 0 : 1;
}

const currentModulePath = fileURLToPath(import.meta.url);
const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";

if (invokedPath === currentModulePath) {
  main().then((exitCode) => {
    process.exit(exitCode);
  }).catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exit(1);
  });
}
