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
- **Priorité** : 🔴 Haute · **Statut** : Fait
- **Réalisé** : `ConversationStore` dispose d'un adapter **Redis** activable via
  `CONVERSATION_STORE=redis`, avec TTL (`CONVERSATION_TTL_SECONDS`). Docker
  Compose lance Redis et configure le backend sur Redis pour les sessions actives.
- **Effet** : N instances backend peuvent partager l'état chaud des conversations
  derrière un load-balancer, au lieu de dépendre d'une map mémoire mono-instance.
- **Suite possible** : réutiliser Redis pour cache sémantique et verrous courts.

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
- **État actuel** : la cible V1 Pipecat (`agent/bot.py`) utilise Gradium STT dans
  le pipeline Pipecat avec VAD serveur Silero. Le bridge legacy conserve
  `stt_streaming.py` + `BatchSttSession` (REST batch) pour fallback/comparaison.
- **Objectif** : benchmarker le STT streaming Pipecat/Gradium sur web et
  téléphonie, puis décider si un provider STT alternatif ou self-hosté est requis.

### L2. TTS streaming chunké + WebSocket TTS persistante
- **Priorité** : 🟠 Moyenne · **Statut** : À faire
- **État actuel** : Pipecat utilise `GradiumTTSService` dans le pipeline cible V1.
  Le bridge legacy conserve `gradium_tts.py`, qui ouvre une WebSocket par phrase.
- **Objectif** : mesurer le first-audio Pipecat/Gradium, puis n'optimiser le TTS
  legacy que si le fallback reste nécessaire.

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
  `fetchAll()`) — couture déjà en place (cf. `../knowledge-base/knowledge-base-technical.md`).

### K2. Ingestion PDF (extraction structurée)
- **Priorité** : 🟠 Moyenne · **Statut** : À faire
- **Objectif** : extraction structurée (titres, sections) pour préserver la
  hiérarchie au chunking. Lié à K1 (connecteur PDF via Apache Tika).

---

## Conversation

### C1. Mémoire conversationnelle persistante (JPA)
- **Priorité** : 🟠 Moyenne · **Statut** : Fait
- **Réalisé** : `ConversationEventStore` dispose d'un adapter JPA/Postgres,
  activable via `CONVERSATION_EVENT_STORE=jpa`, pour conserver l'historique admin
  et les métriques après redémarrage.
- **Décision** : les sessions actives restent dans Redis (**S1**) ; Postgres garde
  les événements durables plutôt que le state chaud conversationnel.

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

### FUT2. Pipecat comme couche voix temps réel approfondie
- **Intention** : utiliser Pipecat plus profondément comme moteur d'orchestration
  voix temps réel, sans déplacer le métier hors du backend Java. Pipecat doit
  piloter le chemin audio (WebRTC/Twilio → STT → backend RAG streaming → TTS →
  retour audio), tandis que le backend conserve les règles métier, guardrails,
  routage d'agents, RAG/vector search, facturation et persistance conversationnelle.
- **Pistes** : faire de Pipecat le seul chemin voix cible, supprimer
  progressivement le bridge legacy, unifier WebRTC et Twilio dans un pipeline
  Pipecat, exploiter le barge-in framework, propager les événements RTVI/UI
  (`listening`, `thinking`, `speaking`, agent courant, citations, erreurs typées)
  et consommer `/api/conversation/ask-stream` en streaming end-to-end.
- **Signaux à remonter au backend/observabilité** : début/fin de parole,
  confidence STT, interruptions, silences, time-to-first-token,
  time-to-first-audio, latence STT/RAG/TTS et taux de barge-in.
- **À ne pas déplacer dans Pipecat** : décisions métier, comparaison de factures,
  règles de sécurité, modèle conversationnel persistant et logique RAG. Ces
  responsabilités restent côté backend Java pour préserver l'architecture
  hexagonale et la testabilité.

---

## Fait (référence)

- [x] Streaming inter-étapes (TTS phrase par phrase pendant la génération LLM)
- [x] VAD serveur Pipecat/Silero — conversation naturelle sans clic stop
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
