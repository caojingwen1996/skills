# Output Layout

All outputs are organized under the fixed output root `/Users/cjw/dev/projects/skills_output`.

The same directory structure applies under that root.

## Directory layers

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

## Author layer: raw capture and per-author outputs

Each author directory stores one account's artifacts for one date:

- `*.txt` raw files
- `state.json`
- `task.log`
- `processing/`
- `summary.md`

Rules:

- keep one state file and one log per account-date
- keep raw `.txt` files at the author directory root
- keep per-author intermediate analysis under `{yyyymmdd}/{author}/processing/`
- keep the per-author final Markdown at `{yyyymmdd}/{author}/summary.md`

## Per-author processing layer: intermediate analysis

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

Current final outputs:

- one `summary.md` per author

Rules:

- keep final readable Markdown only
- do not write intermediate JSON or analysis artifacts beside these Markdown files

## Completion check

A correct output root should make it easy to answer:

- where the raw files were saved
- which intermediate artifacts were generated
- where the final Markdown results live
