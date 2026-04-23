# Error Policy

These situations require explicit operator visibility and must not be silently ignored:

- login expired
- page abnormal
- page structure changed
- extracted content is empty
- save failed
- risk-control prompt appeared

## Handling principles

1. Record the failure

- write the problem into logs or state when possible
- do not silently swallow the error

2. Preserve completed work

- already captured raw files must remain intact
- later failures must not destroy successfully saved results

3. Isolate the failure

- one failed item should not automatically invalidate the entire day
- one failing account should not corrupt results for other accounts

4. Allow human recovery

- when a Xueqiu verification page appears, first let the script automatically attempt the slider verification when configured
- when login or page issues appear, keep the current automation Chrome window open and let the operator recover in that same window first
- once login or page issues are resolved inside the automation Chrome window, the current extraction pass should continue automatically when possible
- only if the wait window times out or recovery still fails should the operator fall back to a same-day rerun
- reruns must continue from the existing state instead of starting over
- when automatic verification fails, explicitly tell the operator to continue the verification in the automation Chrome window as a manual fallback without switching browsers
- when a Xueqiu login page appears, explicitly tell the operator to log in in the automation Chrome window and wait for extraction to resume
- 保持自动优先、人工兜底；如自动尝试和人工回退都失败，必须停止并暴露问题

## Stop-and-ask cases

Stop and ask the user before continuing when:

- there are no enabled accounts
- an enabled account is missing a homepage URL
- the target date is unclear
- login or page problems prevent reliable extraction
- saved content is empty or clearly malformed
