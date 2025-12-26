# Agentic Insurance Claims Processing Demo

An intelligent insurance claims processing system powered by AI agents, demonstrating advanced document processing, policy retrieval, and automated decision-making capabilities using Model Context Protocol (MCP) and LlamaStack.

## Architecture Overview

This demo showcases an end-to-end agentic workflow for insurance claims processing using OpenShift AI and LlamaStack.

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React)                      │
│              Claims Submission Interface                 │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ↓ HTTP/REST API
┌─────────────────────────────────────────────────────────┐
│              Backend API (FastAPI)                       │
│           LlamaStack ReActAgent Integration              │
└──────────────────┬──────────────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        ↓          ↓          ↓
    ┌───────┐  ┌──────┐  ┌──────────┐
    │  OCR  │  │Guard │  │   RAG    │
    │  MCP  │  │rails │  │Retrieval │
    │Server │  │ MCP  │  │   MCP    │
    └───┬───┘  └──┬───┘  └────┬─────┘
        │         │            │
        └─────────┼────────────┘
                  ↓
        ┌──────────────────┐
        │  PostgreSQL +    │
        │    pgvector      │
        │  (Claims + RAG)  │
        └──────────────────┘
```

### Key Technologies

- **Frontend**: React with TypeScript
- **Backend**: Python FastAPI
- **AI Orchestration**: LlamaStack with ReActAgent (Reasoning + Acting)
- **LLM**: Llama 3.2 3B (vLLM inference, 2 GPUs, 32K context)
- **MCP Protocol**: Model Context Protocol for tool integration
- **Database**: PostgreSQL with pgvector extension
- **Platform**: Red Hat OpenShift AI 3.0

## Features

### 1. Document Processing (OCR MCP Server)
- Automated text extraction from claim documents (PDF, images)
- Multi-format support: PDF, JPG, PNG, TIFF
- Structured data extraction with confidence scores
- LLM-based validation and cleanup

### 2. Policy Retrieval (RAG MCP Server)
- Vector similarity search for user contracts
- PostgreSQL + pgvector for efficient retrieval
- Contextual policy information extraction
- Historical claims precedent analysis

### 3. Intelligent Decision Making
- ReActAgent orchestration with thought-action-observation loops
- Multi-step reasoning with tool usage
- Automated claim approval/denial recommendations
- Detailed reasoning with policy citations

### 4. Guardrails & Safety
- PII detection and data protection
- LLM-based content validation
- Configurable safety rules

## Agent Workflow

The system uses a **ReActAgent** (Reasoning and Acting) pattern:

```
1. User submits insurance claim with document
   ↓
2. Agent analyzes the task
   → THOUGHT: "I need to extract information from the document"
   → ACTION: Call OCR MCP tool
   → OBSERVATION: Structured claim data extracted
   ↓
3. Agent continues reasoning
   → THOUGHT: "I need to check user's insurance coverage"
   → ACTION: Call RAG MCP tool to retrieve contracts
   → OBSERVATION: User's active policies and coverage details
   ↓
4. Agent makes final decision
   → THOUGHT: "Based on policy X, section Y, this claim is covered"
   → FINAL ANSWER: Approve with reasoning and estimated coverage
```

## MCP Servers

### OCR Server
**Endpoint**: `http://ocr-server.claims-demo.svc.cluster.local:8080/sse`

**Tools**:
- `ocr_document`: Extract text and structured data from claim documents
  - Supports multiple document types (claim forms, invoices, medical records, ID cards)
  - Multi-language OCR support
  - LLM validation for accuracy

### RAG Server
**Endpoint**: `http://rag-server.claims-demo.svc.cluster.local:8080/sse`

**Tools**:
- `retrieve_user_info`: Get user profile and insurance contracts
- `retrieve_similar_claims`: Find historical claims for precedent
- `search_knowledge_base`: Query policy information and guidelines

**Vector Database**: PostgreSQL with pgvector extension for semantic search

### Guardrails Server
**Endpoint**: `http://claims-guardrails.claims-demo.svc.cluster.local:8080`

**Features**:
- PII detection (SSN, credit cards, emails, phone numbers)
- Sensitive data filtering
- LLM-based validation for context-aware protection

## Deployment

### Prerequisites
- Red Hat OpenShift AI 3.0
- OpenShift cluster with GPU nodes (for vLLM)
- PostgreSQL with pgvector extension

### OpenShift Resources

The deployment uses OpenShift AI Custom Resource Definitions (CRDs):

- **LlamaStackDistribution**: Manages LlamaStack server deployment
- **MCPServer**: Deploys custom MCP servers (OCR, RAG)
- **Guardrails**: Configures safety and validation rules
- **InferenceService**: Manages vLLM model serving

### Quick Start

1. **Deploy Database**:
```bash
oc apply -f backend/openshift/deployments/postgresql-statefulset.yaml
oc apply -f backend/openshift/services/postgresql-service.yaml
```

2. **Deploy MCP Servers**:
```bash
oc apply -f backend/openshift/deployments/ocr-server-deployment.yaml
oc apply -f backend/openshift/deployments/rag-server-deployment.yaml
oc apply -f backend/openshift/services/
```

3. **Deploy LlamaStack**:
```bash
oc apply -f backend/openshift/configmaps/llama-stack-config.yaml
oc apply -f backend/openshift/deployments/llamastack-deployment.yaml
```

4. **Deploy vLLM Model**:
```bash
oc apply -f backend/openshift/vllm/llama-3.2-3b-inferenceservice.yaml
```

5. **Deploy Backend**:
```bash
oc apply -f backend/openshift/configmaps/backend-config.yaml
oc apply -f backend/openshift/deployments/backend-deployment.yaml
oc apply -f backend/openshift/routes/backend-route.yaml
```

6. **Deploy Frontend**:
```bash
oc apply -f frontend/openshift/deployments/frontend-deployment.yaml
oc apply -f frontend/openshift/routes/frontend-route.yaml
```

### Configuration

Key configuration is externalized via ConfigMaps:

- **Backend Config**: `backend/openshift/configmaps/backend-config.yaml`
  - API settings, database connections, LlamaStack endpoints

- **LlamaStack Config**: `backend/openshift/configmaps/llama-stack-config.yaml`
  - Model configurations, tool groups, MCP server endpoints

- **Prompts**: `backend/openshift/configmaps/backend-prompts.yaml`
  - Agent instructions and system prompts

## API Endpoints

### Backend REST API

**Base URL**: `http://backend-service.claims-demo.svc.cluster.local:8000/api/v1`

**Main Endpoints**:
- `GET /claims` - List all claims
- `POST /claims` - Create new claim
- `GET /claims/{id}` - Get claim details
- `POST /claims/{id}/process` - Process claim with AI agent
- `GET /claims/{id}/status` - Get processing status
- `GET /claims/{id}/decision` - Get AI decision and reasoning

## Development

### Local Setup

1. **Backend**:
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

2. **Frontend**:
```bash
cd frontend
npm install
npm start
```

3. **Database** (via Docker Compose):
```bash
docker-compose up -d postgresql
```

### Environment Variables

Required environment variables for local development:

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=claims_db
POSTGRES_USER=claims_user
POSTGRES_PASSWORD=your_password

# LlamaStack
LLAMASTACK_ENDPOINT=http://localhost:8321
LLAMASTACK_DEFAULT_MODEL=vllm-inference-1/llama-instruct-32-3b

# MCP Servers
OCR_SERVER_URL=http://localhost:8080
RAG_SERVER_URL=http://localhost:8081
```

## Project Structure

```
agentic-claim-demo/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI endpoints
│   │   │   ├── claims.py     # Claims processing API
│   │   │   └── schemas.py    # Pydantic models
│   │   ├── core/             # Core configuration
│   │   │   ├── config.py     # Settings management
│   │   │   └── database.py   # Database connections
│   │   ├── models/           # SQLAlchemy models
│   │   │   └── claim.py      # Claim data models
│   │   └── llamastack/       # LlamaStack integration
│   │       ├── client.py     # LlamaStack client
│   │       └── prompts.py    # Agent prompts
│   ├── mcp_servers/          # Custom MCP servers
│   │   ├── ocr_server/
│   │   ├── rag_server/
│   │   └── orchestrator_server/
│   └── openshift/            # OpenShift manifests
│       ├── configmaps/
│       ├── deployments/
│       └── services/
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── pages/            # Page components
│   │   └── services/         # API clients
│   └── openshift/
└── database/
    ├── init.sql              # Database schema
    └── migrations/           # Database migrations
```

## Technology Stack Details

### Backend Stack
- **Python 3.12**
- **FastAPI**: Modern async web framework
- **SQLAlchemy**: ORM with async support
- **Pydantic**: Data validation
- **llama-stack-client 0.3.5**: LlamaStack SDK
- **asyncpg**: Async PostgreSQL driver

### Frontend Stack
- **React 18**
- **TypeScript**
- **Axios**: HTTP client
- **React Router**: Navigation

### AI & ML Stack
- **LlamaStack**: AI orchestration platform
- **vLLM**: High-performance LLM inference
- **Llama 3.2 3B**: Language model (32K context window)
- **pgvector**: Vector similarity search
- **MCP Protocol**: Standardized tool integration

## Performance Considerations

### vLLM Configuration
- **GPUs**: 2x NVIDIA L40 (48GB each)
- **Tensor Parallelism**: Enabled for model distribution
- **Context Length**: 32K tokens
- **GPU Memory Utilization**: 75% (optimized for stability)

### Database Optimization
- **pgvector HNSW Index**: Fast similarity search
- **Connection Pooling**: 10 connections, 20 max overflow
- **Async Operations**: Non-blocking database queries

## Security

- **Input Validation**: All inputs validated via Pydantic schemas
- **PII Protection**: Guardrails for sensitive data detection
- **CORS**: Configurable allowed origins
- **Secret Management**: OpenShift Secrets for credentials
- **Network Isolation**: Internal service communication
