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

1. Créer l'adapter :

```java
// infrastructure/adapter/out/llm/OpenAILlmAdapter.java
public class OpenAILlmAdapter implements LlmPort {
    private final ChatClient chatClient;
    // ...
}
```

2. Ajouter la configuration conditionnelle :

```java
// infrastructure/config/DomainServiceConfig.java
@Bean
@ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "openai")
public LlmPort openAiLlmPort(ChatClient chatClient) {
    return new OpenAILlmAdapter(chatClient);
}
```

3. Ajouter la propriété dans `application.yml` :

```yaml
voice-support:
  llm:
    provider: openai  # ou ollama
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

## Ajouter un document à la base de connaissance

1. Créer un fichier Markdown dans `knowledge-base/` :

```markdown
# Nouveau sujet

## Section 1

Contenu structuré avec des paragraphes séparés par des lignes vides.

## Section 2

Chaque paragraphe devient un chunk potentiel.
```

2. Ingérer via l'API :

```bash
curl -X POST http://localhost:8081/api/knowledge/ingest \
  -F "file=@knowledge-base/nouveau-sujet.md" \
  -F "source=nouveau-sujet"
```

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

## Commandes utiles

```bash
# Vérifier l'état des services
curl http://localhost:8081/api/health
docker compose ps

# Lancer l'agent vocal (navigateur — bridge mode)
cd voice-agent && python -u -m agent.bridge_server

# Lancer l'agent vocal (navigateur — Pipecat natif, sans bridge)
cd voice-agent && python -m agent.ws_server

# Lancer l'agent vocal (Twilio)
cd voice-agent && python -m agent.twilio_server

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

# Arrêter tout
docker compose down
kill $(lsof -ti:8081) 2>/dev/null
kill $(lsof -ti:8765) 2>/dev/null
```
