# V1 Decision Log

## DEC-001 - V1 centree sur l'explication de facture

**Status:** Proposed  
**Date:** 2026-06-30

### Decision

La V1 se concentre sur l'explication des ecarts de facture pour les utilisateurs
finaux de l'operateur.

### Rationale

Le besoin prioritaire identifie est la capacite a expliquer pourquoi une facture
change d'une periode a l'autre. Les autres domaines de support restent une
orientation produit future, mais ne doivent pas diluer la V1.

### Implication

Les EPICs V1 priorisent le BSS, la comparaison de facture, l'explication avec
preuves, les parcours Voice2Voice et l'escalade humaine.

---

## DEC-002 - Le BSS est la source de verite

**Status:** Proposed  
**Date:** 2026-06-30

### Decision

Le BSS operateur est la source de verite pour les factures, contrats, offres,
options, remises, consommations, taxes, regularisations et evenements billing.

### Rationale

Le bot ne doit pas inventer les montants ni les causes. Les ecarts doivent etre
calcules a partir des donnees BSS, puis expliques en langage naturel.

### Implication

Le LLM peut reformuler et pedagogiser, mais il ne decide pas seul des causes ni
des montants.

---

## DEC-003 - Voice2Voice obligatoire en V1

**Status:** Proposed  
**Date:** 2026-06-30

### Decision

La V1 doit couvrir les parcours Voice2Voice par telephone et par chat vocal web.
Le canal ecrit est complementaire.

### Rationale

La cible produit est l'utilisateur final, qui doit pouvoir poser sa question
oralement et recevoir une reponse orale.

### Implication

Les EPICs telephone et web vocal sont prioritaires, et la performance percue du
parcours vocal devient un critere produit.

---

## DEC-004 - Gradium et Pipecat comme point de depart

**Status:** Proposed  
**Date:** 2026-06-30

### Decision

Le POC/V1 demarre avec Gradium pour les capacites STT/TTS et Pipecat pour
l'orchestration temps reel du pipeline vocal.

### Rationale

Ces solutions fournissent un point de depart operationnel pour le benchmark et
l'industrialisation progressive.

### Implication

Ces choix restent des adapters de reference. Le coeur produit doit pouvoir
tester ou remplacer les solutions LLM, STT et TTS sans redefinir les besoins
metier.

---

## DEC-005 - Escalade humaine requise

**Status:** Proposed  
**Date:** 2026-06-30

### Decision

Le bot doit pouvoir transferer vers un agent humain lorsque le client le demande
ou lorsque l'IA ne peut pas repondre avec assez de certitude.

### Rationale

L'objectif n'est pas seulement d'automatiser, mais de fournir un parcours fiable
et de confiance. Une absence de preuve doit etre visible et actionnable.

### Implication

Le backlog inclut un EPIC dedie a l'escalade, avec transmission du contexte deja
collecte a l'agent humain.

---

## DEC-006 - Backend metier Java et voice-agent Python

**Status:** Proposed  
**Date:** 2026-06-30

### Decision

La V1 conserve une architecture hybride :

- le backend metier reste en Java/Spring Boot ;
- le voice-agent reste en Python ;
- aucune reecriture du backend metier en Python n'est prevue pour la V1.

### Rationale

Le backend porte les responsabilites critiques de la V1 : acces BSS en lecture,
comparaison deterministe de factures, regles de preuve, audit, securite et API
stables. Java/Spring Boot est adapte a ces besoins entreprise et au modele
hexagonal deja en place.

Python reste le bon choix pour la couche audio et IA temps reel : WebSocket
audio, STT/TTS, integration Gradium, orchestration vocale et prototypage de
providers IA.

### Implication

Le systeme reste separe en deux responsabilites :

- Java/Spring Boot pour le coeur produit fiable, testable et auditable ;
- Python pour le bord vocal temps reel et les integrations audio.

Un worker IA Python pourra etre ajoute plus tard si certaines capacites IA
necessitent un runtime Python dedie, mais il devra rester derriere un contrat
clair et ne pas absorber les regles metier de comparaison facture.
