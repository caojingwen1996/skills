# File Layout

This file describes naming and per-file structure inside the configured output root declared in `EXTEND.md`.

## Daily raw artifacts

For a task started on `2026-03-25` for account `某博主`, the workflow writes:

- date root: `20260325/`
- author directory: `20260325/某博主/`
- log file: `20260325/某博主/task.log`
- state file: `20260325/某博主/state.json`

The raw `.txt` files also live directly under `20260325/某博主/`.

## Raw result file format

Each saved raw result file is a UTF-8 `.txt` file with at least:

```text
标题：...
发布时间：...
原始链接：...

正文：
...
```

Additional metadata may be included, but downstream summary generation must only rely on fields that are actually present in the saved file.

## State file highlights

The JSON state file tracks:

- `account`
- `task_date`
- `start_time`
- `end_time`
- `scan_round`
- `success_count`
- `failure_count`
- `chrome_profile`
- `log_file`
- `result_dir`
- `state_file`
- `processed_items`

`processed_items` is the primary deduplication source of truth for the current day when the state file is present.
