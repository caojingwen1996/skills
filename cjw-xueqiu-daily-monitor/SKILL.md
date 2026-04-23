---
name: cjw-xueqiu-daily-monitor
description: 当用户需要手动抓取一个或多个指定雪球账号主页的当日帖子、对同一天任务进行无重复补抓，或基于已保存的原始文本生成每位作者的 Markdown 汇总时使用。当用户说:“开启雪球任务” “抓取雪球帖子”时触发
---

# 雪球日常监控

面向已配置账号主页的手动当日雪球监控流程。

使用这个 skill 时，应从 `EXTEND.md` 读取账号配置，每次手动启动执行一轮抓取，在同日重跑时复用既有状态，并基于已保存的原始文本生成每位作者的 Markdown 汇总。

`EXTEND.md` 是本 skill 的唯一操作配置来源，包括输出根目录等运行偏好。主流程文档不得另行定义与 `EXTEND.md` 冲突的固定路径。

## 范围边界

这个 skill 只定义雪球业务流程本身：

- 账号配置与操作者确认
- 目标日期解析
- 同日重跑识别与去重
- 原始文件和汇总输出要求

当任务需要访问主页、复用登录态、进行页面交互或从雪球页面提取内容时，必须使用本 skill 自带的浏览器访问层：

- `scripts/start_automation_chrome.sh`：启动或复用固定自动化 Chrome/CDP 实例
- `scripts/extract_xueqiu_posts.mjs`：通过本地 CDP 连接访问雪球页面并提取结构化 JSON

这个 skill 现在自带浏览器访问能力，不再依赖外部浏览器访问 skill。

## 工作流

```text
- [ ] 第 1 步：预检 `EXTEND.md` 并确认任务输入
- [ ] 第 2 步：确认目标日期和运行模式
- [ ] 第 3 步：对每个启用账号执行一轮抓取
- [ ] 第 4 步：同日重跑时复用既有状态
- [ ] 第 5 步：基于已保存的原始文本生成 Markdown 汇总
- [ ] 第 6 步：收尾并汇报输出位置
```

## 第 1 步：预检

### 1.1 读取 `EXTEND.md` ⛔ 阻塞项

在开始任何抓取准备前：

- 读取 `EXTEND.md`
- 列出当前启用账号、禁用账号、URL、备注、手动规则、日期规则和输出偏好
- 询问用户是否需要补充或更正配置
- 提供标准确认选项：
  - `1. 需要补充或更正配置`
  - `2. 不需要修改，按指定日期抓取 YYYY-MM-DD`
  - `3. 不需要修改，按今天抓取`

在用户明确确认其中一个允许结果，或 `EXTEND.md` 更新完成之前，不要继续。

完整流程见：[references/workflow.md](references/workflow.md#step-1-pre-check)

### 1.2 校验任务输入与环境

确认：

- 至少有一个账号为 `enabled`
- 每个启用账号都配置了有效的雪球主页 URL
- 目标日期是明确的，或选项 `3` 已经被解析成绝对日期

在进入任何雪球页面抓取前，必须先确认浏览器环境可用。

如果配置或环境不完整，停止执行并要求用户先修正。

### 1.3 浏览器自动检测与启动

在调用 `scripts/extract_xueqiu_posts.mjs` 前，必须先检测固定自动化 Chrome/CDP 实例是否可用，并将其作为后续抓取复用的 `自动化专用 Chrome 实例`。

如重试后仍失败，必须停止当前任务，并将该项记录为待人工跟进。
完整流程见：[references/workflow.md](references/workflow.md#step-1-pre-check)




## 第 2 步：确认运行模式

判断本次启动属于：

- 当天首次抓取，或
- 必须复用既有当日输出的同日重跑

如果用户选择了 `3. 不需要修改，按今天抓取`，必须在判断运行模式前先把 `today` 解析成当前绝对日期。

使用现有的作者-日期目录，尤其是 `state.json`、`task.log` 和已保存的原始 `.txt` 文件，作为判断是否重跑的事实来源。

完整流程见：[references/workflow.md](references/workflow.md#step-2-choose-date-and-run-mode)

## 第 3 步：抓取

每次手动启动只执行一轮抓取。

- 第 3 步必须 `复用第 1.3 步` 已准备好的 `自动化专用 Chrome 实例`
- 使用 `scripts/extract_xueqiu_posts.mjs` 处理主页访问、页面交互、登录态复用、验证页自动尝试与人工回退，以及帖子内容提取
- 使用 `scripts/task_store.py` 处理状态、去重和日志
- 只处理目标日期的帖子
- 保存原始 `.txt` 文件和日志
- 不要启动自动循环或按小时扫描

## 第 4 步：同日重跑

同日重跑只能做增量补抓。

- 读取现有作者-日期输出目录
- 优先复用 `state.json`，只有在需要手动重建状态时才回退到已保存的原始 `.txt` 文件
- 只保存新发现的帖子
- 不要覆盖已有原始文件

完整流程见：[references/workflow.md](references/workflow.md#step-4-same-day-rerun)

## 第 5 步：生成汇总

当某个作者当天的抓取已经足够完整后：

- 从已保存的原始 `.txt` 文件准备作者输入
- 构建 `references/workflow.md` 中定义的作者汇总提示词
- 将最终 Markdown 与中间文件分开保存

汇总格式见：[references/summary-format.md](references/summary-format.md)

每份最终作者汇总都必须保留 `总观点` 和 `分观点` 这两个必需章节。

## 第 6 步：收尾

需要汇报：

- 目标日期
- 已处理作者数量
- 输出根目录
- 每位作者的汇总文件位置
- 每位作者的 processing 目录
- 仍需人工跟进的失败项

## 输出目录

所有输出都组织在 `EXTEND.md` 配置的 `preferred output root` 下。

```text
{output-root}/
└── {yyyymmdd}/
    ├── {author}/
    │   ├── *.txt
    │   ├── state.json
    │   ├── task.log
    │   ├── processing/
    │   └── summary.md
```

详细规则见：[references/output-layout.md](references/output-layout.md)

如存在中间分析产物，必须放在 `{yyyymmdd}/{author}/processing/` 下。

## 不要这样做

- 不要自动启动抓取
- 不要假设存在调度系统
- 不要把同日重跑当作全新任务
- 不要把中间文件混放在 `{yyyymmdd}/{author}/summary.md` 旁边
- 不要声称存在超出当前汇总启发式范围的 `spec` 匹配能力
- 不要在登录、页面、保存或风控失败后静默继续

## 参考资料

| File | Purpose |
|------|---------|
| [EXTEND.md](EXTEND.md) | 手动账号配置与任务启动确认来源 |
| [references/workflow.md](references/workflow.md) | 详细操作流程 |
| [references/output-layout.md](references/output-layout.md) | 输出根目录和目录层级规则 |
| [references/summary-format.md](references/summary-format.md) | 必需的 Markdown 汇总结构 |
| [references/error-policy.md](references/error-policy.md) | 失败处理与停止条件 |
| [references/file-layout.md](references/file-layout.md) | 原始文件命名和单文件内容格式 |
| [scripts/start_automation_chrome.sh](scripts/start_automation_chrome.sh) | 启动固定自动化 Chrome/CDP 实例 |
| [scripts/extract_xueqiu_posts.mjs](scripts/extract_xueqiu_posts.mjs) | 通过本地 CDP 访问雪球主页并提取结构化帖子 JSON |
| [scripts/task_store.py](scripts/task_store.py) | 状态与去重工具 |
