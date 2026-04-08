#!/usr/bin/env python3

from __future__ import annotations

import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_EXTEND_FILE = Path(__file__).resolve().parent.parent / "EXTEND.md"


def ensure_dir(path: str | os.PathLike[str]) -> Path:
    directory = Path(path).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def sanitize_filename(name: str, max_length: int = 80, replacement: str = "_") -> str:
    cleaned = (name or "").strip()
    cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1F]+", replacement, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(rf"{re.escape(replacement)}+", replacement, cleaned)
    cleaned = cleaned.strip(" ._")
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_length].rstrip(" ._") or "untitled"


def read_preferred_output_root(extend_file: str | os.PathLike[str] | None = None) -> str | None:
    target = Path(extend_file).expanduser().resolve() if extend_file else DEFAULT_EXTEND_FILE
    if not target.exists():
        return None

    text = target.read_text(encoding="utf-8")
    match = re.search(r"preferred output root:\s*`([^`]+)`", text)
    if not match:
        return None

    value = match.group(1).strip()
    return value or None


def resolve_output_root(
    output_root: str | os.PathLike[str] | None = None,
    *,
    extend_file: str | os.PathLike[str] | None = None,
) -> Path:
    chosen = str(output_root).strip() if output_root is not None and str(output_root).strip() else None
    if not chosen:
        chosen = read_preferred_output_root(extend_file)
    if not chosen:
        raise ValueError("未提供输出目录，且 EXTEND.md 中未配置 preferred output root")
    return ensure_dir(chosen)


def init_logger(
    name: str = "xueqiu_utils",
    log_file: str | os.PathLike[str] | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    has_console = any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in logger.handlers
    )
    if not has_console:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        console.setLevel(level)
        logger.addHandler(console)

    if log_file:
        target = ensure_dir(Path(log_file).expanduser().resolve().parent) / Path(log_file).name
        has_file = any(
            isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == target
            for handler in logger.handlers
        )
        if not has_file:
            file_handler = logging.FileHandler(target, encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            logger.addHandler(file_handler)

    return logger


def write_log(logger: logging.Logger | None, level: str, message: str) -> None:
    if logger is None:
        logger = init_logger()
    log_method = getattr(logger, level.lower(), None)
    if not callable(log_method):
        log_method = logger.info
    log_method(message)


def wait_for_condition(
    check_fn: Any,
    timeout_seconds: float = 10.0,
    interval_seconds: float = 0.5,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if check_fn():
                return True
        except Exception:
            pass
        time.sleep(interval_seconds)
    return False


__all__ = [
    "ensure_dir",
    "init_logger",
    "read_preferred_output_root",
    "resolve_output_root",
    "sanitize_filename",
    "wait_for_condition",
    "write_log",
]
