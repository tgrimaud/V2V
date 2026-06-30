# Voice Support Bot - Product Backlog

Depot local dedie au backlog produit du Voice Support Bot.

Objectif : conserver un decoupage EPIC / User Stories lisible en Markdown,
versionnable localement, puis migrable vers Jira lorsque l'outillage sera pret.

## Produit V1

Assistant vocal d'analyse de facturation operateur, cible utilisateurs finaux,
accessible par telephone et par chat vocal web, connecte en lecture au BSS,
capable de comparer deux factures ou periodes client, d'identifier les causes
metier des ecarts de prix, puis de produire une explication orale claire,
fiable et tracable.

## Principes Product / Business

- Rester au niveau probleme, besoin, valeur, regles metier et acceptance.
- Ne pas decrire d'API, schema, table, framework ou detail d'implementation
  dans les stories produit.
- Ne pas inventer les faits manquants : les mettre en open questions.
- Garder les acceptance criteria observables par un utilisateur, un conseiller,
  un auditeur ou un metier.
- Tracer les regles metier importantes vers des scenarios d'acceptance.

## Structure

```text
epics/
  EPIC-001-*.md
stories/
  US-001-*.md
decisions/
  DEC-001-*.md
open-questions/
  OQ-001-*.md
```

## Etats

- `Draft` : brouillon en cours.
- `Ready for review` : pret a relire avec Product / Architecture / Security.
- `Ready for delivery split` : peut etre decoupe en taches techniques.
- `Blocked` : decision externe requise.
- `Done` : livre ou remplace par un artefact Jira.

## Conventions

- EPIC keys : `EPIC-001`, `EPIC-002`, ...
- User story keys : `US-001`, `US-002`, ...
- Open questions : `OQ-001`, `OQ-002`, ...
- Decisions : `DEC-001`, `DEC-002`, ...

Chaque story doit referencer son EPIC parent et contenir des acceptance criteria
en langage produit.
