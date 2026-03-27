#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_datetime(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("empty datetime")
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"unsupported datetime format: {value}")


def now_text() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def sanitize_name(value: str) -> str:
    value = value.strip()
    if not value:
        return "unknown"
    sanitized = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value, flags=re.UNICODE)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "unknown"


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def write_log(log_file: Path, level: str, round_id: int, message: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    line = f"{now_text()} [{level}] [round:{round_id}] {message}\n"
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line)


def build_item_key(
    source_id: str | None, url: str, title: str, published_at: str
) -> str:
    if source_id and source_id.strip():
        return source_id.strip()
    raw = "\n".join([url.strip(), title.strip(), published_at.strip()])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def ensure_same_day(task_date: str, published_at: datetime) -> bool:
    return published_at.strftime("%Y%m%d") == task_date


def read_content(args: argparse.Namespace) -> str:
    direct = (args.content or "").strip()
    if direct:
        return direct
    if args.content_file:
        return Path(args.content_file).read_text(encoding="utf-8").strip()
    raise ValueError("content is required via --content or --content-file")


def append_event(state: dict[str, Any], event_type: str, payload: dict[str, Any]) -> None:
    state.setdefault("events", []).append(
        {
            "type": event_type,
            "time": now_text(),
            **payload,
        }
    )


def build_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "account": state["account"],
        "start_time": state["start_time"],
        "end_time": state.get("end_time"),
        "scan_rounds": state["scan_round"],
        "success_count": state["success_count"],
        "failure_count": state["failure_count"],
        "log_file": state["log_file"],
        "result_dir": state["result_dir"],
        "state_file": state["state_file"],
    }


def init_command(args: argparse.Namespace) -> int:
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    start_time = parse_datetime(args.start_time)
    task_date = start_time.strftime("%Y%m%d")
    account = args.account.strip()
    account_slug = sanitize_name(account)
    base_name = f"{account_slug}_{task_date}"

    log_file = output_root / f"{base_name}.log"
    result_dir = output_root / base_name
    state_file = output_root / f"{base_name}.state.json"

    if state_file.exists():
        if not args.resume_existing:
            raise SystemExit(
                f"state file already exists: {state_file}. Use --resume-existing to reuse it."
            )
        state = load_state(state_file)
        write_log(Path(state["log_file"]), "INFO", state["scan_round"], "恢复既有当日任务状态")
        print(json.dumps(build_summary(state), ensure_ascii=False, indent=2))
        return 0

    result_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "account": account,
        "task_date": task_date,
        "start_time": start_time.isoformat(sep=" ", timespec="seconds"),
        "end_time": None,
        "scan_interval_minutes": 60,
        "chrome_profile": args.chrome_profile,
        "scan_round": 0,
        "success_count": 0,
        "failure_count": 0,
        "log_file": str(log_file),
        "result_dir": str(result_dir),
        "state_file": str(state_file),
        "processed_items": {},
        "events": [],
    }
    append_event(state, "task_started", {"message": "任务启动"})
    save_state(state_file, state)
    write_log(log_file, "INFO", 0, f"任务启动 account={account} start_time={state['start_time']}")
    print(json.dumps(build_summary(state), ensure_ascii=False, indent=2))
    return 0


def begin_scan_command(args: argparse.Namespace) -> int:
    state_file = Path(args.state_file).expanduser().resolve()
    state = load_state(state_file)
    state["scan_round"] += 1
    round_id = state["scan_round"]
    note = args.note.strip() if args.note else "开始扫描"
    append_event(state, "scan_started", {"round": round_id, "message": note})
    save_state(state_file, state)
    write_log(Path(state["log_file"]), "INFO", round_id, note)
    print(json.dumps({"scan_round": round_id, "message": note}, ensure_ascii=False, indent=2))
    return 0


def should_process_command(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state_file).expanduser().resolve())
    published_at = parse_datetime(args.published_at)
    item_key = build_item_key(args.source_id, args.url, args.title, args.published_at)
    round_id = state["scan_round"]

    if not ensure_same_day(state["task_date"], published_at):
        result = {"should_process": False, "reason": "not_today", "item_key": item_key}
        write_log(Path(state["log_file"]), "INFO", round_id, f"跳过非当日内容 item_key={item_key}")
    elif item_key in state["processed_items"]:
        result = {"should_process": False, "reason": "already_processed", "item_key": item_key}
        write_log(Path(state["log_file"]), "INFO", round_id, f"跳过已处理内容 item_key={item_key}")
    else:
        result = {"should_process": True, "reason": "new_item", "item_key": item_key}
        write_log(Path(state["log_file"]), "INFO", round_id, f"发现新内容 item_key={item_key}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def save_item_command(args: argparse.Namespace) -> int:
    state_file = Path(args.state_file).expanduser().resolve()
    state = load_state(state_file)
    published_at = parse_datetime(args.published_at)
    if not ensure_same_day(state["task_date"], published_at):
        raise SystemExit("refusing to save non-task-day content")

    title = args.title.strip()
    url = args.url.strip()
    content = read_content(args)
    if not title or not url or not content:
        raise SystemExit("title, url, and content must all be non-empty")

    item_key = build_item_key(args.source_id, url, title, args.published_at)
    round_id = state["scan_round"]
    processed_items = state["processed_items"]

    if item_key in processed_items:
        existing = processed_items[item_key]
        write_log(Path(state["log_file"]), "INFO", round_id, f"重复保存已拦截 item_key={item_key}")
        print(
            json.dumps(
                {
                    "saved": False,
                    "reason": "already_processed",
                    "item_key": item_key,
                    "file_path": existing["file_path"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    title_slug = sanitize_name(title)[:48]
    filename = f"{published_at.strftime('%H%M%S')}_{title_slug}_{item_key[:8]}.txt"
    result_path = Path(state["result_dir"]) / filename

    body = "\n".join(
        [
            f"标题：{title}",
            f"发布时间：{published_at.isoformat(sep=' ', timespec='seconds')}",
            f"原始链接：{url}",
            "",
            "正文：",
            content,
            "",
        ]
    )
    atomic_write_text(result_path, body)

    processed_items[item_key] = {
        "source_id": args.source_id,
        "title": title,
        "published_at": published_at.isoformat(sep=" ", timespec="seconds"),
        "url": url,
        "file_path": str(result_path),
        "saved_at": now_text(),
    }
    state["success_count"] += 1
    append_event(
        state,
        "item_saved",
        {
            "round": round_id,
            "item_key": item_key,
            "file_path": str(result_path),
        },
    )
    save_state(state_file, state)
    write_log(
        Path(state["log_file"]),
        "INFO",
        round_id,
        f"保存抓取结果 item_key={item_key} file={result_path}",
    )
    print(
        json.dumps(
            {
                "saved": True,
                "item_key": item_key,
                "file_path": str(result_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def record_failure_command(args: argparse.Namespace) -> int:
    state_file = Path(args.state_file).expanduser().resolve()
    state = load_state(state_file)
    state["failure_count"] += 1
    round_id = state["scan_round"]
    append_event(
        state,
        "failure",
        {
            "round": round_id,
            "kind": args.kind,
            "message": args.message,
        },
    )
    save_state(state_file, state)
    write_log(
        Path(state["log_file"]),
        "ERROR",
        round_id,
        f"异常 kind={args.kind} message={args.message}",
    )
    print(
        json.dumps(
            {
                "recorded": True,
                "failure_count": state["failure_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def log_command(args: argparse.Namespace) -> int:
    state = load_state(Path(args.state_file).expanduser().resolve())
    round_id = args.round if args.round is not None else state["scan_round"]
    write_log(Path(state["log_file"]), args.level.upper(), round_id, args.message)
    print(
        json.dumps(
            {"logged": True, "level": args.level.upper(), "round": round_id},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def finish_command(args: argparse.Namespace) -> int:
    state_file = Path(args.state_file).expanduser().resolve()
    state = load_state(state_file)
    end_time = parse_datetime(args.end_time) if args.end_time else datetime.now()
    state["end_time"] = end_time.isoformat(sep=" ", timespec="seconds")
    append_event(state, "task_finished", {"message": "任务结束"})
    save_state(state_file, state)

    summary = build_summary(state)
    write_log(
        Path(state["log_file"]),
        "INFO",
        state["scan_round"],
        "任务结束 "
        f"success={state['success_count']} failure={state['failure_count']} "
        f"log={state['log_file']} result_dir={state['result_dir']}",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="State and file manager for cjw-xueqiu-daily-monitor.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--account", required=True)
    init_parser.add_argument("--start-time", required=True)
    init_parser.add_argument("--output-root", default=".")
    init_parser.add_argument("--chrome-profile", default="./.xueqiu-chrome-profile")
    init_parser.add_argument("--resume-existing", action="store_true")
    init_parser.set_defaults(func=init_command)

    scan_parser = subparsers.add_parser("begin-scan")
    scan_parser.add_argument("--state-file", required=True)
    scan_parser.add_argument("--note")
    scan_parser.set_defaults(func=begin_scan_command)

    should_parser = subparsers.add_parser("should-process")
    should_parser.add_argument("--state-file", required=True)
    should_parser.add_argument("--source-id")
    should_parser.add_argument("--title", required=True)
    should_parser.add_argument("--published-at", required=True)
    should_parser.add_argument("--url", required=True)
    should_parser.set_defaults(func=should_process_command)

    save_parser = subparsers.add_parser("save-item")
    save_parser.add_argument("--state-file", required=True)
    save_parser.add_argument("--source-id")
    save_parser.add_argument("--title", required=True)
    save_parser.add_argument("--published-at", required=True)
    save_parser.add_argument("--url", required=True)
    save_group = save_parser.add_mutually_exclusive_group(required=True)
    save_group.add_argument("--content")
    save_group.add_argument("--content-file")
    save_parser.set_defaults(func=save_item_command)

    failure_parser = subparsers.add_parser("record-failure")
    failure_parser.add_argument("--state-file", required=True)
    failure_parser.add_argument("--kind", required=True)
    failure_parser.add_argument("--message", required=True)
    failure_parser.set_defaults(func=record_failure_command)

    log_parser = subparsers.add_parser("log")
    log_parser.add_argument("--state-file", required=True)
    log_parser.add_argument("--message", required=True)
    log_parser.add_argument("--level", default="INFO")
    log_parser.add_argument("--round", type=int)
    log_parser.set_defaults(func=log_command)

    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("--state-file", required=True)
    finish_parser.add_argument("--end-time")
    finish_parser.set_defaults(func=finish_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
