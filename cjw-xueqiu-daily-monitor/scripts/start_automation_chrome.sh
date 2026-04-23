#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_DIR="${XUEQIU_CHROME_PROFILE_DIR:-$SCRIPT_DIR/.xueqiu-chrome-profile}"
DEFAULT_DEBUG_PORT="9333"
DEBUG_PORT="${XUEQIU_CHROME_DEBUG_PORT:-$DEFAULT_DEBUG_PORT}"
DEBUG_HOST="${XUEQIU_CHROME_DEBUG_HOST:-127.0.0.1}"
START_URL="${XUEQIU_CHROME_START_URL:-https://xueqiu.com/}"
LOG_FILE="${XUEQIU_CHROME_LOG_FILE:-$SCRIPT_DIR/.xueqiu-automation-chrome.log}"
VERSION_URL="http://${DEBUG_HOST}:${DEBUG_PORT}/json/version"

app_bundle_for_binary() {
  local chrome_bin="$1"
  case "$chrome_bin" in
    *.app/Contents/MacOS/*)
      printf '%s\n' "${chrome_bin%/Contents/MacOS/*}"
      return 0
      ;;
  esac
  return 1
}

find_chrome_path() {
  if [[ -n "${CHROME_PATH:-}" ]]; then
    printf '%s\n' "$CHROME_PATH"
    return 0
  fi

  local candidates=(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
    "$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "$HOME/Applications/Chromium.app/Contents/MacOS/Chromium"
    "/usr/bin/google-chrome"
    "/usr/bin/google-chrome-stable"
    "/usr/bin/chromium"
    "/usr/bin/chromium-browser"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  if command -v google-chrome >/dev/null 2>&1; then
    command -v google-chrome
    return 0
  fi
  if command -v chromium >/dev/null 2>&1; then
    command -v chromium
    return 0
  fi
  if command -v chromium-browser >/dev/null 2>&1; then
    command -v chromium-browser
    return 0
  fi

  return 1
}

if curl -fsS "$VERSION_URL" >/dev/null 2>&1; then
  echo "Automation Chrome already running at $VERSION_URL"
  exit 0
fi

CHROME_BIN="$(find_chrome_path)" || {
  echo "Unable to find Chrome or Chromium executable." >&2
  exit 1
}

mkdir -p "$PROFILE_DIR"

CHROME_ARGS=(
  "--user-data-dir=$PROFILE_DIR"
  "--remote-debugging-port=$DEBUG_PORT"
  "--no-first-run"
  "--no-default-browser-check"
  "--disable-popup-blocking"
  "$START_URL"
)

CMD=()
if [[ "$(uname -s)" == "Darwin" ]]; then
  if APP_BUNDLE="$(app_bundle_for_binary "$CHROME_BIN")"; then
    CMD=(
      open
      -na
      "$APP_BUNDLE"
      --args
      "${CHROME_ARGS[@]}"
    )
  fi
fi

if [[ ${#CMD[@]} -eq 0 ]]; then
  CMD=(
    "$CHROME_BIN"
    "${CHROME_ARGS[@]}"
  )
fi

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  printf 'DRY RUN:'
  printf ' %q' "${CMD[@]}"
  printf '\n'
  exit 0
fi

nohup "${CMD[@]}" >"$LOG_FILE" 2>&1 &

for _ in $(seq 1 20); do
  if curl -fsS "$VERSION_URL" >/dev/null 2>&1; then
    echo "Automation Chrome started at $VERSION_URL"
    echo "Profile: $PROFILE_DIR"
    exit 0
  fi
  sleep 1
done

echo "Automation Chrome failed to start within timeout. Check $LOG_FILE" >&2
exit 1
