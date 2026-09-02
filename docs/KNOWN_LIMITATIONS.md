# Known Limitations

## Current Operational Limits - 2026-09-02

- The production scheduled run is operational, but the latest inspected run had
  `monitoring_status=WARNING` because `1` source failed and `3` sources had
  health warnings.
- Dashboard visibility means candidate/focus relevance, not verified active
  status. The current production dashboard reports `0` `VERIFIED_ACTIVE` rows.
- Reverse Pricing is not a production-complete workflow. The inspected local
  pricing database has pilot data but no `pricing_budget_audit` state on
  `pricing_projects`.
- GEO_AFOI statistics exclude rows marked `NEEDS_REVIEW`. The remaining review
  rows are `77.34Ν`, `N.5354.1`, `ΝΕΟ N/4720.A.2.1` and `Σ.72`.
- The production deploy script currently depends on droplet-local key selection
  through `GIT_SSH_COMMAND`; a rebuilt droplet must recreate that operational
  setting unless it is moved into tracked deployment automation.

1. Οι δημόσιες σελίδες μπορεί να απαιτούν JavaScript και προσωρινές
   συνεδρίες.
2. Δεν είναι δεδομένο ότι κάθε επίσημη ιστοσελίδα διαθέτει πλήρες
   πακέτο συνημμένων.
3. Σαρωμένα PDF μπορεί να απαιτούν OCR και χειροκίνητη επιβεβαίωση.
4. Η κατάσταση διαγωνισμού είναι χρονικά μεταβαλλόμενη.
5. Οι search engines είναι discovery εργαλεία, όχι τελική απόδειξη.
6. Η έννοια «πανελλαδικά όλα» απαιτεί μετρήσιμη κάλυψη και μηδενικές
   ανεξήγητες αποτυχίες.
7. Τα subscription sources, όπως η πλατφόρμα ΤΕΕ, απαιτούν ξεχωριστή πολιτική
   credentials και έλεγχο όρων χρήσης πριν μπουν σε παραγωγική ροή.
8. Το official attachment listing έχει αποδειχθεί για τους διαγωνισμούς
   `221744`, `221380`, `221629` και `221675`, αλλά το controlled bulk `Λήψη`
   έχει αποδειχθεί πλήρως μόνο για τα δείγματα `221744` και `221675`.
9. Η εξαγωγή κειμένου PDF γίνεται με `pypdf` και δεν καλύπτει OCR για
   σκαναρισμένα έγγραφα.
10. Το πρώτο search profile matching είναι phrase/term matching με βασικό
    dedup, αλλά δεν κάνει ακόμα stemming, aliases expansion ή semantic scoring.
11. Τα attachment rows του ΕΣΗΔΗΣ μπορεί να φτάνουν με καθυστερημένο Oracle
    ADF stream μετά το click στην καρτέλα `Συνημμένα Αρχεία`. Ο adapter πρέπει
    να περιμένει το `t1::db` table και τα download controls πριν κάνει snapshot.
