# PUBLIC WORKS TENDER RADAR
## Product Specification

## 0. Σκοπός

Το παρόν είναι η κανονιστική προδιαγραφή ενός επεκτάσιμου συστήματος
παρακολούθησης ελληνικών διαγωνισμών δημοσίων έργων.

Δεν είναι εντολή να υλοποιηθούν όλες οι λειτουργίες ταυτόχρονα.
Η υλοποίηση γίνεται σύμφωνα με το `docs/IMPLEMENTATION_PHASES.md`.

---

# 1. Αποστολή του συστήματος

Το σύστημα πρέπει να:

1. Εντοπίζει δημόσια διαθέσιμους διαγωνισμούς έργων.
2. Προσδιορίζει αν δέχονται ακόμη προσφορές.
3. Κατεβάζει και οργανώνει τα διαθέσιμα τεύχη.
4. Ταξινομεί και αναλύει PDF, Excel, Word, ZIP και εικόνες.
5. Επιτρέπει αναζήτηση μέσα στο πραγματικό περιεχόμενο των τευχών.
6. Εξάγει άρθρα, κωδικούς, ποσότητες, τιμές και δαπάνες.
7. Καταγράφει πηγές, εκδόσεις, σφάλματα και ιστορικό αλλαγών.
8. Επαναλαμβάνει σαρώσεις και εντοπίζει νέα έργα ή μεταβολές.
9. Παράγει ελέγξιμες αναφορές και αρχεία Excel.
10. Λειτουργεί γενικά για οποιαδήποτε τεχνική εργασία ή όρο,
    χωρίς αλλαγές στον βασικό κώδικα.

## 1.1 Εκτός αρχικού scope

- αυτόματη υποβολή προσφορών,
- χρήση ιδιωτικών ή συνδρομητικών λογαριασμών,
- παράκαμψη CAPTCHA ή authentication,
- νομική γνωμοδότηση,
- πλήρης αυτόματη αξιολόγηση καταλληλότητας εταιρείας,
- αυτόματη επιχειρηματική απόφαση.

---

# 2. Τρόποι λειτουργίας

## MODE A — Γεωγραφική αναζήτηση

Το σύστημα συλλέγει επιβεβαιωμένα ενεργούς διαγωνισμούς που αφορούν:

1. Δήμο Ναυπακτίας
2. Δήμο Δωρίδος
3. Δήμο Ιερής Πόλης Μεσολογγίου
4. Δήμο Θέρμου
5. Περιφέρεια Δυτικής Ελλάδας:
   - Π.Ε. Αιτωλοακαρνανίας
   - Π.Ε. Αχαΐας
6. Περιφέρεια Στερεάς Ελλάδας:
   - όλες τις Περιφερειακές Ενότητες
   - ιδιαίτερη προσοχή στη Φωκίδα

Η αντιστοίχιση δεν βασίζεται μόνο στην έδρα της αναθέτουσας αρχής.

Χρησιμοποιούνται συνδυαστικά:

- τόπος εκτέλεσης,
- NUTS,
- Δήμος και Περιφερειακή Ενότητα,
- τίτλος,
- αναθέτουσα αρχή,
- τεχνική περιγραφή,
- διακήρυξη,
- τοπωνύμια και aliases,
- γεωγραφικές αναφορές στα τεύχη.

Οι περιοχές και οι κωδικοί βρίσκονται σε configuration και δεν
hardcode-άρονται.

## MODE B — Αντίστροφη αναζήτηση περιεχομένου

Ο χρήστης αναζητά ενεργούς διαγωνισμούς με βάση το περιεχόμενο των
τευχών, ανεξάρτητα από περιοχή.

Πρέπει να υποστηρίζονται:

- φράσεις,
- λέξεις,
- άρθρα,
- κωδικοί άρθρων,
- κωδικοί αναθεώρησης,
- υλικά,
- τεχνικά χαρακτηριστικά,
- μονάδες,
- ποσότητες,
- τιμές μονάδας,
- συνολικές δαπάνες,
- AND, OR, NOT,
- περιορισμός ανά είδος εγγράφου,
- γεωγραφικά και χρονικά φίλτρα.

## MODE C — Παρακολούθηση αλλαγών

Σε επαναλαμβανόμενη σάρωση εντοπίζονται:

- νέα έργα,
- νέα ή τροποποιημένα συνημμένα,
- παρατάσεις,
- μεταθέσεις,
- ματαιώσεις,
- αλλαγές κατάστασης,
- αλλαγές προϋπολογισμού,
- αντικαταστάσεις εγγράφων.

---

# 3. Κανόνας παραμετροποίησης

Ο πυρήνας δεν περιέχει hardcoded:

- τεχνικές λέξεις ή φράσεις,
- κωδικούς άρθρων ή αναθεώρησης,
- ειδικές μονάδες,
- συγκεκριμένα έργα,
- λίστες συναφών όρων συγκεκριμένης αναζήτησης.

Κάθε αναζήτηση ορίζεται με:

1. runtime SearchRequest, ή
2. YAML profile στο `config/search_profiles/`.

Τα παραδείγματα και fixtures είναι μόνο tests.

---

# 4. Πηγές δεδομένων

## 4.1 Προτεραιότητα

1. Δημόσια αναζήτηση έργων ΕΣΗΔΗΣ:
   `https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/faces/active_search_main.jspx`
2. Δημόσια καρτέλα συγκεκριμένου διαγωνισμού ΕΣΗΔΗΣ.
3. Δημόσια συνημμένα διαγωνισμού.
4. ΚΗΜΔΗΣ μέσω ΑΔΑΜ.
5. Επίσημη ιστοσελίδα αναθέτουσας αρχής.
6. Διαύγεια, όταν περιέχει σχετική επίσημη πράξη.
7. Άλλη επίσημη δημόσια πηγή.
8. Μηχανές αναζήτησης μόνο για discovery.

Δεν χρησιμοποιείται scraping σε συνδρομητική Τράπεζα Πληροφοριών ΤΕΕ.

## 4.2 Πρόσβαση

Σειρά τεχνικής προσέγγισης:

1. Έρευνα για σταθερά δημόσια HTTP endpoints.
2. Επιθεώρηση network requests.
3. Direct HTTP όταν υπάρχει σταθερό δημόσιο endpoint.
4. Playwright/Chromium όταν απαιτείται browser.
5. Rate limiting, retry και exponential backoff.
6. Snapshots και logs όταν αλλάζει DOM ή ροή.
7. Καμία παράκαμψη authentication ή CAPTCHA.

## 4.3 Source adapters

Κάθε πηγή υλοποιείται ως adapter με κοινό συμβόλαιο:

- `discover_tenders`
- `fetch_tender_metadata`
- `list_attachments`
- `download_attachment`
- `fetch_status_evidence`
- `health_check`

Η αποτυχία μιας πηγής δεν πρέπει να κρύβεται.

---

# 5. Content discovery και status verification

Οι δύο διαδικασίες είναι ανεξάρτητες.

## 5.1 Content discovery

Στόχος είναι η υψηλή ανάκληση πιθανών ευρημάτων.

Μπορεί να βρεθούν:

- ενεργές διακηρύξεις,
- ληγμένες διακηρύξεις,
- μελέτες,
- αποφάσεις χρηματοδότησης,
- πρακτικά αξιολόγησης,
- ΑΠΕ,
- επιμετρήσεις,
- συμβάσεις.

Κάθε νέο εύρημα ξεκινά ως:

`CONTENT_MATCH_PENDING_STATUS`

## 5.2 Status verification

Για κάθε υποψήφιο έργο ελέγχονται:

- αρχική προθεσμία,
- τελευταία ισχύουσα προθεσμία,
- παράταση ή μετάθεση,
- τροποποίηση ή ορθή επανάληψη,
- αναστολή,
- ματαίωση ή ακύρωση,
- πρακτικό αποσφράγισης,
- πίνακας συμμετεχόντων,
- προσωρινός μειοδότης,
- απόφαση κατακύρωσης,
- υπογεγραμμένη σύμβαση.

## 5.3 Καταστάσεις

- CONTENT_MATCH_PENDING_STATUS
- VERIFIED_ACTIVE
- POSSIBLY_ACTIVE
- SUBMISSION_EXPIRED
- OPENING_COMPLETED
- EVALUATION_STAGE
- PROVISIONAL_CONTRACTOR
- AWARDED
- CONTRACT_SIGNED
- CANCELLED
- SUSPENDED
- STUDY_ONLY
- EXECUTION_DOCUMENT
- UNKNOWN

`VERIFIED_ACTIVE` σημαίνει ότι ο διαγωνισμός δέχεται νέες προσφορές
τη στιγμή του ελέγχου, σύμφωνα με την τελευταία επίσημη πράξη.

## 5.4 Χρονική ζώνη

`Europe/Athens`

## 5.5 Ιεραρχία αξιοπιστίας

1. Νεότερη επίσημη παράταση, τροποποίηση ή ματαίωση.
2. Τρέχουσα δημόσια καρτέλα ΕΣΗΔΗΣ.
3. Υπογεγραμμένη διακήρυξη.
4. ΚΗΜΔΗΣ.
5. Επίσημη σελίδα αναθέτουσας αρχής.
6. Άλλη επίσημη πράξη.
7. Search-engine metadata.

Η ημερομηνία indexing ή crawling δεν είναι ημερομηνία διαγωνισμού.

---

# 6. Δεδομένα διαγωνισμού

Όπου υπάρχουν, εξάγονται:

- Α/Α ΕΣΗΔΗΣ
- ΑΔΑΜ
- ΑΔΑ
- τίτλος
- αναθέτουσα αρχή
- υπηρεσία
- Περιφέρεια
- Περιφερειακή Ενότητα
- Δήμος
- τόπος εκτέλεσης
- NUTS
- CPV
- διαδικασία
- ημερομηνία δημοσίευσης
- αρχική προθεσμία
- τελευταία ισχύουσα προθεσμία
- ημερομηνία αποσφράγισης
- προϋπολογισμός χωρίς ΦΠΑ
- ΦΠΑ
- προϋπολογισμός με ΦΠΑ
- εγγύηση συμμετοχής
- διάρκεια έργου
- κριτήριο ανάθεσης
- κατηγορίες έργου
- απαιτήσεις πτυχίων ή τάξεων
- δημόσια links
- κατάσταση
- confidence
- ημερομηνία τελευταίου ελέγχου
- πηγή κάθε πεδίου

Όταν ένα πεδίο δεν τεκμηριώνεται:

- αποθηκεύεται `null`,
- καταγράφονται οι πηγές που ελέγχθηκαν,
- δεν γίνεται εικασία.

---

# 7. Συνημμένα και versioning

Για κάθε διαγωνισμό:

1. Καταγράφονται όλα τα δημόσια συνημμένα ΕΣΗΔΗΣ.
2. Γίνεται fallback σε ΚΗΜΔΗΣ και επίσημο φορέα.
3. Κατεβαίνουν τα αρχεία με ασφαλή ονόματα.
4. Υπολογίζεται SHA-256.
5. Τα διπλότυπα ανιχνεύονται με hash.
6. Οι διαφορετικές εκδόσεις διατηρούνται.
7. Η τελευταία έκδοση επισημαίνεται χωρίς διαγραφή των παλιών.
8. Καταγράφονται αποτυχίες και ελλείψεις.

Υποστηριζόμενα formats:

- PDF
- XLS/XLSX
- CSV
- DOC/DOCX
- ZIP
- RAR όταν είναι ασφαλές και πρακτικό
- XML
- εικόνες
- λοιπά συνήθη αρχεία

Η αποσυμπίεση προστατεύεται από:

- path traversal,
- zip bombs,
- υπερβολικό συνολικό μέγεθος,
- μη επιτρεπτούς τύπους αρχείων.

Metadata αρχείου:

- original_name
- local_name
- source_url
- source_type
- retrieved_at
- mime_type
- size_bytes
- sha256
- document_type
- version
- is_latest
- extraction_status
- page_or_sheet_count

---

# 8. Ταξινόμηση εγγράφων

Ενδεικτικές κατηγορίες:

- tender_declaration
- tender_summary
- budget
- bill_of_quantities
- price_list
- technical_description
- technical_specification
- technical_study
- special_conditions
- general_conditions
- financial_offer_form
- ESPD
- drawings
- schedule
- clarification
- extension
- amendment
- correction
- cancellation
- funding_decision
- study_approval
- participation_table
- evaluation_minutes
- provisional_award
- final_award
- contract
- APE
- measurement
- execution_report
- other

Η ταξινόμηση χρησιμοποιεί:

1. όνομα αρχείου,
2. τίτλο εγγράφου,
3. περιεχόμενο,
4. metadata,
5. κανόνες ή classifier,
6. confidence score.

Η κατηγορία επηρεάζει τον status engine.
Ένα ΑΠΕ ή μια σύμβαση δεν αποδεικνύει ενεργή δημοπράτηση.

---

# 9. Εξαγωγή περιεχομένου

## PDF

- πραγματικό text layer πρώτα,
- διατήρηση αριθμού σελίδας,
- extraction πινάκων,
- OCR μόνο όταν δεν υπάρχει χρήσιμο κείμενο,
- καταγραφή OCR confidence και σφαλμάτων.

## Excel

- ανάγνωση όλων των φύλλων,
- διατήρηση sheet και row,
- διατήρηση αριθμητικών τύπων,
- αξιολόγηση merged cells και πολλαπλών headers.

## DOCX

- παράγραφοι,
- πίνακες,
- headers και footers όπου είναι χρήσιμα.

## Archives

- ασφαλής αποσυμπίεση,
- recursive processing με όριο βάθους,
- κάθε εσωτερικό αρχείο ως ανεξάρτητο document.

## OCR

Το OCR είναι fallback και καταγράφει:

- ocr_used
- ocr_engine
- confidence
- πιθανές αμφιβολίες σε κωδικούς και αριθμούς

---

# 10. Generic SearchRequest

Κάθε αίτημα μετατρέπεται σε δομημένο SearchRequest.

Βασικά πεδία:

- name
- scope
- active_only
- document_types
- exact_phrases
- required_terms
- optional_terms
- excluded_terms
- article_codes
- revision_codes
- geographic_filters
- date_filters
- numeric_filters
- matching_modes
- extraction_fields
- output_fields

Πρότυπο:
`config/search_request.template.yml`

## 10.1 Matching modes

### EXACT
Ίδια σαφής φράση, κωδικός ή άρθρο.

### MORPHOLOGICAL
Παραλλαγές πεζών/κεφαλαίων, τόνων, τελικού σίγμα,
ενικού/πληθυντικού, παυλών, whitespace και κοινών OCR σφαλμάτων.

### STRONG_RELATED
Ίδια τεχνική οικογένεια με διαφορετικό τεχνικό χαρακτηριστικό.

### SEMANTIC_CANDIDATE
Συναφές νόημα που απαιτεί περαιτέρω επιβεβαίωση.

### FALSE_MATCH
Η φράση εμφανίζεται αλλά δεν αφορά τη ζητούμενη εργασία.

## 10.2 Κανονικοποίηση

- ελληνική Unicode κανονικοποίηση,
- αφαίρεση τόνων για index,
- διατήρηση πρωτότυπου κειμένου,
- κανονικοποίηση παυλών και whitespace,
- κανονικοποίηση μονάδων,
- tolerant matching κωδικών,
- profile-specific aliases μόνο μέσα στο profile.

## 10.3 Στρατηγική

1. exact μικρές queries,
2. morphological variants,
3. code-based discovery,
4. semantic candidate titles,
5. αναζήτηση μέσα στα ληφθέντα τεύχη,
6. deduplication,
7. status verification.

---

# 11. Προϋπολογισμοί και άρθρα

Όπου είναι εφικτό εξάγονται:

- section
- work_group
- item_number
- AT
- article_code
- revision_code
- description
- unit
- quantity
- unit_price
- total_cost
- revision_percentage
- document
- page
- sheet
- row
- extraction_confidence

Αναγνώριση ελληνικών αριθμών:

- 2.650.000,00
- 1.491.935,48
- 16.805,58

Αριθμητικός έλεγχος:

`quantity × unit_price ≈ total_cost`

με ανοχή στρογγυλοποίησης.

Όταν μια εργασία δηλώνει ότι δεν περιλαμβάνει συναφή δαπάνη:

1. σημαίνεται η εξαίρεση,
2. αναζητούνται σχετικά άρθρα στο ίδιο έργο,
3. εμφανίζεται προειδοποίηση ότι η κύρια τιμή δεν είναι πλήρες κόστος.

---

# 12. Αποτελέσματα αντίστροφης αναζήτησης

Κάθε αποτέλεσμα περιλαμβάνει:

- Α/Α ΕΣΗΔΗΣ
- ΑΔΑΜ
- τίτλο
- φορέα
- περιοχή
- κατάσταση
- τελευταία προθεσμία
- συνολικό budget
- document name/type
- page/sheet/row
- πλήρη περιγραφή
- article code
- revision code
- unit
- quantity
- unit price
- total cost
- match type
- content confidence
- status confidence
- source links
- local paths

Συγκεντρωτικά:

- πλήθος σχετικών άρθρων ανά έργο,
- συνολική σχετική δαπάνη,
- ποσοστό επί του έργου,
- exact και candidate αποτελέσματα χωριστά.

---

# 13. Deduplication και entity resolution

Κύρια αναγνωριστικά:

1. Α/Α ΕΣΗΔΗΣ
2. ΑΔΑΜ
3. ΑΔΑ
4. fallback fingerprint τίτλου + φορέα + budget + ημερομηνίας

Μία canonical tender record μπορεί να έχει πολλές source records.

Δεν συγχωνεύονται λανθασμένα:

- διαφορετικές διαδικασίες του ίδιου έργου,
- επαναδημοπρατήσεις,
- διαφορετικά υποέργα,
- διαφορετικές εκδόσεις εγγράφων.

---

# 14. Έλεγχος πληρότητας φακέλου

Checklist:

- διακήρυξη
- περίληψη
- τεχνική περιγραφή
- προϋπολογισμός
- τιμολόγιο
- προμέτρηση
- ΕΣΥ
- τεχνικές προδιαγραφές
- σχέδια
- έντυπο οικονομικής προσφοράς
- ΕΕΕΣ
- παρατάσεις/τροποποιήσεις

Παράγεται:

- completeness score,
- missing documents,
- πηγές που ελέγχθηκαν,
- λόγος αδυναμίας λήψης.

Το score δεν αποδεικνύει νομική πληρότητα.

---

# 15. Database και ιστορικό

Πρώτη έκδοση: SQLite.
Μελλοντικά: PostgreSQL.

Ενδεικτικοί πίνακες:

- tenders
- authorities
- locations
- tender_sources
- tender_status_history
- attachments
- attachment_versions
- documents
- document_pages
- budget_items
- search_profiles
- search_requests
- search_runs
- search_hits
- rejection_log
- errors
- crawl_runs

Κάθε scan έχει μοναδικό run ID και timestamps.

---

# 16. Απόρριψη ευρημάτων

Τα απορριφθέντα αποτελέσματα διατηρούνται.

Λόγοι:

- DEADLINE_EXPIRED
- PARTICIPATION_TABLE_EXISTS
- PROVISIONAL_CONTRACTOR_EXISTS
- AWARD_DECISION_EXISTS
- CONTRACT_ALREADY_SIGNED
- STUDY_NOT_TENDERED
- EXECUTION_STAGE_DOCUMENT
- FALSE_TEXT_MATCH
- DUPLICATE_TENDER
- STATUS_NOT_VERIFIABLE
- DOCUMENT_NOT_ACCESSIBLE

Το rejection log αποτελεί audit trail.

---

# 17. Αποθήκευση

```text
data/
  database/
  tenders/
    {ESHIDIS_ID}_{SHORT_TITLE}/
      metadata.json
      status_history.json
      sources/
      attachments/
        original/
        extracted/
        versions/
      parsed/
      search_hits/
      logs/
  cache/
exports/
reports/
```

Τα πρωτότυπα είναι immutable.

---

# 18. CLI

Ενδεικτικά:

```bash
python -m tender_radar scan --scope default
python -m tender_radar scan --region "Αιτωλοακαρνανία"
python -m tender_radar download --eshidis-id 221684
python -m tender_radar search --request request.yml
python -m tender_radar search --profile rockfall_energy_barrier
python -m tender_radar export --format xlsx
python -m tender_radar status-check --eshidis-id 221684
```

Οι τελικές εντολές πρέπει να είναι σταθερές, τεκμηριωμένες και scriptable.

---

# 19. Εξαγωγές

- active_tenders.xlsx
- reverse_search_results.xlsx
- missing_documents.xlsx
- status_changes.xlsx
- rejected_matches.xlsx
- run_summary.json
- report.html ή dashboard

Excel requirements:

- filters,
- frozen header,
- σωστά numeric/date types,
- hyperlinks,
- εύλογα widths,
- sheets για active, candidates, rejected, errors.

---

# 20. Logging, coverage και ειλικρίνεια

Για κάθε scan:

- χρόνος έναρξης/λήξης,
- πηγές,
- σελίδες,
- records,
- attachments,
- successful/failed downloads,
- parsed/unparsed documents,
- OCR count,
- content matches,
- status results,
- rejected matches,
- errors,
- coverage.

Δεν επιτρέπεται η φράση «Βρέθηκαν όλα τα ενεργά έργα» όταν υπάρχουν:

- ανεπεξέργαστες σελίδες,
- failed downloads,
- unknown statuses,
- μη αναγνώσιμα αρχεία,
- μη εξηγημένα σφάλματα.

---

# 21. Ασφάλεια

- δημόσια δεδομένα μόνο,
- secrets μέσω environment variables,
- safe filename handling,
- safe archive extraction,
- file size limits,
- network timeouts,
- rate limiting,
- δεν τροποποιούνται source files,
- δεν διαγράφονται versions,
- δεν αποθηκεύονται προσωπικά cookies ή credentials στο repository.

---

# 22. Testing

Unit tests:

- ελληνικοί αριθμοί,
- ημερομηνίες,
- Unicode,
- κωδικοί με διαφορετικές παύλες,
- document classification,
- status transitions,
- hash deduplication,
- archive safety,
- SearchRequest validation,
- budget arithmetic.

Integration tests:

- πραγματική δημόσια σελίδα,
- attachment listing,
- download,
- PDF parsing,
- Excel parsing,
- end-to-end search,
- export.

Fixtures:
`tests/fixtures/`

Τα fixtures δεν αποτελούν μόνιμη πηγή τρέχουσας κατάστασης.

---

# 23. Acceptance definition

πηγή
→ tender metadata
→ status evidence
→ attachment
→ document classification
→ content extraction
→ search hit
→ page/sheet/row
→ database
→ export.

Κάθε φάση έχει gate στο:
`docs/IMPLEMENTATION_PHASES.md`

---

# 24. Παραδοτέα

- λειτουργικό repository,
- README,
- source audit,
- database schema,
- configuration,
- CLI,
- tests,
- sample scans,
- sample reverse searches,
- Excel exports,
- known limitations,
- operational runbook,
- progress and decision logs.
