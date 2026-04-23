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

`EXTEND.md` is also the single source of truth for output-root configuration. This workflow must not redefine a conflicting output root.

### 1.2 验证任务就绪状态

确认以下条件全部成立：

- 至少存在一个 `enabled` 账号
- 每个启用账号都配置了有效的雪球主页 URL
- 目标日期已经明确，或者选项 `3` 已经被解析为绝对日期
- 本 skill 的浏览器访问前置条件已经满足：本地 Chrome 可用，固定自动化 Chrome 实例能够通过 CDP 连接，如有需要操作者可以手动完成雪球登录
- 如出现登录失效或访问验证，脚本应先按配置自动尝试滑块验证；自动失败时由操作者在自动化 Chrome 窗口内继续人工处理，并等待当前轮次继续

如果配置或运行环境不完整：

- 停止本次任务
- 要求操作者先修复 `EXTEND.md` 或本地运行环境，再继续

### 1.3 验证本地 CDP 就绪状态 ⛔ BLOCKING

在访问任何雪球页面之前，必须确认浏览器调试链路已经真正可用，而不只是完成了表面配置。

必做检查：

- 检查固定自动化 Chrome/CDP 实例是否已经可访问
- 如果 Chrome 页面仍显示 remote debugging 为 `starting...`，视为尚未就绪
- 在继续抓取前，必须确认至少有一个调试端口正在实际监听
- 不能仅凭一个陈旧的 `DevToolsActivePort` 文件就判断环境可用

出现以下任一情况时，必须停止并要求操作人先修复 Chrome 运行状态，再继续任务：

- 浏览器界面仍显示 remote debugging 为 `starting...`
- 没有任何可访问的活动调试端口
- 只存在旧的 `DevToolsActivePort` 文件，但其中记录的端口并未实际监听
- 自动启动 Chrome 只解决“浏览器未启动”问题，不代表本地提取脚本一定已经可以成功连接 CDP
- 端口 `3456` 已被占用，不代表当前 Proxy 一定可用

当 `scripts/extract_xueqiu_posts.mjs` 返回以下错误时，应按不同情况处理：

- `Unable to find Chrome or Chromium executable.`
- `Chrome debug port not ready`
- `CDP connection failed.`
- 其他等价的浏览器未连接错误

处理规则如下：

1. 先不要立即判定抓取失败
2. 先检查固定自动化 Chrome/CDP 实例是否已经启动
3. 如果未启动，则执行 `scripts/start_automation_chrome.sh` 自动启动浏览器
4. 启动后，确认该自动化 Chrome 实例内已完成 `chrome://inspect/#remote-debugging` 授权
5. 检查目标调试端口是否已经暴露 `/json/version`
6. 如端口可用，则直接复用并重试一次本地提取脚本

如果浏览器已经启动，但本地提取脚本仍然预检失败，则应判定为：

- Chrome 已启动，但 CDP 调试连接仍不可用
- 当前问题不属于“未打开浏览器”，而属于浏览器调试连接异常

此时必须停止当前任务，并将该项记录为待人工跟进，不要继续后续抓取。

### 1.4 登录失效或访问验证时的等待恢复 ⛔ BLOCKING

当自动化 Chrome 已经可用，但雪球页面要求重新登录或出现访问验证时：

1. 不要关闭自动化 Chrome 窗口
2. 不要切换到其他浏览器完成登录或验证
3. 必须在当前自动化 Chrome 窗口内完成登录或验证
4. 让当前抓取轮次保持等待，页面恢复后继续当前账号，不要求手动重跑本轮

处理规则：

- 登录页：提示操作者在自动化 Chrome 窗口内完成雪球登录，然后等待页面恢复
- 验证页：脚本应先自动尝试滑块验证；如果自动尝试失败，再提示操作者在自动化 Chrome 窗口内继续人工验证
- 页面恢复后：继续当前账号抓取，从阻塞位置往后执行
- 若等待超时或恢复后页面仍异常：停止当前账号，并记录为待人工跟进


## Step 2: Choose date and run mode

The workflow always operates on one explicit target date.

If Step 1 ended with option `3. 不需要修改，按今天抓取`, first convert `today` to the current absolute date and use that date for all later path, state, and rerun checks.

Classify the run as:

- `new-day start`: no same-day author directory exists yet
- `same-day rerun`: the author directory already exists for that date

Use the existing author-date output directory as the source of truth. Prefer `state.json` when present, and use saved raw `.txt` files for fallback reconstruction when needed. Do not guess from memory alone.

Related files:

- browser access: `scripts/extract_xueqiu_posts.mjs`
- state and logs: `scripts/task_store.py`
- output root: `EXTEND.md`

## Step 3: Capture one pass

Each manual start performs one pass only.

For each enabled account:

1. ensure `scripts/start_automation_chrome.sh` has prepared the dedicated browser instance
2. reuse the `自动化专用 Chrome 实例` prepared in Step 1.3

In other words, Step 3 must `复用第 1.3 步` already prepared browser instance instead of recreating the browser startup path.
2. run `scripts/extract_xueqiu_posts.mjs` against the account homepage
3. open the homepage through the repo-local browser-access method defined by `extract_xueqiu_posts.mjs`
4. scan currently visible posts
5. keep only posts that belong to the target date
6. compare with already saved state or raw files for the same author-date directory
7. open only newly discovered items
8. extract content into structured JSON and pass it to `scripts/content_task.py`
9. save raw `.txt` files
9. append task logs and leave saved raw files available for later reruns

Required behavior:

- do not bypass `scripts/extract_xueqiu_posts.mjs` with ad hoc browser instructions in this skill
- do not capture non-target-date items
- do not overwrite existing raw files
- do not enter automatic loops
- do not invent scheduling behavior
- when login interrupts extraction, keep the automation Chrome window open and wait for manual recovery before resuming the current pass
- when verification interrupts extraction, automatically attempt the slider first and only then fall back to manual recovery in the same automation Chrome window

Local responsibility split for this step:

- `scripts/start_automation_chrome.sh`: launch or reuse the dedicated automation Chrome instance
- `scripts/extract_xueqiu_posts.mjs`: homepage access, page interaction, login-state reuse, verification auto-attempt with manual fallback, DOM extraction
- `scripts/task_store.py`: state file, deduplication, scan rounds, logs
- `scripts/content_task.py`: consume extracted post JSON, filter by target date, deduplicate, and save raw `.txt` files

### Extract structured posts

```bash
node scripts/extract_xueqiu_posts.mjs \
  --account-url https://xueqiu.com/u/9838764557 \
  --date 2026-03-25 \
  --author-name "闵行一霸" \
  --output-file ./tmp/posts.json
```

### Persist extracted posts

```bash
python3 scripts/content_task.py \
  --input-file ./tmp/posts.json \
  --author-name "闵行一霸" \
  --account-url https://xueqiu.com/u/9838764557 \
  --date 2026-03-25 \
  --output-dir {output-root}
```

Common repo-local commands:

### Initialize or resume a day task

```bash
python3 scripts/task_store.py init \
  --account "闵行一霸" \
  --start-time "2026-03-25 09:30:00" \
  --output-root {output-root} \
  --chrome-profile ./scripts/.xueqiu-chrome-profile
```

### Start a scan round

```bash
python3 scripts/task_store.py begin-scan \
  --state-file {output-root}/20260325/闵行一霸/state.json \
  --note "开始扫描"
```

### Check whether an item should be processed

```bash
python3 scripts/task_store.py should-process \
  --state-file {output-root}/20260325/闵行一霸/state.json \
  --title "示例标题" \
  --published-at "2026-03-25 15:08:00" \
  --url https://xueqiu.com/u/9838764557/381078922
```

### Save an item

```bash
python3 scripts/task_store.py save-item \
  --state-file {output-root}/20260325/闵行一霸/state.json \
  --title "示例标题" \
  --published-at "2026-03-25 15:08:00" \
  --url https://xueqiu.com/u/9838764557/381078922 \
  --content-file ./tmp/post.txt
```

### Record a failure

```bash
python3 scripts/task_store.py record-failure \
  --state-file {output-root}/20260325/闵行一霸/state.json \
  --kind save_failed \
  --message "Failed to persist extracted post"
```

### Finish a day task

```bash
python3 scripts/task_store.py finish \
  --state-file {output-root}/20260325/闵行一霸/state.json
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

- login expired and does not recover within the wait window
- page abnormal
- page structure changed
- extracted content is empty
- save failed
- risk-control prompt appeared and does not recover within the wait window

Detailed failure handling: [error-policy.md](error-policy.md)
