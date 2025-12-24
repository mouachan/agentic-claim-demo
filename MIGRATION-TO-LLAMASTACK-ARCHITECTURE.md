# Migration vers Architecture LlamaStack Officielle Red Hat

## Objectif

Migrer l'architecture actuelle (custom HTTP services) vers l'architecture officielle Red Hat OpenShift AI 3.0 avec:
- **LlamaStack Distribution** comme control plane
- **Vrais serveurs MCP** (protocole SSE/stdio)
- **Agents API** de LlamaStack pour l'orchestration

## Sources de Référence

1. [Red Hat OpenShift AI 3.0 - Working with Llama Stack](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html-single/working_with_llama_stack/working_with_llama_stack)
2. [opendatahub-io/llama-stack-demos](https://github.com/opendatahub-io/llama-stack-demos)
3. [rh-ai-quickstart/llama-stack-mcp-server](https://github.com/rh-ai-quickstart/llama-stack-mcp-server)
4. [Exploring Llama Stack with Python: Tool calling and agents](https://developers.redhat.com/articles/2025/07/15/exploring-llama-stack-python-tool-calling-and-agents)

## Architecture Actuelle ❌

```
Frontend → Backend FastAPI (custom)
              ↓
         Orchestrator (custom Python/HTTP)
              ↓
    ┌─────────┼─────────┐
    ↓         ↓         ↓
  OCR       RAG      Llama 3.2 3B
  (HTTP)    (HTTP)   (InferenceService)
```

**Problèmes:**
- Pas de LlamaStack central
- "MCP servers" sont juste des services HTTP custom
- Orchestration manuelle dans le code
- Ne suit pas l'architecture Red Hat officielle

## Architecture Cible ✅

```
Frontend
    ↓ (OpenAI-compatible API)
LlamaStack Distribution (control plane)
    ├─ Agents API (orchestration)
    ├─ Inference API → Llama 3.2 3B vLLM
    └─ Tool Runtime (MCP protocol)
         ↓
    ┌────┼────┐
    ↓    ↓    ↓
  OCR  RAG  Decision
  (MCP) (MCP) (MCP)
  SSE  SSE   SSE
```

**Avantages:**
- Conforme à Red Hat OpenShift AI 3.0
- LlamaStack gère l'orchestration (Agents API)
- Protocole MCP standard (SSE)
- Unified API layer
- Standardisé et supporté

## Plan de Migration

### Phase 1: Déployer LlamaStack Distribution

#### 1.1 Créer le Custom Resource LlamaStackDistribution

**Fichier:** `openshift/llamastack/distribution.yaml`

```yaml
apiVersion: llamastack.io/v1alpha1
kind: LlamaStackDistribution
metadata:
  name: claims-llamastack
  namespace: claims-demo
spec:
  replicas: 1

  server:
    containerSpec:
      image: rh-dev  # Red Hat internal reference
      resources:
        requests:
          cpu: "500m"
          memory: "2Gi"
        limits:
          cpu: 4
          memory: "8Gi"

      env:
        # Inference configuration
        - name: INFERENCE_MODEL
          value: "llama-3.2-3b-instruct"
        - name: VLLM_URL
          value: "http://llama-instruct-32-3b-predictor.llama-instruct-32-3b-demo.svc.cluster.local:80/v1"
        - name: VLLM_MAX_TOKENS
          value: "8192"

        # Vector store (FAISS inline pour démo)
        - name: VECTOR_STORE_TYPE
          value: "faiss"
        - name: EMBEDDING_MODEL
          value: "sentence-transformers/all-mpnet-base-v2"
        - name: EMBEDDING_DIMENSION
          value: "768"

        # MCP Tool Servers
        - name: MCP_OCR_SERVER_URL
          value: "http://ocr-mcp-server.claims-demo.svc.cluster.local:8080/sse"
        - name: MCP_RAG_SERVER_URL
          value: "http://rag-mcp-server.claims-demo.svc.cluster.local:8080/sse"
        - name: MCP_DECISION_SERVER_URL
          value: "http://decision-mcp-server.claims-demo.svc.cluster.local:8080/sse"

  # Configuration des APIs activées
  apis:
    - inference
    - agents
    - tool_runtime
    - safety
    - telemetry
    - vector_io

  # Providers
  providers:
    inference:
      - provider_type: remote::vllm
        config:
          url: "http://llama-instruct-32-3b-predictor.llama-instruct-32-3b-demo.svc.cluster.local:80/v1"
          model: llama-3.2-3b-instruct

    tool_runtime:
      - provider_type: model-context-protocol
        config:
          mcp_servers:
            - name: ocr-server
              uri: "sse://ocr-mcp-server.claims-demo.svc.cluster.local:8080"
              tools:
                - ocr_document

            - name: rag-server
              uri: "sse://rag-mcp-server.claims-demo.svc.cluster.local:8080"
              tools:
                - retrieve_user_info
                - retrieve_similar_claims

            - name: decision-server
              uri: "sse://decision-mcp-server.claims-demo.svc.cluster.local:8080"
              tools:
                - make_final_decision
```

#### 1.2 Service pour LlamaStack

**Fichier:** `openshift/llamastack/service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: llamastack
  namespace: claims-demo
spec:
  selector:
    app.kubernetes.io/name: llamastack
    app.kubernetes.io/instance: claims-llamastack
  ports:
    - name: http
      port: 8080
      targetPort: 8080
      protocol: TCP
  type: ClusterIP
```

#### 1.3 Route pour accès externe (si nécessaire)

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: llamastack
  namespace: claims-demo
spec:
  to:
    kind: Service
    name: llamastack
  port:
    targetPort: http
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

### Phase 2: Convertir les Serveurs MCP au Protocole Standard

Les serveurs MCP actuels utilisent HTTP custom. Il faut les convertir au **protocole MCP standard (SSE)**.

#### 2.1 Structure d'un Serveur MCP SSE

**Template Python pour serveur MCP SSE:**

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import json
import asyncio

app = FastAPI()

# MCP Tools definitions
TOOLS = {
    "ocr_document": {
        "description": "Extract text from document",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_path": {"type": "string"}
            },
            "required": ["document_path"]
        }
    }
}

async def mcp_event_stream() -> AsyncGenerator[str, None]:
    """
    Server-Sent Events stream pour MCP protocol.
    LlamaStack se connecte à ce endpoint.
    """
    # Envoyer les tools disponibles
    yield f"data: {json.dumps({'type': 'tools', 'tools': TOOLS})}\n\n"

    # Keep-alive et attente de requêtes
    while True:
        await asyncio.sleep(30)
        yield f"data: {json.dumps({'type': 'ping'})}\n\n"

@app.get("/sse")
async def mcp_sse_endpoint():
    """
    Endpoint SSE pour MCP protocol.
    LlamaStack se connecte ici pour découvrir les tools.
    """
    return StreamingResponse(
        mcp_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/tools/{tool_name}")
async def execute_tool(tool_name: str, params: dict):
    """
    Endpoint appelé par LlamaStack pour exécuter un tool.
    """
    if tool_name == "ocr_document":
        # Logic OCR ici
        result = await process_ocr(params["document_path"])
        return {"success": True, "result": result}

    return {"success": False, "error": "Unknown tool"}
```

#### 2.2 Déploiement Serveur MCP OCR

**Fichier:** `openshift/mcp-servers/ocr-mcp-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ocr-mcp-server
  namespace: claims-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ocr-mcp-server
  template:
    metadata:
      labels:
        app: ocr-mcp-server
        mcp-server: "true"
    spec:
      containers:
      - name: ocr-mcp
        image: quay.io/claims-demo/ocr-mcp-server:latest
        ports:
        - containerPort: 8080
          name: sse
        env:
        - name: MCP_SERVER_NAME
          value: "ocr-server"
        - name: LOG_LEVEL
          value: "INFO"
        volumeMounts:
        - name: documents
          mountPath: /mnt/documents
          readOnly: true
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2"
            memory: "4Gi"
      volumes:
      - name: documents
        persistentVolumeClaim:
          claimName: claim-documents-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: ocr-mcp-server
  namespace: claims-demo
  labels:
    mcp-server: "true"
spec:
  selector:
    app: ocr-mcp-server
  ports:
  - name: sse
    port: 8080
    targetPort: 8080
  type: ClusterIP
```

#### 2.3 Serveurs MCP à Créer

1. **OCR MCP Server** (`backend/mcp_servers/ocr_mcp_server/`)
   - Tool: `ocr_document`
   - Protocole: SSE
   - Endpoint: `/sse`

2. **RAG MCP Server** (`backend/mcp_servers/rag_mcp_server/`)
   - Tools:
     - `retrieve_user_info`
     - `retrieve_similar_claims`
   - Protocole: SSE
   - Endpoint: `/sse`

3. **Decision MCP Server** (`backend/mcp_servers/decision_mcp_server/`)
   - Tool: `make_final_decision`
   - Protocole: SSE
   - Endpoint: `/sse`

### Phase 3: Modifier le Backend pour Utiliser LlamaStack Agents API

#### 3.1 Nouveau Client LlamaStack

**Fichier:** `backend/app/llamastack/client_agents.py`

```python
import httpx
from typing import Optional, Dict, List, Any

class LlamaStackAgentsClient:
    """
    Client pour LlamaStack Agents API.
    Remplace l'orchestrateur custom.
    """

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=300.0)

    async def create_agent_session(
        self,
        agent_config: Dict[str, Any],
        session_name: str
    ) -> str:
        """
        Créer une session d'agent.
        """
        response = await self.client.post(
            f"{self.base_url}/agents/sessions/create",
            json={
                "agent_config": agent_config,
                "session_name": session_name
            }
        )
        response.raise_for_status()
        return response.json()["session_id"]

    async def run_agent_turn(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Exécuter un tour d'agent avec tool calling automatique.
        LlamaStack orchestre les appels aux MCP servers.
        """
        response = await self.client.post(
            f"{self.base_url}/agents/turn/create",
            json={
                "session_id": session_id,
                "messages": messages,
                "stream": stream
            }
        )
        response.raise_for_status()
        return response.json()

    async def process_claim_with_agent(
        self,
        claim_id: str,
        claim_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process un claim en utilisant LlamaStack Agents API.
        """
        # Configuration de l'agent avec tools MCP
        agent_config = {
            "model": "llama-3.2-3b-instruct",
            "instructions": """You are a claims processing agent.
            You must process the claim through these steps:
            1. Extract text using ocr_document
            2. Retrieve user info using retrieve_user_info
            3. Find similar claims using retrieve_similar_claims
            4. Make final decision using make_final_decision
            """,
            "tools": [
                {"type": "mcp", "mcp_server": "ocr-server", "tool_name": "ocr_document"},
                {"type": "mcp", "mcp_server": "rag-server", "tool_name": "retrieve_user_info"},
                {"type": "mcp", "mcp_server": "rag-server", "tool_name": "retrieve_similar_claims"},
                {"type": "mcp", "mcp_server": "decision-server", "tool_name": "make_final_decision"}
            ],
            "tool_choice": "auto"
        }

        # Créer session
        session_id = await self.create_agent_session(
            agent_config=agent_config,
            session_name=f"claim-{claim_id}"
        )

        # Lancer le traitement
        messages = [{
            "role": "user",
            "content": f"Process claim {claim_id} with document at {claim_data['document_path']}"
        }]

        result = await self.run_agent_turn(
            session_id=session_id,
            messages=messages
        )

        return result
```

#### 3.2 Modifier l'Endpoint Backend

**Fichier:** `backend/app/api/claims.py`

```python
from app.llamastack.client_agents import LlamaStackAgentsClient

@router.post("/{claim_id}/process")
async def process_claim(claim_id: str, db: AsyncSession = Depends(get_db)):
    """
    Process a claim using LlamaStack Agents API.
    """
    # Get claim from DB
    claim = await get_claim_by_id(db, claim_id)

    # Créer client LlamaStack
    llamastack = LlamaStackAgentsClient(
        base_url=settings.llamastack_endpoint
    )

    # Process via LlamaStack Agents API
    result = await llamastack.process_claim_with_agent(
        claim_id=claim_id,
        claim_data={
            "document_path": claim.document_path,
            "user_id": claim.user_id
        }
    )

    # Update claim status
    await update_claim_status(db, claim_id, "completed", result)

    return result
```

### Phase 4: Déploiement et Migration

#### 4.1 Ordre de Déploiement

```bash
# 1. Déployer LlamaStack Distribution
oc apply -f openshift/llamastack/distribution.yaml
oc apply -f openshift/llamastack/service.yaml

# 2. Attendre que LlamaStack soit ready
oc wait --for=condition=Ready llamastackdistribution/claims-llamastack -n claims-demo --timeout=5m

# 3. Déployer les MCP servers
oc apply -f openshift/mcp-servers/ocr-mcp-deployment.yaml
oc apply -f openshift/mcp-servers/rag-mcp-deployment.yaml
oc apply -f openshift/mcp-servers/decision-mcp-deployment.yaml

# 4. Vérifier que LlamaStack découvre les MCP servers
oc logs -n claims-demo deployment/llamastack | grep "MCP server registered"

# 5. Redéployer le backend avec nouveau client
oc apply -f openshift/deployments/backend-deployment.yaml

# 6. Tester l'intégration
curl -X POST https://backend-claims-demo.apps.cluster.../api/v1/claims/{id}/process
```

#### 4.2 Vérification

```bash
# Check LlamaStack status
oc get llamastackdistribution claims-llamastack -n claims-demo

# Check MCP servers
oc get pods -n claims-demo -l mcp-server=true

# Test LlamaStack Agents API directement
curl http://llamastack.claims-demo.svc.cluster.local:8080/agents/turn/create \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session",
    "messages": [{"role": "user", "content": "Process claim"}]
  }'
```

## Comparaison Avant/Après

| Aspect | Avant (Custom) | Après (LlamaStack) |
|--------|----------------|-------------------|
| Orchestration | Code Python custom | LlamaStack Agents API |
| MCP Protocol | HTTP custom | SSE standard |
| Tool Discovery | Hardcodé | Automatique via config |
| API Standard | Non | Oui (OpenAI-compatible) |
| Red Hat Support | Non | Oui |
| Maintenance | Custom code | Framework standard |

## Bénéfices

1. **Conformité Red Hat:** Architecture officielle OpenShift AI 3.0
2. **Standardisation:** Protocole MCP + API OpenAI-compatible
3. **Moins de code:** LlamaStack gère l'orchestration
4. **Évolutivité:** Facile d'ajouter de nouveaux MCP servers
5. **Support:** Red Hat supporte cette architecture

## Références

- [Red Hat OpenShift AI 3.0 - Working with Llama Stack](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.0/html-single/working_with_llama_stack/working_with_llama_stack)
- [opendatahub-io/llama-stack-demos](https://github.com/opendatahub-io/llama-stack-demos)
- [Running llama-stack with MCP server](https://medium.com/@jameswnl/running-llama-stack-with-mcp-server-ad4cd38b2c62)
- [MCP with llama-stack](https://medium.com/@j.robert.boos/mcp-with-llama-stack-984615403b6d)
- [Exploring Llama Stack with Python: Tool calling and agents](https://developers.redhat.com/articles/2025/07/15/exploring-llama-stack-python-tool-calling-and-agents)
