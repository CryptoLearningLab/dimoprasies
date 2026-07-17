# NEXT TASK

Execute:
`Investigate metadata-only ESHIDIS attachment listing`

## Instruction

Keep the discovery/status separation:

1. Use the existing official audit JSON files:
   - `work/source_audit/eshidis_resource_audit_221380.json`
   - `work/source_audit/eshidis_resource_audit_221629.json`
   - `work/source_audit/eshidis_resource_audit_221675.json`
2. Determine whether the missing attachment rows are caused by:
   - no public attachments for these tenders,
   - a different Oracle ADF attachment table shape,
   - insufficient wait/click behavior in `fetch_resource_audit`.
3. If there is a public, non-authenticated attachment table shape, update the
   parser/importer with tests and re-run `sources fetch-resource` for the same
   three IDs.
4. Keep `221380`, `221629` and `221675` as `UNKNOWN` or candidate-only unless
   a status verification step explicitly supports a stronger state.
5. Download/analyze attachments only after official attachment rows are listed.

Do not store TEE subscription credentials in the repository. Treat TEE as a
future authenticated adapter.
