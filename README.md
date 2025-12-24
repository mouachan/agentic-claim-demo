# Agentic Claims Processing Demo

Démonstration complète d'un système de traitement de claims d'assurance utilisant des agents MCP (Model Context Protocol), LlamaStack et OpenShift AI 3.0.

## 🎯 Vue d'Ensemble

Application full-stack combinant :
- **Backend FastAPI** avec API REST complète
- **Frontend React** avec interface moderne
- **3 Agents MCP** : OCR, RAG et Orchestrator
- **LlamaStack** pour l'intelligence LLM
- **PostgreSQL + pgvector** pour stockage et recherche vectorielle
- **Déploiement OpenShift AI 3.0** avec CRDs natifs

## 🏗️ Architecture

```
Frontend (React)
   │
   ├──> Backend API (FastAPI)
          │
          └──> Orchestrator MCP
                 │
                 ├──> OCR Agent (Tesseract + LLM)
                 ├──> Guardrails (PII detection)
                 ├──> RAG Agent (pgvector + LLM)
                 └──> LlamaStack (vLLM + Milvus/FAISS)
```

## 🚀 Démarrage Rapide

### Développement Local

```bash
# 1. Démarrer tous les services avec Docker/Podman
podman-compose up -d

# 2. Accéder à l'interface
open http://localhost:3000

# Backend API
open http://localhost:8000/docs
```

### Déploiement OpenShift AI 3.0

Voir le guide de déploiement complet : `openshift/README-OPENSHIFT-AI.md`

Les fichiers de déploiement sont conformes à OpenShift AI 3.0 selon la documentation officielle Red Hat.

## 📂 Structure du Projet

```
.
├── backend/
│   ├── app/                      # FastAPI application
│   │   ├── api/                 # Endpoints REST
│   │   ├── models/              # SQLAlchemy models
│   │   └── core/                # Configuration
│   └── mcp_servers/             # Agents MCP
│       ├── ocr_server/          # OCR + validation LLM
│       ├── rag_server/          # RAG + recherche vectorielle
│       └── orchestrator_server/ # Orchestration des agents
├── frontend/
│   └── src/                     # Application React
│       ├── components/          # Composants UI
│       ├── pages/               # Pages (Dashboard, Claims)
│       └── services/            # Client API
├── database/
│   ├── init.sql                 # Schema PostgreSQL + pgvector
│   └── seed_data/               # Données de test
├── openshift/
│   ├── crds/                    # Custom Resources (LlamaStack)
│   ├── deployments/             # Deployments Kubernetes
│   └── services/                # Services et Routes
└── documents/                   # Documents de test
```

## 📚 Documentation

### Déploiement OpenShift AI 3.0
- **openshift/README-OPENSHIFT-AI.md** - Guide de déploiement complet
- **openshift/crds/** - Custom Resource Definitions conformes OpenShift AI 3.0

## ✨ Fonctionnalités

### Frontend
- ✅ Dashboard avec statistiques en temps réel
- ✅ Liste des claims avec filtres et pagination
- ✅ Détails de claim avec workflow de traitement
- ✅ Suivi du traitement en temps réel

### Backend API
- ✅ CRUD complet pour les claims
- ✅ Workflow de traitement agentic
- ✅ Logs détaillés par étape
- ✅ Décisions avec raisonnement LLM

### Agents MCP
- ✅ **OCR Agent** : Extraction de texte (Tesseract) + validation LLM
- ✅ **Guardrails Agent** : Détection PII + redaction
- ✅ **RAG Agent** : Recherche vectorielle + augmentation contexte
- ✅ **Orchestrator** : Coordination des agents + décision finale

### Base de Données
- ✅ PostgreSQL avec extension pgvector
- ✅ Stockage des claims et documents
- ✅ Recherche vectorielle pour RAG
- ✅ Logs de traitement par agent

## 🎯 Workflow de Traitement

```
1. Soumission du claim
   ↓
2. OCR → Extraction de texte du document
   ↓
3. Guardrails → Validation et détection PII
   ↓
4. RAG → Récupération contrats et claims similaires
   ↓
5. LLM Decision → Analyse finale et recommandation
   (APPROVE / DENY / MANUAL_REVIEW)
```

## 🛠️ Stack Technique

### Backend
- Python 3.11+
- FastAPI (API REST)
- SQLAlchemy (ORM)
- PostgreSQL + pgvector
- Tesseract OCR
- LlamaStack / Ollama (LLM)

### Frontend
- React 18
- TypeScript
- Vite
- TailwindCSS
- React Router v6
- Axios

### Infrastructure
- Docker / Podman
- OpenShift / Kubernetes
- OpenShift AI 3.0
- vLLM (inference)
- Milvus / FAISS (vector DB)

## 📊 État du Projet

### ✅ Complété
- Backend FastAPI avec tous les endpoints
- Frontend React fonctionnel
- 3 serveurs MCP (OCR, RAG, Orchestrator)
- PostgreSQL + pgvector configuré
- Seed data et tests
- Documentation complète
- CRDs conformes OpenShift AI 3.0

### 🔄 En Cours
- Déploiement sur OpenShift AI 3.0
- Configuration avec LlamaStack et vos 4 modèles LLM
- Tests end-to-end sur OpenShift

## 🧪 Tests

### Développement Local

```bash
# Démarrer tous les services
podman-compose up -d

# Vérifier que tout fonctionne
curl http://localhost:8000/health
curl http://localhost:3000

# Accéder à l'interface
open http://localhost:3000
```

### Déploiement OpenShift

Voir la documentation dans `openshift/README-OPENSHIFT-AI.md` pour le guide de déploiement complet.

---

**Version** : 0.1.0
**Statut** : Production Ready
