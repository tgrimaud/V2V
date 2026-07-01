# Guidance for AI agents — Voice Support Bot

## Repo & git

- `voice-support-bot` est un **repo git séparé** (branche par défaut `main`), imbriqué dans le workspace `BMad` (qui est un autre repo). Committer/pusher le travail du bot **dans ce repo**, pas dans `BMad`.
- **Une branche par sprint/epic** (`feat/<nom>`). Ne pas committer directement sur `main`. Merge après validation.
- **Committer après chaque tâche** ; ne pas laisser de code non commité.

## Before you edit

1. Backend Java : suivre la skill `java-backend-developer` + `code-guidelines` (méthodes ≤ 20 lignes, classes ≤ 200 lignes, pas de Javadoc sur ports).
2. Domaine pur (aucune annotation Spring) ; brancher les services via `@Bean` dans `DomainServiceConfig`.
3. Tests : fakes manuels, GIVEN/WHEN/THEN, **pas de Mockito**.

## Common mistakes to avoid

- Confondre **LLM** et **embedding** : ce sont 2 modèles distincts. Le chat est sur Mistral (API), l'embedding sur Ollama (`nomic-embed-text`, 768 dim). "Passer sur Mistral" ne change PAS l'embedding (auto-config embedding Mistral exclue).
- Faire un `ALTER TABLE vector_store` pour ajouter des métadonnées : inutile, elles sont en **JSONB**. En revanche, **changer le modèle d'embedding** (donc la dimension) impose de recréer la table + re-synchroniser.
- Oublier que les lignes seedées via l'ancien `curl /ingest` n'ont pas de `source_id` → `deleteBySource` ne les nettoie pas. Vider `vector_store` une fois avant la première synchro.
- Ajouter une méthode à un port out (`VectorStorePort`, etc.) sans mettre à jour **tous** les implémenteurs, y compris les **fakes de test**.
- Retourner un type vectoriel `mistral-embed` (1024) sans aligner `pgvector.dimensions` — mismatch silencieux à l'insertion/recherche.
- Ajouter une dépendance pour parser le YAML du front-matter : SnakeYAML est déjà là (transitif Spring Boot).
- Mettre des annotations Spring dans le domaine, ou injecter un connecteur en oubliant le `@Bean` (il ne sera pas dans `List<KnowledgeSourceConnector>`).
- Croire que `mvn test` a besoin d'une DB/Ollama : il n'y a pas de `@SpringBootTest`, les tests sont des unités de domaine avec fakes.
- Mettre les learnings du bot dans le `CLAUDE.md` racine de `BMad` : il concerne un autre projet (cursor-usage-dashboard). Les fichiers de connaissance du bot vivent dans `voice-support-bot/`.
- Repartir de zero pour la V1 billing : conserver le socle voix/RAG/orchestrateur du POC, mais reconstruire le coeur metier autour du BSS et de la comparaison de factures.
- Utiliser un MCP generique comme acces BSS principal en runtime client : preferer un port metier typé lecture seule (`BssBillingPort`) avec adapters BSS ; reserver MCP a l'exploration et aux outils internes.
- Coupler le coeur produit a un SDK LLM/STT/TTS precis : exposer ces capacites via ports/adapters configurables pour benchmarker et changer facilement de fournisseur.
- Fermer le produit a la facturation uniquement : V1 = explication de facture, mais l'architecture doit rester extensible a d'autres domaines support operateur.
- Creer un repo separe pour le backlog produit quand l'utilisateur veut surtout le conserver avec le projet : par defaut, stocker les artefacts dans `product-backlog/` du repo `voice-support-bot` sauf demande explicite d'un depot Git externe.
- Rediger EPICs/US produit sans le skill `product-business` : ce skill garde les stories au niveau besoin, valeur, regles metier et acceptance observable, sans details d'API ou implementation.
- Prendre `billing-service` comme source Galaxion pour les factures : il n'est plus utilise. Pour la V1, cibler `billing-api` uniquement.
- Chercher un endpoint Galaxion de lignes facture structurees sans preuve : aucun n'a ete identifie. Recuperer le PDF via `bill-run-documents` et passer par un `InvoicePdfExtractor` deterministe.
- Faire lire le PDF facture directement au LLM pour calculer les montants : interdit. Extraire d'abord un JSON structure, verifier la reconciliation, puis seulement formuler l'explication.

## Checklist après changement substantiel

- [ ] `mvn test` vert dans `backend/`.
- [ ] Si contrat REST modifié : mettre à jour `docs/` (architecture.md, README, api).
- [ ] Si nouveau bean/port : câblage dans `DomainServiceConfig`.
- [ ] Mettre à jour `docs/` en même temps que le code (pas en lot séparé).
