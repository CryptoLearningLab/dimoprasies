# Deduplication Protocol

This protocol prevents duplicate tender records without relying on title-only
matching. It is designed for cases such as multiple tenders named
`Αναπλάσεις ΔΕ Ναυπάκτου`.

## Principle

The project title is supporting evidence only. It is never enough by itself to
merge two records.

When evidence is ambiguous, keep separate tender records and link them as
`POSSIBLY_RELATED` for manual review.

## Identity Keys

Use the strongest available identifiers first:

1. `ESHIDIS_ID`
   - Same ESHIDIS id means same ESHIDIS tender.
2. KIMDIS ADAM by record family:
   - `PROC_ADAM` for declaration.
   - `AWRD_ADAM` for award/assignment.
   - `SYMV_ADAM` for signed contract.
   - PROC, AWRD and SYMV are different document families and must not collapse
     into one source record.
3. Diavgeia `ADA`.
   - Same ADA means same Diavgeia act, not necessarily the same tender unless
     it cross-references the tender id/ADAM.
4. TED notice id.
5. Normalized official URL.
6. Attachment SHA-256.

## Merge Levels

### Level 0 - Same Source Record

Merge only when the source family and source id are identical:

- same `source_type`,
- same source identifier,
- same document family where relevant.

Examples:

- same `ESHIDIS_ID`,
- same `PROC_ADAM`,
- same Diavgeia `ADA`.

### Level 1 - Official Cross-Reference

Merge/link as the same tender when an official source explicitly cross-references
another official id:

- KIMDIS notice mentions ESHIDIS id,
- Diavgeia act mentions ESHIDIS id,
- Diavgeia act mentions ADAM,
- signed contract references the original declaration ADAM.

The cross-reference text and source location must be recorded as provenance.

### Level 2 - Strong Composite Match

Use only when no official id cross-reference exists. A composite match requires
at least four independent matching fields:

- normalized contracting authority,
- execution place/NUTS or municipality/regional unit,
- budget within 1 percent or exact published budget,
- CPV overlap,
- same submission deadline or publication date within 3 days,
- same funding/program code,
- title similarity.

Title similarity can contribute, but it cannot be one of the four decisive
fields by itself. A repeated generic title should reduce confidence.

### Level 3 - Possible Relation

If only title, authority or geography match, keep separate records and add a
manual-review relation:

`POSSIBLY_RELATED`

This is the default for repeated titles such as `Αναπλάσεις ΔΕ Ναυπάκτου`
unless official identifiers or strong composite evidence prove identity.

## Required Stored Evidence

Every dedup decision must store:

- source ids used,
- source URLs,
- retrieval timestamps,
- fields compared,
- decision level,
- confidence,
- rationale,
- unresolved conflicts.

## Conflicts

Never merge automatically when these disagree without explicit official
cross-reference:

- different ESHIDIS ids,
- different contracting authority,
- different regional unit/execution place,
- different budget beyond tolerance,
- different deadline sequence,
- different CPV family.

## Current Implementation Status

This protocol is documented and ready for schema/adapter implementation. The
current SQLite schema has not yet added tender identity groups or relation
tables, so ambiguous records must remain separate until that migration exists.
