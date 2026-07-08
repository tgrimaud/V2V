# Revue adversariale d'architecture — Vision omnicanale

Date : 2026-07-08

## Verdict

La direction générale est saine : canaux indépendants, backend Java commun pour
le métier, Genesys Cloud CX et WhatsApp positionnés comme adaptateurs et non
comme moteurs métier.

En revanche, la solution ne doit pas encore être présentée comme une plateforme
omnicanale industrialisée. À ce stade, elle correspond plutôt à un **POC solide
avec une vision d'industrialisation cohérente**. Les points faibles concernent
surtout les NFR/SLA, les modes dégradés, l'observabilité et les contrats
d'intégration entre canaux et backend.

## Scorecard

| Dimension | Score /5 | Rationale |
|---|---:|---|
| NFR / SLA fitness | 2 | La cible de latence existe, mais les prérequis STT streaming, TTS chunké, cache sémantique et observabilité restent au backlog. |
| SLA failure modes | 2 | Des timeouts existent, mais il manque retry, circuit breaker, rate limiting et modes dégradés explicites par canal. |
| Modularity and boundaries | 3.5 | Le backend Java est bien structuré autour de ports/adapters ; côté voice-agent, Gradium/Twilio restent encore très présents directement dans les pipelines. |
| External dependency replaceability | 2.5 | LLM et persistence sont relativement remplaçables. STT/TTS, Twilio, Genesys et WhatsApp doivent encore être formalisés comme adapters/ports. |
| Evolvability and industrialization | 3 | La vision omnicanale est correcte, mais il manque des contrats stables et des preuves d'isolation opérationnelle. |
| Overall | 2.8 | Bon socle MVP, pas encore une cible production robuste. |

## Critical Risks

- **Backend Java comme point de concentration** : tous les canaux convergent vers
  le même moteur conversationnel. C'est souhaitable pour la cohérence métier,
  mais dangereux sans rate limiting, timeouts, métriques et quotas par canal.
- **Couplage Gradium côté voice-agent** : `GradiumSTTService` et
  `GradiumTTSService` sont instanciés directement dans les pipelines Python.
  Remplacer Gradium demandera plus qu'un simple nouvel adapter.
- **Genesys/WhatsApp encore conceptuels** : ils sont correctement positionnés
  dans la vision, mais il n'existe pas encore de contrat d'intégration, payload
  d'escalade, mapping de conversation, idempotence ou stratégie d'erreur.
- **SLOs non vérifiables** : la documentation annonce des cibles de latence, mais
  l'observabilité par étape et les budgets mesurés restent à faire.
- **Risque de dérive documentaire** : certaines docs d'architecture peuvent être
  en retard sur le code, par exemple autour de `TokenStream` vs Reactor. Les
  décisions d'industrialisation doivent s'appuyer sur le code et les tests, pas
  seulement sur les diagrammes.

## Hard Questions

- Quel SLO officiel doit être tenu : first audio p95 inférieur à 700 ms, 800 ms
  ou 1 seconde ?
- Que se passe-t-il si Gradium STT est lent mais les canaux texte fonctionnent ?
- Que se passe-t-il si Genesys Cloud CX est indisponible au moment d'une
  escalade ?
- Un canal peut-il être désactivé, redémarré ou déployé sans redéployer le
  backend Java ?
- Quel contrat unique les canaux doivent-ils appeler : `ask`, `ask-stream`, ou
  une future API de conversation orientée canal ?
- Comment éviter qu'un flood WhatsApp dégrade la voix temps réel ?

## Architecture Challenges

### Backend Java commun

Le choix est bon, car il centralise le RAG, les guardrails, le routage
multi-agent, l'escalade et la persistance. Mais il faut maintenant le traiter
comme un **produit interne consommé par plusieurs canaux**, avec contrats,
versioning, timeouts, quotas et observabilité.

### Canaux indépendants

La vision est correcte, mais elle doit être traduite en objets et contrats
stables : `channel`, `conversation_id`, `external_session_id`, `message_id`,
`idempotency_key`, `reply_mode`, `escalation_context`.

### Pipecat comme cible voix

Pipecat est un choix crédible pour le temps réel vocal. En revanche, le projet
doit décider explicitement si le bridge legacy reste un fallback maintenu ou un
chemin à supprimer. Garder deux chemins voix complets augmente le coût de test
et le risque de divergence.

### Genesys Cloud CX

Genesys doit rester une couche centre de contact : canaux, files d'attente,
agent desktop, supervision et handoff humain. Il ne doit pas devenir propriétaire
du RAG, des règles métier, de l'escalade ou de la mémoire conversationnelle.

## External Dependency Review

| Dependency | Current role | Replaceability | Concern | Recommendation |
|---|---|---|---|---|
| Gradium STT/TTS | Transcription et synthèse vocale | Hard | Couplage direct dans les pipelines Python. | Introduire une abstraction provider STT/TTS côté voice-agent. |
| Twilio | Téléphonie / Media Streams | Moderate | Le protocole est partiellement isolé mais reste lié au flux téléphonie. | Garder Twilio comme adapter canal et définir un contrat téléphonie interne. |
| Genesys Cloud CX | Future couche centre de contact | Unknown | Pas encore de connecteur ni payload d'escalade. | Définir un contrat `EscalationHandoff`. |
| WhatsApp | Futur canal messagerie | Unknown | Pas encore d'adapter ni contrat async. | Créer un contrat messaging avec idempotence. |
| Mistral / Ollama | Génération LLM | Good | Ports backend existants. | Ajouter tests de fallback, timeout et erreurs provider. |
| PostgreSQL / pgvector | Vector store et événements | Moderate | pgvector reste structurant dans l'implémentation. | Conserver `VectorSearchPort` et documenter une migration possible. |
| Redis | Sessions actives | Good | Adapter existant, mais mode panne à formaliser. | Ajouter stratégie panne Redis, TTL métier et fallback contrôlé. |

## NFR / SLA Gaps

- SLOs non stabilisés : p95/p99, time-to-first-audio, time-to-first-token, taux
  d'erreur, temps d'escalade.
- Pas de budget clair par étape : STT, RAG, vector search, LLM, TTS, réseau.
- Pas de stratégie documentée de circuit breaker ou retry par provider.
- Pas de rate limiting par canal.
- Pas de politique de priorité entre canaux temps réel et canaux asynchrones.
- Pas de contrat d'escalade humain exploitable par Genesys ou équivalent.
- Observabilité OpenTelemetry et dashboard latence encore au backlog.

## Recommended Changes

### 1. Must fix before production

- Définir les SLOs mesurables : first audio p95, timeout STT/TTS/LLM, taux
  d'erreur, temps d'escalade.
- Instrumenter les métriques par étape et par canal.
- Définir le contrat d'escalade humain compatible Genesys ou équivalent.
- Ajouter timeouts, quotas et rate limiting par canal.

### 2. Should fix before pilot

- Introduire une abstraction STT/TTS côté Python.
- Définir une API canal stable pour WhatsApp, web chat et téléphonie.
- Formaliser les champs `channel`, `external_session_id`, `message_id` et
  `idempotency_key`.
- Ajouter des tests de défaillance : provider STT/TTS indisponible, backend lent,
  Redis indisponible, double message, escalade impossible.

### 3. Can defer safely

- Connecteur Genesys Cloud CX réel.
- Canal WhatsApp réel.
- Self-hosting STT/TTS/LLM.
- Dashboard admin avancé.

## Décision à retenir

La cible à privilégier est : **points d'entrée indépendants par canal + backend
Java commun pour le métier**.

Cette cible maximise l'évolutivité et limite les impacts croisés, mais elle ne
devient robuste qu'à partir du moment où les contrats canal/backend, les SLOs et
les modes dégradés sont explicitement définis et testés.
