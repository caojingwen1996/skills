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
    parser = argparse.ArgumentParser(description="将已提取的雪球帖子写入日期目录下的原始文本文件。")
    parser.add_argument("--input-file", required=True, help="已提取帖子 JSON 文件，内容必须是数组")
    parser.add_argument("--author-name", help="作者名；未传时优先从 JSON 中读取")
    parser.add_argument("--account-url", help="账号主页链接，仅用于任务摘要")
    parser.add_argument("--date", help="目标日期，格式 YYYY-MM-DD，默认当天")
    parser.add_argument("--output-dir", help="输出根目录；未传时从 EXTEND.md 读取")
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
    return "xueqiu_account"


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


def normalize_extracted_post(payload: dict[str, Any], target_date: date, author_name: str) -> PostRecord:
    title = str(payload.get("title") or "").strip()
    published_at_raw = str(payload.get("published_at") or payload.get("publish_time") or "").strip()
    url = str(payload.get("url") or "").strip()
    content = str(payload.get("content") or "").strip()
    record_author = str(payload.get("author_name") or author_name).strip()

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
    if published_date != target_date:
        raise NonTargetDateError(f"帖子不属于目标日期: {published_date.isoformat()}")

    content_id = str(payload.get("content_id") or "").strip() or extract_content_id_from_url(url)

    return PostRecord(
        content_id=content_id,
        title=title,
        publish_time=publish_time,
        publish_date=published_date.isoformat(),
        url=url,
        author_name=record_author,
        content=content,
        fetched_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
    )


def build_result_paths(output_root: Path, author_name: str, target_date: date) -> tuple[Path, Path]:
    date_root = output_root / target_date.strftime("%Y%m%d")
    result_dir = date_root / sanitize_name(author_name)
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
    for path in result_dir.glob("*.txt"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith("内容ID：") or line.startswith("原始链接："):
                keys.add(line.split("：", 1)[1].strip())
    return keys


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


def process_extracted_posts(args: argparse.Namespace) -> TaskSummary:
    target_date = parse_target_date(args.date)
    output_root = resolve_output_root(args.output_dir)
    input_items = load_input_items(args.input_file)
    author_name = derive_author_name(args.author_name, args.account_url, input_items)
    result_dir, log_file = build_result_paths(output_root, author_name, target_date)
    logger = init_logger(name="content_task", log_file=log_file)

    summary = TaskSummary(
        account_url=str(getattr(args, "account_url", "") or ""),
        target_date=target_date.isoformat(),
        author_name=author_name,
        candidate_count=len(input_items),
        result_dir=str(result_dir),
        log_file=str(log_file),
    )

    write_log(
        logger,
        "info",
        f"开始处理已提取帖子 input_file={args.input_file} author={author_name} target_date={target_date.isoformat()}",
    )

    existing_keys = load_existing_keys(result_dir)
    saved_keys = set(existing_keys)

    for payload in input_items:
        try:
            record = normalize_extracted_post(payload, target_date, author_name)
        except NonTargetDateError as exc:
            summary.skipped_count += 1
            write_log(logger, "info", f"跳过非目标日期内容: {exc}")
            continue
        except Exception as exc:
            summary.failure_count += 1
            summary.failures.append(str(exc))
            write_log(logger, "error", f"输入记录无效: {exc}")
            continue

        summary.matched_count += 1
        dedupe_key = record.content_id or record.url
        if dedupe_key in saved_keys or record.url in saved_keys:
            summary.skipped_count += 1
            write_log(logger, "info", f"跳过重复帖子: {record.url}")
            continue

        summary.success_count += save_posts_to_files([record], result_dir, logger)
        saved_keys.add(dedupe_key)
        saved_keys.add(record.url)

    if summary.success_count == 0 and summary.failure_count == 0:
        write_log(logger, "warning", "没有新的目标日期帖子需要保存。")

    return summary


def main() -> int:
    args = parse_args()
    summary = process_extracted_posts(args)
    print_task_summary(summary)
    return 0 if summary.failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
