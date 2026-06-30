# Galaxion Billing - Contrat V1 initial

## Sources analysees

Swaggers analyses :

| Service | URL OpenAPI | Version | Paths | Schemas |
|---------|-------------|---------|-------|---------|
| `billing-api` | `https://billing-api.rke-itsf-devgalaxioncore-prd.itsf.io/v3/api-docs` | `1.4.0-SNAPSHOT` | 26 | 34 |
| `billing-service` | `https://billing-service.rke-itsf-devgalaxioncore-prd.itsf.io/v3/api-docs` | `2.5.0-SNAPSHOT` | 7 | 5 |

## Lecture rapide

La verite d'integration semble etre entre les deux services :

- `billing-service` est le meilleur point de depart pour retrouver les factures
  d'un compte : il expose directement l'historique par `accountId`.
- `billing-api` expose une facture composee plus riche pour la comparaison
  detaillee, mais son acces passe par les concepts de bill periods, bill runs et
  bill run accounts.

`billing-api` expose des endpoints de bill runs, periodes de facturation et
factures. Pour la V1 Voice Support Bot, les endpoints directement utiles sont :

- `/bill-periods`
- `/bill-periods/{bill_period_id}`
- `/bill-runs/{bill_run_id}/bill-run-accounts/search`
- `/invoices/selected`
- `/invoices/composed`

`billing-service` expose des endpoints plus proches du parcours client :

- `/api/v1/accounts/{account_id}/invoices`
- `/api/v1/invoices/{invoice_number}`
- `/api/v1/invoices/{invoice_number}/details`
- `/api/v1/invoices/{invoice_number}/detail-report`
- `/api/v1/invoices/{invoice_number}/summary-report`

Hypothese actuelle : demarrer le mock par `billing-service` pour l'historique de
factures et utiliser `billing-api` si le detail structure necessaire a la
comparaison n'est pas disponible dans `billing-service`.

## Billing-service

### Historique de factures par compte

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

Lecture V1 :

Cet endpoint repond directement au besoin "lister les factures/periodes" pour un
compte. C'est le meilleur candidat pour selectionner les deux factures a
comparer, sous reserve de confirmer l'unite du champ `amount` et le lien avec
les periodes de facturation.

### Recuperer le PDF facture

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

### Recuperer les details de facture

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

### Rapports CSV facture

```text
GET /api/v1/invoices/{invoice_number}/detail-report
GET /api/v1/invoices/{invoice_number}/summary-report
```

Reponse :

```text
200 -> text/csv
```

Lecture V1 :

Ces endpoints peuvent contenir les lignes de facture exploitables si
`InvoiceDetailsResponse` est trop pauvre. Ils sont interessants pour le mock si
le BSS reel utilise deja ces exports comme source de detail facture.

## Billing-api

### Endpoints retenus pour le mock V1 candidat

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

### Recuperer une facture composee

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

Lecture V1 :

`composed` est le meilleur candidat pour le moteur de comparaison car il expose
des montants composes :

- `amount` au niveau facture ;
- `amount` au niveau section ;
- `amount` au niveau item ;
- taxes composees avec `amount`.

## Schemas utiles

### `ComposedInvoiceResponse`

Champs utiles V1 :

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

## Flux candidat pour recuperer deux factures

Flux hypothese a valider avec exemples reels :

1. Recuperer les periodes via `GET /bill-periods?year={year}`.
2. Choisir les deux periodes comparables, par exemple mois courant et mois
   precedent.
3. Recuperer les `billRuns[]` associes aux periodes.
4. Pour chaque bill run, appeler
   `GET /bill-runs/{bill_run_id}/bill-run-accounts/search?accountIdTerm={accountId}&billPeriodId={billPeriodId}`.
5. Extraire `BillRunAccountResponse.id` comme `billRunAccountId` et
   `invoiceNumber`.
6. Recuperer la facture composee via
   `GET /invoices/composed?billRunAccountId={billRunAccountId}`.
7. Utiliser `ComposedInvoiceResponse.amount`, `sections[]`, `items[]` et
   `taxes[]` pour le moteur de comparaison.

## Mapping vers le domaine Voice Support Bot

| Domaine cible | Source billing-api |
|---------------|--------------------|
| `Invoice.id` | `ComposedInvoiceResponse.id` |
| `Invoice.number` | `invoiceNumber` |
| `Invoice.accountId` | `accountId` |
| `Invoice.totalAmount` | `amount.amountTaxesIncluded` |
| `Invoice.period` | `usagePeriod` ou `recurringPeriod`, a confirmer |
| `InvoiceLine.id` | `ComposedItemResponse.id` |
| `InvoiceLine.code` | `ComposedItemResponse.code` |
| `InvoiceLine.label` | `ComposedItemResponse.description` |
| `InvoiceLine.type` | `ComposedItemResponse.type` |
| `InvoiceLine.amount` | `ComposedItemResponse.amount.amountTaxesIncluded` |
| `InvoiceLine.volume` | `ComposedItemResponse.volume` |
| `InvoiceLine.effectiveAt` | `ComposedItemResponse.effectiveAt` |
| `InvoiceLine.referencePeriod` | `ComposedItemResponse.referencePeriod` |
| `InvoiceLine.effectivePeriod` | `ComposedItemResponse.effectivePeriod` |
| `Tax.amount` | `ComposedTaxResponse.amount` |
| `Tax.rate` | `ComposedTaxResponse.rate` |
| `Evidence.source` | `billing-api` |

## Endpoints a reproduire dans le mock

Pour un premier mock API-compatible, reproduire en priorite cote
`billing-service` :

- `GET /api/v1/accounts/{account_id}/invoices`
- `GET /api/v1/invoices/{invoice_number}/details`
- `GET /api/v1/invoices/{invoice_number}/detail-report`, si les lignes sont
  dans le CSV

Ajouter cote `billing-api` si le detail structure de facture n'est pas suffisant
dans `billing-service` :

- `GET /bill-periods?year={year}`
- `GET /bill-periods/{bill_period_id}`
- `GET /bill-runs/{bill_run_id}/bill-run-accounts/search`
- `GET /invoices/composed`

`GET /invoices/selected` est utile en second temps pour verifier la difference
entre facture selectionnee et facture composee, mais il n'est pas le meilleur
point de depart pour le moteur de comparaison car les montants composes sont
moins explicites.

## Questions ouvertes

- Le `InvoiceDetailsResponse` de `billing-service` est-il vraiment limite a
  `accountId` et `invoiceNumber`, ou le Swagger est-il incomplet ?
- Les lignes de facture V1 sont-elles dans
  `/api/v1/invoices/{invoice_number}/detail-report` ?
- Le champ `InvoiceHistoryResponse.amount` est-il en cents, euros, ou autre
  unite ?
- Quel est le sens exact de `optionalInvoice` sur le PDF facture ?
- `billing-api` est-il bien la facade recommandee pour consultation client, ou
  seulement une API interne de bill-run ?
- Existe-t-il dans `billing-service` un endpoint plus direct pour lister les
  factures d'un compte ?
- `AmountResponse` est-il en euros, cents, ou unite monetaire dependante du
  contexte ?
- Faut-il utiliser `usagePeriod` ou `recurringPeriod` comme periode principale
  de comparaison ?
- Quels statuts de `BillRunAccountResponse.status` indiquent qu'une facture est
  exploitable par le bot ?
- Les lignes remises, proratas, regularisations et hors forfait sont-elles
  distinguables via `ComposedItemResponse.type`, `code`, `metadata`, ou faut-il
  interroger `discounts-service`, `adjustments-service` et `CDR` ?
- Quel format d'erreur standard Galaxion faut-il reproduire dans le mock ?

## Conclusion provisoire

Preference provisoire :

- utiliser `billing-service` pour l'historique facture et la selection des deux
  factures ;
- verifier par exemple reel si `billing-service` fournit les lignes detaillees ;
- utiliser `billing-api /invoices/composed` comme source de detail structure si
  `billing-service` ne fournit pas les lignes et montants exploitables.

## Prochaine analyse

Analyser un exemple reel ou anonymise de :

- `GET /api/v1/accounts/{account_id}/invoices` ;
- `GET /api/v1/invoices/{invoice_number}/details` ;
- `GET /api/v1/invoices/{invoice_number}/detail-report`.

Si ces exemples ne donnent pas les lignes detaillees, continuer avec
`billing-api /invoices/composed` et analyser `accounts-service`,
`contracts-service`, `discounts-service` et `CDR` pour les causes metier.
