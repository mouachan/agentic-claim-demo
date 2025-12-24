```markdown
# MCP RAG Server

Model Context Protocol (MCP) server for RAG (Retrieval-Augmented Generation) operations using Server-Sent Events (SSE).

## Overview

This server exposes RAG functionality via the **MCP (Model Context Protocol)** using **Server-Sent Events (SSE)**. LlamaStack connects to discover 3 tools for vector search and retrieval operations.

## Architecture

```
LlamaStack                    MCP RAG Server
    |                               |
    |--- GET /mcp/sse ------------->|  (1) Discover 3 tools via SSE
    |<-- event: tools --------------|      - retrieve_user_info
    |                                |      - retrieve_similar_claims
    |                                |      - search_knowledge_base
    |<-- event: ping ----------------|  (2) Keep-alive every 30s
    |                                |
    |--- POST /mcp/tools/retrieve_user_info ->| (3) Execute tool
    |<-- user data + contracts ------|
```

## Files

- **`mcp_server.py`** - MCP server with SSE protocol
  - `/mcp/sse` - Server-Sent Events endpoint for tool discovery
  - `/mcp/tools/retrieve_user_info` - Retrieve user info and contracts
  - `/mcp/tools/retrieve_similar_claims` - Find similar historical claims
  - `/mcp/tools/search_knowledge_base` - Search policy information
  - `/health/live`, `/health/ready` - Health checks

- **`rag_logic.py`** - RAG processing logic
  - `retrieve_user_info_logic()` - User data + vector search on contracts
  - `retrieve_similar_claims_logic()` - Vector similarity search on claims
  - `search_knowledge_base_logic()` - KB search + LLM synthesis
  - `create_embedding()` - Generate embeddings via LlamaStack
  - `synthesize_with_llm()` - LLM answer synthesis

- **`prompts.py`** - LLM prompts for synthesis

- **`server.py`** - Legacy HTTP server (backward compatibility)

## MCP Tools Exposed

### 1. retrieve_user_info

Retrieve user profile and insurance contracts using vector search.

**Parameters:**
```json
{
  "user_id": "string (required)",
  "query": "string (required) - e.g., 'medical coverage', 'emergency services'",
  "top_k": "integer (default: 5) - number of contracts to retrieve",
  "include_contracts": "boolean (default: true)"
}
```

**Returns:**
```json
{
  "user_info": {
    "id": "...",
    "user_id": "...",
    "email": "...",
    "full_name": "...",
    "date_of_birth": "...",
    "phone_number": "...",
    "address": "..."
  },
  "contracts": [
    {
      "id": "...",
      "contract_number": "...",
      "contract_type": "medical|auto|property",
      "coverage_amount": 100000.00,
      "full_text": "...",
      "key_terms": "..."
    }
  ],
  "similarity_scores": [0.92, 0.85, 0.78],
  "source_documents": ["CONTRACT-001", "CONTRACT-002"]
}
```

### 2. retrieve_similar_claims

Find similar historical claims using vector similarity.

**Parameters:**
```json
{
  "claim_text": "string (required) - text of current claim",
  "claim_type": "string (optional) - medical|auto|property",
  "top_k": "integer (default: 10) - number of similar claims",
  "min_similarity": "number (default: 0.7) - minimum similarity score 0.0-1.0"
}
```

**Returns:**
```json
{
  "similar_claims": [
    {
      "claim_id": "...",
      "claim_number": "CLAIM-123",
      "claim_text": "... (truncated to 500 chars)",
      "similarity_score": 0.89,
      "outcome": "completed|denied|manual_review",
      "processing_time": 1234
    }
  ]
}
```

### 3. search_knowledge_base

Search knowledge base for policy information with LLM synthesis.

**Parameters:**
```json
{
  "query": "string (required) - e.g., 'what is covered under emergency medical?'",
  "filters": "object (optional) - category, tags, etc.",
  "top_k": "integer (default: 5) - number of articles to retrieve"
}
```

**Returns:**
```json
{
  "results": [
    {
      "id": "...",
      "title": "Emergency Medical Coverage",
      "content": "...",
      "category": "medical",
      "similarity_score": 0.94
    }
  ],
  "synthesized_answer": "Based on the policy documents, emergency medical services are covered..."
}
```

## MCP Protocol Endpoints

### Tool Discovery (SSE)

**Endpoint:** `GET /mcp/sse`

```bash
curl -N http://rag-mcp-server:8080/mcp/sse
```

**Events received:**
```
event: tools
data: {"tools": [
  {"type": "function", "function": {"name": "retrieve_user_info", ...}},
  {"type": "function", "function": {"name": "retrieve_similar_claims", ...}},
  {"type": "function", "function": {"name": "search_knowledge_base", ...}}
]}

event: ping
data: {"status": "alive", "timestamp": 1703456789.123}
...
```

### Tool Execution Examples

#### Retrieve User Info
```bash
curl -X POST http://rag-mcp-server:8080/mcp/tools/retrieve_user_info \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "query": "medical emergency coverage",
    "top_k": 3
  }'
```

#### Find Similar Claims
```bash
curl -X POST http://rag-mcp-server:8080/mcp/tools/retrieve_similar_claims \
  -H "Content-Type: application/json" \
  -d '{
    "claim_text": "Patient visited emergency room for chest pain on 2024-01-15...",
    "top_k": 5,
    "min_similarity": 0.75
  }'
```

#### Search Knowledge Base
```bash
curl -X POST http://rag-mcp-server:8080/mcp/tools/search_knowledge_base \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is covered under emergency medical services?",
    "top_k": 5
  }'
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `POSTGRES_HOST` | `postgresql.claims-demo.svc.cluster.local` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `claims_db` | Database name |
| `POSTGRES_USER` | `claims_user` | Database user |
| `POSTGRES_PASSWORD` | `ClaimsDemo2025!` | Database password |
| `LLAMASTACK_ENDPOINT` | `http://llamastack.claims-demo.svc.cluster.local:8321` | LlamaStack API |
| `EMBEDDING_MODEL` | `granite-embedding-125m` | Embedding model |
| `VECTOR_DIMENSION` | `768` | Vector dimension |

## Dependencies

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
pgvector==0.2.4
httpx==0.26.0
pydantic==2.5.3
numpy==1.26.3
sse-starlette==1.8.2
```

## Database Schema

### Tables Used

**users**
- id, user_id, email, full_name, date_of_birth, phone_number, address

**user_contracts**
- id, user_id, contract_number, contract_type, coverage_amount, full_text, key_terms, is_active
- **embedding** (vector(768)) - pgvector for similarity search

**claims**
- id, claim_number, user_id, status, claim_type, total_processing_time_ms

**claim_documents**
- id, claim_id, raw_ocr_text
- **embedding** (vector(768)) - pgvector for similarity search

**knowledge_base**
- id, title, content, category, is_active
- **embedding** (vector(768)) - pgvector for similarity search

### Vector Search with pgvector

All retrieval functions use **pgvector** for cosine similarity search:

```sql
SELECT *,
  1 - (embedding <=> query_embedding) AS similarity
FROM table_name
WHERE 1 - (embedding <=> query_embedding) >= 0.7
ORDER BY embedding <=> query_embedding
LIMIT 10
```

**Operators:**
- `<=>` - Cosine distance (0 = identical, 2 = opposite)
- `1 - distance` - Cosine similarity (0 to 1)

## Local Development

### Prerequisites

```bash
# PostgreSQL with pgvector
docker run -d \
  -e POSTGRES_USER=claims_user \
  -e POSTGRES_PASSWORD=ClaimsDemo2025! \
  -e POSTGRES_DB=claims_db \
  -p 5432:5432 \
  ankane/pgvector
```

### Run Server

```bash
cd backend/mcp_servers/rag_server

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export POSTGRES_HOST=localhost
export LLAMASTACK_ENDPOINT=http://localhost:8321

# Start server
python mcp_server.py
```

Server starts on http://localhost:8080

### Test SSE Endpoint

```bash
# Connect to SSE stream
curl -N http://localhost:8080/mcp/sse

# You should see:
# event: tools
# data: {"tools": [...3 tools...]}
#
# event: ping
# data: {"status": "alive"}
```

### Test RAG Tools

```bash
# Test user info retrieval
curl -X POST http://localhost:8080/mcp/tools/retrieve_user_info \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "query": "medical coverage"
  }'
```

## Docker Build

```bash
# Build image
docker build -t rag-mcp-server:latest .

# Run container
docker run -p 8080:8080 \
  -e POSTGRES_HOST=host.docker.internal \
  -e LLAMASTACK_ENDPOINT=http://llamastack:8321 \
  rag-mcp-server:latest
```

## OpenShift Deployment

```bash
# Build on OpenShift
oc start-build rag-mcp-server --from-dir=. --follow -n claims-demo

# Deploy
oc apply -f ../../../openshift/deployments/rag-server-deployment.yaml
oc apply -f ../../../openshift/services/rag-server-service.yaml
```

## Health Checks

### Liveness Probe
```bash
curl http://rag-mcp-server:8080/health/live
```

Response:
```json
{
  "status": "alive",
  "service": "mcp-rag-server",
  "version": "2.0.0",
  "mcp_protocol": "sse",
  "tools_count": 3,
  "database_connected": false
}
```

### Readiness Probe
```bash
curl http://rag-mcp-server:8080/health/ready
```

Response (when DB is connected):
```json
{
  "status": "ready",
  "service": "mcp-rag-server",
  "version": "2.0.0",
  "mcp_protocol": "sse",
  "tools_count": 3,
  "database_connected": true
}
```

## Integration with LlamaStack

### 1. LlamaStack Configuration

Add to `openshift/llamastack/run.yaml`:

```yaml
providers:
  tool_runtime:
    - provider_id: model-context-protocol
      provider_type: remote::model-context-protocol
      config:
        mcp_servers:
          - name: rag-server
            uri: sse://rag-mcp-server.claims-demo.svc.cluster.local:8080/mcp/sse
            tools:
              - retrieve_user_info
              - retrieve_similar_claims
              - search_knowledge_base

tool_groups:
  - toolgroup_id: claims-processing
    provider_id: model-context-protocol
    tools:
      - name: rag-server::retrieve_user_info
      - name: rag-server::retrieve_similar_claims
      - name: rag-server::search_knowledge_base
```

### 2. LlamaStack Discovery

When LlamaStack starts:
1. Connects to `sse://rag-mcp-server:8080/mcp/sse`
2. Receives `event: tools` with 3 tool definitions
3. Registers all tools automatically
4. Maintains persistent SSE connection

### 3. Agent Usage

```python
# Create agent with RAG tools
agent_config = {
    "model": "llama-instruct-32-3b",
    "tools": ["claims-processing"],  # Includes all 3 RAG tools
    "instructions": """
        You are a claims processing assistant.
        Use retrieve_user_info to get user contracts.
        Use retrieve_similar_claims to find precedents.
        Use search_knowledge_base for policy questions.
    """
}

# Run agent turn
result = await llamastack.run_agent_turn(
    session_id=session_id,
    messages=[{
        "role": "user",
        "content": "Process claim for user user-123 about emergency room visit"
    }]
)

# Agent automatically:
# 1. Calls retrieve_user_info(user_id="user-123", query="emergency coverage")
# 2. Calls retrieve_similar_claims(claim_text="emergency room visit...")
# 3. Calls search_knowledge_base(query="emergency room coverage policy")
# 4. Synthesizes final answer using all retrieved information
```

## Monitoring

### Logs

```bash
# View logs
oc logs -n claims-demo deployment/rag-mcp-server --tail=100 -f

# Filter for SSE connections
oc logs -n claims-demo deployment/rag-mcp-server | grep "SSE"

# Filter for tool executions
oc logs -n claims-demo deployment/rag-mcp-server | grep "Executing"
```

### Metrics

Key metrics to monitor:
- SSE connections (should be persistent)
- Tool execution counts (per tool)
- Vector search performance
- Embedding generation time
- LLM synthesis latency
- Database query performance

## Troubleshooting

### SSE Connection Drops

**Symptom:** LlamaStack can't discover tools

**Solution:**
```bash
# Check server is running
oc get pods -n claims-demo -l app=rag-mcp-server

# Test SSE endpoint
curl -N http://rag-mcp-server.claims-demo.svc.cluster.local:8080/mcp/sse

# Check logs
oc logs -n claims-demo deployment/rag-mcp-server
```

### Database Connection Failed

**Symptom:** Readiness probe fails

**Solution:**
```bash
# Verify PostgreSQL is running
oc get pods -n claims-demo -l app=postgresql

# Test connection
oc exec -it deployment/rag-mcp-server -- \
  psql -h postgresql.claims-demo.svc.cluster.local -U claims_user -d claims_db

# Check credentials
oc get secret postgresql-secret -n claims-demo -o yaml
```

### Empty Vector Search Results

**Symptom:** Tools return no results even with data in DB

**Solutions:**
1. **Check embeddings exist:**
   ```sql
   SELECT COUNT(*) FROM user_contracts WHERE embedding IS NOT NULL;
   SELECT COUNT(*) FROM claim_documents WHERE embedding IS NOT NULL;
   ```

2. **Lower similarity threshold:**
   ```json
   {"min_similarity": 0.5}  // Instead of 0.7
   ```

3. **Verify embedding dimension:**
   ```sql
   SELECT pg_typeof(embedding) FROM user_contracts LIMIT 1;
   // Should show: vector(768)
   ```

### LlamaStack Embedding Fails

**Symptom:** Error creating embeddings

**Solution:**
```bash
# Test LlamaStack embeddings API directly
curl -X POST http://llamastack:8321/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "granite-embedding-125m", "input": "test"}'

# Check LlamaStack is running
oc get pods -n claims-demo -l app.kubernetes.io/name=llamastack
```

## Migration from Legacy Server

Old HTTP endpoints (deprecated):
```
POST /retrieve_user_info
POST /retrieve_similar_claims
POST /search_knowledge_base
```

New MCP endpoints:
```
GET  /mcp/sse                              # Tool discovery
POST /mcp/tools/retrieve_user_info         # Tool execution
POST /mcp/tools/retrieve_similar_claims    # Tool execution
POST /mcp/tools/search_knowledge_base      # Tool execution
```

**Clients should migrate to use LlamaStack Agents API** instead of calling RAG server directly.

## References

- [Model Context Protocol Specification](https://spec.modelcontextprotocol.io/)
- [Server-Sent Events (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [LlamaStack Documentation](https://llamastack.github.io/)

## Version History

- **2.0.0** - MCP protocol with SSE, 3 tools, LlamaStack integration
- **1.0.0** - Legacy HTTP server (backward compatibility)
```
