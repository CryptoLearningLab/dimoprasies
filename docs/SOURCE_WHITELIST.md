# PUBLIC WORKS TENDER RADAR
## Source Whitelist για γεωγραφική αναζήτηση έργων

Το παρόν αρχείο ορίζει τις βασικές επίσημες και συμπληρωματικές πηγές που πρέπει να χρησιμοποιεί το PUBLIC WORKS TENDER RADAR για συλλογή, επαλήθευση και εμπλουτισμό διαγωνισμών δημοσίων έργων στις περιοχές:

- Δήμος Ναυπακτίας
- Δήμος Θέρμου
- Δήμος Ιερής Πόλης Μεσολογγίου
- Δήμος Δωρίδος / Ευπάλιο
- Δήμος Πατρέων / Πάτρα
- Περιφέρεια Δυτικής Ελλάδας
- Π.Ε. Αιτωλοακαρνανίας
- Περιφέρεια Στερεάς Ελλάδας
- Π.Ε. Φωκίδας

Σημαντικό: Το Ευπάλιο ανήκει στον Δήμο Δωρίδος. Οι παλιοί «νομοί» αναφέρονται σήμερα ως Περιφερειακές Ενότητες.

---

# 1. Πανελλαδικές βασικές πηγές

## 1.1 ΕΣΗΔΗΣ Δημοσίων Έργων

### Κεντρική αναζήτηση ενεργών έργων

https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/faces/active_search_main.jspx

### Δημόσια καρτέλα συγκεκριμένου έργου

https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/{ESHIDIS_ID}

Παράδειγμα:

https://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/221684

Από τη δημόσια καρτέλα συλλέγονται:

- metadata
- αναθέτουσα αρχή
- ημερομηνίες
- κατάσταση
- συνημμένα
- τεύχη
- νεότερες ανακοινώσεις

Η εφαρμογή μπορεί να απαιτεί Playwright/Chromium λόγω JavaScript και Oracle ADF.

## 1.2 Πύλη Προμηθεύς

https://portal.eprocurement.gov.gr/

---

# 2. ΚΗΜΔΗΣ Open Data API

## 2.1 Τεκμηρίωση

https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help

## 2.2 Αναζήτηση διακηρύξεων

POST

https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice?page=0

Για δημόσια έργα χρησιμοποιείται `contractType: 10`.

## 2.3 Λήψη PDF διακήρυξης με ΑΔΑΜ

https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice/attachment/{PROC_ADAM}

## 2.4 Αναζήτηση αναθέσεων / κατακυρώσεων

POST

https://cerpp.eprocurement.gov.gr/khmdhs-opendata/auction?page=0

## 2.5 Λήψη PDF ανάθεσης / κατακύρωσης

https://cerpp.eprocurement.gov.gr/khmdhs-opendata/auction/attachment/{AWRD_ADAM}

## 2.6 Αναζήτηση συμβάσεων

POST

https://cerpp.eprocurement.gov.gr/khmdhs-opendata/contract?page=0

## 2.7 Λήψη υπογεγραμμένης σύμβασης

https://cerpp.eprocurement.gov.gr/khmdhs-opendata/contract/attachment/{SYMV_ADAM}

Το σύστημα πρέπει να ξεχωρίζει αυστηρά:

- PROC = διακήρυξη
- AWRD = ανάθεση / κατακύρωση
- SYMV = υπογεγραμμένη σύμβαση

---

# 3. Διαύγεια

## Κεντρική σελίδα

https://diavgeia.gov.gr/

## Απευθείας σελίδες φορέων

- Δήμος Ναυπακτίας: https://diavgeia.gov.gr/f/nafpaktia
- Δήμος Θέρμου: https://diavgeia.gov.gr/f/dimosthermo
- Δήμος Ι.Π. Μεσολογγίου: https://diavgeia.gov.gr/f/dimos_i_p_mesolonghiou
- Δήμος Δωρίδος: https://diavgeia.gov.gr/f/DHMOSDORIDOS
- Δήμος Πατρέων: https://diavgeia.gov.gr/f/dimospatras
- Περιφέρεια Δυτικής Ελλάδας: https://diavgeia.gov.gr/f/pde
- Περιφέρεια Στερεάς Ελλάδας: https://diavgeia.gov.gr/f/pste

Η Διαύγεια χρησιμοποιείται κυρίως για:

- Πρακτικά Ι, ΙΙ και ΙΙΙ
- πίνακες συμμετεχόντων
- οικονομικές προσφορές
- προσωρινούς αναδόχους
- μέσες εκπτώσεις
- κατακυρώσεις
- παρατάσεις
- ματαιώσεις
- εγκρίσεις συμβάσεων

---

# 4. Δήμος Ναυπακτίας

## Πηγές

- Προκηρύξεις και διαγωνισμοί: https://www.nafpaktos.gr/el/prokirixeis-diagonismoi
- Διαύγεια Δήμου: https://diavgeia.gov.gr/f/nafpaktia
- ΔΕΥΑ Ναυπακτίας: https://diavgeia.gov.gr/f/deya_nafpaktias

## Όροι αναζήτησης

- Δήμος Ναυπακτίας
- Ναυπακτία
- Ναύπακτος
- Ναυπάκτου
- Αντίρριο
- Χάλκεια
- Αποδοτία
- Πλάτανος
- Πυλλήνη
- EL631

---

# 5. Δήμος Θέρμου

## Πηγές

- Διακηρύξεις / προκηρύξεις: https://www.dimos-thermou.gr/website/category/diakyrikseis-prokyrikseis/
- Διαύγεια Δήμου: https://diavgeia.gov.gr/f/dimosthermo

## Όροι αναζήτησης

- Δήμος Θέρμου
- Θέρμο
- Θέρμου
- Δ.Ε. Θέρμου
- EL631

Προσοχή να μη συγχέεται με τον Δήμο Θέρμης Θεσσαλονίκης.

---

# 6. Δήμος Ιερής Πόλης Μεσολογγίου

## Πηγές

- Διαγωνισμοί: https://messolonghi.gov.gr/diagonismoi-2/
- Διαύγεια Δήμου: https://diavgeia.gov.gr/f/dimos_i_p_mesolonghiou

## Όροι αναζήτησης

- Δήμος Ιερής Πόλης Μεσολογγίου
- Δήμος Ι.Π. Μεσολογγίου
- Ι.Π. Μεσολογγίου
- Μεσολόγγι
- Μεσολογγίου
- Ιερά Πόλη Μεσολογγίου
- Αιτωλικό
- Οινιάδες
- Νεοχώρι
- Κατοχή
- EL631

Για ύδρευση και αποχέτευση να γίνεται επιπλέον αναζήτηση στο ΚΗΜΔΗΣ και στη Διαύγεια με την πλήρη επωνυμία του αντίστοιχου φορέα.

---

# 7. Δήμος Δωρίδος / Ευπάλιο

## Πηγές

- Προκηρύξεις: https://www.dorida.gr/blog/category/%CF%84%CE%B5%CE%BB%CE%B5%CF%85%CF%84%CE%B1%CE%AF%CE%B1-%CE%BD%CE%AD%CE%B1/%CF%80%CF%81%CE%BF%CE%BA%CE%B7%CF%81%CF%8D%CE%BE%CE%B5%CE%B9%CF%82
- Αποφάσεις επιτροπών: https://www.dorida.gr/dimotiko-symvoulio/apofaseis-epitropon
- Διαύγεια Δήμου: https://diavgeia.gov.gr/f/DHMOSDORIDOS
- Δημοτικό Λιμενικό Ταμείο Δωρίδος: https://diavgeia.gov.gr/f/D.L.T.DORIDOS

## Όροι αναζήτησης

- Δήμος Δωρίδος
- Δωρίδα
- Δωρίδος
- Ευπάλιο
- Ευπαλίου
- Δ.Ε. Ευπαλίου
- Μοναστηράκι
- Χιλιαδού
- Σεργούλα
- Γλυφάδα
- Μαραθιάς
- Τολοφώνα
- Ερατεινή
- Λιδωρίκι
- EL645

---

# 8. Δήμος Πατρέων / Πάτρα

## Πηγές

- Διακηρύξεις: https://e-patras.gr/el/tenders
- Αποφάσεις Δημοτικής Επιτροπής: https://e-patras.gr/el/e-democracy/decisions/municipal-committee-decisions
- Διαύγεια Δήμου: https://diavgeia.gov.gr/f/dimospatras
- ΔΕΥΑ Πάτρας: https://deyap.gr/category/news/shmantikes_anakoinwseis_prokurhxeis/prokurhxeis/

## Όροι αναζήτησης

- Δήμος Πατρέων
- Πάτρα
- Πατρών
- Ρίο
- Παραλία Πατρών
- Βραχναίικα
- Μεσσάτιδα
- EL632

---

# 9. Περιφέρεια Δυτικής Ελλάδας / Π.Ε. Αιτωλοακαρνανίας

## Πηγές

- Προκηρύξεις: https://pde.gov.gr/el/diafaneia/prokirikseis/
- Περιφερειακή Επιτροπή: https://pde.gov.gr/el/perifereia/perifereiaki_epitropi/
- Διεύθυνση Τεχνικών Έργων Π.Ε. Αιτωλοακαρνανίας: https://pde.gov.gr/el/perifereia/organotiki-domi/genikes-dieuthinseis/dieuthinsi-anapt-progr/dtepea/
- Διαύγεια Περιφέρειας: https://diavgeia.gov.gr/f/pde

## Όροι αναζήτησης

- Περιφέρεια Δυτικής Ελλάδας
- Π.Ε. Αιτωλοακαρνανίας
- Περιφερειακή Ενότητα Αιτωλοακαρνανίας
- Αιτωλοακαρνανία
- Ναυπακτία
- Μεσολόγγι
- Θέρμο
- EL63
- EL631

---

# 10. Περιφέρεια Στερεάς Ελλάδας / Π.Ε. Φωκίδας

## Πηγές

- Διαγωνισμοί Περιφέρειας: https://diafania.pste.gov.gr/?cat=3
- Διαύγεια Περιφέρειας: https://diavgeia.gov.gr/f/pste

## Όροι αναζήτησης

- Περιφέρεια Στερεάς Ελλάδας
- Π.Ε. Φωκίδας
- Περιφερειακή Ενότητα Φωκίδας
- Φωκίδα
- Φωκίδος
- Άμφισσα
- Δελφοί
- Ιτέα
- Δωρίδα
- Ευπάλιο
- EL64
- EL645

---

# 11. TED — Ευρωπαϊκοί διαγωνισμοί

https://ted.europa.eu/en/search/result

Χρησιμοποιείται συμπληρωματικά για μεγάλους προϋπολογισμούς, ευρωπαϊκές δημοσιεύσεις, CPV, τόπο εκτέλεσης, γνωστοποιήσεις ανάθεσης και τροποποιήσεις.

---

# 12. Προτεινόμενη σειρά συλλογής

1. ΕΣΗΔΗΣ πανελλαδική συλλογή ενεργών έργων.
2. ΚΗΜΔΗΣ διακηρύξεις τύπου PROC.
3. Γεωγραφική ταξινόμηση με NUTS, τοπωνύμια και περιεχόμενο.
4. Δημόσια καρτέλα ΕΣΗΔΗΣ και όλα τα συνημμένα.
5. Ιστοσελίδα Δήμου ή Περιφέρειας ως συμπλήρωμα.
6. Διαύγεια και αποφάσεις επιτροπών για πρακτικά και status.
7. ΚΗΜΔΗΣ AWRD για ανάθεση, ανάδοχο και έκπτωση.
8. ΚΗΜΔΗΣ SYMV για υπογεγραμμένη σύμβαση.
9. TED για ευρωπαϊκές δημοσιεύσεις.

---

# 13. Κανόνας γεωγραφικής αντιστοίχισης

Να μη γίνεται φιλτράρισμα μόνο με βάση την έδρα του φορέα.

Η αντιστοίχιση πρέπει να βασίζεται συνδυαστικά σε:

- NUTS
- τόπο εκτέλεσης
- τίτλο
- τεχνική περιγραφή
- διακήρυξη
- τοπωνύμια
- aliases
- αναθέτουσα αρχή
- Περιφερειακή Ενότητα
- Δήμο

---

# 14. Ενσωμάτωση στο repository

Αποθήκευσε το παρόν ως:

`docs/SOURCE_WHITELIST.md`

και το συνοδευτικό YAML ως:

`config/sources.yml`

Το `AGENTS.md` πρέπει να ορίζει ότι:

- οι πηγές ελέγχονται με σειρά προτεραιότητας,
- κάθε αποτυχία source adapter καταγράφεται,
- η σάρωση δεν θεωρείται πλήρης όταν αποτυγχάνει βασική πηγή,
- κάθε URL και ημερομηνία retrieval αποθηκεύονται ως provenance.
