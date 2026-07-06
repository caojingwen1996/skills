# Output Layout

All outputs are organized under the configured output root declared in `EXTEND.md`.

## Directory layers

```text
{output-root}/
└── {yyyymmdd}/
    └── {author}/
        ├── *.md
        ├── state.json
        ├── task.log
        ├── processing/
        └── summary.md
```

## Author layer

Each author directory stores one account's artifacts for one date:

- `*.md` raw files
- `state.json`
- `task.log`
- `processing/`
- `summary.md`

Rules:

- keep one state file and one log per account-date
- keep raw Markdown files at the author directory root
- keep per-author intermediate analysis under `{yyyymmdd}/{author}/processing/`
- keep the per-author final Markdown at `{yyyymmdd}/{author}/summary.md`

## Per-author processing layer

Intermediate files must live under:

```text
{output-root}/{yyyymmdd}/{author}/processing/
```

Rules:

- keep intermediate artifacts only
- preserve these files for traceability and review
- do not write final Markdown results here

## Final Markdown outputs

Final Markdown results must live at:

```text
{output-root}/{yyyymmdd}/{author}/summary.md
```

## Completion check

A correct output root should make it easy to answer:

- where the raw Markdown files were saved
- which intermediate artifacts were generated
- where the final Markdown results live

## Day-level daily brief

In addition to each author's `summary.md`, keep one whole-day brief at:

```text
{output-root}/{yyyymmdd}/daily_brief.md
```

Rules:

- `daily_brief.md` lives under the date root, not inside an author directory
- it is generated after per-author `summary.md` files are complete
- it synthesizes the current date's saved articles across all authors
