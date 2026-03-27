# File Layout

This file describes naming and per-file structure inside the selected output root.

## Daily raw artifacts

For a task started on `2026-03-25` for account `某博主`, the workflow writes:

- log file: `某博主_20260325.log`
- result directory: `某博主_20260325/`
- state file: `某博主_20260325.state.json`

All three live directly under the selected output root.

## Raw result file format

Each saved raw result file is a UTF-8 `.txt` file with at least:

```text
标题：...
内容ID：...
发布时间：...
发布日期：...
原始链接：...
作者名称：...
抓取时间：...

正文：
...
```

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

`processed_items` is the deduplication source of truth for the current day.
