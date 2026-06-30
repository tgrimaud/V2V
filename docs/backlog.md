# Backlog — Voice Support Bot

Suivi des travaux restants. La source de vérité des items ouverts est ce
fichier ; la section « Roadmap » du `README.md` en donne une vue condensée.

Les items sont issus de la Roadmap et des plans de travail archivés
(`~/.cursor/plans/` : *Latence Conversation Operateur*, *Optimisations latence
voix*, *Multi-Agent Routing POC*, *KB multi-sources*). Les statuts ci-dessous
ont été **vérifiés dans le code** (les plans contenaient des statuts obsolètes).

**Légende statut** : `À faire` · `En cours` · `Fait`
**Légende priorité** : 🔴 Haute · 🟠 Moyenne · 🟢 Basse

---

## Cloud privé / cible 700 ms

### P1. Pré-requis techniques pour tenir `first audio < 700 ms`
- **Priorité** : 🔴 Haute · **Statut** : À faire
- **Objectif** : documenter et implémenter les prérequis nécessaires pour tenir
  une cible de latence `first audio < 700 ms` en cloud privé.
- **À couvrir** : STT streaming réel (**L1**), TTS streaming chunké/persistant
  (**L2**), cache sémantique (**L3**), état conversationnel partagé Redis
  (**S1**) et observabilité par span (**O1**).
- **Critère de validation** : mesurer le budget de latence par étape
  (STT → retrieval → LLM first-token → TTS first-audio → réseau) et vérifier le
  SLO sur un environnement co-localisé et pré-warmé.

---

## Scalabilité & omnicanal

### S1. Backend stateless + état partagé (Redis)
- **Priorité** : 🔴 Haute · **Statut** : À faire
- **État actuel** : l'état conversationnel est **en mémoire mono-instance**
  (`InMemoryConversationStore`, `InMemoryConversationEventStore`,
  `ConcurrentHashMap`) → impossible de scaler horizontalement.
- **Objectif** : sortir l'état de la JVM derrière un adapter **Redis** (state +
  futur cache sémantique), events en Postgres/Kafka. Permet N instances backend
  derrière un load-balancer → indispensable pour l'omnicanal à volume.
- **Pistes** : le port `ConversationEventStore` existe déjà → ajouter l'adapter
  sans toucher au domaine. Partage l'abstraction avec **C1** (persistance JPA) :
  une même interface `ConversationStore`, impl. Redis (partage + faible latence)
  et/ou JPA (durabilité).

### S2. Co-location + Kubernetes / autoscaling
- **Priorité** : 🟢 Basse (infra) · **Statut** : À faire
- **Objectif** : déployer bridge + backend + services IA dans le même VPC/région
  (supprimer les hops internet du chemin critique), HPA sur backend + bridge
  (métrique custom « appels actifs »), node pools CPU/GPU séparés, pré-warm
  anti cold-start. Dépend de S1.

---

## Latence (Time To First Audio)

### L1. STT streaming réel + turn-detection serveur
- **Priorité** : 🟠 Moyenne · **Statut** : À faire
- **État actuel** : `stt_streaming.py` n'expose qu'une **couture** ; l'impl
  concrète `BatchSttSession` fait un `POST` Gradium sur tout le buffer (REST
  batch). La fin de parole repose sur le **VAD navigateur** (absent en
  téléphonie côté serveur).
- **Objectif** : STT streaming WebSocket (transcription pendant que l'utilisateur
  parle) + détection de fin de tour sémantique côté serveur (endpointing).

### L2. TTS streaming chunké + WebSocket TTS persistante
- **Priorité** : 🟠 Moyenne · **Statut** : À faire
- **État actuel** : `gradium_tts.py` ouvre une **nouvelle WebSocket par phrase**
  et **bufferise tous les chunks** avant de renvoyer l'audio complet.
- **Objectif** : (a) maintenir une WebSocket TTS persistante par session
  (handshake éliminé, ~50-100 ms/phrase) ; (b) streamer les chunks PCM vers le
  frontend au fil de l'eau (`useAudioQueue`) → la voix démarre dès les premiers
  ~100 ms au lieu d'attendre la phrase complète.

### L3. Cache sémantique des FAQ fréquentes
- **Priorité** : 🟠 Moyenne · **Statut** : À faire
- **État actuel** : aucun cache (vérifié — pas de `@Cacheable`/cache sémantique).
- **Objectif** : court-circuiter le vector search (et idéalement le LLM) pour les
  questions ultra-courantes (« ma box ne marche pas ») → gain ~150-200 ms.

### L4. Réutilisation du client HTTP STT — ✅ Fait
- **Priorité** : 🟢 Basse (quick win) · **Statut** : Fait
- **Réalisé** : `gradium_stt.py` réutilise un `httpx.AsyncClient` partagé
  (`get_stt_client()`, pool de connexions TCP/TLS process-wide) → handshake
  éliminé entre appels (~30-80 ms). Fermeture propre du client câblée au
  shutdown du bridge (`close_stt_client()` dans `bridge_server.main()`).
- **Tests** : cycle de vie du client partagé (réutilisation, fermeture,
  recréation) dans `tests/test_gradium_stt.py`.

---

## Knowledge base

### K1. Connecteurs Confluence / PDF (Tika) / base de données
- **Priorité** : 🔴 Haute · **Statut** : À faire
- **Objectif** : nouveaux connecteurs au socle multi-sources pour ingérer des
  documents hétérogènes sans conversion Markdown manuelle.
- **Pistes** : implémenter `KnowledgeSourceConnector` (`sourceType()` +
  `fetchAll()`) — couture déjà en place (cf. `docs/knowledge-base-technical.md`).

### K2. Ingestion PDF (extraction structurée)
- **Priorité** : 🟠 Moyenne · **Statut** : À faire
- **Objectif** : extraction structurée (titres, sections) pour préserver la
  hiérarchie au chunking. Lié à K1 (connecteur PDF via Apache Tika).

---

## Conversation

### C1. Mémoire conversationnelle persistante (JPA)
- **Priorité** : 🟠 Moyenne · **Statut** : À faire
- **Objectif** : persister l'historique en base (JPA) pour survivre aux
  redémarrages et permettre la reprise de session. Partage l'abstraction
  `ConversationStore` avec **S1** (Redis) — à traiter ensemble.

---

## Observabilité

### O1. Traces OpenTelemetry sur le pipeline
- **Priorité** : 🟠 Moyenne · **Statut** : À faire
- **Objectif** : instrumenter chaque étape (STT → vector → LLM first-token → TTS)
  avec un budget par span, SLO « first audio < 800 ms p95 », dashboards + alerting.

---

## Frontend / Admin

### F1. Dashboard admin enrichi
- **Priorité** : 🟢 Basse · **Statut** : À faire
- **Objectif** : visualisations latence du pipeline, heatmap horaire des
  conversations, métriques d'usage.

---

## Voix

### V1. Voice cloning Gradium (voix de marque)
- **Priorité** : 🟢 Basse · **Statut** : À faire
- **Objectif** : voix de marque personnalisée via le voice cloning Gradium.

---

## Améliorations futures (hors périmètre actuel)

### FUT1. Self-hosting GPU (souveraineté + latence ultime)
- Internaliser le LLM (vLLM, continuous batching, first-token ~50-100 ms) puis
  STT/TTS sur GPU on-prem. Cible ~500-600 ms et données 100 % internes (secret
  des correspondances). CAPEX GPU + MLOps ; rentable à fort volume.
- La couche LLM est déjà abstraite (`LlmPort`/`LlmStreamingPort`) ; étendre la
  même abstraction à STT/TTS pour basculer sans réécriture. À acter via une ADR
  « self-hosting vs managé ».
- **Déclencheurs** : TCO managé > TCO GPU, contrainte réglementaire de
  non-sortie des données, ou besoin latence < 600 ms p95 inatteignable en managé.

---

## Fait (référence)

- [x] Streaming inter-étapes (TTS phrase par phrase pendant la génération LLM)
- [x] VAD navigateur (Silero) — conversation naturelle sans clic stop
- [x] Barge-in — interrompre le bot en parlant
- [x] Multi-langues (FR + EN) avec sélection automatique de voix Gradium
- [x] Fallback Mistral API quand Ollama est trop lent (`LLM_PROVIDER`)
- [x] Socle KB multi-sources (pivot `SourceDocument`, synchro idempotente,
  connecteur Markdown, pull planifié)
- [x] Guardrails : détection « hors sujet » avec score de confiance
- [x] **Routage multi-agent** (support / facturation / commercial) :
  `IntentClassifier`, `AgentRegistry`, filtrage KB par `domain`, stickiness
  d'agent, badges colorés du nom d'agent dans le chat
- [x] **Téléphonie SIP/PSTN** : `TwilioWebhookController`, `twilio_server.py`,
  `telephony.py`, codec `ulaw_8000` (`audio_codec.py`) — chemin reconstruit
- [x] Latence quick wins : seuil sentence splitter (10-12 chars + split virgule),
  silence VAD réduit (500 → 300 ms)
