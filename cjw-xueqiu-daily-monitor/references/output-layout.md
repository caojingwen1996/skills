# Output Layout

All outputs are organized under a selected output root.

Repo-local examples in this skill use `./scripts/output`, but the same structure applies to any chosen output root.

## Directory layers

```text
{output-root}/
├── {author}_{yyyymmdd}.log
├── {author}_{yyyymmdd}.state.json
├── {author}_{yyyymmdd}/
├── processing/{yyyymmdd}/
└── summaries/{yyyymmdd}/
```

## Root layer: raw capture

The root layer stores per-account raw artifacts for one date:

- `{author}_{yyyymmdd}.log`
- `{author}_{yyyymmdd}.state.json`
- `{author}_{yyyymmdd}/` raw `.txt` files

Rules:

- keep one log and one state file per account-date
- keep raw `.txt` files inside the account-date directory
- do not mix summaries or intermediate analysis files into this layer

## Processing layer: intermediate analysis

Intermediate files must live under:

```text
{output-root}/processing/{yyyymmdd}/
```

Current subdirectories created by `scripts/daily_summary.py`:

- `raw_index/`
- `normalized/`
- `extracted/`
- `post_analysis/`
- `author_daily/`
- `market_daily/`

Rules:

- keep intermediate artifacts only
- preserve these files for traceability and review
- do not write final Markdown results here

## Summaries layer: final Markdown

Final Markdown results must live under:

```text
{output-root}/summaries/{yyyymmdd}/
```

Current final outputs:

- one Markdown daily report per author
- one `daily_summary.md` combined report

Rules:

- keep final readable Markdown only
- do not mix intermediate JSON or analysis artifacts into this directory

## Completion check

A correct output root should make it easy to answer:

- where the raw files were saved
- which intermediate artifacts were generated
- where the final Markdown results live
