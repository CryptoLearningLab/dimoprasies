# ExecPlan: GEO AFOI Budget Pricing Database

## Purpose

Να δημιουργηθεί ανεξάρτητη βάση δεδομένων τιμών μελέτης από τους
προϋπολογισμούς έργων του Synology/GEO_AFOI, ώστε για κάθε νέο έργο να
μπορούμε να συγκρίνουμε τις τιμές μονάδας του προϋπολογισμού με ιστορικές
τιμές ανά άρθρο, κεφάλαιο και είδος εργασίας.

## Current State

- Το Synology share είναι διαθέσιμο στο:
  `/mnt/synology/Files/Files/1. ΔΗΜΟΣΙΑ ΕΡΓΑ`.
- Το κύριο project έχει ήδη reverse-pricing parser/schema στο
  `src/tender_radar/pricing.py`, αλλά το νέο workflow πρέπει να μείνει
  απομονωμένο μέχρι να επιβεβαιωθεί η ποιότητα των extracted rows.
- Ο source φάκελος περιέχει και πραγματικούς φακέλους έργων και άσχετα
  εταιρικά/δικαιολογητικά αρχεία, άρα απαιτείται ταξινόμηση και audit.

## Scope

In scope για το πρώτο milestone:

- Δημιουργία ανεξάρτητου workspace.
- Σχεδίαση τοπικού schema.
- Pilot scanner/parser για μικρό δείγμα έργων.
- Reports με πλήρη αποτυχίες και provenance.

Out of scope για το πρώτο milestone:

- Πανελλαδική ή πλήρης κάλυψη.
- Αυτόματη επιχειρηματική απόφαση.
- Σύνδεση με production UI.
- Τροποποίηση ή καθαρισμός πρωτότυπων αρχείων στο Synology.

## Milestones

### M1 - Workspace and Schema

Παραδοτέα:

- `geo_afoi_pricing/` με README, ExecPlan, schema και placeholders.
- Αρχικό schema για projects, source files, budget chapters, budget rows,
  article statistics και run logs.

Acceptance:

- Το workspace είναι απομονωμένο από το κύριο runtime.
- Το schema καλύπτει provenance και parsing failures.

### M2 - Pilot Inventory

Παραδοτέα:

- Resumable inventory command για το Synology root.
- Checkpointed SQLite insert για project folders και files.
- Report με counts ανά extension, candidate budget filenames και skipped
  folders/files.

Acceptance:

- Το scan μπορεί να διακοπεί και να συνεχίσει.
- Δεν ανοίγει ακριβά/OCR όλα τα αρχεία.
- Καταγράφεται κάθε skipped/error κατάσταση.

### M3 - Pilot Budget Extraction

Παραδοτέα:

- Parser route που ξεχωρίζει προϋπολογισμό μελέτης από οικονομική προσφορά.
- Εξαγωγή chapter/group και budget rows για 3-5 έργα.
- Fixtures/tests για layouts που βρέθηκαν στο pilot.

Acceptance:

- Κάθε extracted row έχει project, document, chapter, article code,
  description, unit, quantity, unit price, amount και confidence.
- Κάθε row έχει provenance σε αρχείο και διαθέσιμη θέση εγγράφου.
- Τα failures εμφανίζονται σε report.

### M4 - Statistics and New Project Comparison

Παραδοτέα:

- Aggregation ανά canonical article/chapter.
- Mean, median, min, max, sample count και outlier flags.
- Report σύγκρισης νέου έργου με ιστορικό δείγμα.

Acceptance:

- Δεν εμφανίζεται ένδειξη “καλή/κακή τιμή” όταν το δείγμα είναι ανεπαρκές.
- Οι αποκλίσεις εξηγούνται με αριθμούς και sample count.

## Data and Interfaces

Primary source:

```text
/mnt/synology/Files/Files/1. ΔΗΜΟΣΙΑ ΕΡΓΑ
```

Local database:

```text
geo_afoi_pricing/data/geo_afoi_pricing.sqlite
```

Reports:

```text
geo_afoi_pricing/reports/
```

Future integration point:

- Read-only export or view into the main Tender Radar pricing UI after M3/M4.

## Validation

Minimum validation per milestone:

- SQL schema can initialize an empty SQLite database.
- Parser fixtures pass focused tests.
- Pilot reports include counts and errors.
- Manual spot-check of extracted rows against source PDFs/Excel files.

## Progress

- 2026-08-15: Workspace scaffold created with README, ExecPlan, schema,
  config example and local data/work/report placeholders. Schema validates in
  in-memory SQLite.
- 2026-08-15: Direct-document pilot importer created and run on
  `2. ΕΣΩΤΕΡΙΚΗ ΟΔΟΠΟΙΙΑ ΟΙΚΙΣΜΩΝ ΤΟΥ ΔΗΜΟΥ ΘΕΡΜΟΥ` /
  `1. ΕΝΤΥΠΑ ΔΗΜΟΠΡΑΤΗΣΗΣ/3.-ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.pdf`. It inserted `26`
  budget rows, linked all rows to `4` detected chapters and passed amount
  validation: extracted row total `444.207,70` equals declared work total
  `444.207,70`.
- 2026-08-15: Added article identity/alias tables, repaired article/revision
  fields, `usable_for_stats`, and repaired/canonical chapter titles. Re-running
  the same pilot kept the numeric result unchanged and marked `26/26` article
  rows and `4/4` chapters `READY`.
- 2026-08-15: Added dependency-free XLSX worksheet extraction and structured
  XLSX budget row parsing. The second pilot,
  `12. ΚΟΜΒΟΣ ΜΑΛΑΜΑΤΩΝ/ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ 2η φαση για Ασημάκη.xlsx`, inserted
  `73` rows, linked `7` chapters, matched declared works total `472.410,00`,
  had `0` row arithmetic mismatches and marked `67/73` article rows usable for
  stats. Six custom/bare article rows initially remained `NEEDS_REVIEW`.
- 2026-08-15: Added a project-local identity policy for `Ν.Τ.` / `N.T.` new
  price rows. The same second pilot now has `67/73` article rows `READY` and
  usable for stats, `2/73` `READY_ZERO_AMOUNT` local new-price rows excluded
  from stats, and `4/73` true `NEEDS_REVIEW` custom/bare article rows.
- 2026-08-15: Added reviewed numeric `ΟΙΚ` aliases for `77.10 -> ΝΑΟΙΚ 77.10`
  and `77.30 -> ΝΑΟΙΚ 77.30`. The second XLSX pilot now has `69/73` article
  rows `READY` and usable for stats, `2/73` `READY_ZERO_AMOUNT` rows, and
  `2/73` true `NEEDS_REVIEW` rows.
- 2026-08-15: Added LibreOffice-backed `.doc` extraction and block parsing for
  legacy Word budgets. The third pilot,
  `3. ΑΝΑΠΛΑΣΕΙΣ ΚΑΙ ΕΣΩΤΕΡΙΚΗ ΟΔΟΠΟΙΪΑ ΔΕ ΝΑΥΠΑΚΤΟΥ/1. ΕΝΤΥΠΑ ΕΡΓΟΥ ΓΙΑ ΔΗΜΟΠΡΑΣΙΑ/4. ΠΡΟΥΠΟΛΟΓΙΣΜΟΣ.doc`,
  inserted `25` rows, linked `2` chapters, matched declared works total
  `173.942,11`, had `0` row arithmetic mismatches and marked `24/25` rows
  usable for stats. The one `NEEDS_REVIEW` row is `ΝΕΟ N/4720.A.2.1`.
- 2026-08-15: Added fixed-column YPEHODE-style PDF parsing for older road-work
  budgets. The fourth pilot,
  `6. ΑΜΦΙΣΣΑ -ΑΓΙΑ ΕΥΘΥΜΙΑ/1. ΕΝΤΥΠΑ ΕΣΗΔΗΣ/PROYPOLOG.xlk_signed.pdf`,
  inserted `33` rows, linked `3` chapters, matched declared works total
  `93.020,10`, and marked `32/33` rows usable for stats. The one
  `NEEDS_REVIEW` row is `Σ.72` with revision `ΥΔΡ-7107.1`.
- 2026-08-15: Added canonical unit normalization and materialized
  `geo_article_stats` refresh. Re-ran all four pilots: the database now has
  `157` budget rows, `151` usable rows, `134` stats rows, `15` reusable
  stats groups with at least two samples, and `0` stale article identities.
  The strict pass also mapped the first-pilot mojibake `Γ03` asphaltic-precoat
  row to `ΝΑΟΔΟ Δ03` instead of the true drainage article `ΝΑΟΔΟ Γ03`.

## Decisions

- Keep GEO_AFOI historical pricing as a separate workspace until extraction
  confidence is measured.
- Treat Synology source as read-only.
- Store uncertain or failed extraction explicitly instead of silently dropping
  files.

## Discoveries and Risks

- CIFS recursive listing can be slow; inventory must be checkpointed and
  should avoid repeated full-tree scans.
- Folder names alone are not reliable project identifiers.
- Files named as offers may contain contractor prices and must not be mixed
  with official study budget prices.
- Some documents may require OCR or spreadsheet extraction.
- The first pilot PDF has an extractable text layer, but Greek text and some
  article prefixes are font-encoding mojibake. OCR gives readable Greek but
  does not preserve enough table layout for deterministic row parsing.
  Therefore the current safe path is: parse numeric rows from the PDF text
  layer, store OCR text as an audit artifact, and repair descriptions/article
  prefixes before using rows for averages.

## Outcome

M1 workspace/schema scaffold is complete. The first direct-document pilot
database is populated, amount-validated and article-identity repaired for one
project. A second XLSX pilot is also populated, amount-validated and adjusted
for project-local `Ν.Τ.` identity handling and reviewed numeric `ΟΙΚ` aliases.
A third legacy Word pilot and fourth fixed-column PDF pilot are populated and
amount-validated. Canonical units and materialized stats are now in place. The
next outcome is custom/new article alias review policy for the remaining
`NEEDS_REVIEW` rows and the one visible `ΝΑΟΔΟ Δ06` revision variant, then
checkpointed multi-project inventory.
