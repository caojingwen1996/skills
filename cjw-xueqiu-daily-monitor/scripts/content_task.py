#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from utils import (
    close_browser,
    ensure_login,
    get_default_profile_dir,
    init_logger,
    safe_attr,
    safe_open,
    safe_text,
    scroll_page,
    write_log,
    launch_persistent_browser,
)

HOME_SCAN_JS = r"""
() => {
  const results = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll("a[href]"));
  const isVisible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 &&
      rect.height > 0 &&
      style.display !== "none" &&
      style.visibility !== "hidden";
  };
  const normalize = (text) => (text || "").replace(/\s+/g, " ").trim();
  const pickContainer = (el) => el.closest("article,[role='article'],section,li,div");
  const clip = (text, limit) => {
    const cleaned = normalize(text);
    return cleaned.length <= limit ? cleaned : cleaned.slice(0, limit);
  };

  for (const anchor of anchors) {
    const href = anchor.href || anchor.getAttribute("href") || "";
    if (!href || seen.has(href) || !isVisible(anchor)) continue;
    const container = pickContainer(anchor);
    if (!container || !isVisible(container)) continue;

    const containerText = clip(container.innerText || container.textContent || "", 1200);
    const anchorText = clip(anchor.innerText || anchor.textContent || "", 280);
    if (!containerText) continue;

    seen.add(href);
    results.push({
      href,
      anchor_text: anchorText,
      container_text: containerText,
    });
  }

  return results;
}
"""

DETAIL_EXTRACT_JS = r"""
() => {
  const normalize = (text) => (text || "").replace(/\u00a0/g, " ").replace(/\s+\n/g, "\n").trim();
  const textOf = (selector) => {
    const el = document.querySelector(selector);
    return el ? normalize(el.innerText || el.textContent || "") : "";
  };
  const attrOf = (selector, attrName) => {
    const el = document.querySelector(selector);
    const value = el ? el.getAttribute(attrName) : "";
    return normalize(value || "");
  };
  const firstLine = (text) => normalize((text || "").split("\n").find(Boolean) || "");

  const candidates = [
    "article",
    "main",
    "[role='main']",
    ".article__bd",
    ".article-content",
    ".status-content",
    ".detail__content",
    "body",
  ];

  let bestText = "";
  for (const selector of candidates) {
    const text = textOf(selector);
    if (text.length > bestText.length) {
      bestText = text;
    }
  }

  const bodyText = normalize(document.body ? document.body.innerText || document.body.textContent || "" : "");
  const publishSource = [
    attrOf("meta[property='article:published_time']", "content"),
    attrOf("meta[name='publish_time']", "content"),
    bodyText,
  ].filter(Boolean).join("\n");

  return {
    page_title: normalize(document.title),
    meta_title: attrOf("meta[property='og:title']", "content"),
    meta_url: attrOf("meta[property='og:url']", "content"),
    body_text: bodyText,
    content_text: bestText,
    first_line: firstLine(bestText || bodyText),
    publish_source: publishSource,
  };
}
"""

IGNORE_PATH_KEYWORDS = (
    "/setting",
    "/settings",
    "/service",
    "/about",
    "/help",
    "/download",
    "/apps",
    "/hq",
    "/k",
    "/today",
    "/calendar",
    "/topic",
    "/search",
    "/ask",
)

SHORT_UI_LINES = {
    "赞",
    "评论",
    "转发",
    "分享",
    "收藏",
    "风险提示",
    "全部评论",
    "加载中",
    "展开",
    "收起",
}


@dataclass
class PostCandidate:
    url: str
    summary: str
    container_text: str
    publish_text: str
    publish_date: date | None
    publish_time: str
    content_id: str


@dataclass
class PostRecord:
    content_id: str
    title: str
    publish_time: str
    publish_date: str
    url: str
    author_name: str
    content: str
    fetched_at: str


@dataclass
class TaskSummary:
    account_url: str
    target_date: str
    author_name: str = ""
    candidate_count: int = 0
    matched_count: int = 0
    skipped_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    result_dir: str = ""
    log_file: str = ""
    failures: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取雪球指定账号指定日期的帖子内容。")
    parser.add_argument("--account-url", required=True, help="目标账号主页链接")
    parser.add_argument("--date", help="目标日期，格式 YYYY-MM-DD，默认当天")
    parser.add_argument("--profile-dir", help="Chrome 持久化 profile 路径")
    parser.add_argument("--output-dir", required=True, help="输出根目录")
    parser.add_argument("--headless", action="store_true", help="是否启用无头模式")
    return parser.parse_args()


def parse_target_date(raw: str | None) -> date:
    if not raw:
        return datetime.now().date()
    return datetime.strptime(raw, "%Y-%m-%d").date()


def sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "unknown"


def slugify_filename(value: str, fallback: str = "post") -> str:
    slug = sanitize_name(value)[:48]
    return slug or fallback


def safe_text_value(page: Any, selector: str) -> str:
    return safe_text(page, selector, default="")


def safe_attr_value(page: Any, selector: str, attr_name: str) -> str:
    return safe_attr(page, selector, attr_name, default="")


def looks_like_post_url(url: str, account_url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if "xueqiu.com" not in parsed.netloc:
        return False
    path = parsed.path or ""
    lowered = path.lower()
    if not path or lowered == "/" or any(keyword in lowered for keyword in IGNORE_PATH_KEYWORDS):
        return False
    if lowered.rstrip("/") == urlparse(account_url).path.rstrip("/").lower():
        return False
    if "/u/" in lowered and lowered.count("/") <= 2:
        return False
    if "/status/" in lowered:
        return True
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return False
    if parts[0].upper() in {"S", "P"}:
        return False
    tail = parts[-1]
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{6,}", tail) or re.fullmatch(r"\d{6,}", tail))


def extract_content_id_from_url(url: str) -> str:
    path = urlparse(url).path
    match = re.search(r"/status/(\d+)", path)
    if match:
        return match.group(1)
    parts = [part for part in path.split("/") if part]
    for part in reversed(parts):
        if re.fullmatch(r"[A-Za-z0-9_-]{6,}", part):
            return part
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def find_datetime_text(text: str) -> str:
    patterns = [
        r"\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?",
        r"\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?",
        r"\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}",
        r"(?:今天|昨日|昨天)\s*\d{1,2}:\d{2}",
        r"\d{1,2}:\d{2}(?::\d{2})?",
        r"\d+\s*分钟前",
        r"\d+\s*小时前",
        r"刚刚",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return ""


def parse_publish_datetime(raw_text: str, target_date: date) -> tuple[date | None, str]:
    text = (raw_text or "").strip()
    if not text:
        return None, ""

    now = datetime.now()
    normalized = re.sub(r"\s+", " ", text.replace("年", "-").replace("月", "-").replace("日", " "))

    exact_formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    )
    for matched in re.findall(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?", normalized):
        for fmt in exact_formats:
            try:
                parsed = datetime.strptime(matched, fmt)
                return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

    month_day_match = re.search(r"(\d{1,2})[-/](\d{1,2})\s+(\d{1,2}:\d{2}(?::\d{2})?)", normalized)
    if month_day_match:
        month, day_value, time_text = month_day_match.groups()
        hour_minute = datetime.strptime(time_text, "%H:%M:%S" if time_text.count(":") == 2 else "%H:%M")
        parsed = datetime(
            target_date.year,
            int(month),
            int(day_value),
            hour_minute.hour,
            hour_minute.minute,
            hour_minute.second,
        )
        return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")

    chinese_match = re.search(r"(\d{1,2})-(\d{1,2})\s+(\d{1,2}:\d{2})", normalized)
    if chinese_match:
        month, day_value, time_text = chinese_match.groups()
        hour_minute = datetime.strptime(time_text, "%H:%M")
        parsed = datetime(target_date.year, int(month), int(day_value), hour_minute.hour, hour_minute.minute)
        return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")

    relative_match = re.search(r"(今天|昨天|昨日)\s*(\d{1,2}:\d{2})", normalized)
    if relative_match:
        day_text, time_text = relative_match.groups()
        base_date = now.date() if day_text == "今天" else (now.date() - timedelta(days=1))
        hour_minute = datetime.strptime(time_text, "%H:%M")
        parsed = datetime(base_date.year, base_date.month, base_date.day, hour_minute.hour, hour_minute.minute)
        return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")

    if "刚刚" in normalized:
        return now.date(), now.strftime("%Y-%m-%d %H:%M:%S")

    minutes_match = re.search(r"(\d+)\s*分钟前", normalized)
    if minutes_match:
        parsed = now - timedelta(minutes=int(minutes_match.group(1)))
        return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")

    hours_match = re.search(r"(\d+)\s*小时前", normalized)
    if hours_match:
        parsed = now - timedelta(hours=int(hours_match.group(1)))
        return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")

    time_only_match = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", normalized)
    if time_only_match:
        time_text = time_only_match.group(1)
        hour_minute = datetime.strptime(time_text, "%H:%M:%S" if time_text.count(":") == 2 else "%H:%M")
        parsed = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour_minute.hour,
            hour_minute.minute,
            hour_minute.second,
        )
        return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")

    return None, ""


def guess_summary(anchor_text: str, container_text: str) -> str:
    for source in (anchor_text, container_text):
        lines = [line.strip() for line in source.splitlines() if line.strip()]
        for line in lines:
            if len(line) >= 6:
                return line[:80]
    return container_text[:80].strip() or "未命名帖子"


def resolve_author_name(page: Any, account_url: str) -> str:
    candidates = [
        safe_text_value(page, "h1"),
        safe_text_value(page, "header"),
        safe_attr_value(page, "meta[name='author']", "content"),
        safe_attr_value(page, "meta[property='og:title']", "content"),
    ]
    if hasattr(page, "evaluate"):
        try:
            title = page.evaluate("() => document.title || ''").strip()
            candidates.append(title)
        except Exception:
            pass
    for candidate in candidates:
        if not candidate:
            continue
        candidate = candidate.replace("\n", " ").strip()
        match = re.search(r"(.+?)(?:的雪球| - 雪球|_雪球)", candidate)
        if match:
            return match.group(1).strip()
        if 1 <= len(candidate) <= 40:
            return candidate
    path = urlparse(account_url).path.rstrip("/").split("/")
    return path[-1] if path and path[-1] else "xueqiu_account"


def scan_posts_on_homepage(page: Any, account_url: str, target_date: date, logger: Any) -> list[PostCandidate]:
    if not hasattr(page, "evaluate"):
        raise RuntimeError("page 对象不支持 evaluate，无法执行主页扫描。")

    found: dict[str, PostCandidate] = {}
    stagnant_rounds = 0

    for round_index in range(1, 19):
        raw_items = page.evaluate(HOME_SCAN_JS) or []
        new_items = 0

        for item in raw_items:
            url = item.get("href", "").strip()
            if not looks_like_post_url(url, account_url):
                continue
            normalized_url = urljoin(account_url, url)
            if normalized_url in found:
                continue

            container_text = (item.get("container_text") or "").strip()
            anchor_text = (item.get("anchor_text") or "").strip()
            publish_text = find_datetime_text(container_text)
            publish_date, publish_time = parse_publish_datetime(publish_text or container_text, target_date)

            found[normalized_url] = PostCandidate(
                url=normalized_url,
                summary=guess_summary(anchor_text, container_text),
                container_text=container_text,
                publish_text=publish_text,
                publish_date=publish_date,
                publish_time=publish_time,
                content_id=extract_content_id_from_url(normalized_url),
            )
            new_items += 1

        write_log(logger, "info", f"主页扫描第 {round_index} 轮，新增候选 {new_items}，累计候选 {len(found)}。")

        if new_items == 0:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
        if stagnant_rounds >= 3:
            break

        scroll_page(page, step=1400, times=1, pause=1.0, logger=logger)
        time.sleep(0.5)

    return list(found.values())


def filter_posts_by_date(
    candidates: list[PostCandidate],
    target_date: date,
    logger: Any,
) -> tuple[list[PostCandidate], int]:
    matched: list[PostCandidate] = []
    skipped = 0
    for candidate in candidates:
        if candidate.publish_date == target_date:
            matched.append(candidate)
        else:
            skipped += 1
            write_log(
                logger,
                "info",
                f"跳过非目标日期或时间无法识别的帖子: {candidate.url} publish_text={candidate.publish_text or 'unknown'}",
            )
    return matched, skipped


def load_existing_keys(result_dir: Path) -> set[str]:
    keys: set[str] = set()
    if not result_dir.exists():
        return keys
    for path in result_dir.glob("*.txt"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith("内容ID：") or line.startswith("原始链接："):
                keys.add(line.split("：", 1)[1].strip())
    return keys


def deduplicate_posts(
    candidates: list[PostCandidate],
    existing_keys: set[str],
    logger: Any,
) -> tuple[list[PostCandidate], int]:
    unique: list[PostCandidate] = []
    seen = set(existing_keys)
    skipped = 0
    for candidate in candidates:
        dedupe_key = candidate.content_id or candidate.url
        if dedupe_key in seen or candidate.url in seen:
            skipped += 1
            write_log(logger, "info", f"跳过重复帖子: {candidate.url}")
            continue
        seen.add(dedupe_key)
        seen.add(candidate.url)
        unique.append(candidate)
    return unique, skipped


def open_post_detail(context: Any, home_page: Any, candidate: PostCandidate, logger: Any) -> tuple[Any, bool]:
    if context is not None and hasattr(context, "new_page"):
        detail_page = context.new_page()
        safe_open(detail_page, candidate.url, logger=logger)
        return detail_page, True
    safe_open(home_page, candidate.url, logger=logger)
    return home_page, False


def clean_content_text(text: str, title: str, publish_time: str, author_name: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line in SHORT_UI_LINES:
            continue
        if line in {title, publish_time, author_name}:
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return "\n".join(lines).strip()


def first_non_empty(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def extract_post_content(
    page: Any,
    candidate: PostCandidate,
    target_date: date,
    author_name: str,
) -> PostRecord:
    if not hasattr(page, "evaluate"):
        raise RuntimeError("详情页对象不支持 evaluate，无法提取正文。")

    extracted = page.evaluate(DETAIL_EXTRACT_JS) or {}
    meta_url = safe_attr_value(page, "meta[property='og:url']", "content")
    meta_title = safe_attr_value(page, "meta[property='og:title']", "content")
    article_text = first_non_empty(
        safe_text_value(page, "article"),
        safe_text_value(page, "main"),
        extracted.get("content_text", ""),
        extracted.get("body_text", ""),
    )

    title = first_non_empty(
        meta_title,
        extracted.get("meta_title", ""),
        candidate.summary,
        extracted.get("first_line", ""),
        extracted.get("page_title", ""),
    )
    raw_publish = first_non_empty(candidate.publish_text, extracted.get("publish_source", ""), article_text)
    publish_date, publish_time = parse_publish_datetime(raw_publish, target_date)

    if publish_date is None:
        raise ValueError("发布时间无法识别")
    if publish_date != target_date:
        raise ValueError(f"帖子不属于目标日期: {publish_date.isoformat()}")

    content = clean_content_text(article_text, title, publish_time, author_name)
    if not content:
        raise ValueError("正文提取失败或正文为空")

    return PostRecord(
        content_id=candidate.content_id,
        title=title,
        publish_time=publish_time,
        publish_date=publish_date.isoformat(),
        url=first_non_empty(meta_url, extracted.get("meta_url", ""), candidate.url),
        author_name=author_name,
        content=content,
        fetched_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
    )


def build_result_paths(output_root: Path, author_name: str, target_date: date) -> tuple[Path, Path]:
    base_name = f"{sanitize_name(author_name)}_{target_date.strftime('%Y%m%d')}"
    return output_root / base_name, output_root / f"{base_name}.log"


def make_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def save_posts_to_files(records: list[PostRecord], result_dir: Path, logger: Any) -> int:
    saved = 0
    result_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        timestamp_part = record.publish_time[11:19].replace(":", "") if len(record.publish_time) >= 19 else "000000"
        filename = f"{timestamp_part}_{slugify_filename(record.title)}_{record.content_id[:8]}.txt"
        file_path = make_unique_path(result_dir / filename)
        body = "\n".join(
            [
                f"标题：{record.title}",
                f"内容ID：{record.content_id}",
                f"发布时间：{record.publish_time}",
                f"发布日期：{record.publish_date}",
                f"原始链接：{record.url}",
                f"作者名称：{record.author_name}",
                f"抓取时间：{record.fetched_at}",
                "",
                "正文：",
                record.content,
                "",
            ]
        )
        file_path.write_text(body, encoding="utf-8")
        saved += 1
        write_log(logger, "info", f"保存成功: {file_path}")
    return saved


def print_task_summary(summary: TaskSummary) -> None:
    print("\n任务结果汇总")
    print(f"目标账号: {summary.account_url}")
    print(f"博主名称: {summary.author_name}")
    print(f"目标日期: {summary.target_date}")
    print(f"候选帖子数: {summary.candidate_count}")
    print(f"目标日期帖子数: {summary.matched_count}")
    print(f"跳过数: {summary.skipped_count}")
    print(f"成功抓取数: {summary.success_count}")
    print(f"失败数: {summary.failure_count}")
    print(f"结果目录: {summary.result_dir}")
    print(f"日志文件: {summary.log_file}")
    if summary.failures:
        print("失败明细:")
        for item in summary.failures:
            print(f"- {item}")


def fetch_posts_by_date(args: argparse.Namespace) -> TaskSummary:
    target_date = parse_target_date(args.date)
    output_root = Path(args.output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    pre_logger = init_logger(name="content_task_bootstrap")
    summary = TaskSummary(account_url=args.account_url, target_date=target_date.isoformat())
    session: dict[str, Any] | None = None

    write_log(pre_logger, "info", f"任务启动，目标账号={args.account_url}，目标日期={target_date.isoformat()}")

    try:
        profile_dir = get_default_profile_dir(args.profile_dir)
        session = launch_persistent_browser(
            profile_dir=profile_dir,
            headless=args.headless,
            logger=pre_logger,
        )
        page = session["page"]
        context = session["context"]

        safe_open(page, args.account_url, logger=pre_logger)
        ensure_login(
            page,
            account_url=args.account_url,
            headless=args.headless,
            logger=pre_logger,
        )
        safe_open(page, args.account_url, logger=pre_logger)

        author_name = resolve_author_name(page, args.account_url)
        result_dir, log_file = build_result_paths(output_root, author_name, target_date)
        logger = init_logger(name="content_task", log_file=log_file)

        summary.author_name = author_name
        summary.result_dir = str(result_dir)
        summary.log_file = str(log_file)

        write_log(logger, "info", f"已进入主页，博主={author_name}，profile_dir={profile_dir}，headless={args.headless}")

        candidates = scan_posts_on_homepage(page, args.account_url, target_date, logger)
        summary.candidate_count = len(candidates)

        matched, skipped_by_date = filter_posts_by_date(candidates, target_date, logger)
        summary.matched_count = len(matched)
        summary.skipped_count += skipped_by_date

        existing_keys = load_existing_keys(result_dir)
        deduped, skipped_by_duplicate = deduplicate_posts(matched, existing_keys, logger)
        summary.skipped_count += skipped_by_duplicate

        if not deduped:
            write_log(logger, "warning", "目标日期无可抓取新帖子。")
            return summary

        saved_keys = set(existing_keys)
        for candidate in deduped:
            detail_page = None
            should_close = False
            try:
                write_log(logger, "info", f"开始处理帖子: {candidate.url}")
                detail_page, should_close = open_post_detail(context, page, candidate, logger)
                record = extract_post_content(detail_page, candidate, target_date, author_name)
                dedupe_key = record.content_id or record.url
                if dedupe_key in saved_keys or record.url in saved_keys:
                    summary.skipped_count += 1
                    write_log(logger, "info", f"详情页去重命中，跳过: {record.url}")
                    continue
                summary.success_count += save_posts_to_files([record], result_dir, logger)
                saved_keys.add(dedupe_key)
                saved_keys.add(record.url)
            except Exception as exc:
                summary.failure_count += 1
                message = f"{candidate.url} -> {exc}"
                summary.failures.append(message)
                write_log(logger, "error", f"处理失败: {message}")
            finally:
                if detail_page is not None and should_close and hasattr(detail_page, "close"):
                    try:
                        detail_page.close()
                    except Exception:
                        write_log(logger, "warning", f"详情页关闭失败: {candidate.url}")

        if summary.success_count == 0 and summary.failure_count == 0:
            write_log(logger, "warning", "目标日期无帖子。")
        return summary
    except Exception as exc:
        summary.failure_count += 1
        summary.failures.append(str(exc))
        write_log(pre_logger, "error", f"任务异常中断: {exc}")
        return summary
    finally:
        if session is not None:
            try:
                close_browser(session, logger=pre_logger)
            except Exception:
                write_log(pre_logger, "warning", "浏览器关闭失败，请手动检查。")
        write_log(pre_logger, "info", "任务结束。")


def main() -> int:
    args = parse_args()
    summary = fetch_posts_by_date(args)
    print_task_summary(summary)
    return 0 if summary.failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
