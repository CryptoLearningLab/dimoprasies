# NEXT TASK

Execute:
`Download and analyze one candidate attachment set`

## Instruction

Keep the discovery/status separation:

1. Select one high-priority candidate with official attachment rows:
   - preferred: `221675` because it is road-maintenance relevant and has
     `9` official latest attachment rows,
   - alternative: `221629` with `10` official latest attachment rows.
2. Run controlled attachment download:

```bash
.venv/bin/python -m tender_radar sources download-attachment 221675 --all --limit 20 --allow-insecure-tls
```

3. Analyze downloaded documents:

```bash
.venv/bin/python -m tender_radar documents analyze \
  --eshidis-id 221675 \
  --report work/reports/document_analysis_221675.json \
  --markdown-report work/reports/document_analysis_221675.md
```

4. Run the existing dynamic evaluation profile:

```bash
.venv/bin/python -m tender_radar evaluate run \
  --profile config/evaluation_profiles/public_works_dynamic.yml \
  --eshidis-id 221675 \
  --report work/reports/evaluation_public_works_dynamic_221675.json \
  --markdown-report work/reports/evaluation_public_works_dynamic_221675.md
```

5. Keep the tender `UNKNOWN` or candidate-only unless a separate status
   verification step explicitly supports a stronger state.

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
