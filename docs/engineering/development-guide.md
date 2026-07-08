# Guide de développement

## Conventions du projet

### Architecture

- **Domaine pur** : aucune annotation Spring, aucune dépendance externe dans `domain/`
- **Ports IN** : interfaces des cas d'usage (ce que le système offre)
- **Ports OUT** : interfaces des dépendances (ce dont le système a besoin)
- **Adapters** : implémentations techniques des ports
- **Configuration** : le câblage Spring est dans `infrastructure/config/` — les beans du domaine sont enregistrés via `@Bean`, jamais via `@Service`

### Tests

- **Pas de Mockito** : les tests utilisent des fakes manuels (inner classes `static`)
- **Nommage** : `shouldVerbeQuelqueChose` (ex: `shouldReturnAnswerWithCitations`)
- **Structure** : GIVEN / WHEN / THEN (implicite dans la structure du test)

### Style de code

- Méthodes : max 20 lignes
- Classes : max 200 lignes
- Nesting : max 3 niveaux
- Pas de Javadoc sur les ports et modèles (convention projet)
- Pas de commentaires évidents

## Ajouter un nouveau provider

### Exemple : ajouter OpenAI comme LLM alternatif

1. Créer l'adapter (doit implémenter les deux ports) :

```java
// infrastructure/adapter/out/llm/OpenAILlmAdapter.java
public class OpenAILlmAdapter implements LlmPort, LlmStreamingPort {
    private final ChatClient chatClient;

    @Override
    public String generateAnswer(...) {
        return chatClient.prompt().system(sys).user(q).call().content();
    }

    @Override
    public TokenStream streamAnswer(...) {
        return TokenStream.fromIterable(chatClient.prompt().system(sys).user(q).stream().content().toIterable());
    }
}
```

2. Ajouter le bean conditionnel (un seul bean satisfait les deux interfaces) :

```java
// infrastructure/config/DomainServiceConfig.java
@Bean
@ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "openai")
public OpenAILlmAdapter openAiLlmAdapter(ChatClient chatClient) {
    return new OpenAILlmAdapter(chatClient);
}
```

3. Ajouter la propriété dans `application.yml` :

```yaml
voice-support:
  llm:
    provider: openai  # ou mistral-api (défaut) ou ollama
```

### Changer le provider STT/TTS (agent vocal)

Le STT et TTS sont gérés par l'agent Pipecat (Python). Pour changer de fournisseur :

1. Modifier `voice-agent/pyproject.toml` — changer l'extra Pipecat :

```toml
dependencies = [
    "pipecat-ai[deepgram,cartesia,websocket,silero]",  # ex: Deepgram STT + Cartesia TTS
]
```

2. Modifier le pipeline cible `voice-agent/agent/bot.py` — instancier le bon service Pipecat :

```python
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.cartesia import CartesiaTTSService

stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
tts = CartesiaTTSService(api_key=os.getenv("CARTESIA_API_KEY"), voice_id="...")
```

Aucune modification du backend Java n'est nécessaire — le processeur RAG Pipecat
continue d'appeler la même API conversationnelle backend. Si le bridge WebSocket
legacy reste utilisé pour comparaison, documenter séparément son adapter STT/TTS
au lieu d'en faire le chemin cible.

## Ajouter un nouvel agent spécialisé

Le système multi-agent est extensible. Pour ajouter un nouvel agent (ex: agent SAV retours) :

1. **Créer la KB** dans `knowledge-base/sav-faq.md`

2. **Ajouter le profil** dans `AgentProfile.java` :

```java
public static AgentProfile sav() {
    return new AgentProfile(
            "sav",
            "Agent SAV",
            """
            Tu es un agent SAV spécialisé dans les retours et échanges...
            Contexte de la base de connaissance :
            {context}
            """,
            "sav",
            List.of("retour", "échange", "panne matériel", "renvoi", "colis",
                    "garantie", "remplacement", "défectueux")
    );
}
```

3. **Enregistrer** dans `DomainServiceConfig.agentRegistry()` :

```java
@Bean
public AgentRegistry agentRegistry() {
    return new AgentRegistry(
            List.of(AgentProfile.support(), AgentProfile.billing(),
                    AgentProfile.commercial(), AgentProfile.sav()),
            "support"
    );
}
```

4. **Ingérer la KB** avec le tag domaine :

```bash
curl -X POST http://localhost:8081/api/knowledge/ingest \
  -F "file=@knowledge-base/sav-faq.md" \
  -F "source=sav-faq.md" \
  -F "domain=sav"
```

Aucune modification de l'orchestrateur, du classifier ou des adapters n'est nécessaire.

## Ajouter un document à la base de connaissance

> Voir aussi : [`knowledge-base-technical.md`](../knowledge-base/knowledge-base-technical.md) (architecture
> KB + ajout d'un connecteur) et [`knowledge-base-guide.md`](../knowledge-base/knowledge-base-guide.md)
> (guide de rédaction pour contributeurs).

1. Créer un fichier Markdown dans `knowledge-base/` :

```markdown
# Nouveau sujet

## Section 1

Contenu structuré avec des paragraphes séparés par des lignes vides.

## Section 2

Chaque paragraphe devient un chunk potentiel.
```

2. Ingérer via l'API avec le tag de domaine (obligatoire pour le routing multi-agent) :

```bash
# Support technique
curl -X POST http://localhost:8081/api/knowledge/ingest \
  -F "file=@knowledge-base/telecom-faq.md" \
  -F "source=telecom-faq.md" \
  -F "domain=support"

# Facturation
curl -X POST http://localhost:8081/api/knowledge/ingest \
  -F "file=@knowledge-base/billing-faq.md" \
  -F "source=billing-faq.md" \
  -F "domain=billing"

# Commercial
curl -X POST http://localhost:8081/api/knowledge/ingest \
  -F "file=@knowledge-base/commercial-faq.md" \
  -F "source=commercial-faq.md" \
  -F "domain=commercial"
```

Le paramètre `domain` tag chaque chunk pour que la recherche vectorielle soit filtrée par agent.
Sans `domain`, les chunks sont stockés sans filtre (rétrocompatible mais non recommandé).

Le chunking respecte les frontières de paragraphes et propage les headings comme métadonnées de section.

### Synchronisation multi-sources (recommandé)

Le `curl ... /ingest` reste disponible pour un upload ponctuel, mais la KB est
désormais alimentée par des **connecteurs de source** synchronisés. Le connecteur
de référence `MarkdownFolderConnector` lit `knowledge-base/*.md` et résout le
`domain` depuis un **front-matter YAML** en tête de chaque fichier :

```markdown
---
domain: billing
language: fr
---

# Base de connaissance — Facturation et Abonnements
...
```

Déclencher une synchro manuellement :

```bash
# Toutes les sources
curl -X POST http://localhost:8081/api/knowledge/sync

# Une seule source (par type de connecteur)
curl -X POST http://localhost:8081/api/knowledge/sync/markdown
```

La réponse est un rapport : `{ "processed": 3, "ingested": 3, "skipped": 0, "deleted": 0 }`.
La synchro est **idempotente** : un document inchangé (même `content_hash`) est
ignoré (`skipped`), un document modifié est ré-ingéré (`deleted` puis re-chunké),
et un document disparu de la source est supprimé du vector store. L'état de
synchro est conservé dans la table `kb_source_state`.

Une synchro **planifiée** tourne via cron (`voice-support.knowledge.sync-cron`,
défaut horaire `0 0 * * * *`). Mettre `KB_SYNC_CRON=-` pour la désactiver en dev.

Migration depuis l'ancien seeding `curl /ingest` : les lignes pré-existantes n'ont
pas de `source_id`, donc pour éviter les doublons, vider une fois la table avant la
première synchro : `DELETE FROM vector_store;` puis `POST /api/knowledge/sync`.

## Résolution de problèmes courants

| Problème | Cause | Solution |
|----------|-------|----------|
| `Unknown type vector` | Extension pgvector pas activée | `docker exec <container> psql -U voicesupport -d voicesupport -c "CREATE EXTENSION vector;"` |
| `relation "vector_store" does not exist` | Schema pas initialisé | Ajouter `initialize-schema: true` dans la config pgvector |
| `model 'llama3.1' not found` | Mauvais tag de modèle | Utiliser `llama3.1:8b` (vérifier avec `ollama list`) |
| Port 8081 occupé | Autre instance tourne | `kill $(lsof -ti:8081)` |
| Port 7860 occupé | Agent Pipecat déjà lancé | `kill $(lsof -ti:7860)` |
| Port 8765/8766 occupé | Bridge custom legacy déjà lancé | `kill $(lsof -ti:8765)` |
| Ingestion lente | Ollama génère les embeddings | Normal au premier appel (~1s/chunk), ensuite caché |
| UI Pipecat indisponible | Runner non démarré | `cd voice-agent && python -m agent.bot -t webrtc`, puis ouvrir `http://localhost:7860` |
| Frontend React legacy ne se connecte pas au voice agent | URL incorrecte | Vérifier `VITE_VOICE_AGENT_URL=ws://localhost:8765` |
| `GRADIUM_API_KEY not set` | Variable manquante | `cp voice-agent/.env.example voice-agent/.env` et configurer |
| `Embeddings not found for default` | `GRADIUM_VOICE_ID` invalide | Utiliser un vrai ID du [catalogue](https://docs.gradium.ai/guides/voices/all-voices) (ex: `b35yykvVppLXyw_l` pour Elise FR) |
| Audio TTS non joué dans le navigateur | PCM brut non décodable par `decodeAudioData` | Le bridge doit wrapper le PCM dans un header WAV (44 octets) avant envoi |
| Agent Pipecat ne démarre pas | Dépendances manquantes | `cd voice-agent && uv pip install -e .` |
| VAD charge `silero_vad_legacy.onnx` | Mauvais modèle par défaut | Ajouter `model: 'v5'` dans les options `MicVAD.new()` |
| VAD `Can't create a session` | Fichier ONNX manquant dans `public/` | Copier `node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx` et `vad.worklet.bundle.min.js` dans `frontend/public/` |
| VAD ne détecte pas la parole | `startOnLoad: true` + double-mount React | Ajouter `startOnLoad: false` et appeler `vad.start()` manuellement |
| Barge-in ne coupe pas le bot | Mauvais chemin vocal lancé | Utiliser Pipecat (`python -m agent.bot -t webrtc`) pour la cible V1, ou redémarrer le bridge legacy |
| `401 Unauthorized` de Mistral | Clé API non chargée | Lancer le backend avec `export $(cat backend/.env \| xargs) && mvn spring-boot:run` ou sourcer le `.env` avant |
| Bot répond hors-sujet sur "Bonjour" | Guardrails non actifs | Vérifier que `GuardrailService` est dans `DomainServiceConfig` et redémarrer le backend |
| Le bot re-salue au 1er message Pipecat | Le message d'accueil joué par le TTS n'est pas dans l'historique backend | `bot.py` doit appeler `POST /api/conversation/seed` au `on_client_connected` ; redémarrer l'agent vocal après mise à jour |
| Routing multi-agent ne fonctionne pas | KB non taguée | Ré-ingérer avec le paramètre `domain=support\|billing\|commercial` |
| Réponses génériques malgré routing | Chunks sans domaine en BDD | Vider la table et ré-ingérer : `DELETE FROM vector_store;` puis re-curl ingest |

## Commandes utiles

```bash
# Vérifier l'état des services
curl http://localhost:8081/api/health
docker compose ps

# Installer les assets VAD après npm install
cp node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx frontend/public/
cp node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js frontend/public/

# Lancer le backend Java (charger le .env pour la clé Mistral)
cd backend && export $(cat .env | xargs) && mvn spring-boot:run

# Lancer l'agent vocal cible V1 (Pipecat + Gradium)
# Web (WebRTC) + UI prebuilt sur http://localhost:7860
cd voice-agent && python -m agent.bot -t webrtc
# Tous transports (web + telephonie) :
cd voice-agent && python -m agent.bot
# Telephonie Pipecat (necessite un proxy public, ex: ngrok) :
cd voice-agent && python -m agent.bot -t twilio -x <votre-host-public>

# Lancer le bridge custom legacy/fallback (React :5173, ws:8765/8766)
cd voice-agent && python -u -m agent.bridge_server

# Tester le streaming SSE (réponse token par token)
curl -N "http://localhost:8081/api/conversation/ask-stream?question=Bonjour&conversation_id=test"

# Amorcer l'historique avec le message d'accueil (utilisé par le bot Pipecat)
# pour éviter que le LLM ne re-salue au 1er message utilisateur
curl -X POST http://localhost:8081/api/conversation/seed \
  -H "Content-Type: application/json" \
  -d '{"message": "Bonjour ! Je suis votre assistant virtuel.", "conversation_id": "test"}'

# Tester le RAG (mode synchrone)
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Ma box ne marche plus", "conversationId": "test"}' | python3 -m json.tool

# Mesurer le time-to-first-byte (latence streaming)
curl -w "\nTTFB: %{time_starttransfer}s\nTotal: %{time_total}s\n" -s -o /dev/null \
  "http://localhost:8081/api/conversation/ask-stream?question=Bonjour&conversation_id=perf"

# Voir les chunks indexés
docker exec voice-support-bot-postgres-1 psql -U voicesupport -d voicesupport \
  -c "SELECT id, substring(content, 1, 80) FROM vector_store LIMIT 10;"

# Vider la base de connaissance (réingestion)
docker exec voice-support-bot-postgres-1 psql -U voicesupport -d voicesupport \
  -c "DELETE FROM vector_store;"

# Voir les stats admin
curl -s http://localhost:8081/api/admin/stats | python3 -m json.tool

# Tester l'escalade
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Je veux résilier"}' | python3 -m json.tool

# Tester les guardrails — salutation (pas de RAG)
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Bonjour", "conversationId": "test"}' | python3 -m json.tool

# Tester les guardrails — off-topic
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Quel temps fait-il dehors ?", "conversationId": "test"}' | python3 -m json.tool

# Tester le routing multi-agent — facturation
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Comment consulter ma facture ?", "conversation_id": "test-billing"}' | python3 -m json.tool

# Tester le routing multi-agent — commercial
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Je déménage, comment transférer mon abonnement ?", "conversation_id": "test-commercial"}' | python3 -m json.tool

# Ingérer les 3 KB avec domaines (après un reset)
curl -X POST http://localhost:8081/api/knowledge/ingest -F "file=@knowledge-base/telecom-faq.md" -F "source=telecom-faq.md" -F "domain=support"
curl -X POST http://localhost:8081/api/knowledge/ingest -F "file=@knowledge-base/billing-faq.md" -F "source=billing-faq.md" -F "domain=billing"
curl -X POST http://localhost:8081/api/knowledge/ingest -F "file=@knowledge-base/commercial-faq.md" -F "source=commercial-faq.md" -F "domain=commercial"

# Arrêter tout
docker compose down
kill $(lsof -ti:8081) 2>/dev/null
kill $(lsof -ti:8765) 2>/dev/null
```

## Mesure de latence (baseline)

Le chemin critique est instrumenté avec des logs structurés préfixés `[LATENCY]`, sans dépendance supplémentaire. Chaque étape émet une ligne `[LATENCY] step=<nom> ms=<valeur> [extra...]` :

| Étape (`step`) | Émis par | Fichier |
|----------------|----------|---------|
| `stt` | Voice agent | `voice-agent/agent/gradium_stt.py` |
| `vector_search` | Backend | `PgVectorStoreAdapter` |
| `llm_first_token` / `llm_total` | Backend | `MistralLlmAdapter` / `OllamaLlmAdapter` |
| `tts` | Voice agent | `voice-agent/agent/gradium_tts.py` |
| `time_to_first_audio` | Voice agent | `bridge_server.py` legacy ou Pipecat metrics selon le chemin testé |
| `turn_total` | Voice agent | `bridge_server.py` legacy ou Pipecat metrics selon le chemin testé |

**SLO de référence** : `time_to_first_audio` p95 < 800 ms.

### Capturer et agréger une baseline

```bash
# 1. Capturer les logs des services pendant une session Pipecat
cd backend && export $(cat .env | xargs) && mvn spring-boot:run 2>&1 | tee /tmp/backend.log
cd voice-agent && python -m agent.bot -t webrtc 2>&1 | tee /tmp/pipecat.log

# 2. Mener quelques échanges vocaux représentatifs (10-20 tours)

# 3. Agréger en p50/p95 par étape
python voice-agent/tools/latency_report.py /tmp/backend.log /tmp/pipecat.log
```

Le rapport affiche `n / p50 / p95 / min / max / mean` par étape et marque
`OK`/`FAIL` sur le SLO `time_to_first_audio`. Le bridge legacy peut être lancé à
part pour comparaison, mais la baseline V1 doit partir de Pipecat.
