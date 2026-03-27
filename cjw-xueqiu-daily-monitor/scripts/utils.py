#!/usr/bin/env python3

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, Playwright, TimeoutError, sync_playwright

XUEQIU_HOME_URL = "https://xueqiu.com/"
DEFAULT_PROFILE_ENV = "XUEQIU_PROFILE_DIR"
DEFAULT_CHROME_ENV = "CHROME_PATH"
DEFAULT_WAIT_TIMEOUT_MS = 60_000
DEFAULT_LOGIN_WAIT_SECONDS = 300


class BrowserLaunchError(RuntimeError):
    """Raised when Chrome or the persistent Playwright context cannot be started."""


class LoginRequiredError(RuntimeError):
    """Raised when a login is required but cannot be completed automatically."""


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


def get_default_profile_dir(profile_dir: str | os.PathLike[str] | None = None) -> str:
    chosen = profile_dir or os.environ.get(DEFAULT_PROFILE_ENV)
    if chosen:
        return str(ensure_dir(chosen))
    # Keep the default profile local to the current task directory so a stale
    # global Chrome profile does not poison every run.
    default_path = Path.cwd() / ".xueqiu-chrome-profile"
    return str(ensure_dir(default_path))


def _common_chrome_candidates() -> list[str]:
    home = Path.home()
    system = platform.system().lower()
    candidates: list[str] = []

    if system == "darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                str(home / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                str(home / "Applications/Chromium.app/Contents/MacOS/Chromium"),
            ]
        )
    elif system == "windows":
        local = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("PROGRAMFILES", "")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
        candidates.extend(
            [
                os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(local, "Chromium", "Application", "chrome.exe"),
                os.path.join(program_files, "Chromium", "Application", "chrome.exe"),
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium",
            ]
        )

    for command in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        found = shutil.which(command)
        if found:
            candidates.append(found)
    return candidates


def get_chrome_executable(chrome_path: str | os.PathLike[str] | None = None) -> str:
    explicit = chrome_path or os.environ.get(DEFAULT_CHROME_ENV)
    if explicit:
        resolved = Path(explicit).expanduser()
        if resolved.exists():
            return str(resolved.resolve())
        raise FileNotFoundError(f"Chrome 可执行文件不存在: {resolved}")

    for candidate in _common_chrome_candidates():
        if candidate and Path(candidate).exists():
            return str(Path(candidate).resolve())
    raise FileNotFoundError(
        "未找到 Chrome/Chromium 可执行文件。请通过参数 chrome_path 或环境变量 CHROME_PATH 显式提供。"
    )


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


def launch_persistent_browser(
    profile_dir: str | os.PathLike[str] | None = None,
    headless: bool = False,
    chrome_path: str | os.PathLike[str] | None = None,
    start_url: str | None = XUEQIU_HOME_URL,
    viewport: dict[str, int] | None = None,
    slow_mo: int = 0,
    logger: logging.Logger | None = None,
    timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
) -> dict[str, Any]:
    logger = logger or init_logger()
    profile_path = get_default_profile_dir(profile_dir)
    executable_path = get_chrome_executable(chrome_path)
    write_log(
        logger,
        "info",
        f"启动持久化浏览器 profile={profile_path} headless={headless} chrome={executable_path}",
    )

    playwright: Playwright | None = None
    try:
        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            executable_path=executable_path,
            channel=None,
            headless=headless,
            viewport=viewport,
            accept_downloads=False,
            slow_mo=slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-default-browser-check",
                "--disable-popup-blocking",
            ],
        )
        context.set_default_timeout(timeout_ms)
        context.set_default_navigation_timeout(timeout_ms)

        page = context.pages[0] if context.pages else context.new_page()
        if start_url:
            safe_open(page, start_url, timeout=timeout_ms, logger=logger)

        return {
            "playwright": playwright,
            "browser": getattr(context, "browser", None),
            "context": context,
            "page": page,
            "profile_dir": profile_path,
            "chrome_path": executable_path,
            "headless": headless,
        }
    except Exception as exc:
        error_text = str(exc)
        profile_hint = (
            f"当前 profile={profile_path}。可尝试删除该目录后重试，"
            "或通过 --profile-dir 指向一个全新的 profile 目录。"
        )
        if any(
            keyword in error_text
            for keyword in (
                "Browser.getWindowForTarget",
                "Failed to create a ProcessSingleton",
                "Failed to decrypt token",
                "SingletonLock",
            )
        ):
            raise BrowserLaunchError(f"浏览器启动失败，疑似 profile 状态损坏或仍被占用。{profile_hint} 原始错误: {exc}") from exc
        raise BrowserLaunchError(f"浏览器启动失败: {exc}") from exc
    finally:
        if "context" not in locals() and playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass


def is_logged_in(page: Page) -> bool:
    if page is None:
        return False

    checks = [
        "text=登录",
        "text=注册",
        "text=立即登录",
        "text=手机号登录",
        "[data-testid='login-button']",
        "a[href*='/login']",
    ]
    try:
        for selector in checks:
            locator = page.locator(selector)
            if locator.count() > 0 and locator.first.is_visible():
                return False
    except Exception:
        pass

    try:
        cookies = page.context.cookies()
        cookie_names = {cookie["name"] for cookie in cookies}
        if {"xq_a_token", "xqat"}.intersection(cookie_names):
            return True
    except Exception:
        pass

    try:
        body_text = page.locator("body").inner_text(timeout=5_000)
    except Exception:
        body_text = ""
    suspicious = ("登录后即可查看", "登录", "注册", "手机号登录")
    if any(text in body_text for text in suspicious):
        return False
    return True


def ensure_login(
    page: Page,
    account_url: str | None = None,
    login_url: str = XUEQIU_HOME_URL,
    headless: bool | None = None,
    prompt: str | None = None,
    wait_seconds: int = DEFAULT_LOGIN_WAIT_SECONDS,
    poll_interval: float = 2.0,
    logger: logging.Logger | None = None,
) -> bool:
    logger = logger or init_logger()
    if is_logged_in(page):
        write_log(logger, "info", "检测到当前已登录，复用现有 session。")
        return True

    actual_headless = bool(headless)
    if actual_headless:
        raise LoginRequiredError("当前为 headless 模式且检测到未登录。请先用有头模式人工登录一次。")

    target_url = account_url or login_url
    write_log(logger, "warning", f"检测到未登录，准备打开页面等待人工登录: {target_url}")
    safe_open(page, target_url, logger=logger)

    message = prompt or (
        "请在打开的浏览器中手动完成雪球登录，登录成功后回到终端按回车继续。"
    )
    print(message)
    input()

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            pass
        if is_logged_in(page):
            write_log(logger, "info", "人工登录确认成功，后续将复用持久化 session。")
            return True
        time.sleep(poll_interval)

    raise LoginRequiredError("等待人工登录超时，未检测到有效登录状态。")


def safe_open(
    page: Page,
    url: str,
    wait_until: str = "domcontentloaded",
    timeout: int = DEFAULT_WAIT_TIMEOUT_MS,
    retries: int = 2,
    retry_delay: float = 1.5,
    logger: logging.Logger | None = None,
) -> Page:
    logger = logger or init_logger()
    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            write_log(logger, "info", f"打开页面 attempt={attempt} url={url}")
            page.goto(url, wait_until=wait_until, timeout=timeout)
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
            return page
        except Exception as exc:
            last_error = exc
            write_log(logger, "warning", f"页面打开失败 attempt={attempt} url={url} error={exc}")
            if attempt <= retries:
                time.sleep(retry_delay)
    raise RuntimeError(f"页面加载失败: {url}; error={last_error}") from last_error


def safe_text(
    target: Page | BrowserContext,
    selector: str,
    default: str = "",
    timeout: int = 5_000,
) -> str:
    try:
        locator = target.locator(selector)  # type: ignore[union-attr]
        if locator.count() == 0:
            return default
        return (locator.first.inner_text(timeout=timeout) or "").strip()
    except Exception:
        return default


def safe_attr(
    target: Page | BrowserContext,
    selector: str,
    attr_name: str,
    default: str = "",
    timeout: int = 5_000,
) -> str:
    try:
        locator = target.locator(selector)  # type: ignore[union-attr]
        if locator.count() == 0:
            return default
        value = locator.first.get_attribute(attr_name, timeout=timeout)
        return (value or default).strip()
    except Exception:
        return default


def safe_click(
    page: Page,
    selector: str,
    timeout: int = 5_000,
    retries: int = 1,
    logger: logging.Logger | None = None,
) -> bool:
    logger = logger or init_logger()
    for attempt in range(1, retries + 2):
        try:
            locator = page.locator(selector)
            if locator.count() == 0:
                return False
            locator.first.click(timeout=timeout)
            return True
        except Exception as exc:
            write_log(logger, "warning", f"点击失败 attempt={attempt} selector={selector} error={exc}")
            time.sleep(0.8)
    return False


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


def scroll_page(
    page: Page,
    step: int = 1200,
    times: int = 1,
    pause: float = 1.0,
    logger: logging.Logger | None = None,
) -> None:
    logger = logger or init_logger()
    for index in range(times):
        try:
            page.mouse.wheel(0, step)
        except Exception:
            page.evaluate("(delta) => window.scrollBy(0, delta)", step)
        write_log(logger, "info", f"页面滚动 index={index + 1} step={step}")
        time.sleep(pause)


def close_browser(session: Any, logger: logging.Logger | None = None) -> None:
    logger = logger or init_logger()
    playwright: Playwright | None = None
    context: BrowserContext | None = None

    if isinstance(session, dict):
        playwright = session.get("playwright")
        context = session.get("context")
    elif isinstance(session, BrowserContext):
        context = session
    elif isinstance(session, Playwright):
        playwright = session
    else:
        context = getattr(session, "context", None) if not isinstance(session, Page) else session.context
        playwright = getattr(session, "playwright", None)

    try:
        if context is not None:
            context.close()
            write_log(logger, "info", "浏览器上下文已关闭。")
    finally:
        if playwright is not None:
            playwright.stop()
            write_log(logger, "info", "Playwright 已停止。")


__all__ = [
    "BrowserLaunchError",
    "LoginRequiredError",
    "close_browser",
    "ensure_dir",
    "ensure_login",
    "get_chrome_executable",
    "get_default_profile_dir",
    "init_logger",
    "is_logged_in",
    "launch_persistent_browser",
    "safe_attr",
    "safe_click",
    "safe_open",
    "safe_text",
    "sanitize_filename",
    "scroll_page",
    "wait_for_condition",
    "write_log",
]
