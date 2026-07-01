# Galaxion Billing - Contrat V1 initial

## Sources analysees

Swaggers analyses :

| Service | URL OpenAPI | Version | Paths | Schemas |
|---------|-------------|---------|-------|---------|
| `billing-api` | `https://billing-api.rke-itsf-devgalaxioncore-prd.itsf.io/v3/api-docs` | `1.4.0-SNAPSHOT` | 26 | 34 |
| `billing-service` | `https://billing-service.rke-itsf-devgalaxioncore-prd.itsf.io/v3/api-docs` | `2.5.0-SNAPSHOT` | 7 | 5 |

## Lecture rapide

Decision mise a jour : `billing-service` n'est plus utilise. La cible V1 doit
utiliser uniquement `billing-api` pour le perimetre Billing.

`billing-service` reste documente ci-dessous uniquement comme reference
historique de l'analyse. Il ne doit pas etre implemente dans le mock V1, ni etre
utilise par le backend Voice Support Bot.

`billing-api` expose des endpoints de bill runs, periodes de facturation et
factures. Pour la V1 Voice Support Bot, les endpoints directement utiles sont :

- `/bill-periods`
- `/bill-periods/{bill_period_id}`
- `/bill-runs/{bill_run_id}/bill-run-accounts/search`
- `/bill-run-documents/search`
- `/bill-run-documents/{document_id}/download`

Flux cible : bill periods -> bill runs -> bill run accounts -> documents de
facture -> PDF facture -> extraction structuree.

## Decision d'integration

| Sujet | Decision |
|-------|----------|
| Source Billing cible | `billing-api` uniquement |
| `billing-service` | Non utilise / hors cible V1 |
| Recherche facture/document | `GET /bill-run-documents/search` |
| Telechargement facture/document | `GET /bill-run-documents/{document_id}/download` |
| Detail facture exploitable | Extraction structuree depuis le PDF facture |
| Selection des periodes | `GET /bill-periods?year={year}` |
| Lien compte -> facture | `GET /bill-runs/{bill_run_id}/bill-run-accounts/search` |
| Mock V1 | Reproduire les endpoints utiles de `billing-api`, pas ceux de `billing-service` |

## Billing-service non retenu

`billing-service` expose des endpoints plus proches du parcours client, mais il
n'est plus utilise dans Galaxion pour ce besoin. Cette section reste en archive
pour expliquer pourquoi il ne doit pas etre pris comme dependance V1.

### Historique de factures par compte non retenu

```text
GET /api/v1/accounts/{account_id}/invoices
```

Parametres :

| Nom | In | Obligatoire | Type | Usage V1 |
|-----|----|-------------|------|----------|
| `account_id` | path | oui | string | Compte client |
| `galaxion-user-type` | header | oui | string | Contexte utilisateur Galaxion |
| `galaxion-user-identifier` | header | oui | string | Identifiant utilisateur Galaxion |

Reponses documentees :

| Code | Description | Schema |
|------|-------------|--------|
| 200 | Success | `InvoiceHistoryResponse[]` |
| 401 | Unauthorized, problem title `access-not-authorized` | `InvoiceHistoryResponse[]` dans le Swagger |
| 404 | Account not found, problem title `account-not-found` | `InvoiceHistoryResponse[]` dans le Swagger |

Champs utiles de `InvoiceHistoryResponse` :

| Champ | Type | Usage V1 |
|-------|------|----------|
| `invoiceNumber` | int64 | Cle principale pour recuperer la facture |
| `amount` | int64 | Montant facture, unite a confirmer |
| `invoiceDate` | date | Date facture |
| `dueDate` | date | Date d'echeance |

Lecture :

Cet endpoint semblait repondre directement au besoin "lister les
factures/periodes" pour un compte, mais il ne doit pas etre utilise dans la cible
V1 car `billing-service` est hors usage.

### Recuperer le PDF facture non retenu

```text
GET /api/v1/invoices/{invoice_number}?accountId={accountId}&optionalInvoice={optionalInvoice}
```

Parametres utiles :

| Nom | In | Obligatoire | Type | Usage V1 |
|-----|----|-------------|------|----------|
| `invoice_number` | path | oui | int64 | Numero facture |
| `accountId` | query | oui | string | Compte client |
| `optionalInvoice` | query | non | boolean | Option facture |
| `galaxion-user-type` | header | oui | string | Contexte utilisateur Galaxion |
| `galaxion-user-identifier` | header | oui | string | Identifiant utilisateur Galaxion |

Reponse :

```text
200 -> application/pdf
```

Lecture V1 :

Le PDF n'est pas le meilleur support pour le moteur deterministe, mais il peut
servir de preuve ou de fallback humain. Il ne doit pas devenir la source
principale de calcul si des donnees structurees existent.

### Recuperer les details de facture non retenu

```text
GET /api/v1/invoices/{invoice_number}/details
```

Parametres :

| Nom | In | Obligatoire | Type |
|-----|----|-------------|------|
| `invoice_number` | path | oui | int64 |
| `galaxion-user-type` | header | oui | string |
| `galaxion-user-identifier` | header | oui | string |

Reponse :

```text
200 -> InvoiceDetailsResponse
```

Schema documente :

| Champ | Type | Usage V1 |
|-------|------|----------|
| `accountId` | string | Compte client |
| `invoiceNumber` | int64 | Numero facture |

Lecture V1 :

Le Swagger documente seulement `accountId` et `invoiceNumber`. Cela peut vouloir
dire que le schema est incomplet dans la documentation, ou que le vrai detail est
porte par les CSV/PDF ou par `billing-api`. Avant de conclure, il faut tester un
exemple reel de reponse ou demander un payload anonymise.

### Rapports CSV facture non retenus

```text
GET /api/v1/invoices/{invoice_number}/detail-report
GET /api/v1/invoices/{invoice_number}/summary-report
```

Reponse :

```text
200 -> text/csv
```

Lecture V1 :

Ces endpoints ne doivent pas etre reproduits dans le mock V1 tant que
`billing-service` reste hors cible.

## Billing-api

### Endpoints retenus pour le mock V1

### Recuperer les periodes de facturation

```text
GET /bill-periods?year={year}
```

Parametres :

| Nom | In | Obligatoire | Type | Notes |
|-----|----|-------------|------|-------|
| `year` | query | oui | integer | Annee des periodes |

Reponse :

```text
200 -> BillPeriodResponse[]
```

Champs utiles :

| Champ | Usage V1 |
|-------|----------|
| `id` | Identifiant Galaxion de la periode |
| `year` | Annee de facturation |
| `month` | Mois de facturation |
| `billRuns[]` | Bill runs associes a la periode |

### Recuperer une periode de facturation

```text
GET /bill-periods/{bill_period_id}
```

Parametres :

| Nom | In | Obligatoire | Type |
|-----|----|-------------|------|
| `bill_period_id` | path | oui | uuid |

Reponse :

```text
200 -> BillPeriodResponse
```

### Rechercher les comptes dans un bill run

```text
GET /bill-runs/{bill_run_id}/bill-run-accounts/search
```

Parametres utiles V1 :

| Nom | In | Obligatoire | Type | Usage V1 |
|-----|----|-------------|------|----------|
| `bill_run_id` | path | oui | uuid | Bill run issu de la periode |
| `accountIdTerm` | query | non | string | Filtrer sur le compte client |
| `billPeriodId` | query | non | uuid | Restreindre a la periode |
| `page` | query | non | integer | Pagination |
| `size` | query | non | integer | Pagination |
| `statuses` | query | non | array | Filtrer les statuts si necessaire |

Reponse :

```text
200 -> PagedResponseBillRunAccountResponse
```

Champs utiles de `BillRunAccountResponse` :

| Champ | Usage V1 |
|-------|----------|
| `id` | `billRunAccountId`, necessaire pour recuperer une facture |
| `accountId` | Compte facture |
| `invoiceNumber` | Numero facture, autre cle possible |
| `status` | Verifier si la facture est exploitable |
| `currentStep` | Diagnostic si facture incomplete |
| `errorType` / `errorMessage` | Cas d'erreur a exposer ou escalader |
| `brand` | Marque |
| `accountType` | B2C/B2B ou equivalent |

### Rechercher les documents de facture

```text
GET /bill-run-documents/search
```

Parametres utiles V1 :

| Nom | In | Obligatoire | Type | Usage V1 |
|-----|----|-------------|------|----------|
| `billRunAccountId` | query | non | uuid | Recherche directe depuis le bill run account |
| `accountId` | query | non | string | Recherche par compte client |
| `invoiceNumber` | query | non | string | Recherche par numero de facture |
| `billPeriodId` | query | non | uuid | Recherche par periode |

Reponse :

```text
200 -> BillRunDocumentResponse[]
```

Champs utiles de `BillRunDocumentResponse` :

| Champ | Type | Usage V1 |
|-------|------|----------|
| `id` | uuid | Identifiant du document a telecharger |
| `filename` | string | Nom du document facture |
| `contentType` | string | Type de contenu du document |

Lecture V1 :

Cet endpoint est le point d'entree pour recuperer une facture/document a partir
d'un ou plusieurs criteres : `billRunAccountId`, `accountId`, `invoiceNumber`,
`billPeriodId`. Il doit etre reproduit dans le mock car il couvre le cas
"retrouver la facture" sans imposer un seul identifiant d'appel.

### Telecharger un document de facture

```text
GET /bill-run-documents/{document_id}/download
```

Parametres :

| Nom | In | Obligatoire | Type | Usage V1 |
|-----|----|-------------|------|----------|
| `document_id` | path | oui | uuid | Document retourne par `/bill-run-documents/search` |
| `billPeriodId` | query | non | uuid | Contexte periode si necessaire |

Reponse :

```text
200 -> application/octet-stream
```

Lecture V1 :

Le document telecharge est la source principale du detail facture lorsque
Galaxion ne fournit pas d'endpoint structure pour les lignes de facture. Le
backend doit extraire les donnees utiles du PDF vers un format interne structure
avant de lancer le moteur de comparaison.

### Recuperer une facture selectionnee

```text
GET /invoices/selected
```

Parametres :

| Nom | In | Obligatoire | Type | Notes |
|-----|----|-------------|------|-------|
| `billRunAccountId` | query | non | uuid | Cle la plus directe si connue |
| `invoiceNumber` | query | non | string | Alternative |
| `billPeriodId` | query | non | uuid | Filtre periode |

Reponse :

```text
200 -> SelectedInvoiceResponse
```

Lecture V1 :

`selected` semble representer la facture selectionnee/calculable, avec les
lignes et sections, mais sans montants composes explicites au niveau facture,
section et item. Les items portent `defaultPrice` en cents, des taxes et des
periodes de reference/effectivite.

### Facture composee non retenue pour le detail facture V1

```text
GET /invoices/composed
```

Parametres :

| Nom | In | Obligatoire | Type | Notes |
|-----|----|-------------|------|-------|
| `billRunAccountId` | query | non | uuid | Cle la plus directe si connue |
| `invoiceNumber` | query | non | string | Alternative |
| `billPeriodId` | query | non | uuid | Filtre periode |

Reponse :

```text
200 -> ComposedInvoiceResponse
```

Lecture :

`invoices/composed` ne correspond pas au besoin courant de recuperation du detail
facture client. Il ne doit pas etre utilise comme source principale pour le mock
V1 tant que son role exact dans Galaxion n'est pas clarifie.

## Extraction PDF facture

Comme aucun endpoint structure de lignes facture n'a ete identifie, la V1 doit
introduire un composant `InvoicePdfExtractor`.

```text
PDF facture Galaxion
        |
        v
InvoicePdfExtractor
        |
        v
Invoice normalisee JSON
        |
        v
Moteur deterministe de comparaison
```

Responsabilites :

- extraire le texte et les tableaux du PDF facture ;
- identifier le total facture, les dates, les sections et les lignes ;
- normaliser les montants, devises, taxes, remises, frais et proratas ;
- produire un JSON interne stable pour le moteur de comparaison ;
- signaler les zones non parsees ou ambigues ;
- verifier que les lignes extraites reconciliant le total dans une tolerance
  definie.

Le LLM ne doit pas lire directement le PDF pour deduire les montants. Il peut
formuler l'explication uniquement apres extraction structuree et validation.

### JSON cible d'extraction

Le format exact sera ajuste apres analyse de PDFs anonymises, mais le mock et
les tests doivent viser une structure de ce type :

```json
{
  "invoice_number": "2025123214540001",
  "account_id": "100231079",
  "period": {
    "start": "2026-06-01",
    "end": "2026-06-30"
  },
  "invoice_date": "2026-07-01",
  "due_date": "2026-07-15",
  "currency": "EUR",
  "total_tax_included": 68.4,
  "lines": [
    {
      "id": "line-1",
      "label": "Mobile plan",
      "category": "subscription",
      "amount_tax_included": 29.99,
      "period_start": "2026-06-01",
      "period_end": "2026-06-30",
      "evidence_text": "Mobile plan ... 29.99 EUR"
    }
  ],
  "warnings": []
}
```

## Schemas utiles hors chemin principal

### `ComposedInvoiceResponse`

Champs eventuellement utiles si `invoices/composed` est requalifie plus tard :

| Champ | Type | Usage |
|-------|------|-------|
| `id` | uuid | Identifiant facture |
| `billRunAccountId` | uuid | Cle de facture dans le bill run |
| `billRunId` | uuid | Bill run source |
| `accountId` | string | Compte facture |
| `invoiceNumber` | string | Numero facture |
| `dueDate` | date | Date d'echeance |
| `usagePeriod` | `BillingPeriodResponse` | Periode d'usage |
| `recurringPeriod` | `BillingPeriodResponse` | Periode recurrente |
| `brand` | string | Marque |
| `accountType` | string | Type de compte |
| `sections[]` | `ComposedSectionResponse[]` | Sections facture |
| `items[]` | `ComposedItemResponse[]` | Items facture |
| `taxes[]` | `ComposedTaxResponse[]` | Taxes facture |
| `amount` | `AmountResponse` | Total HT/TTC |
| `balanceChanges[]` | `BalanceChangeResponse[]` | Changements de solde |

### `ComposedItemResponse`

Champs utiles V1 :

| Champ | Type | Usage |
|-------|------|-------|
| `id` | uuid | Identifiant ligne |
| `code` | string | Code catalogue/billing |
| `description` | string | Libelle client/metier |
| `type` | string | Type ligne : recurring, one-off, usage, etc. a confirmer |
| `defaultPrice` | integer cents | Prix par defaut |
| `amount` | `AmountResponse` | Montant compose HT/TTC |
| `taxes[]` | `ComposedTaxResponse[]` | Taxes associees |
| `volume` | integer | Volume usage si applicable |
| `percentage` | number | Pour remise ou taxe si applicable |
| `effectiveAt` | date-time | Date d'effet one-off |
| `frequency` | string | Frequence recurrente |
| `referencePeriod` | `BillingPeriodResponse` | Periode de reference |
| `effectivePeriod` | `BillingPeriodResponse` | Periode d'effectivite |
| `metadata` | object | Donnees additionnelles a inspecter sur exemples reels |

### `AmountResponse`

| Champ | Type | Usage |
|-------|------|-------|
| `amountTaxesExcluded` | number | Montant HT |
| `amountTaxesIncluded` | number | Montant TTC |

Attention : `defaultPrice` est en cents, alors que `AmountResponse` est expose
comme `number`. Il faudra verifier si ces montants sont en euros ou en cents via
des exemples reels.

## Flux cible pour recuperer deux factures

Flux a valider avec exemples reels :

1. Recuperer les periodes via `GET /bill-periods?year={year}`.
2. Choisir les deux periodes comparables, par exemple mois courant et mois
   precedent.
3. Recuperer les `billRuns[]` associes aux periodes.
4. Pour chaque bill run, appeler
   `GET /bill-runs/{bill_run_id}/bill-run-accounts/search?accountIdTerm={accountId}&billPeriodId={billPeriodId}`.
5. Extraire `BillRunAccountResponse.id` comme `billRunAccountId` et
   `invoiceNumber`.
6. Rechercher les documents facture via
   `GET /bill-run-documents/search?billRunAccountId={billRunAccountId}` ou
   `GET /bill-run-documents/search?accountId={accountId}&invoiceNumber={invoiceNumber}`.
7. Telecharger le PDF facture via
   `GET /bill-run-documents/{document_id}/download`.
8. Extraire le PDF avec `InvoicePdfExtractor`.
9. Utiliser le JSON normalise extrait pour le moteur de comparaison.

## Mapping vers le domaine Voice Support Bot

| Domaine cible | Source |
|---------------|--------|
| `Invoice.number` | PDF extrait / `BillRunDocumentResponse.filename` / critere `invoiceNumber` |
| `Invoice.accountId` | Critere de recherche `accountId` ou PDF extrait |
| `Invoice.totalAmount` | PDF extrait |
| `Invoice.period` | PDF extrait |
| `InvoiceLine.id` | Identifiant interne d'extraction |
| `InvoiceLine.label` | PDF extrait |
| `InvoiceLine.type` | Classification post-extraction |
| `InvoiceLine.amount` | PDF extrait |
| `InvoiceLine.volume` | PDF extrait si present |
| `InvoiceLine.evidenceText` | Fragment de texte PDF source |
| `Evidence.source` | `billing-api` |
| `Evidence.documentId` | `BillRunDocumentResponse.id` |
| `Evidence.documentFilename` | `BillRunDocumentResponse.filename` |
| `Evidence.documentContentType` | `BillRunDocumentResponse.contentType` |

## Endpoints a reproduire dans le mock

Pour un premier mock API-compatible, reproduire uniquement cote `billing-api` :

- `GET /bill-periods?year={year}`
- `GET /bill-periods/{bill_period_id}`
- `GET /bill-runs/{bill_run_id}/bill-run-accounts/search`
- `GET /bill-run-documents/search`
- `GET /bill-run-documents/{document_id}/download`

`GET /invoices/selected` est utile en second temps pour verifier la difference
entre facture selectionnee et facture composee, mais il n'est pas dans le chemin
principal V1.

## Questions ouvertes

- Quel flux exact permet, depuis un `accountId`, de retrouver les deux derniers
  `billRunAccountId` exploitables dans `billing-api` ?
- Quels `contentType` sont retournes par `/bill-run-documents/search` pour les
  factures : PDF, CSV, JSON, autre ?
- Le document telecharge contient-il seulement le PDF client, ou aussi un export
  structure exploitable ?
- Quel moteur d'extraction PDF utiliser pour obtenir texte et tableaux avec une
  qualite suffisante ?
- Quelle tolerance de reconciliation accepter entre somme des lignes extraites et
  total facture ?
- Quels statuts de `BillRunAccountResponse.status` indiquent qu'une facture est
  exploitable par le bot ?
- Les lignes remises, proratas, regularisations et hors forfait sont-elles
  distinguables dans le PDF seul, ou faut-il enrichir avec `discounts-service`,
  `adjustments-service` et `CDR` ?
- Quel format d'erreur standard Galaxion faut-il reproduire dans le mock ?

## Conclusion provisoire

Conclusion mise a jour :

- utiliser `billing-api` uniquement pour le perimetre Billing ;
- reproduire le flux `bill-periods -> bill-runs -> bill-run-accounts ->
  bill-run-documents/search -> download` dans le mock ;
- ajouter un composant `InvoicePdfExtractor` pour transformer le PDF en JSON
  structure ;
- ne pas implementer les endpoints `billing-service` dans le mock V1.

## Prochaine analyse

Analyser un exemple reel ou anonymise du flux `billing-api` :

- periodes disponibles via `GET /bill-periods?year={year}` ;
- bill runs associes a une periode ;
- recherche `BillRunAccount` pour un `accountId` ;
- recherche document via `GET /bill-run-documents/search` avec un ou plusieurs
  criteres ;
- telechargement document via `GET /bill-run-documents/{document_id}/download` ;
- extraction du PDF vers le JSON cible.

Puis analyser `accounts-service`, `contracts-service`, `discounts-service` et
`CDR` pour les causes metier.
