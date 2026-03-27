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

- once login or page issues are resolved, the operator can rerun the same day
- reruns must continue from the existing state instead of starting over

## Stop-and-ask cases

Stop and ask the user before continuing when:

- there are no enabled accounts
- an enabled account is missing a homepage URL
- the target date is unclear
- login or page problems prevent reliable extraction
- saved content is empty or clearly malformed
