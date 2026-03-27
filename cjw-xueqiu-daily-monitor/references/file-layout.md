# File Layout

## Daily files

For a task started on `2026-03-25` for account `某博主`, the skill writes:

- log file: `某博主_20260325.log`
- result directory: `某博主_20260325/`
- state file: `某博主_20260325.state.json`

All three live under the selected `--output-root`.

## Result file format

Each saved result file is a UTF-8 `.txt` file with at least:

```text
标题：...
发布时间：...
原始链接：...

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
- `processed_items`

`processed_items` is the deduplication source of truth for the current day.
