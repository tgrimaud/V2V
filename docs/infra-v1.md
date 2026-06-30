# Infrastructure V1 - Cible machines/VM

## Objectif

Ce document decrit une cible d'infrastructure V1 pour faire tourner le Voice
Support Bot chez un operateur telecom, par exemple Eir en Irlande.

La cible vise un pilote operateur realiste : trafic limite mais services
deployes proprement, haute disponibilite minimale, donnees client protegees et
capacite d'evoluer vers une plateforme de production.

## Hypotheses V1

- Region cloud EU, idealement Irlande (`eu-west-1` ou equivalent).
- IA STT/TTS/LLM consommee via providers manages au demarrage.
- BSS accessible en lecture seule via lien prive, VPN ou endpoint dedie.
- Frontend servi par CDN ou object storage, sans VM dediee.
- Kubernetes est recommande pour la V1 operateur, mais le sizing ci-dessous
  reste lisible en "equivalent VM".
- La cible initiale couvre un pilote de quelques dizaines d'appels simultanes,
  pas un deploiement national a pleine charge.

## Environnement pilote minimal

Cette option convient pour une demonstration operateur ou un pilote controle.

| Role | Nombre | Taille indicative | Remarques |
|------|--------|-------------------|-----------|
| Load balancer / ingress | 1 service manage | N/A | TLS, routage HTTPS/WSS, health checks |
| Backend Java | 2 VM ou pods | 2-4 vCPU, 4-8 Go RAM | API conversation, RAG, orchestration metier |
| Voice bridge Python | 2 VM ou pods | 2-4 vCPU, 4-8 Go RAM | WebSocket audio, STT/TTS, telephonie |
| PostgreSQL + pgvector | 1 instance managee | 4 vCPU, 16 Go RAM, SSD | KB, embeddings, etat technique |
| Redis | 1 instance managee | 2 vCPU, 4-8 Go RAM | Sessions, etat conversationnel partage, cache |
| Observabilite | Managee ou 1 VM | 2-4 vCPU, 8 Go RAM | Logs, traces, dashboards |
| Bastion / VPN admin | 1 petite VM | 1-2 vCPU, 1-4 Go RAM | Acces admin controle, optionnel si SSO/VPN manage |

Cette cible represente environ 6 a 8 VM equivalentes si tout est self-managed,
ou 4 VM applicatives si base de donnees, Redis et observabilite sont manages.

## Cible V1 operateur recommandee

Cette option est la cible conseillee pour une V1 exploitable avec un operateur.

| Pool / Service | Nombre | Taille indicative | Usage |
|----------------|--------|-------------------|-------|
| Kubernetes worker pool general | 3 VM | 4-8 vCPU, 16-32 Go RAM | Backend Java, jobs KB, petits services |
| Kubernetes worker pool voice | 2-3 VM | 4-8 vCPU, 16 Go RAM | Voice bridge, WebSocket audio, telephonie |
| PostgreSQL + pgvector HA | 2 instances managees | 4-8 vCPU, 16-32 Go RAM, SSD | Donnees KB, vector store, etat persistant |
| Redis HA | 2 instances managees | 2-4 vCPU, 8-16 Go RAM | Sessions, cache, etat partage faible latence |
| Observabilite | Service manage ou 2 VM | 4-8 vCPU, 16-32 Go RAM | OpenTelemetry, logs, metriques, alerting |
| Bastion / VPN admin | 1 petite VM | 1-2 vCPU, 1-4 Go RAM | Acces restreint au reseau prive |

Cette cible represente environ 8 a 12 VM equivalentes selon le niveau de
services manages retenu.

## Repartition des workloads

### Backend Java

- Minimum 2 replicas.
- CPU dimensionne pour le RAG, les appels BSS et le streaming SSE.
- Stateless autant que possible.
- Etat conversationnel partage dans Redis ou persiste en base selon le besoin.

### Voice bridge Python

- Pool separe du backend pour scaler selon les appels simultanes.
- Minimum 2 replicas.
- Sensible a la latence reseau vers STT/TTS et backend.
- Doit etre co-localise dans la meme region que le backend.
- Prevoir session draining avant redemarrage pour ne pas couper les appels actifs.

### PostgreSQL + pgvector

- Preferer un service manage HA.
- Stocke les embeddings, l'etat de synchronisation KB et les donnees techniques.
- Disque SSD obligatoire.
- Sauvegardes automatiques et restauration testee.

### Redis

- Preferer un service manage HA.
- Utilise pour l'etat conversationnel partage, les sessions et les caches courts.
- Necessaire des que plusieurs instances backend ou voice bridge tournent en
  parallele.

### Frontend

- Pas de VM dediee recommandee.
- Servir via object storage + CDN ou service static hosting.
- WAF, TLS, CSP et cache controle au niveau edge.

## Option IA self-hosted

La V1 peut demarrer avec IA managee. Si l'operateur impose une contrainte forte
de souverainete ou de non-sortie des donnees, ajouter un pool GPU.

| Role IA | Nombre | Taille indicative | Remarques |
|---------|--------|-------------------|-----------|
| LLM inference | 1-2 GPU VM | NVIDIA L4/A10 minimum selon modele | vLLM ou runtime equivalent |
| Embeddings | 1 VM CPU ou GPU legere | 4-8 vCPU, 16 Go RAM | Peut etre separe du LLM |
| STT/TTS self-hosted | 1-2 GPU VM | L4/A10 minimum | A dimensionner apres benchmark audio |

Cette option doit etre traitee comme une evolution d'architecture, pas comme un
pre-requis du pilote, sauf contrainte contractuelle.

## Zones reseau recommandees

- Subnet public : load balancer, ingress public, eventuel bastion.
- Subnet applicatif prive : backend Java, voice bridge, jobs.
- Subnet donnees prive : Postgres, Redis, stockage interne.
- Sorties internet controlees : STT/TTS/LLM manages, mises a jour, observabilite.
- Lien prive BSS : VPN, peering, private endpoint ou interconnexion dediee.

## Sizing par charge vocale

Les valeurs ci-dessous sont des points de depart a valider par test de charge.

| Appels simultanes | Backend Java | Voice bridge | Donnees |
|-------------------|--------------|--------------|---------|
| 5-10 | 2 replicas, 2 vCPU chacun | 2 replicas, 2 vCPU chacun | Postgres 4 vCPU, Redis 2 vCPU |
| 20-50 | 3-4 replicas, 2-4 vCPU chacun | 3-5 replicas, 4 vCPU chacun | Postgres 4-8 vCPU, Redis 2-4 vCPU |
| 50-100 | 5+ replicas, 4 vCPU chacun | 6+ replicas, 4-8 vCPU chacun | Postgres 8+ vCPU, Redis HA 4 vCPU |

Le voice bridge doit etre scale sur les appels actifs et la latence audio. Le
backend doit etre scale sur le nombre de conversations, la latence BSS et le
temps de generation LLM.

## Observabilite minimale

Chaque conversation doit permettre de mesurer :

- temps jusqu'a premiere transcription STT ;
- temps de recuperation BSS ;
- temps de recherche vectorielle ;
- temps jusqu'au premier token LLM ;
- temps jusqu'au premier audio TTS ;
- nombre et raison des escalades ;
- erreurs provider STT/TTS/LLM ;
- erreurs BSS ou donnees insuffisantes.

## Recommandation de demarrage

Pour un pilote operateur, demarrer avec :

- 3 VM Kubernetes generales ;
- 2 VM Kubernetes dediees voice bridge ;
- PostgreSQL + pgvector manage HA ;
- Redis manage HA ;
- frontend sur CDN ;
- observabilite managee ;
- IA managee, avec chemin d'evolution documente vers un pool GPU.

Cette cible evite de surdimensionner le pilote tout en preparant les points
critiques d'une production operateur : scalabilite, haute disponibilite,
separation des roles, securite reseau et observabilite.
