# Agentic Insurance Claims Processing Demo

An intelligent insurance claims processing system powered by AI agents on Red Hat OpenShift AI, demonstrating autonomous decision-making through **ReAct (Reasoning + Acting)** workflows with built-in compliance guardrails.

## 📋 Table of Contents

- [Business Overview](#business-overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Deployment](#deployment)
- [Testing the Application](#testing-the-application)
- [Configuration Management](#configuration-management)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Known Issues](#known-issues)

---

## Business Overview

### What Problem Does This Solve?

Insurance claims processing traditionally requires manual review of documents, policy lookups, and precedent analysis—a time-consuming process prone to inconsistencies. This demo showcases how AI agents can **autonomously** process claims through intelligent reasoning and tool usage, while maintaining human oversight where needed.

### The ReAct Agentic Workflow

Instead of rigid, pre-programmed rules, the system uses **ReAct (Reasoning + Acting)** pattern where an AI agent:

1. **Thinks** about what information it needs
2. **Acts** by calling appropriate tools (OCR, RAG retrieval)
3. **Observes** the results
4. **Repeats** until it has enough information to make a decision

#### How ReAct Works in Claims Processing

```
Customer Submits Claim
        ↓
┌───────────────────────────────────────────────────────┐
│  ReAct Agent Autonomous Decision Loop                 │
├───────────────────────────────────────────────────────┤
│                                                       │
│  💭 Agent Thinks: "I need to read the document"      │
│  🔧 Agent Acts: Calls ocr_document tool              │
│  👁️ Agent Observes: Receives structured claim data   │
│                                                       │
│  💭 Agent Thinks: "I need the user's policy"         │
│  🔧 Agent Acts: Calls retrieve_user_info tool        │
│  👁️ Agent Observes: Gets coverage limits, terms      │
│                                                       │
│  💭 Agent Thinks: "Let me check similar cases"       │
│  🔧 Agent Acts: Calls retrieve_similar_claims tool   │
│  👁️ Agent Observes: Finds historical precedents      │
│                                                       │
│  💭 Agent Thinks: "I have enough information"        │
│  ✅ Agent Decides: Approve/Deny/Manual Review        │
│     with confidence score and reasoning              │
└───────────────────────────────────────────────────────┘
        ↓
  Compliance Check (PII Detection)
        ↓
  Human Review (if needed)
```

**Key Difference from Traditional Automation**:
- ❌ **Traditional**: Fixed workflow (always call tool A, then B, then C)
- ✅ **ReAct**: Agent decides which tools to use and when, based on reasoning

### Business Capabilities

#### 1. Autonomous Document Processing
- Agent decides when OCR is needed
- Understands claim context, not just text extraction
- 2-4 seconds per document vs minutes of manual review

#### 2. Smart Policy Matching
- Semantic search through user contracts
- Understands coverage limits and exclusions
- Cross-references with claim type and amount

#### 3. Precedent-Based Reasoning
- Finds similar historical claims
- Applies consistent reasoning across cases
- Identifies patterns humans might miss

#### 4. Transparent Decision-Making
- **Reasoning**: Natural language explanation
- **Evidence**: References to policies and precedents
- **Confidence Score**: Agent's certainty level
- **Full Audit Trail**: Every tool call, every thought

### Compliance & Guardrails

#### PII Detection & Protection

**Business Need**: Insurance claims contain sensitive personal information (emails, phone numbers, dates of birth) that must be protected for GDPR/CCPA compliance.

**How It Works**:
- Automatic detection during processing
- Real-time flagging without blocking workflow
- Complete audit trail for regulatory review

**What Gets Detected**:
- Email addresses
- Phone numbers
- Dates of birth
- License plates
- Other PII patterns

**Compliance Benefits**:
- GDPR/CCPA compliance support
- Audit trail for regulators
- Risk mitigation for data exposure
- Automated reporting

#### Human-in-the-Loop (HITL) Review

**When Manual Review Triggers**:
- Low confidence scores (< 70%)
- High-value claims above threshold
- Complex edge cases
- Regulatory requirements

**Review Workflow**:
1. System shows AI recommendation with reasoning
2. Reviewer can ask clarifying questions to the agent ("Ask Agent" feature)
3. Reviewer makes final decision (approve/deny/request info)
4. System tracks both AI and human decisions for audit

**Business Value**:
- Faster processing with human oversight
- Consistent decisions with expert review
- Training data for improving the agent
- Regulatory compliance (human-in-loop requirement)

---

## Architecture

### System Overview

```mermaid
graph TB
    subgraph "User Layer"
        U[👤 Customer / Claims Adjuster]
    end

    subgraph "OpenShift Cluster"
        subgraph "Application - claims-demo namespace"
            F[📱 Frontend React]
            B[⚙️ Backend FastAPI]
        end

        subgraph "OpenShift AI 3.2 - AI Platform"
            subgraph "LlamaStack Distribution"
                LS[🧠 LlamaStack 0.3.5<br/>ReAct Orchestration]
            end

            subgraph "AI Models - vLLM"
                LLM["🦙 Llama 3.3 70B INT8<br/>4xGPU (L40)<br/>20K context"]
                EMB["🔢 Gemma 300M<br/>768-dim embeddings"]
            end

            subgraph "Data Science Pipelines"
                DSPA["📊 Kubeflow Pipelines v2"]
                MINIO["💾 MinIO S3 Storage"]
            end

            subgraph "Compliance"
                GR["🛡️ TrustyAI Guardrails<br/>PII Detection"]
            end
        end

        subgraph "MCP Tool Servers - claims-demo"
            OCR["📄 OCR MCP Server<br/>EasyOCR (2-4s)"]
            RAG["🔍 RAG MCP Server<br/>pgvector similarity"]
        end

        subgraph "Data Layer - claims-demo"
            DB[(🗄️ PostgreSQL 15<br/>+ pgvector)]
        end
    end

    U -->|HTTPS| F
    F -->|REST API| B
    B -->|Responses API| LS
    LS -->|Inference| LLM
    LS -->|Embeddings| EMB
    LS -->|MCP/SSE| OCR
    LS -->|MCP/SSE| RAG
    LS -->|Shields API| GR
    RAG -->|Vector Search| DB
    B -->|CRUD| DB
    DSPA -->|Artifacts| MINIO

    style LS fill:#f3e5f5
    style LLM fill:#e8f5e9
    style GR fill:#ffebee
```

### Services Architecture

Clean separation of concerns for maintainability:

```
backend/
├── app/
│   ├── api/              # Thin API layer (HTTP routing)
│   ├── services/         # Business logic
│   │   ├── claim_service.py       # Orchestration
│   │   └── agent/                 # AI components
│   │       ├── responses_orchestrator.py  # LlamaStack client
│   │       ├── context_builder.py         # Prompt building
│   │       └── response_parser.py         # Parse AI output
│   ├── models/           # Database ORM
│   └── llamastack/       # Prompts & integration
```

**Benefits**: Testable, reusable, clear responsibilities.

### Technology Stack

- **AI Platform**: Red Hat OpenShift AI 3.2
- **LLM**: Llama 3.3 70B INT8 (vLLM, 4x L40 GPUs)
- **Embeddings**: Gemma 300M (768-dim vectors)
- **Orchestration**: LlamaStack 0.3.5 (ReAct)
- **Compliance**: TrustyAI Guardrails
- **Backend**: Python 3.12 + FastAPI
- **Frontend**: React 18 + TypeScript
- **Database**: PostgreSQL 15 + pgvector
- **Pipelines**: Kubeflow Pipelines v2
- **Deployment**: Helm 3.x on OpenShift 4.20+

---

## Prerequisites

### Required Infrastructure

1. **OpenShift 4.20+** with:
   - **GPU Nodes**: 4x NVIDIA L40 (48GB) or equivalent
   - **CPU/Memory**: 32+ vCPU, 128GB+ RAM
   - **Storage**: Dynamic provisioning (RWO, RWX)

2. **Red Hat OpenShift AI 3.2**:
   - Operator installed
   - vLLM ServingRuntime configured
   - LlamaStack operator enabled

3. **Tools**:
   ```bash
   helm version  # 3.12+
   oc version    # 4.20+
   ```

### Accounts

- **HuggingFace Token**: https://huggingface.co/settings/tokens (for model downloads)
- **Container Registry**: Quay.io, Docker Hub, or internal registry

---

## Deployment

### 1. Use Pre-built Images (Recommended)

Pre-built images are available on Quay.io:

```yaml
# In your values file
backend:
  image:
    repository: quay.io/mouachan/agentic-claims-demo/backend
    tag: v1.7.5

frontend:
  image:
    repository: quay.io/mouachan/agentic-claims-demo/frontend
    tag: v1.7.5

ocr:
  image:
    repository: quay.io/mouachan/agentic-claims-demo/ocr-server
    tag: v1.7.5

rag:
  image:
    repository: quay.io/mouachan/agentic-claims-demo/rag-server
    tag: v1.7.5

postgresql:
  image:
    repository: pgvector/pgvector
    tag: pg15
```

**Or build your own**: See [Development Guide](docs/DEVELOPMENT.md#building-container-images)

### 2. Configure Values

```bash
cd helm/agentic-claims-demo
cp values-sample.yaml values-mydeployment.yaml
```

Edit key settings:

```yaml
# Cluster domain
inference:
  endpoint: "https://llama-3-3-70b-llama-3-3-70b.apps.YOUR-CLUSTER.com/v1"

embedding:
  endpoint: "https://embeddinggemma-300m-embeddinggemma-300m.apps.YOUR-CLUSTER.com/v1"

# HuggingFace token
hfcli:
  token: "hf_YOUR_TOKEN"

# MinIO credentials
minio:
  rootPassword: "StrongPassword123!"

# Enable features
dataSciencePipelines:
  enabled: true
  objectStorage:
    scheme: http  # IMPORTANT: must be http

guardrails:
  enabled: true
```

### 3. Deploy

```bash
helm install agentic-claims-demo . \
  -f values-mydeployment.yaml \
  -n claims-demo \
  --create-namespace \
  --timeout=30m
```

**Expected time**: ~25-30 minutes (AI models download ~40GB)

### 4. Verify Deployment

```bash
# Check pods
oc get pods -n claims-demo

# Check DSPA (should be Ready=True)
oc get dspa -n claims-demo

# Get URLs
oc get routes -n claims-demo
```

### 5. Generate Embeddings (Required)

After deployment, run the embedding generation pipeline:

1. **Access OpenShift AI Dashboard** → Data Science Projects → `claims-demo` → Pipelines

2. **Import Pipeline**:

   ![Import Pipeline](assets/pipeline-import.png)

   - Click "Import pipeline"
   - Upload: `backend/pipelines/data_initialization_pipeline.yaml`
   - Name: "Historical Claims Initialization"

3. **Create Pipeline Run**:

   ![Create Run](assets/pipeline-create-run.png)

   - Click "Create run"
   - Set parameters:
     - `batch_size`: 5
     - `embedding_model`: `vllm-embedding/embeddinggemma-300m`
     - `llamastack_endpoint`: `http://llamastack-rhoai-service.claims-demo.svc.cluster.local:8321`
     - `llm_model`: `vllm-inference/llama-3-3-70b-instruct-quantized-w8a8`
     - `max_retries`: 30
     - `num_claims`: 60 (default: 10, recommended: 60 for testing)

4. **Monitor Execution**:

   ![Pipeline Graph](assets/pipeline-run-graph.png)

   - Watch pipeline graph (15-20 minutes with num_claims=60)
   - Steps: Generate PDFs → Parse → Generate Embeddings

5. **Verify**:
   ```bash
   # Check knowledge base (should be 15/15)
   oc exec -n claims-demo statefulset/postgresql -- \
     psql -U claims_user -d claims_db -c \
     "SELECT COUNT(*) FROM knowledge_base WHERE embedding IS NOT NULL;"

   # Check claims (should be 60/60 with num_claims=60)
   oc exec -n claims-demo statefulset/postgresql -- \
     psql -U claims_user -d claims_db -c \
     "SELECT COUNT(*) FROM claim_documents WHERE embedding IS NOT NULL;"
   ```

### 6. Access Application

```bash
# Frontend URL
echo "Frontend: http://$(oc get route frontend -n claims-demo -o jsonpath='{.spec.host}')"

# Backend API
echo "Backend: http://$(oc get route backend -n claims-demo -o jsonpath='{.spec.host}')/api/v1"
```

---

## Testing the Application

### Via Web UI

#### 1. View Claims List

![Claims List](assets/ui-claims-list.png)

- Navigate to Claims page
- See all processed claims with status
- Filter by status, type, user
- Processing time displayed for each claim

#### 2. Process a Pending Claim

![Claim Details](assets/ui-claim-pending.png)

- Click "View Details" on a pending claim
- Review claim information
- Click "Process Claim" button
- Wait 5-10 seconds for processing

#### 3. View Processing Steps

![Processing Steps](assets/ui-processing-steps.png)

After processing completes:
- See all tool executions (OCR, RAG retrieval)
- View agent reasoning and confidence
- Check similar claims found
- Review policy matches

#### 4. PII Detection

![PII Detection](assets/ui-pii-detection.png)

- PII detections shown as warnings
- Details: what was detected, where, confidence
- Non-blocking (claim still processes)

#### 5. Human-in-the-Loop Review

![HITL Review](assets/ui-hitl-review.png)

For claims requiring manual review:
- System decision shown with reasoning
- "Ask Agent" to ask clarifying questions
- Agent responds with context-aware answers
- Reviewer approves/denies with notes

### Via API

```bash
BACKEND_URL=$(oc get route backend -n claims-demo -o jsonpath='{.spec.host}')

# List pending claims
curl "http://$BACKEND_URL/api/v1/claims?status=pending" | jq

# Process a claim
CLAIM_ID="<from-list>"
curl -X POST "http://$BACKEND_URL/api/v1/claims/${CLAIM_ID}/process" \
  -H "Content-Type: application/json" \
  -d '{"skip_ocr": false, "enable_rag": true}'

# Check status
curl "http://$BACKEND_URL/api/v1/claims/${CLAIM_ID}/status" | jq

# Get decision
curl "http://$BACKEND_URL/api/v1/claims/${CLAIM_ID}/decision" | jq
```

---

## Configuration Management

### Helm Values

For detailed configuration options, see [Helm Values Reference](docs/HELM_VALUES.md).

**Quick reference**:

```yaml
global:
  namespace: claims-demo
  clusterDomain: apps.cluster.com

backend:
  image:
    repository: quay.io/mouachan/agentic-claims-demo/backend
    tag: v1.7.5
  replicas: 1

postgresql:
  image:
    repository: pgvector/pgvector
    tag: pg15
  persistence:
    size: 10Gi
    storageClass: ""  # Use cluster default

inference:
  endpoint: "https://llama-3-3-70b-llama-3-3-70b.apps.CLUSTER/v1"
  resources:
    requests:
      nvidia.com/gpu: 4

dataSciencePipelines:
  enabled: true
  objectStorage:
    scheme: http  # CRITICAL for internal MinIO

guardrails:
  enabled: true
```

### Agent Prompts

Agent prompts are stored in `app/llamastack/prompts/` and mounted via ConfigMap.

**Location**: `backend/app/llamastack/prompts/`
- `agent_prompt.txt` - Main ReAct agent instructions
- `claim_processor_prompt.txt` - Claim processing workflow

**Modifying Prompts**:

1. **Development** - Edit files directly in `backend/app/llamastack/prompts/`
2. **Production** - Update ConfigMap:
   ```bash
   oc edit configmap claims-prompts -n claims-demo
   ```
3. **Restart backend** to load changes:
   ```bash
   oc rollout restart deployment/backend -n claims-demo
   ```

**Environment Variable**: `PROMPTS_DIR=/app/prompts`

### Backend Environment Variables

Backend configuration via ConfigMap (`backend-config`) and Secrets.

**Key Variables**:

```yaml
# LlamaStack
LLAMASTACK_ENDPOINT: http://llamastack-rhoai-service.claims-demo.svc.cluster.local:8321
LLAMASTACK_DEFAULT_MODEL: vllm-inference/llama-3-3-70b-instruct-quantized-w8a8
LLAMASTACK_EMBEDDING_MODEL: vllm-embedding/embeddinggemma-300m
LLAMASTACK_MAX_TOKENS: 4096

# MCP Servers
OCR_SERVER_URL: http://ocr-server.claims-demo.svc.cluster.local:8080
RAG_SERVER_URL: http://rag-server.claims-demo.svc.cluster.local:8080

# Guardrails
GUARDRAILS_SERVER_URL: https://guardrails-orchestrator-service.claims-demo.svc.cluster.local:8032
ENABLE_PII_DETECTION: true

# Database
DATABASE_URL: postgresql+asyncpg://claims_user:***@postgresql.claims-demo.svc.cluster.local:5432/claims_db
```

**Modify**:
```bash
oc edit configmap backend-config -n claims-demo
oc rollout restart deployment/backend -n claims-demo
```

### Frontend Environment Variables

Frontend configuration built into image at build time.

**Key Variables** (during build):

```bash
REACT_APP_BACKEND_URL=http://backend.claims-demo.svc.cluster.local:8000
REACT_APP_ENV=production
```

**Note**: Frontend env vars are baked into the build. To change, rebuild the image.

---

## Troubleshooting

### DSPA Not Ready

**Problem**: DataSciencePipelinesApplication stuck

**Check**:
```bash
oc get dspa -n claims-demo -o yaml
oc logs -l app=ds-pipeline-dspa -n claims-demo
```

**Common fixes**:
- Verify `scheme: http` (not https) in values.yaml
- Wait for MariaDB pod to be Running
- Use short DSPA name (< 10 chars)

### LlamaStack Cannot Connect

**Problem**: LlamaStack fails to query models

**Check**:
```bash
oc get inferenceservice -A
oc logs deployment/llamastack-rhoai -n claims-demo
```

**Solution**: Update model endpoints with correct cluster domain in values.yaml

### Embeddings Zero

**Problem**: RAG tools return no results

**Solution**: Run embedding generation pipeline (see step 5 above)

### More Issues

See full troubleshooting guide in main documentation.

---

## Development

For local development, testing, and contributing:

**[→ Development Guide](docs/DEVELOPMENT.md)**

Includes:
- Local setup (backend, frontend, database)
- Running tests
- Building images
- Database migrations
- Debugging tips

---

## Known Issues

### ReAct Streaming Not Captured

- **Status**: Intermediate reasoning steps (thoughts between tool calls) not stored
- **Cause**: LlamaStack 0.3.5 bug - requires 0.5.0+ for streaming persistence
- **Issue**: https://github.com/llamastack/llama-stack/pull/4738
- **Workaround**: Check LlamaStack pod logs for full trace

### Embeddings

- **Knowledge Base**: Run pipeline to generate 15/15 embeddings
- **Similar Claims**: May return zero results if embeddings missing

### Current Version: v1.7.5

**Working**:
- ✅ End-to-end claim processing
- ✅ PII detection & audit trail
- ✅ HITL review workflow
- ✅ Ask Agent feature

