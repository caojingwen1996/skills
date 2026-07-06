#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from .utils import init_logger, resolve_output_root, write_log
except ImportError:
    from utils import init_logger, resolve_output_root, write_log


class NonTargetDateError(ValueError):
    """Raised when an extracted post does not belong to the requested date."""


@dataclass
class PostRecord:
    content_id: str
    title: str
    publish_time: str
    publish_date: str
    url: str
    author_name: str
    platform: str
    content: str
    author_comments: list[dict[str, str]]
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
    parser = argparse.ArgumentParser(description="Save extracted platform posts as per-author Markdown raw files.")
    parser.add_argument("--input-file", required=True, help="JSON file containing a list of extracted posts")
    parser.add_argument("--author-name", help="Explicit author name override")
    parser.add_argument("--account-url", help="Homepage URL for summary output")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD format")
    parser.add_argument("--output-dir", help="Output root; defaults to EXTEND.md preferred output root")
    parser.add_argument(
        "--date-source",
        choices=("target", "post"),
        default="target",
        help="Use target date or each post's publish date for the output directory date",
    )
    parser.add_argument(
        "--date-filter",
        choices=("target-date", "off"),
        default="target-date",
        help="Whether to keep only posts matching the target date",
    )
    parser.add_argument(
        "--layout",
        choices=("date-author", "author-root-date"),
        default="date-author",
        help="Directory layout under the output root",
    )
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

    date_only_match = re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", normalized)
    if date_only_match:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                parsed_date = datetime.strptime(date_only_match.group(0), fmt).date()
                parsed = datetime(parsed_date.year, parsed_date.month, parsed_date.day)
                return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

    month_day_match = re.search(r"(\d{1,2})[-/](\d{1,2})\s+(\d{1,2}:\d{2}(?::\d{2})?)", normalized)
    if month_day_match:
        month, day_value, time_text = month_day_match.groups()
        time_value = datetime.strptime(time_text, "%H:%M:%S" if time_text.count(":") == 2 else "%H:%M")
        parsed = datetime(
            target_date.year,
            int(month),
            int(day_value),
            time_value.hour,
            time_value.minute,
            time_value.second,
        )
        return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")

    relative_match = re.search(r"(今天|昨天|昨日)\s*(\d{1,2}:\d{2})", normalized)
    if relative_match:
        day_text, time_text = relative_match.groups()
        base_date = now.date() if day_text == "今天" else (now.date() - timedelta(days=1))
        time_value = datetime.strptime(time_text, "%H:%M")
        parsed = datetime(base_date.year, base_date.month, base_date.day, time_value.hour, time_value.minute)
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
        time_value = datetime.strptime(time_text, "%H:%M:%S" if time_text.count(":") == 2 else "%H:%M")
        parsed = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            time_value.hour,
            time_value.minute,
            time_value.second,
        )
        return parsed.date(), parsed.strftime("%Y-%m-%d %H:%M:%S")

    return None, ""


def derive_author_name(explicit_author_name: str | None, account_url: str | None, items: list[dict[str, Any]]) -> str:
    if explicit_author_name and explicit_author_name.strip():
        return explicit_author_name.strip()
    for item in items:
        name = str(item.get("author_name") or "").strip()
        if name:
            return name
    if account_url:
        path_parts = [part for part in urlparse(account_url).path.split("/") if part]
        if path_parts:
            return path_parts[-1]
    return "platform_account"


def load_input_items(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("input-file must contain a JSON array")
    normalized: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each extracted post must be a JSON object")
        normalized.append(item)
    return normalized


def normalize_author_comments(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_comments = payload.get("author_comments") or payload.get("comments") or []
    if not isinstance(raw_comments, list):
        return []

    comments: list[dict[str, str]] = []
    for item in raw_comments:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        comments.append(
            {
                "author_name": str(item.get("author_name") or "").strip(),
                "published_at": str(item.get("published_at") or "").strip(),
                "content": content,
            }
        )
    return comments


def normalize_platform(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text or "xueqiu"


def normalize_extracted_post(
    payload: dict[str, Any],
    target_date: date,
    author_name: str,
    *,
    date_filter: str = "target-date",
) -> PostRecord:
    title = str(payload.get("title") or "").strip()
    published_at_raw = str(payload.get("published_at") or payload.get("publish_time") or "").strip()
    url = str(payload.get("url") or "").strip()
    content = str(payload.get("content") or "").strip()
    record_author = str(payload.get("author_name") or author_name).strip()
    platform = normalize_platform(payload.get("platform"))

    if not title:
        raise ValueError("title is required")
    if not published_at_raw:
        raise ValueError("published_at is required")
    if not url:
        raise ValueError("url is required")
    if not content:
        raise ValueError("content is required")
    if not record_author:
        raise ValueError("author_name is required")

    published_date, publish_time = parse_publish_datetime(published_at_raw, target_date)
    if published_date is None:
        raise ValueError(f"发布时间无法识别: {published_at_raw}")
    if date_filter == "target-date" and published_date != target_date:
        raise NonTargetDateError(f"帖子不属于目标日期: {published_date.isoformat()}")

    content_id = str(payload.get("content_id") or "").strip() or extract_content_id_from_url(url)
    return PostRecord(
        content_id=content_id,
        title=title,
        publish_time=publish_time,
        publish_date=published_date.isoformat(),
        url=url,
        author_name=record_author,
        platform=platform,
        content=content,
        author_comments=normalize_author_comments(payload),
        fetched_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
    )


def build_result_paths(
    output_root: Path,
    author_name: str,
    target_date: date,
    *,
    layout: str = "date-author",
) -> tuple[Path, Path]:
    date_root = output_root / target_date.strftime("%Y%m%d")
    result_dir = date_root if layout == "author-root-date" else date_root / sanitize_name(author_name)
    return result_dir, result_dir / "task.log"


def make_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def load_existing_keys(result_dir: Path) -> set[str]:
    keys: set[str] = set()
    if not result_dir.exists():
        return keys
    for path in result_dir.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith("内容ID：") or line.startswith("原始链接："):
                _, _, value = line.partition("：")
                keys.add(value.strip())
    return keys


def format_author_comments(comments: list[dict[str, str]]) -> list[str]:
    if not comments:
        return []

    lines = ["", "作者评论："]
    for index, comment in enumerate(comments, start=1):
        meta_parts = [part for part in (comment.get("published_at", "").strip(), comment.get("author_name", "").strip()) if part]
        prefix = f"{index}. "
        if meta_parts:
            prefix += f"[{' | '.join(meta_parts)}] "
        lines.append(f"{prefix}{comment.get('content', '').strip()}")
    return lines


def read_json_file(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    return payload if isinstance(payload, dict) else fallback


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_day_state(result_dir: Path, author_name: str, account_url: str, target_date: date) -> dict[str, Any]:
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "processing").mkdir(exist_ok=True)
    state_file = result_dir / "state.json"
    fallback = {
        "account": author_name,
        "account_url": account_url,
        "task_date": target_date.strftime("%Y%m%d"),
        "start_time": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "end_time": None,
        "scan_round": 1,
        "success_count": 0,
        "failure_count": 0,
        "log_file": str(result_dir / "task.log"),
        "result_dir": str(result_dir),
        "state_file": str(state_file),
        "processed_items": {},
        "events": [],
    }
    state = read_json_file(state_file, fallback)
    state.setdefault("processed_items", {})
    state.setdefault("events", [])
    state["account"] = author_name
    state["account_url"] = account_url
    state["task_date"] = target_date.strftime("%Y%m%d")
    state["log_file"] = str(result_dir / "task.log")
    state["result_dir"] = str(result_dir)
    state["state_file"] = str(state_file)
    write_json_file(state_file, state)
    return state


def update_day_state(result_dir: Path, state: dict[str, Any], record: PostRecord, file_path: Path) -> None:
    item_key = record.content_id or record.url
    state.setdefault("processed_items", {})[item_key] = {
        "source_id": record.content_id,
        "title": record.title,
        "published_at": record.publish_time,
        "url": record.url,
        "platform": record.platform,
        "file_path": str(file_path),
        "saved_at": record.fetched_at,
    }
    state["success_count"] = int(state.get("success_count") or 0) + 1
    state.setdefault("events", []).append(
        {
            "type": "item_saved",
            "time": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "item_key": item_key,
            "file_path": str(file_path),
        }
    )
    write_json_file(result_dir / "state.json", state)


def append_processing_payload(result_dir: Path, payload: dict[str, Any]) -> None:
    processing_dir = result_dir / "processing"
    processing_dir.mkdir(parents=True, exist_ok=True)
    output_file = processing_dir / "column-posts.json"
    existing: list[dict[str, Any]] = []
    if output_file.exists():
        try:
            loaded = json.loads(output_file.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = [item for item in loaded if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            existing = []

    payload_url = str(payload.get("url") or "").strip()
    if payload_url and any(str(item.get("url") or "").strip() == payload_url for item in existing):
        return
    existing.append(payload)
    output_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def close_logger_handlers(logger: Any) -> None:
    for handler in list(getattr(logger, "handlers", [])):
        logger.removeHandler(handler)
        handler.close()


def save_posts_to_files(records: list[PostRecord], result_dir: Path, logger: Any) -> list[Path]:
    saved_paths: list[Path] = []
    result_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        timestamp_part = record.publish_time[11:19].replace(":", "") if len(record.publish_time) >= 19 else "000000"
        filename = f"{timestamp_part}_{slugify_filename(record.title)}_{record.content_id[:8]}.md"
        file_path = make_unique_path(result_dir / filename)
        body = "\n".join(
            [
                f"标题：{record.title}",
                f"内容ID：{record.content_id}",
                f"发布时间：{record.publish_time}",
                f"发布日期：{record.publish_date}",
                f"原始链接：{record.url}",
                f"作者名称：{record.author_name}",
                f"平台：{record.platform}",
                f"抓取时间：{record.fetched_at}",
                "",
                "正文：",
                record.content,
                *format_author_comments(record.author_comments),
            ]
        )
        file_path.write_text(body + "\n", encoding="utf-8")
        saved_paths.append(file_path)
        write_log(logger, "info", f"保存成功: {file_path}")
    return saved_paths


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


def process_extracted_posts(args: argparse.Namespace) -> TaskSummary:
    target_date = parse_target_date(args.date)
    output_root = resolve_output_root(args.output_dir)
    input_items = load_input_items(args.input_file)
    author_name = derive_author_name(args.author_name, args.account_url, input_items)
    date_source = getattr(args, "date_source", "target")
    date_filter = getattr(args, "date_filter", "target-date")
    layout = getattr(args, "layout", "date-author")
    account_url = str(getattr(args, "account_url", "") or "")
    default_result_dir, default_log_file = build_result_paths(output_root, author_name, target_date, layout=layout)

    summary = TaskSummary(
        account_url=account_url,
        target_date=target_date.isoformat(),
        author_name=author_name,
        candidate_count=len(input_items),
        matched_count=0,
        skipped_count=0,
        success_count=0,
        failure_count=0,
        result_dir=str(default_result_dir),
        log_file=str(default_log_file),
    )

    loggers: dict[Path, Any] = {}
    logged_starts: set[Path] = set()
    saved_keys_by_dir: dict[Path, set[str]] = {}

    def logger_for(log_file: Path) -> Any:
        if log_file not in loggers:
            loggers[log_file] = init_logger(name=f"content_task.{abs(hash(str(log_file)))}", log_file=log_file)
        return loggers[log_file]

    try:
        for payload in input_items:
            try:
                record = normalize_extracted_post(payload, target_date, author_name, date_filter=date_filter)
            except NonTargetDateError as exc:
                summary.skipped_count += 1
                logger = logger_for(default_log_file)
                write_log(logger, "info", f"跳过非目标日期内容: {exc}")
                continue
            except Exception as exc:
                summary.failure_count += 1
                summary.failures.append(str(exc))
                logger = logger_for(default_log_file)
                write_log(logger, "error", f"输入记录无效: {exc}")
                continue

            record_date = datetime.strptime(record.publish_date, "%Y-%m-%d").date() if date_source == "post" else target_date
            result_dir, log_file = build_result_paths(output_root, author_name, record_date, layout=layout)
            logger = logger_for(log_file)
            if log_file not in logged_starts:
                write_log(
                    logger,
                    "info",
                    f"开始处理已提取帖子 input_file={args.input_file} author={author_name} target_date={record_date.isoformat()}",
                )
                logged_starts.add(log_file)

            day_state = ensure_day_state(result_dir, author_name, account_url, record_date)
            append_processing_payload(result_dir, payload)
            if result_dir not in saved_keys_by_dir:
                saved_keys_by_dir[result_dir] = load_existing_keys(result_dir)
                saved_keys_by_dir[result_dir].update(day_state.get("processed_items", {}).keys())
            saved_keys = saved_keys_by_dir[result_dir]

            summary.matched_count += 1
            dedupe_key = record.content_id or record.url
            if dedupe_key in saved_keys or record.url in saved_keys:
                summary.skipped_count += 1
                write_log(logger, "info", f"跳过重复帖子: {record.url}")
                continue

            saved_paths = save_posts_to_files([record], result_dir, logger)
            for file_path in saved_paths:
                update_day_state(result_dir, day_state, record, file_path)
            summary.success_count += len(saved_paths)
            saved_keys.add(dedupe_key)
            saved_keys.add(record.url)

        if summary.success_count == 0 and summary.failure_count == 0:
            logger = logger_for(default_log_file)
            write_log(logger, "warning", "没有新的目标日期帖子需要保存。")
    finally:
        for logger in loggers.values():
            close_logger_handlers(logger)

    return summary


def main() -> int:
    args = parse_args()
    summary = process_extracted_posts(args)
    print_task_summary(summary)
    return 0 if summary.failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
