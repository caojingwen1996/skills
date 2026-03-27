# Usage

This file documents the exact script entrypoints for the current workflow.

## Recommended repo-local paths

For this repository, the typical local paths are:

- output root: `./scripts/output`
- Chrome profile: `./scripts/.xueqiu-chrome-profile`

Use the same output root for capture and summary on the same task date.

## Capture commands

### Single-account capture

```bash
python3 scripts/content_task.py \
  --account-url https://xueqiu.com/u/9838764557 \
  --date 2026-03-25 \
  --profile-dir ./scripts/.xueqiu-chrome-profile \
  --output-dir ./scripts/output
```

Optional:

- add `--headless` to run in headless mode
- omit `--date` to default to today

### What `content_task.py` accepts

- `--account-url` required
- `--date` optional, format `YYYY-MM-DD`
- `--profile-dir` optional
- `--output-dir` required
- `--headless` optional flag

## Summary command

```bash
python3 scripts/daily_summary.py \
  --date 2026-03-25 \
  --output-dir ./scripts/output
```

### What `daily_summary.py` accepts

- `--date` required, format `YYYY-MM-DD`
- `--output-dir` optional, defaults to `./output`

## State utility commands

`scripts/task_store.py` manages state, deduplication, and logging for one account-date task.

### Initialize or resume a day task

```bash
python3 scripts/task_store.py init \
  --account "闵行一霸" \
  --start-time "2026-03-25 09:30:00" \
  --output-root ./scripts/output \
  --chrome-profile ./scripts/.xueqiu-chrome-profile
```

### Start a scan round

```bash
python3 scripts/task_store.py begin-scan \
  --state-file ./scripts/output/闵行一霸_20260325.state.json \
  --note "开始扫描"
```

### Check whether an item should be processed

```bash
python3 scripts/task_store.py should-process \
  --state-file ./scripts/output/闵行一霸_20260325.state.json \
  --title "示例标题" \
  --published-at "2026-03-25 15:08:00" \
  --url https://xueqiu.com/u/9838764557/381078922
```

### Save an item

```bash
python3 scripts/task_store.py save-item \
  --state-file ./scripts/output/闵行一霸_20260325.state.json \
  --title "示例标题" \
  --published-at "2026-03-25 15:08:00" \
  --url https://xueqiu.com/u/9838764557/381078922 \
  --content-file ./tmp/post.txt
```

### Record a failure

```bash
python3 scripts/task_store.py record-failure \
  --state-file ./scripts/output/闵行一霸_20260325.state.json \
  --kind save_failed \
  --message "Failed to persist extracted post"
```

### Finish a day task

```bash
python3 scripts/task_store.py finish \
  --state-file ./scripts/output/闵行一霸_20260325.state.json
```

## Responsibility map

- `scripts/content_task.py`: capture raw posts for one account and one date
- `scripts/task_store.py`: state file, deduplication, scan rounds, logs
- `scripts/daily_summary.py`: build intermediate artifacts and final Markdown summaries from raw files
