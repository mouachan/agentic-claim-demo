# LlamaStack Configuration

This directory contains the reference LlamaStack configuration file used in production deployment.

## Configuration File

### `working-run.yaml`
**Status**: ✅ Production configuration (actively used)

Complete LlamaStack configuration with:
- **MCP Tool Groups**: OCR server + RAG server via Model Context Protocol
- **PostgreSQL + pgvector**: Vector database for RAG
- **vLLM Inference**: Llama 3.2 3B + Mistral 3 14B
- **ReActAgent Runtime**: Agent orchestration with tool calling
- **Eval Provider**: Added for agent evaluation

This configuration is the **source of truth** for `openshift/configmaps/llamastack-config.yaml`.

**Key features**:
```yaml
tool_groups:
  - toolgroup_id: builtin::rag
    provider_id: rag-runtime
  - toolgroup_id: mcp::ocr-server
    provider_id: model-context-protocol
    mcp_endpoint:
      uri: http://ocr-server.claims-demo.svc.cluster.local:8080/sse
  - toolgroup_id: mcp::rag-server
    provider_id: model-context-protocol
    mcp_endpoint:
      uri: http://rag-server.claims-demo.svc.cluster.local:8080/sse
```

## How This Configuration Is Used

### In Production Deployment

The `working-run.yaml` configuration is embedded in a Kubernetes ConfigMap:

```bash
# The ConfigMap is created from working-run.yaml
oc apply -f openshift/configmaps/llamastack-config.yaml
```

The ConfigMap is then **mounted** into the LlamaStack pod by the OpenShift AI operator:

```yaml
# Inside claims-llamastack deployment (managed by operator)
volumeMounts:
  - mountPath: /etc/llama-stack/
    name: user-config
    readOnly: true
volumes:
  - configMap:
      name: llama-stack-config
    name: user-config
```

LlamaStack reads the configuration from `/etc/llama-stack/run.yaml` at startup.

### Updating Configuration

To update the LlamaStack configuration:

1. **Edit the ConfigMap**:
   ```bash
   # Option A: Edit directly
   oc edit configmap llama-stack-config

   # Option B: Update file and re-apply
   vi openshift/configmaps/llamastack-config.yaml
   oc apply -f openshift/configmaps/llamastack-config.yaml
   ```

2. **Restart LlamaStack** to load new configuration:
   ```bash
   oc delete pod -l app=llama-stack
   oc wait --for=condition=ready pod -l app=llama-stack --timeout=300s
   ```

3. **Verify MCP tools are registered**:
   ```bash
   oc logs -l app=llama-stack --tail=50 | grep -i mcp

   # Check toolgroups via API
   oc exec -it $(oc get pod -l app=llama-stack -o name | head -1) -- \
     curl -s http://localhost:8321/v1/tool_groups
   ```

## MCP Integration Architecture

```
┌──────────────────────────────────────┐
│  LlamaStack Pod                      │
│                                      │
│  ┌────────────────────────────────┐ │
│  │ /etc/llama-stack/run.yaml      │ │ ← Mounted from ConfigMap
│  │ (contains MCP endpoints)       │ │
│  └────────────────────────────────┘ │
│                                      │
│  ┌────────────────────────────────┐ │
│  │ LlamaStack Server :8321        │ │
│  │ - ReActAgent runtime           │ │
│  │ - MCP client connections       │ │
│  └──────┬──────────────────┬──────┘ │
│         │                  │         │
└─────────┼──────────────────┼─────────┘
          │                  │
          ↓ SSE              ↓ SSE
   ┌─────────────┐    ┌─────────────┐
   │ OCR Server  │    │ RAG Server  │
   │   :8080/sse │    │   :8080/sse │
   └─────────────┘    └─────────────┘
```

## Troubleshooting

### MCP tools not available

**Symptom**: ReActAgent cannot call OCR or RAG tools

**Check**:
```bash
# 1. Verify ConfigMap contains MCP endpoints
oc get configmap llama-stack-config -o yaml | grep mcp -A 3

# 2. Check if LlamaStack loaded the config
oc logs -l app=llama-stack | grep "tool_groups"

# 3. Test MCP server connectivity from LlamaStack pod
oc exec -it $(oc get pod -l app=llama-stack -o name | head -1) -- \
  curl -v http://ocr-server.claims-demo.svc.cluster.local:8080/sse
```

**Solution**: If ConfigMap is missing MCP endpoints, update it from `working-run.yaml` and restart LlamaStack.

### PostgreSQL connection failed

**Symptom**: `vector_io` provider fails to connect

**Check**:
```bash
# Verify PostgreSQL is running
oc get pods -l app=postgresql

# Check credentials in secret
oc get secret postgresql-secret -o yaml

# Test connection from LlamaStack pod
oc exec -it $(oc get pod -l app=llama-stack -o name | head -1) -- \
  env | grep POSTGRES
```

### vLLM inference not working

**Symptom**: LlamaStack cannot call LLM for inference

**Check**:
```bash
# Verify vLLM pod is ready
oc get pods -l serving.kserve.io/inferenceservice=llama-instruct-32-3b

# Test vLLM endpoint
curl -X POST "http://llama-instruct-32-3b-predictor.llama-instruct-32-3b-demo.svc.cluster.local:8080/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model": "llama-instruct-32-3b", "messages": [{"role": "user", "content": "Hello"}]}'
```

## References

- **LlamaStack Documentation**: https://github.com/meta-llama/llama-stack
- **MCP Protocol**: https://modelcontextprotocol.io/
- **OpenShift AI LlamaStack Operator**: https://docs.redhat.com/en/documentation/red_hat_openshift_ai/
