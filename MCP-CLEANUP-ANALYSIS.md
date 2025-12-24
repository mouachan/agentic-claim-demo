# Analyse et Nettoyage des MCP Servers

Date: 2025-12-24
Objectif: Nettoyer l'architecture pour être conforme à LlamaStack

## Problème Identifié

L'architecture actuelle utilise des **services HTTP custom** au lieu de **vrais serveurs MCP** avec le protocole standard (SSE). De plus, l'orchestrateur custom n'est pas nécessaire car **LlamaStack Agents API gère l'orchestration**.

## Architecture Actuelle (Incorrecte) ❌

```
Frontend → Backend → Orchestrator Server (custom HTTP)
                           ↓
                ┌──────────┼──────────┐
                ↓          ↓          ↓
             OCR       RAG      Guardrails
          (HTTP)     (HTTP)      (vide)
```

**Problèmes:**
1. **Orchestrator Server** = orchestration manuelle custom
   - Avec LlamaStack Agents API, c'est LlamaStack qui orchestre
   - Redondant et inutile

2. **Serveurs MCP = HTTP custom** (FastAPI), pas MCP protocol (SSE)
   - Ne peuvent pas être enregistrés comme MCP servers dans LlamaStack
   - Pas de découverte automatique des tools

3. **Guardrails Server** = répertoire vide
   - On utilise TrustyAI Guardrails Orchestrator

4. **Logique d'orchestration dupliquée**
   - `llamastack_agent_orchestrator.py` = orchestration avec tool calling
   - Mais LlamaStack Agents API fait déjà ça automatiquement

## Architecture Cible (Correcte) ✅

```
Frontend → Backend → LlamaStack Distribution
                         ↓ (Agents API)
                         ↓ (Tool Runtime: MCP Protocol SSE)
                    ┌────┼────┐
                    ↓    ↓    ↓
                  OCR  RAG  TrustyAI
                 (MCP) (MCP) (Guardrails)
                  SSE   SSE
```

**Ce qui change:**
1. **LlamaStack Agents API** gère l'orchestration (pas d'orchestrator custom)
2. **Vrais serveurs MCP** avec protocole SSE
3. **TrustyAI Guardrails Orchestrator** pour la sécurité (via CRD)

## Inventaire des MCP Servers Actuels

### 1. `orchestrator_server/` ❌ **À SUPPRIMER**

**Fichiers:**
```
orchestrator_server/
├── Dockerfile
├── llamastack_agent_orchestrator.py    # Orchestration avec LLM
├── llamastack_orchestrator.py
├── llamastack_responses_orchestrator.py
├── prompts.py
├── requirements.txt
└── server.py                           # FastAPI server
```

**Raison de suppression:**
- **LlamaStack Agents API gère déjà l'orchestration**
- L'agent LlamaStack appelle automatiquement les tools MCP dans le bon ordre
- Le fichier `llamastack_agent_orchestrator.py` implémente du tool calling, mais c'est déjà fait par LlamaStack
- Redondant et crée de la complexité inutile

**Workflow avec LlamaStack (sans orchestrator custom):**
```python
# Backend appelle directement LlamaStack Agents API
response = await llamastack_client.post("/v1beta/agents/turn/create", json={
    "agent_config": {
        "model": "llama-instruct-32-3b",
        "tools": ["mcp::ocr-server::ocr_document",
                  "mcp::rag-server::retrieve_user_info",
                  "mcp::rag-server::retrieve_similar_claims"],
        "instructions": "Process this claim..."
    },
    "messages": [{"role": "user", "content": "Process claim 12345"}]
})

# LlamaStack orchestre automatiquement:
# 1. Appelle ocr_document
# 2. Appelle retrieve_user_info
# 3. Appelle retrieve_similar_claims
# 4. Génère la décision finale
# Tout cela sans orchestrator custom!
```

### 2. `guardrails_server/` ❌ **À SUPPRIMER**

**Fichiers:**
```
guardrails_server/
(vide - 0 fichiers)
```

**Raison de suppression:**
- Répertoire vide
- On utilise **TrustyAI Guardrails Orchestrator** (CRD OpenShift AI)
- Voir `TRUSTYAI-GUARDRAILS-GUIDE.md` pour la configuration

### 3. `ocr_server/` ✅ **À CONSERVER mais CONVERTIR au protocole MCP**

**Fichiers:**
```
ocr_server/
├── Dockerfile
├── prompts.py
├── requirements.txt
└── server.py                # FastAPI HTTP - à convertir en MCP SSE
```

**État actuel:**
- Service HTTP FastAPI avec endpoint `POST /ocr_document`
- Pas de protocole MCP (SSE)

**À faire:**
- Convertir en vrai serveur MCP avec protocole SSE
- Exposer le tool `ocr_document` via MCP
- Garder la logique OCR (Tesseract + validation LLM)

**Tool MCP à exposer:**
```python
{
    "type": "function",
    "function": {
        "name": "ocr_document",
        "description": "Extract text from document images or PDFs using OCR and validate with LLM",
        "parameters": {
            "type": "object",
            "properties": {
                "document_path": {"type": "string"},
                "document_type": {"type": "string", "default": "claim_form"},
                "language": {"type": "string", "default": "eng"}
            },
            "required": ["document_path"]
        }
    }
}
```

### 4. `rag_server/` ✅ **À CONSERVER mais CONVERTIR au protocole MCP**

**Fichiers:**
```
rag_server/
├── Dockerfile
├── prompts.py
├── requirements.txt
└── server.py                # FastAPI HTTP - à convertir en MCP SSE
```

**État actuel:**
- Service HTTP FastAPI avec 3 endpoints
- Pas de protocole MCP (SSE)

**À faire:**
- Convertir en vrai serveur MCP avec protocole SSE
- Exposer 3 tools via MCP
- Garder la logique RAG (pgvector + embeddings)

**Tools MCP à exposer:**
```python
[
    {
        "type": "function",
        "function": {
            "name": "retrieve_user_info",
            "description": "Retrieve user information and contracts using vector search",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["user_id", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_similar_claims",
            "description": "Find similar historical claims using vector similarity",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_text": {"type": "string"},
                    "top_k": {"type": "integer", "default": 10},
                    "min_similarity": {"type": "number", "default": 0.7}
                },
                "required": ["claim_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search the knowledge base for policy information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
    }
]
```

## Protocole MCP (SSE) - Template

Voici comment un vrai serveur MCP doit être structuré:

```python
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

app = FastAPI()

# Définition des tools MCP
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ocr_document",
            "description": "Extract text from documents",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_path": {"type": "string"}
                },
                "required": ["document_path"]
            }
        }
    }
]

# SSE endpoint pour la découverte des tools
@app.get("/mcp/sse")
async def mcp_sse_endpoint():
    """
    Server-Sent Events endpoint pour MCP protocol.
    LlamaStack se connecte ici pour découvrir les tools.
    """
    async def event_generator():
        # Envoyer la liste des tools disponibles
        yield {
            "event": "tools",
            "data": json.dumps({"tools": TOOLS})
        }

        # Keep-alive
        while True:
            await asyncio.sleep(30)
            yield {
                "event": "ping",
                "data": json.dumps({"status": "alive"})
            }

    return EventSourceResponse(event_generator())

# Endpoint pour exécuter un tool
@app.post("/mcp/tools/{tool_name}")
async def execute_tool(tool_name: str, params: dict):
    """
    Endpoint appelé par LlamaStack pour exécuter un tool.
    """
    if tool_name == "ocr_document":
        result = await process_ocr(params["document_path"])
        return {"success": True, "result": result}

    return {"success": False, "error": "Unknown tool"}
```

## Plan de Nettoyage et Conversion

### Phase 1: Suppression ❌

#### 1.1 Supprimer `orchestrator_server/`

```bash
# Supprimer le répertoire complet
rm -rf backend/mcp_servers/orchestrator_server/

# Supprimer les déploiements OpenShift associés
oc delete deployment orchestrator-server -n claims-demo
oc delete service orchestrator-server -n claims-demo
oc delete configmap orchestrator-server-config -n claims-demo
```

**Impact:**
- Backend n'appelle plus l'orchestrator
- Backend appelle directement LlamaStack Agents API
- LlamaStack orchestre les tools MCP

**Fichiers backend à modifier:**
- `backend/app/api/claims.py` - supprimer les appels à l'orchestrator
- `backend/app/services/claim_processor.py` - utiliser LlamaStack Agents API

#### 1.2 Supprimer `guardrails_server/`

```bash
# Supprimer le répertoire vide
rm -rf backend/mcp_servers/guardrails_server/
```

**Remplacement:**
- TrustyAI Guardrails Orchestrator (voir `TRUSTYAI-GUARDRAILS-GUIDE.md`)

### Phase 2: Conversion au Protocole MCP ✅

#### 2.1 Convertir `ocr_server/` en vrai MCP server

**Nouveau fichier:** `backend/mcp_servers/ocr_server/mcp_server.py`

Changements:
- Ajouter endpoint SSE `/mcp/sse` pour la découverte des tools
- Changer endpoint REST de `/ocr_document` à `/mcp/tools/ocr_document`
- Implémenter le protocole MCP standard
- Exposer les tools au format MCP

**Dépendances à ajouter:**
```
sse-starlette==1.6.5
```

#### 2.2 Convertir `rag_server/` en vrai MCP server

**Nouveau fichier:** `backend/mcp_servers/rag_server/mcp_server.py`

Changements:
- Ajouter endpoint SSE `/mcp/sse` pour la découverte des tools
- Changer endpoints REST:
  - `/retrieve_user_info` → `/mcp/tools/retrieve_user_info`
  - `/retrieve_similar_claims` → `/mcp/tools/retrieve_similar_claims`
  - `/search_knowledge_base` → `/mcp/tools/search_knowledge_base`
- Implémenter le protocole MCP standard
- Exposer les 3 tools au format MCP

**Dépendances à ajouter:**
```
sse-starlette==1.6.5
```

### Phase 3: Configuration LlamaStack 🔧

#### 3.1 Enregistrer les MCP servers dans LlamaStack

**Fichier:** `openshift/llamastack/run.yaml`

```yaml
providers:
  tool_runtime:
    - provider_id: model-context-protocol
      provider_type: remote::model-context-protocol
      config:
        mcp_servers:
          # OCR MCP Server
          - name: ocr-server
            uri: sse://ocr-mcp-server.claims-demo.svc.cluster.local:8080/mcp/sse
            tools:
              - ocr_document

          # RAG MCP Server
          - name: rag-server
            uri: sse://rag-mcp-server.claims-demo.svc.cluster.local:8080/mcp/sse
            tools:
              - retrieve_user_info
              - retrieve_similar_claims
              - search_knowledge_base

# Tool groups pour les agents
tool_groups:
  - toolgroup_id: builtin::rag
    provider_id: rag-runtime

  - toolgroup_id: claims-processing
    provider_id: model-context-protocol
    tools:
      - name: ocr-server::ocr_document
      - name: rag-server::retrieve_user_info
      - name: rag-server::retrieve_similar_claims
      - name: rag-server::search_knowledge_base
```

#### 3.2 Modifier le Backend pour utiliser Agents API

**Fichier:** `backend/app/services/claim_processor.py`

Avant (avec orchestrator custom):
```python
# Appeler l'orchestrator custom
response = await httpx.post(
    f"{ORCHESTRATOR_URL}/orchestrate_claim_processing",
    json={"claim_id": claim_id, "document_path": doc_path}
)
```

Après (avec LlamaStack Agents API):
```python
# Créer une session d'agent
session_id = await llamastack.create_agent_session(
    agent_config={
        "model": "llama-instruct-32-3b",
        "tools": ["claims-processing"],  # Tool group
        "instructions": "Process this claim by: 1) OCR the document, 2) Retrieve user info, 3) Find similar claims, 4) Make a decision",
        "enable_session_persistence": True
    },
    session_name=f"claim-{claim_id}"
)

# Lancer le traitement (LlamaStack orchestre automatiquement)
result = await llamastack.run_agent_turn(
    session_id=session_id,
    messages=[{
        "role": "user",
        "content": f"Process claim {claim_id} with document at {doc_path}"
    }]
)
```

## Bénéfices du Nettoyage

### Simplicité ✨
- **Moins de code custom** à maintenir
- **Architecture standard** LlamaStack
- **Protocole MCP officiel** au lieu de HTTP custom

### Performance 🚀
- **Découverte automatique** des tools via SSE
- **Orchestration optimisée** par LlamaStack
- **Pas de hop supplémentaire** (orchestrator)

### Conformité 📋
- **Architecture Red Hat officielle**
- **Protocole MCP standard** (opendatahub-io/llama-stack-demos)
- **Supporté et documenté** par Red Hat

### Évolutivité 📈
- **Facile d'ajouter de nouveaux tools** MCP
- **LlamaStack gère la complexité** de l'orchestration
- **Tool calling automatique** avec le bon ordre

## Structure Finale des MCP Servers

```
backend/mcp_servers/
├── ocr_server/              ✅ MCP Server (SSE)
│   ├── Dockerfile
│   ├── mcp_server.py        ← Nouveau: Protocole MCP
│   ├── ocr_logic.py         ← Logique OCR (Tesseract)
│   ├── prompts.py
│   └── requirements.txt
│
└── rag_server/              ✅ MCP Server (SSE)
    ├── Dockerfile
    ├── mcp_server.py        ← Nouveau: Protocole MCP
    ├── rag_logic.py         ← Logique RAG (pgvector)
    ├── prompts.py
    └── requirements.txt

Supprimés:
❌ orchestrator_server/      (LlamaStack Agents API gère l'orchestration)
❌ guardrails_server/        (TrustyAI Guardrails Orchestrator)
```

## Ordre d'Exécution

1. ✅ **Documenter l'analyse** (ce fichier)
2. ❌ **Supprimer `orchestrator_server/`** et `guardrails_server/`
3. 🔄 **Convertir `ocr_server/`** au protocole MCP (SSE)
4. 🔄 **Convertir `rag_server/`** au protocole MCP (SSE)
5. 🔧 **Configurer LlamaStack** pour enregistrer les MCP servers
6. 🔧 **Modifier le backend** pour utiliser Agents API au lieu de l'orchestrator
7. 🧪 **Tester** le workflow complet end-to-end
8. 📝 **Mettre à jour** la documentation

## Validation

Après le nettoyage, vérifier:

- [ ] `orchestrator_server/` supprimé
- [ ] `guardrails_server/` supprimé
- [ ] `ocr_server/` expose endpoint SSE `/mcp/sse`
- [ ] `rag_server/` expose endpoint SSE `/mcp/sse`
- [ ] LlamaStack découvre automatiquement les tools MCP
- [ ] Backend appelle LlamaStack Agents API (pas d'orchestrator)
- [ ] TrustyAI Guardrails Orchestrator configuré
- [ ] Workflow end-to-end fonctionne

## Conclusion

Le nettoyage va:
1. **Supprimer** l'orchestrator custom (redondant avec LlamaStack)
2. **Supprimer** le guardrails vide (remplacé par TrustyAI)
3. **Convertir** les serveurs HTTP custom en vrais serveurs MCP (SSE)
4. **Simplifier** l'architecture pour être conforme à Red Hat OpenShift AI 3.0

Résultat: Architecture propre, standard, et maintainable. ✅
