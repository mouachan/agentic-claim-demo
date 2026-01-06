# LlamaStack v0.3.5+rhai0 Deployment

⚠️ **REQUIRED**: This demo requires LlamaStack v0.3.5+rhai0 for working MCP tool execution.

## Why v0.3.5+rhai0?

**Previous versions (v0.3.0-v0.3.4) have critical bugs:**
- ❌ MCP tool calls fail or timeout
- ❌ No proper streaming support
- ❌ Incorrect `toolgroups` API format
- ❌ Session persistence issues

**v0.3.5+rhai0 fixes all these:**
- ✅ Reliable MCP tool execution
- ✅ Streaming API support
- ✅ Correct `toolgroups` API
- ✅ PostgreSQL persistence

## Deployment Steps

### 1. Prerequisites

Ensure you have:
- PostgreSQL deployed with the secret `postgresql-secret` containing `POSTGRES_PASSWORD`
- OCR and RAG MCP servers deployed and running
- vLLM model service running (llama-instruct-32-3b)

### 2. Deploy ConfigMap

```bash
oc apply -f llama-stack-config.yaml -n claims-demo
```

### 3. Deploy LlamaStack v0.3.5

```bash
# Deploy the pod
oc apply -f deployment.yaml -n claims-demo

# Create the service
oc apply -f service.yaml -n claims-demo

# Expose via route
oc apply -f route.yaml -n claims-demo
```

### 4. Verify Deployment

```bash
# Wait for pod to be ready
oc wait --for=condition=ready pod -l app=llamastack-v035 -n claims-demo --timeout=300s

# Check logs
oc logs -l app=llamastack-v035 -n claims-demo --tail=50

# Get the route URL
oc get route llamastack-test-v035 -n claims-demo
```

### 5. Test MCP Tools Registration

```bash
# Get the route
LLAMASTACK_URL=$(oc get route llamastack-test-v035 -n claims-demo -o jsonpath='{.spec.host}')

# List tool groups (should show mcp::ocr-server and mcp::rag-server)
curl -s "https://${LLAMASTACK_URL}/v1/toolgroups" | jq .
```

Expected output:
```json
{
  "toolgroups": [
    {
      "identifier": "mcp::ocr-server",
      "provider_resource_id": "model-context-protocol",
      "type": "mcp"
    },
    {
      "identifier": "mcp::rag-server",
      "provider_resource_id": "model-context-protocol",
      "type": "mcp"
    }
  ]
}
```

### 6. Create Test Agent

```bash
curl -X POST "https://${LLAMASTACK_URL}/v1/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test-agent",
    "model": "vllm-inference-1/llama-instruct-32-3b",
    "instructions": "You are a helpful assistant.",
    "toolgroups": ["mcp::ocr-server", "mcp::rag-server"]
  }'
```

## Configuration

### MCP Tool Endpoints

The ConfigMap defines MCP server endpoints:

- **OCR Server**: `http://ocr-server.claims-demo.svc.cluster.local:8080/sse`
- **RAG Server**: `http://rag-server.claims-demo.svc.cluster.local:8080/sse`

### Model Configuration

The default model provider points to:
- **vLLM Service**: `http://llama-instruct-32-3b-predictor.edg-demo.svc.cluster.local:8000/v1`

Update `llama-stack-config.yaml` if your service names differ.

### Vector Database (Optional)

If using LlamaStack's builtin RAG runtime:
- **PostgreSQL**: `postgresql.claims-demo.svc.cluster.local:5432`
- **Database**: `claims_db`
- **User**: `claims_user`
- **Password**: From secret `postgresql-secret`

## Updating Configuration

To update the LlamaStack configuration:

```bash
# 1. Edit the ConfigMap
oc edit configmap llama-stack-config-v035 -n claims-demo

# 2. Restart the pod to reload
oc delete pod -l app=llamastack-v035 -n claims-demo

# 3. Wait for new pod
oc wait --for=condition=ready pod -l app=llamastack-v035 -n claims-demo --timeout=300s
```

## Troubleshooting

### MCP Tools Not Registered

Check the logs for MCP connection errors:

```bash
oc logs -l app=llamastack-v035 -n claims-demo | grep -i mcp
```

Ensure OCR and RAG servers are running:

```bash
oc get pods -l component=mcp-server -n claims-demo
```

### Tool Calls Failing

Check LlamaStack logs for tool execution errors:

```bash
oc logs -l app=llamastack-v035 -n claims-demo --tail=100 | grep -i "tool"
```

Verify MCP server health:

```bash
curl http://ocr-server.claims-demo.svc.cluster.local:8080/health/ready
curl http://rag-server.claims-demo.svc.cluster.local:8080/health/ready
```

### Pod Not Starting

Check pod events:

```bash
oc describe pod -l app=llamastack-v035 -n claims-demo
```

Common issues:
- ConfigMap not found → Apply `llama-stack-config.yaml`
- Secret not found → Create `postgresql-secret`
- Image pull error → Check image availability

## Version Notes

- **Image**: `docker.io/llamastack/distribution-rh-dev:0.3.5+rhai0`
- **Port**: 8321
- **Health Endpoint**: `/health`
- **API Version**: v1

## Migration from OpenShift AI Native LlamaStack

When OpenShift AI is updated to include v0.3.5+:

1. Create a `LlamaStackDistribution` CRD
2. Reference this ConfigMap
3. Remove this manual deployment

Until then, this manual deployment is REQUIRED for working MCP tools.

## Documentation

- [LlamaStack v0.3.5 Release Notes](https://github.com/meta-llama/llama-stack/releases/tag/v0.3.5)
- [LlamaStack MCP Provider](https://github.com/meta-llama/llama-stack/blob/main/docs/source/distributions/remote_mcp.md)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
