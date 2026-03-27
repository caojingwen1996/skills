# Summary Format

Both per-author reports and the combined daily summary must be Markdown.

## Required sections

1. `核心内容`
2. `背景语境`
3. `Spec相关`

## `核心内容`

Answer:

- what the author or group of authors actually said that day

Keep:

- main viewpoints
- important tickers, indices, or events
- explicit trading statements

## `背景语境`

Answer:

- why these statements appeared on that day

Include when available:

- earnings
- announcements
- price moves
- short-selling pressure
- liquidity conditions
- market context
- thread or discussion context

## `Spec相关`

Only output this section when it is relevant.

It must be split into:

- `明确相关`
- `候选相关`

Current limitation:

- `明确相关` may remain empty because there is no full spec-matching engine yet
- current implementation only produces heuristic candidate observations

## Current generator behavior

`scripts/daily_summary.py` currently generates:

- one Markdown daily report per author
- one combined `daily_summary.md`

The current reports should preserve the required section names above even if some content is sparse.
