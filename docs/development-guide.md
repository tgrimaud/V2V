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
    public Flux<String> streamAnswer(...) {
        return chatClient.prompt().system(sys).user(q).stream().content();
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

2. Modifier `voice-agent/agent/ws_server.py` — instancier le bon service :

```python
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.cartesia import CartesiaTTSService

stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
tts = CartesiaTTSService(api_key=os.getenv("CARTESIA_API_KEY"), voice_id="...")
```

Aucune modification du backend Java n'est nécessaire — le `RAGProcessor` communique via HTTP.

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

## Résolution de problèmes courants

| Problème | Cause | Solution |
|----------|-------|----------|
| `Unknown type vector` | Extension pgvector pas activée | `docker exec <container> psql -U voicesupport -d voicesupport -c "CREATE EXTENSION vector;"` |
| `relation "vector_store" does not exist` | Schema pas initialisé | Ajouter `initialize-schema: true` dans la config pgvector |
| `model 'llama3.1' not found` | Mauvais tag de modèle | Utiliser `llama3.1:8b` (vérifier avec `ollama list`) |
| Port 8081 occupé | Autre instance tourne | `kill $(lsof -ti:8081)` |
| Port 8765/8766 occupé | Agent Pipecat déjà lancé | `kill $(lsof -ti:8765)` |
| Ingestion lente | Ollama génère les embeddings | Normal au premier appel (~1s/chunk), ensuite caché |
| Frontend ne se connecte pas au voice agent | URL incorrecte | Vérifier `VITE_VOICE_AGENT_URL=ws://localhost:8765` |
| `GRADIUM_API_KEY not set` | Variable manquante | `cp voice-agent/.env.example voice-agent/.env` et configurer |
| `Embeddings not found for default` | `GRADIUM_VOICE_ID` invalide | Utiliser un vrai ID du [catalogue](https://docs.gradium.ai/guides/voices/all-voices) (ex: `b35yykvVppLXyw_l` pour Elise FR) |
| Audio TTS non joué dans le navigateur | PCM brut non décodable par `decodeAudioData` | Le bridge doit wrapper le PCM dans un header WAV (44 octets) avant envoi |
| Agent Pipecat ne démarre pas | Dépendances manquantes | `cd voice-agent && uv pip install -e .` |
| VAD charge `silero_vad_legacy.onnx` | Mauvais modèle par défaut | Ajouter `model: 'v5'` dans les options `MicVAD.new()` |
| VAD `Can't create a session` | Fichier ONNX manquant dans `public/` | Copier `node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx` et `vad.worklet.bundle.min.js` dans `frontend/public/` |
| VAD ne détecte pas la parole | `startOnLoad: true` + double-mount React | Ajouter `startOnLoad: false` et appeler `vad.start()` manuellement |
| Barge-in ne coupe pas le bot | Bridge utilise l'ancien code | Redémarrer le bridge (`kill $(lsof -ti:8765)` puis relancer) |
| `401 Unauthorized` de Mistral | Clé API non chargée | Lancer le backend avec `export $(cat backend/.env \| xargs) && mvn spring-boot:run` ou sourcer le `.env` avant |
| Bot répond hors-sujet sur "Bonjour" | Guardrails non actifs | Vérifier que `GuardrailService` est dans `DomainServiceConfig` et redémarrer le backend |
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

# Lancer l'agent vocal (navigateur — bridge mode streaming)
cd voice-agent && python -u -m agent.bridge_server

# Lancer l'agent vocal (navigateur — Pipecat natif, sans bridge)
cd voice-agent && python -m agent.ws_server

# Lancer l'agent vocal (Twilio)
cd voice-agent && python -m agent.twilio_server

# Tester le streaming SSE (réponse token par token)
curl -N "http://localhost:8081/api/conversation/ask-stream?question=Bonjour&conversation_id=test"

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
