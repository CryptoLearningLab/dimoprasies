# GEO AFOI Pricing Workspace

Αυτός ο φάκελος είναι ανεξάρτητος χώρος εργασίας για την εξαγωγή,
αρχειοθέτηση και στατιστική σύγκριση τιμών προϋπολογισμών από τα έργα
του Synology/GEO_AFOI.

Δεν είναι ακόμη συνδεδεμένος με το κύριο Tender Radar runtime. Η σύνδεση
θα γίνει μόνο αφού περάσει το pilot ingestion gate και υπάρχουν
ελέγξιμα δεδομένα με provenance.

## Source Root

Προεπιλεγμένη πηγή:

```text
/mnt/synology/Files/Files/1. ΔΗΜΟΣΙΑ ΕΡΓΑ
```

Η πηγή αντιμετωπίζεται ως read-only. Τα πρωτότυπα αρχεία δεν
αντικαθίστανται, δεν μετακινούνται και δεν διαγράφονται.

## Local Layout

```text
geo_afoi_pricing/
  README.md
  EXECPLAN.md
  schema.sql
  config.example.yml
  data/
  work/
  reports/
  src/
  tests/
```

- `data/`: τοπική SQLite βάση και derived indexes.
- `work/`: προσωρινά extracted text, OCR artifacts και checkpoints.
- `reports/`: JSON/Markdown/CSV reports ανά run.
- `src/`: importer/parser code για αυτό το workspace.
- `tests/`: focused fixtures/tests για GEO_AFOI budget extraction.

## Target Data Chain

folder/project -> source document -> budget table -> chapter/group
-> article row -> unit price -> provenance -> SQLite -> averages report

## Non-Negotiables

- Κρατάμε provenance ανά path, file metadata, extraction time και θέση
  μέσα στο έγγραφο όπου μπορεί να εξαχθεί.
- Δεν παρουσιάζουμε αβέβαιη εξαγωγή ως έγκυρη τιμή μελέτης.
- Οι οικονομικές προσφορές δεν μπερδεύονται με τιμές μελέτης
  προϋπολογισμού.
- Κάθε αποτυχία ανάγνωσης, OCR ή parsing καταγράφεται σε report.
- Το Synology scan πρέπει να είναι resumable/checkpointed.

## First Gate

Pilot ingestion σε μικρό αριθμό φακέλων έργων:

1. Καταγραφή project folders.
2. Εντοπισμός πιθανών budget documents.
3. Εξαγωγή rows από 3-5 έργα.
4. SQLite insert με provenance.
5. Report με extracted, skipped και failed documents.
6. Focused tests για τουλάχιστον ένα πραγματικό/ανωνυμοποιημένο budget
   layout.
