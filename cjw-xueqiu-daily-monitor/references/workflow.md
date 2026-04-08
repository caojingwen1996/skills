# Detailed Workflow

This document is the authoritative operating procedure for the Xueqiu daily monitor skill.

## Step 1: Pre-check

### 1.1 Load `EXTEND.md` ⛔ BLOCKING

Before any capture preparation:

1. read `EXTEND.md`
2. summarize the current configuration for the user
3. explicitly ask the user to choose one of the standard pre-check outcomes:
   - `1. 需要补充或更正配置`
   - `2. 不需要修改，按指定日期抓取 YYYY-MM-DD`
   - `3. 不需要修改，按今天抓取`

The summary must include:

- enabled accounts
- disabled accounts
- each account URL
- notes when present
- start rules
- target date rule
- output preferences and output expectations

If the user wants changes, update `EXTEND.md` first and restart the pre-check.

If the user selects option `3`, resolve `today` to the current absolute date before continuing.

Do not continue until the user confirms one of the allowed pre-check outcomes.

### 1.2 Validate task readiness

Confirm:

- there is at least one enabled account
- every enabled account has a valid homepage URL
- the target date is explicit, or option `3` has already been resolved to an absolute date
- the Chrome profile is available, or the operator is ready for manual login

If configuration is incomplete:

- stop the run
- ask the operator to fix `EXTEND.md` or the local runtime setup



## Step 2: Choose date and run mode

The workflow always operates on one explicit target date.

If Step 1 ended with option `3. 不需要修改，按今天抓取`, first convert `today` to the current absolute date and use that date for all later path, state, and rerun checks.

Classify the run as:

- `new-day start`: no same-day author directory exists yet
- `same-day rerun`: the author directory already exists for that date

Use the existing author-date output directory as the source of truth. Prefer `state.json` when present, and use saved raw `.txt` files for fallback reconstruction when needed. Do not guess from memory alone.

Related files:

- browser access: `web-access`
- state and logs: `scripts/task_store.py`

## Step 3: Capture one pass

Each manual start performs one pass only.

For each enabled account:

1. load `web-access`
2. reuse the `自动化专用 Chrome 实例` prepared in Step 1.3

In other words, Step 3 must `复用第 1.3 步` already prepared browser instance instead of recreating the browser startup path.
3. open the homepage through the browser-access method defined by `web-access`
4. scan currently visible posts
5. keep only posts that belong to the target date
6. compare with already saved state or raw files for the same author-date directory
7. open only newly discovered items
8. extract content and save raw `.txt` files
9. append task logs and leave saved raw files available for later reruns

Required behavior:

- do not bypass `web-access` with ad hoc browser instructions in this skill
- do not capture non-target-date items
- do not overwrite existing raw files
- do not enter automatic loops
- do not invent scheduling behavior

Local responsibility split for this step:

- `web-access`: homepage access, page interaction, login-state reuse, DOM extraction
- `scripts/task_store.py`: state file, deduplication, scan rounds, logs
- `scripts/content_task.py`: consume extracted post JSON, filter by target date, deduplicate, and save raw `.txt` files

Common repo-local commands:

### Initialize or resume a day task

```bash
python3 scripts/task_store.py init \
  --account "闵行一霸" \
  --start-time "2026-03-25 09:30:00" \
  --output-root /Users/cjw/dev/projects/skills_output \
  --chrome-profile ./scripts/.xueqiu-chrome-profile
```

### Start a scan round

```bash
python3 scripts/task_store.py begin-scan \
  --state-file /Users/cjw/dev/projects/skills_output/20260325/闵行一霸/state.json \
  --note "开始扫描"
```

### Check whether an item should be processed

```bash
python3 scripts/task_store.py should-process \
  --state-file /Users/cjw/dev/projects/skills_output/20260325/闵行一霸/state.json \
  --title "示例标题" \
  --published-at "2026-03-25 15:08:00" \
  --url https://xueqiu.com/u/9838764557/381078922
```

### Save an item

```bash
python3 scripts/task_store.py save-item \
  --state-file /Users/cjw/dev/projects/skills_output/20260325/闵行一霸/state.json \
  --title "示例标题" \
  --published-at "2026-03-25 15:08:00" \
  --url https://xueqiu.com/u/9838764557/381078922 \
  --content-file ./tmp/post.txt
```

### Record a failure

```bash
python3 scripts/task_store.py record-failure \
  --state-file /Users/cjw/dev/projects/skills_output/20260325/闵行一霸/state.json \
  --kind save_failed \
  --message "Failed to persist extracted post"
```

### Finish a day task

```bash
python3 scripts/task_store.py finish \
  --state-file /Users/cjw/dev/projects/skills_output/20260325/闵行一霸/state.json
```

## Step 4: Same-day rerun

Same-day reruns are incremental.

When saved same-day output already exists for the same account and date:

1. inspect the existing author-date output directory
2. derive already processed items from `state.json` when available
3. fall back to saved raw files if the state needs manual reconstruction
4. scan the homepage again
5. keep only posts not already saved
6. save only the newly discovered content
7. append logs for the new pass

Never:

- rewrite old raw files
- treat a rerun like a new task

## Step 5: Generate summaries

Run summary generation only after the operator considers the day's raw capture complete enough.

### 5.1 Prepare author input

For each author directory under `{yyyymmdd}/`:

1. load all saved raw `.txt` files
2. parse only the minimum fields needed for summarization:
   - `title`
   - `published_at`
   - `url`
   - `content`
3. sort posts by publish time when available
4. treat the full set as one author-day input

Rules:

- read saved raw `.txt` files only
- do not mix in logs or unrelated files
- preserve post boundaries
- keep metadata separate from body text

### 5.2 Build author-summary prompt ⛔ BLOCKING

Each author must use a fixed prompt structure for viewpoint consolidation.

Required prompt sections:

| Section | Purpose |
|---------|---------|
| Author | identify the account being summarized |
| Date | bind the summary to one explicit date |
| Task | instruct the model to summarize viewpoints only |
| Output Rules | constrain headings and forbidden content |
| Post Payload | provide the parsed post list in stable order |

Required prompt content:

```text
作者：{author_name}
日期：{yyyy-mm-dd}

任务：
请仅基于下面帖子整理作者当天观点。

输出要求：
1. 只输出两个二级标题：## 总观点 和 ## 分观点
2. 不要输出 Spec、背景语境、交易建议、关键词统计
3. 分观点默认 3-7 条，每条只表达一个明确观点
4. 只有观点不够明确时，才在该条下补一行“证据：...”
5. 不要补充原文之外的推断，不要扩展成泛泛背景介绍

帖子数据：
[
  {
    "title": "...",
    "published_at": "...",
    "url": "...",
    "content": "..."
  }
]
```

Do not continue until the prompt for the author is complete.

### 5.3 Generate per-author viewpoint summary

For each author-day prompt:

1. submit the prepared prompt to the model
2. require the model to produce viewpoint consolidation only
3. save the result to `{yyyymmdd}/{author}/summary.md`

Output format:

```md
# <作者名> - <YYYY-MM-DD> 观点整理

## 总观点
<1 段话，概括作者当天最核心的总体判断>

## 分观点
1. <分观点 1>
   证据：<仅当观点不够明确时才补一小段原文证据>

2. <分观点 2>

3. <分观点 3>
```

Rules:

- summarize viewpoints only
- do not output old heuristic sections such as `核心内容` / `背景语境` / `Spec相关`
- do not overwrite raw `.txt` files
- allow rerunning Step 5 from saved raw files

### 5.4 Preserve intermediate artifacts

The workflow may keep intermediate artifacts separately for traceability, but final readable output must remain distinct.

Required output split:

- per-author intermediate artifacts: `{yyyymmdd}/{author}/processing/`
- per-author final Markdown: `{yyyymmdd}/{author}/summary.md`

Related references:

- [summary-format.md](summary-format.md)
- [output-layout.md](output-layout.md)

## Step 6: Finalize

At the end of a run, report:

- target date
- enabled accounts covered
- whether this was a new run or rerun
- output root
- per-author summary locations
- processing directory
- unresolved failures, if any

The workflow is considered complete for the date when:

- each required account has completed at least one pass
- same-day reruns are no longer needed
- raw data is stable enough for summary generation
- final summaries have been written
- important failures have been recorded for follow-up

## Stop Conditions

Stop and tell the user before continuing when any of the following happens:

- login expired
- page abnormal
- page structure changed
- extracted content is empty
- save failed
- risk-control prompt appeared

Detailed failure handling: [error-policy.md](error-policy.md)
