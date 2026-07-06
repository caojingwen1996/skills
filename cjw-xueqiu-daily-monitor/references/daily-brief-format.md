# Daily Brief Format

After all enabled accounts finish capture for one target date, the skill should also produce one day-level Markdown brief:

```text
{output-root}/{yyyymmdd}/daily_brief.md
```

This file is separate from each author's `summary.md`.

## Source of truth

Build the daily brief only from content already saved for that target date:

- raw Markdown files under `{yyyymmdd}/{author}/`
- per-author `summary.md`
- processing metadata when it clarifies counts or source mix

Do not invent information outside the saved material.

## Daily brief derivation template

Use the following structure as the latest output flow for `daily_brief.md`.

```md
# 每日投研简报

数据来源：雪球（X篇）、微博（X篇）、微信公众号（X篇） | 共 X 篇文章
覆盖时段：YYYY-MM-DD HH:mm ~ YYYY-MM-DD HH:mm（北京时间）
生成时间：YYYY-MM-DD 盘前 / 午间 / 盘后

## <绝对日期>

## 0. 一句话主线
用一句话概括当天材料的核心推导。

格式：
今天的核心主线是：由于【现象】，作者将其归因于【原因】，并进一步外推为【结论/策略】。

---

## 1. 核心矛盾
- 左侧逻辑：
- 右侧逻辑：
- 当前冲突：
- 作者选择：
- 尚未解决的问题：

---

## 2. 现象层
### 市场现象
-

### 资金现象
-

### 产业现象
-

### 认知现象
-

---

## 3. 归因层
### 流动性归因
-

### 政策/行政归因
-

### 资金结构归因
-

### 产业趋势归因
-

### 交易结构归因
-

---

## 4. 传导机制
### 风险传导链
外部变量 → 流动性 → 风险偏好 → 市场结构 → 板块表现 → 仓位含义

### 机会传导链
技术/政策 → 产业变化 → 关键瓶颈 → 资金定价 → 资产表现 → 跟踪方向

### 两条链的冲突处理
- 更紧急的是：
- 更长期的是：
- 已被计价的是：
- 尚缺证据的是：
- 当前处理方式：

---

## 5. 外推结论
### 短期
-

### 中期
-

### 长期
-

---

## 6. 应对策略
- 仓位：
- 观察：
- 等待节点：
- 禁止动作：
- 可做动作：

---

## 7. 反证清单
- 宏观反证：
- 流动性反证：
- 资金流反证：
- 产业反证：
- 价格反证：

---

## 8. 今日待跟踪问题
1.
2.
3.
```

## Writing rules

- summarize the current day's saved articles only
- use the template above as the direct output structure instead of the older section flow
- keep the metadata header at the very top of the brief, directly under `# 每日投研简报`
- the metadata header should include exactly these three lines: `数据来源`、`覆盖时段`、`生成时间`
- keep the brief focused on derivation: phenomenon -> attribution -> transmission -> conclusion -> strategy
- when a subsection lacks evidence in the saved material, keep the heading and mark the evidence gap instead of fabricating detail
- prefer cross-author synthesis over repeating one author at a time
- keep concrete numbers only when they are present in the saved material
- when listing authors or source counts by author, prefer the saved `作者名称` over numeric account IDs; only fall back to IDs when no author name is available
- do not replace or weaken the existing per-author `summary.md` workflow
