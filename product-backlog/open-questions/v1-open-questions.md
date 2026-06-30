# V1 Open Questions

## OQ-001 - Identification client par canal telephone et web

**Status:** Open  
**Owner:** Product / BSS / Security  
**Impacts:** EPIC-001, EPIC-004, EPIC-005, EPIC-008

### Question

Comment l'identite du client est-elle etablie sur chaque canal ?

### Why It Matters

Le bot ne doit expliquer une facture que pour un client identifie avec un niveau
de confiance suffisant. Le niveau d'identification conditionne l'acces aux
donnees BSS, le niveau de detail affiche ou prononce, et les cas d'escalade.

### Needed Decision

- Source d'identite par telephone.
- Source d'identite par web vocal.
- Niveau de confiance minimal pour acceder au contexte facture.
- Comportement produit lorsque l'identite est incomplete.

---

## OQ-002 - Niveau de preuve minimal pour repondre sans escalade

**Status:** Open  
**Owner:** Product / Billing SME / Legal  
**Impacts:** EPIC-003, EPIC-006, EPIC-008

### Question

Quel niveau de preuve est necessaire pour que le bot puisse confirmer une cause
d'ecart de facture sans transferer vers un agent humain ?

### Why It Matters

Une reponse non prouvee peut induire le client en erreur. Un seuil trop strict
peut au contraire provoquer trop d'escalades.

### Needed Decision

- Causes que le bot peut confirmer seul.
- Causes que le bot peut presenter comme probables.
- Causes qui imposent une escalade.
- Formulation attendue quand la certitude est insuffisante.

---

## OQ-003 - Disponibilite et granularite des donnees BSS

**Status:** Open  
**Owner:** BSS owner  
**Impacts:** EPIC-001, EPIC-002, EPIC-003

### Question

Quelles donnees BSS sont disponibles en lecture pour expliquer les ecarts de
facture ?

### Why It Matters

Le moteur de comparaison et les preuves affichables dependent directement de la
granularite disponible : lignes de facture, consommations, remises, proratas,
options, taxes, evenements billing, changements d'offre.

### Needed Decision

- Donnees accessibles en V1.
- Historique disponible.
- Fraicheur attendue des donnees.
- Limites d'acces ou de confidentialite.
