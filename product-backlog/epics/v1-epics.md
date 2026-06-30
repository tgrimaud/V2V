# V1 Epics - Assistant vocal d'explication de facture

## EPIC-001 - Identifier le client et recuperer son contexte de facturation

**Status:** Ready for review  
**Priority:** High  
**Outcome:** Le bot sait pour quel client il travaille et dispose du contexte de facturation necessaire avant d'expliquer une difference de prix.

### Scope

- Identifier le client depuis le canal d'activation lorsque c'est possible.
- Recuperer les factures, periodes et donnees billing utiles depuis la source de verite BSS.
- Detecter les cas ou l'identification ou les donnees sont insuffisantes.

### MVP Delivery Slice

- Accepter un contexte client deja fourni par le canal ou par un jeu de donnees pilote.
- Recuperer au moins deux periodes de facturation comparables pour un client identifie.
- Bloquer l'explication quand l'identite, les periodes ou les donnees minimales ne sont pas fiables.
- Produire un resultat fonctionnel exploitable par EPIC-002, sans imposer encore le mecanisme cible d'identification telephone ou web.

### Out of Scope MVP

- Enrolement client complet.
- Authentification forte definie de bout en bout.
- Modification ou correction de donnees BSS.

### Business Rules

| ID | Rule |
|----|------|
| BR-001-1 | Le bot ne doit expliquer une facture que pour un client identifie avec un niveau de confiance suffisant. |
| BR-001-2 | Si le client ou la periode ne peut pas etre determine, le bot doit demander une clarification ou escalader. |
| BR-001-3 | Les donnees BSS en lecture seule sont la source de verite pour les factures et le contexte client. |

### User Stories

- US-001 - Identifier le client au debut de l'echange.
- US-002 - Recuperer les factures disponibles.
- US-003 - Detecter les donnees BSS insuffisantes.

### Open Questions

- OQ-001 - Comment l'identite client est-elle etablie par telephone et par web vocal ?
- OQ-003 - Quelle granularite BSS est disponible pour les factures et evenements billing ?

---

## EPIC-002 - Comparer deux factures ou periodes de facturation

**Status:** Ready for delivery split  
**Priority:** High  
**Outcome:** Le systeme identifie les ecarts de prix entre deux factures ou periodes et produit une analyse causale metier.

### Scope

- Comparer les lignes apparues, disparues ou modifiees.
- Identifier les variations de consommation, remises, proratas, options, taxes, frais ponctuels et regularisations.
- Calculer un delta global et des deltas par cause.

### MVP Delivery Slice

- Comparer deux periodes explicitement selectionnees ou la derniere periode avec la precedente.
- Identifier les lignes apparues, disparues et modifiees avec leur contribution au delta global.
- Regrouper les differences dans un nombre limite de categories metier V1 : remise expiree, option/service, consommation hors forfait, prorata, frais ponctuel, regularisation, taxe, autre.
- Declarer l'analyse incomplete quand la somme des causes tracees ne couvre pas le delta de maniere suffisante.

### Out of Scope MVP

- Prediction de prochaine facture.
- Negociation commerciale ou proposition automatique de geste.
- Analyse multi-clients ou multi-contrats complexe au-dela du contexte client fourni.

### Business Rules

| ID | Rule |
|----|------|
| BR-002-1 | Le delta global doit etre explique par une somme de causes tracables ou declare incomplet. |
| BR-002-2 | Les causes doivent etre classees par impact decroissant lorsque l'information est disponible. |
| BR-002-3 | Le LLM ne doit pas calculer les montants d'ecart ; il ne fait que formuler l'explication. |

### User Stories

- US-004 - Selectionner deux factures ou periodes a comparer.
- US-005 - Identifier les lignes et montants qui changent.
- US-006 - Identifier les causes metier principales.

---

## EPIC-003 - Expliquer les ecarts de facture avec preuves

**Status:** Ready for review  
**Priority:** High  
**Outcome:** Le client recoit une explication claire, fiable et appuyee sur des preuves BSS et des regles tarifaires.

### Scope

- Produire une synthese orale claire.
- Citer les preuves BSS utilisees.
- Enrichir l'explication par la base de connaissance tarifaire.
- Distinguer cause certaine, cause probable et donnee manquante.

### MVP Delivery Slice

- Commencer chaque explication par le delta global et le sens de variation.
- Presenter les causes par impact decroissant, avec un montant quand il est confirme.
- Associer chaque cause confirmee a au moins une preuve BSS visible ou citable.
- Utiliser la base de connaissance uniquement pour expliquer une regle, jamais pour inventer un montant ou une cause.
- Basculer vers une formulation prudente ou une escalade quand les preuves sont insuffisantes.

### Out of Scope MVP

- Reponse juridique engageante.
- Garantie de resolution commerciale.
- Explication d'une regle tarifaire non presente dans la base de connaissance ou les donnees BSS.

### Business Rules

| ID | Rule |
|----|------|
| BR-003-1 | Chaque explication doit etre rattachee a au moins une preuve BSS ou signaler son absence. |
| BR-003-2 | La base de connaissance explique les regles, mais ne remplace jamais les faits BSS. |
| BR-003-3 | Le bot doit refuser de conclure quand les preuves disponibles sont insuffisantes. |

### User Stories

- US-007 - Recevoir une synthese des causes de hausse ou baisse.
- US-008 - Obtenir les preuves associees a chaque cause.
- US-009 - Expliquer une regle tarifaire associee a l'ecart.

### Open Questions

- OQ-002 - Quel niveau de preuve minimal permet de repondre sans escalade ?

---

## EPIC-004 - Offrir le parcours Voice2Voice par telephone

**Status:** Draft  
**Priority:** High  
**Outcome:** Un client peut appeler le bot, poser sa question oralement et recevoir une reponse orale fiable.

### Scope

- Demarrer une conversation vocale par telephone.
- Comprendre une question de facturation.
- Repondre oralement avec une latence percue acceptable.
- Gerer les clarifications et l'escalade.

### Business Rules

| ID | Rule |
|----|------|
| BR-004-1 | Le canal telephone doit permettre une interaction voix vers voix de bout en bout. |
| BR-004-2 | Si l'analyse prend du temps, le bot doit accuser reception oralement avant de livrer l'explication. |
| BR-004-3 | Le client doit pouvoir demander un conseiller humain a tout moment. |

### User Stories

- US-010 - Appeler le bot pour demander une explication de facture.
- US-011 - Recevoir un accuse de reception vocal lorsque l'analyse prend du temps.
- US-012 - Demander oralement un transfert vers conseiller.

---

## EPIC-005 - Offrir le parcours Voice2Voice sur page web

**Status:** Draft  
**Priority:** High  
**Outcome:** Un client peut utiliser une page web pour parler au bot et recevoir une reponse orale, avec un support visuel.

### Scope

- Demarrer une conversation vocale depuis la page web.
- Afficher la synthese et les preuves quand elles sont disponibles.
- Permettre l'ecrit comme canal complementaire.

### Business Rules

| ID | Rule |
|----|------|
| BR-005-1 | Le web vocal doit fournir le meme niveau de fiabilite metier que le canal telephone. |
| BR-005-2 | Le canal ecrit ne remplace pas l'exigence Voice2Voice, il la complete. |
| BR-005-3 | Les preuves affichees doivent correspondre a l'explication donnee oralement. |

### User Stories

- US-013 - Poser une question par chat vocal web.
- US-014 - Lire la synthese de l'explication sur la page web.
- US-015 - Utiliser l'ecrit pour completer une question vocale.

---

## EPIC-006 - Escalader vers un agent humain

**Status:** Draft  
**Priority:** High  
**Outcome:** Le client est transfere vers un agent humain lorsqu'il le demande ou lorsque le bot ne peut pas repondre avec certitude.

### Scope

- Detecter une demande explicite de conseiller.
- Detecter l'incertitude metier.
- Transmettre le contexte collecte a l'agent humain.

### Business Rules

| ID | Rule |
|----|------|
| BR-006-1 | Toute demande explicite de conseiller doit declencher un parcours d'escalade. |
| BR-006-2 | Le bot doit escalader lorsqu'il manque des preuves suffisantes pour expliquer l'ecart. |
| BR-006-3 | Le contexte transmis doit eviter au client de repeter toute sa demande. |

### User Stories

- US-016 - Etre transfere sur demande explicite.
- US-017 - Etre transfere quand le bot n'a pas assez de certitude.
- US-018 - Fournir a l'agent humain un resume exploitable.

---

## EPIC-007 - Fournir une synthese web et les preuves associees

**Status:** Draft  
**Priority:** Medium  
**Outcome:** Le client ou le conseiller peut consulter une vue claire des causes d'ecart et des preuves associees.

### Scope

- Afficher le delta global.
- Afficher les causes principales.
- Afficher le detail ligne par ligne lorsque disponible.
- Rendre visible le niveau de certitude.

### User Stories

- US-019 - Consulter le delta global.
- US-020 - Consulter le detail des causes.
- US-021 - Voir les preuves et limites de l'analyse.

---

## EPIC-008 - Garantir confiance, securite et audit

**Status:** Draft  
**Priority:** High  
**Outcome:** L'usage du bot respecte les contraintes de donnees sensibles, d'acces BSS et de tracabilite.

### Scope

- Controle d'acces par role ou contexte.
- Masquage des donnees personnelles non necessaires.
- Journalisation des consultations.
- Reponses prudentes en cas de donnees manquantes.

### User Stories

- US-022 - Proteger les donnees personnelles exposees au client.
- US-023 - Journaliser les consultations sensibles.
- US-024 - Signaler les limites de l'analyse.

---

## EPIC-009 - Piloter qualite conversationnelle et performance V1

**Status:** Draft  
**Priority:** Medium  
**Outcome:** L'equipe peut mesurer la qualite du parcours Voice2Voice et la performance de l'explication de facture.

### Scope

- Mesurer la latence percue et le first audio.
- Suivre les transferts vers agent humain.
- Suivre les cas non resolus.
- Suivre la qualite des explications.

### User Stories

- US-025 - Mesurer les temps cles du parcours vocal.
- US-026 - Suivre les escalades et leurs raisons.
- US-027 - Suivre les questions non resolues.
