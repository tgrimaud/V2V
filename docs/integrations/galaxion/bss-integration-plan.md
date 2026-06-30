# Plan d'integration BSS V1

## Objectif

Ce document prepare l'integration du Voice Support Bot avec le BSS operateur
existant.

Le BSS cible est compose de plusieurs microservices. Pour avancer vite sans
attendre tous les acces definitifs, la V1 doit commencer par un mock BSS
contract-compatible : il expose les memes APIs utiles que les microservices BSS
cibles, avec des fixtures realistes et anonymisees.

## Principe d'architecture

Le backend Java ne doit pas consommer directement des fixtures internes
specifiques au bot. Il doit consommer un contrat BSS stable via un adapter.

```text
Voice Support Backend
        |
        | domain port: BillingContextPort / BssCustomerContextPort
        v
BSS adapter
        |
        +--> BSS mock local, API-compatible
        |
        +--> BSS sandbox / reel, meme contrat utile
```

Le mock doit etre remplacable par configuration : URL, authentification et
profil d'environnement. Le domaine de comparaison facture ne doit pas changer
quand on passe du mock au BSS reel.

## Microservices BSS identifies

| Besoin V1 | Microservice source | Priorite | Notes |
|-----------|---------------------|----------|-------|
| Identifier / rechercher un client | `contacts-service` + `accounts-service` | Medium | Peut etre simplifie au debut si le canal fournit deja le client |
| Lister les factures / periodes | `billing-service` ou `billing-api` | High | Necessaire pour selectionner les periodes comparables |
| Recuperer une facture detaillee | `billing-service` ou `billing-api` | High | Necessaire au delta global et aux preuves facture |
| Recuperer les lignes de facture | `billing-service` ou `billing-api` a confirmer | High | Point ouvert : verifier si les lignes sont dans la facture detaillee ou endpoint separe |
| Recuperer remises / options / contrat | `accounts-service`, `contracts-service`, `addons-service`, `discounts-service` | High | Necessaire pour expliquer expiration de remise, option, offre, abonnement |
| Recuperer consommations hors forfait | `cdr-usage-consumption-service` ou `usages-service` | Medium | Necessaire pour expliquer les causes de consommation |
| Recuperer evenements billing | `customer-history-service`, `events-store-service`, `change-offers-service`, `adjustments-service` | High | Activation option, changement offre, regularisation, prorata |

## Catalogue Galaxion fourni

Le BSS cible s'appelle Galaxion. Les Swagger ci-dessous sont les points
d'entree a analyser lorsque l'implementation du mock API-compatible demarre.

| Microservice | Swagger |
|--------------|---------|
| `account-receivable-service` | `https://accounts-receivable-service-v2.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `account-receivable-facade` | `https://account-receivable-facade.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `accounts-service` | `https://accounts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `acquisition-prospects-service` | `https://acquisition-prospects-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `addons-service` | `https://addons-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `addresses-service` | `https://addresses-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `adjustments-service` | `https://adjustments-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `appointments-service` | `https://appointments-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `barrings-service` | `https://barrings-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `billing-cycles-service` | `https://billing-cycles-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `billing-service` | `https://billing-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `billing-api` | `https://billing-api.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `carts-service` | `https://carts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `catalog-service` | `https://catalog-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `cdr-usage-consumption-service` | `https://cdr-usage-consumption-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `change-offers-service` | `https://change-offers-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `collections-service` | `https://collections-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `contract-builder-service` | `https://contract-builder-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `contacts-service` | `https://contacts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `contracts-service` | `https://contracts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `credit-limits-service` | `https://credit-limits-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `credit-scores-service` | `https://credit-scores-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `cross-sell-service` | `https://cross-sell-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `customer-history-service` | `https://customer-history-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `deposits-service` | `https://deposits-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `discounts-service` | `https://discounts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `documents-service` | `https://documents-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `email-sender-service` | `https://email-sender-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `equipments-service` | `https://equipments-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `events-store-service` | `https://events-store-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `iam-facade` | `https://iam-facade.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `notifications-service` | `https://notifications-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `number-swaps-service` | `https://number-swaps-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `otp-verification-service` | `https://otp-verification-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `payments-service` | `https://payments-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `sales-service` | `https://sales-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `search-engine-service` | `https://search-engine-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `search-models-service` | `https://search-models-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `security-questions-service` | `https://security-questions-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `sms-sender-service` | `https://sms-sender-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `top-ups-service` | `https://top-ups-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `unique-references-service` | `https://unique-references-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `usages-service` | `https://usages-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `users-service` | `https://users-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |

## Shortlist Swagger V1

Pour eviter de disperser l'analyse, les premiers Swagger a ouvrir sont :

| Ordre | Microservice | Pourquoi |
|-------|--------------|----------|
| 1 | `billing-api` | Verifier s'il existe une facade plus stable que `billing-service` pour factures et lignes. Analyse comparative initiale : [`galaxion-billing-contracts.md`](galaxion-billing-contracts.md) |
| 2 | `billing-service` | Recuperer historique et details facture. Analyse comparative initiale : [`galaxion-billing-contracts.md`](galaxion-billing-contracts.md) |
| 3 | `accounts-service` | Relier client, compte, abonnement et contexte commercial |
| 4 | `contracts-service` | Recuperer contrat, offre et abonnement actifs sur les periodes comparees |
| 5 | `discounts-service` | Identifier remises, validite et expiration |
| 6 | `addons-service` | Identifier options et services factures |
| 7 | `cdr-usage-consumption-service` | Expliquer les hors-forfait et consommations detaillees |
| 8 | `customer-history-service` | Retrouver les evenements metier utiles a l'explication |
| 9 | `events-store-service` | Verifier s'il contient les evenements techniques/metier manquants |
| 10 | `change-offers-service` | Expliquer les changements d'offre |
| 11 | `adjustments-service` | Expliquer regularisations, ajustements et gestes |
| 12 | `contacts-service` | Identifier ou confirmer le client si le canal ne suffit pas |

## Ordre d'analyse des Swagger

### 1. Billing

Premier Swagger a analyser.

Questions a resoudre :

- Comment lister les factures ou periodes pour un client ?
- Comment identifier la derniere facture et la periode precedente ?
- Comment recuperer le total facture, devise, dates de periode et statut ?
- Les lignes de facture sont-elles incluses dans le detail facture ?
- Les taxes, frais ponctuels, regularisations et proratas sont-ils des lignes
  explicites ou des objets separes ?
- Quels codes erreur existent pour facture introuvable, client introuvable,
  acces interdit et donnees indisponibles ?

Endpoints attendus a reperer :

- list invoices by customer/account ;
- get invoice detail ;
- get invoice lines, si endpoint separe ;
- get billing periods, si distinct des factures.

### 2. Account

Deuxieme Swagger a analyser.

Questions a resoudre :

- Comment recuperer le contrat actif sur une periode donnee ?
- Comment recuperer offre, options et services actifs ?
- Comment recuperer les remises et leurs dates de validite ?
- Comment recuperer les evenements de changement : activation option,
  changement offre, resiliation, remise expiree, geste commercial ?
- Les proratas et regularisations sont-ils portes par `account`, `billing`, ou
  les deux ?

Endpoints attendus a reperer :

- get account / subscription ;
- get active offers and options ;
- get discounts ;
- get account events / lifecycle events.

### 3. CDR

Troisieme Swagger a analyser.

Questions a resoudre :

- Comment recuperer les consommations sur une periode de facturation ?
- Comment distinguer inclus, hors forfait, roaming, data, voix, SMS ?
- Les montants hors forfait sont-ils presents dans CDR ou seulement dans
  `billing` ?
- Comment relier une consommation CDR a une ligne de facture ?

Endpoints attendus a reperer :

- get usage by customer/account and period ;
- get out-of-bundle usage ;
- get usage detail by type.

### 4. Contact

Quatrieme Swagger a analyser.

Questions a resoudre :

- Comment rechercher ou confirmer un client depuis le canal telephone ou web ?
- Quel identifiant permet de relier `contact` a `account` ?
- Quels champs peuvent etre exposes oralement ou sur le web ?
- Quels cas imposent une clarification ou une escalade ?

Endpoints attendus a reperer :

- search contact ;
- get contact detail ;
- get accounts for contact.

## Contrat minimum du mock V1

Le mock doit couvrir au moins quatre parcours.

### Parcours nominal

- Client identifie.
- Deux factures comparables.
- Delta global reconcile avec des causes explicables.
- Preuves disponibles pour chaque cause principale.

### Remise expiree

- Facture precedente avec remise active.
- Facture courante sans remise.
- Evenement ou periode de validite permettant de confirmer l'expiration.

### Hors forfait consommation

- Facture courante avec ligne hors forfait.
- CDR montrant la consommation associee.
- Cause reliee a la ligne facture et a la consommation.

### Prorata / option

- Activation d'option en cours de periode.
- Ligne facture avec montant prorate.
- Evenement account permettant de confirmer la date d'activation.

### Donnees insuffisantes

- Une facture ou une preuve manque.
- Le bot doit expliquer la limite et ne pas inventer la cause.

## Fixtures recommandees

| Fixture | Objectif |
|---------|----------|
| `customer-eir-001` | Cas nominal avec facture courante plus chere |
| `customer-eir-002` | Remise expiree uniquement |
| `customer-eir-003` | Hors forfait data avec preuve CDR |
| `customer-eir-004` | Option activee en milieu de periode avec prorata |
| `customer-eir-005` | Donnees BSS incompletes |

Les donnees doivent etre anonymisees et rester realistes : montants en EUR,
periodes mensuelles, offres telecom plausibles, dates coherentes et deltas qui
se reconcilient avec les causes exposees.

## Erreurs a reproduire

Le mock doit reproduire les erreurs utiles au comportement produit :

- client introuvable ;
- compte introuvable ;
- facture introuvable ;
- periode non disponible ;
- acces interdit ;
- service BSS indisponible ;
- timeout ;
- donnees partielles ;
- donnees incoherentes.

Chaque erreur doit avoir le meme format que le BSS cible lorsque ce format sera
connu.

## Informations a demander quand les Swagger sont disponibles

Pour chaque microservice, extraire :

- base path ;
- endpoints utiles V1 ;
- methode HTTP ;
- parametres obligatoires ;
- identifiants utilises (`contactId`, `accountId`, `customerId`, `invoiceId`,
  etc.) ;
- schema des reponses ;
- schema des erreurs ;
- authentification ;
- headers requis : correlation id, tenant, channel, locale ;
- pagination ;
- conventions de date, devise et timezone.

## Decisions ouvertes

- Les lignes facture viennent-elles bien de `billing` ?
- Les proratas sont-ils explicites dans `billing` ou deduits via `account` ?
- Les regularisations sont-elles des lignes facture, des evenements account, ou
  les deux ?
- Le backend doit-il appeler les microservices BSS directement, ou passer par une
  facade BSS operateur existante ?
- Le mock doit-il etre un service dedie dans `docker-compose` ou un profile du
  backend Java ?

## Recommandation implementation

Demarrer par un faux serveur BSS separe dans `docker-compose`, expose sur un port
dedie, avec fixtures JSON versionnees.

Avantages :

- le backend consomme de vraies APIs HTTP comme il le fera avec le BSS sandbox ;
- les contrats peuvent etre testes par endpoints ;
- les fixtures restent lisibles par Product, BSS et QA ;
- le passage mock -> sandbox se fait par configuration d'URL et d'auth.

Implementation recommandee :

- `bss-mock/` pour le faux serveur et les fixtures ;
- endpoints alignes sur les Swagger reels des que disponibles ;
- tests de contrat sur les payloads utiles V1 ;
- configuration backend `BSS_BASE_URL` ou equivalent ;
- profil local `bss-mock` dans `docker-compose`.
