# NEXT TASK

Execute:
`Build alias risk audit report`

## Current Input

Use the configured focus geography:

```text
config/sources.yml
config/locations.yml
```

Latest recall-safety update as of `2026-07-17`:

```text
Γλυφάδα / Γλυφάδας configured as ambiguous Δήμος Δωρίδος aliases
positive context confirms the match
negative context blocks Attica/Glyfada municipality false positives
context-free ambiguous matches are retained for review
current live expanded report has 0 ambiguous retained matches
```

Recent UI workflow update as of `2026-07-17`:

```text
dashboard row actions now handle per-id Fetch and ZIP document download
KIMDIS fetch supports --official-id for one ADAM at a time
```

## Instruction

Build the next smallest recall-safety step:

1. Add a repeatable alias-risk audit that reads source/location configs and
   reports short, common, duplicated or ambiguous place aliases.
2. Keep the audit informational unless a rule is structurally invalid.
3. Produce JSON and Markdown reports with scope, alias, risk reason and
   recommended handling.
4. Do not remove aliases only because they are noisy; prefer ambiguous review
   buckets over recall loss.
5. Keep status verification and search/evaluation separate.

Do not store TEE subscription credentials in the repository. Treat TEE as a
future authenticated adapter.

## Required Closeout

At the end of the task:

1. Run the relevant targeted tests and `.venv/bin/python -m pytest` if code
   changed.
2. Update `docs/PROGRESS.md` with exact commands and evidence.
3. Update `docs/DECISIONS.md` only if a real decision was made.
4. Update this file with the next single executable gate.
5. Update `docs/HANDOFF.md` if the project state or next gate changed.
6. Commit and push tracked changes to GitHub unless explicitly told not to.
