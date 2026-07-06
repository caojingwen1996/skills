# File Layout

This file describes naming and per-file structure inside the configured output root declared in `EXTEND.md`.

## Daily raw artifacts

For a task started on `2026-03-25` for one author, the workflow writes:

- date root: `20260325/`
- author directory: `20260325/{author}/`
- log file: `20260325/{author}/task.log`
- state file: `20260325/{author}/state.json`

The raw `.md` files also live directly under `20260325/{author}/`.

## Raw result file format

Each saved raw result file is a UTF-8 Markdown document with at least:

```md
标题：...
内容ID：...
发布时间：...
发布日期：...
原始链接：...
作者名称：...
平台：xueqiu|weibo|wechat
抓取时间：...

正文：
...
```

When author comments are present, append them as:

```md
作者评论：
1. [发布时间 | 作者名称] ...
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
- `log_file`
- `result_dir`
- `state_file`
- `processed_items`

`processed_items` is the primary deduplication source of truth for the current day when the state file is present.
