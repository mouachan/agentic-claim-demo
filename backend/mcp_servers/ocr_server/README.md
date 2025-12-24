# MCP OCR Server

Model Context Protocol (MCP) server for OCR processing using Server-Sent Events (SSE).

## Overview

This server exposes OCR functionality via the **MCP (Model Context Protocol)** using **Server-Sent Events (SSE)**. LlamaStack connects to discover available tools and execute OCR operations on documents.

## Architecture

```
LlamaStack                    MCP OCR Server
    |                               |
    |--- GET /mcp/sse ------------->|  (1) Discover tools via SSE
    |<-- event: tools --------------|
    |    data: [ocr_document]        |
    |                                |
    |<-- event: ping ----------------|  (2) Keep-alive every 30s
    |                                |
    |                                |
    |--- POST /mcp/tools/ocr_document->| (3) Execute tool
    |<-- result ---------------------|
```

## Files

- **`mcp_server.py`** - MCP server with SSE protocol
  - `/mcp/sse` - Server-Sent Events endpoint for tool discovery
  - `/mcp/tools/ocr_document` - Tool execution endpoint
  - `/health/live`, `/health/ready` - Health checks

- **`ocr_logic.py`** - OCR processing logic
  - `process_ocr_document()` - Main OCR function
  - `extract_text_from_image()` - Tesseract OCR for images
  - `extract_text_from_pdf()` - PDF to images + OCR
  - `validate_with_llm()` - LLM validation of OCR text

- **`prompts.py`** - LLM prompts for OCR validation

- **`server.py`** - Legacy HTTP server (backward compatibility)

## MCP Protocol Endpoints

### 1. Tool Discovery (SSE)

**Endpoint:** `GET /mcp/sse`

Connect to this endpoint to receive a stream of Server-Sent Events:

```bash
curl -N http://ocr-mcp-server:8080/mcp/sse
```

**Events received:**

```
event: tools
data: {"tools": [{"type": "function", "function": {"name": "ocr_document", ...}}]}

event: ping
data: {"status": "alive", "timestamp": 1703456789.123}

event: ping
data: {"status": "alive", "timestamp": 1703456819.123}
...
```

### 2. Tool Execution

**Endpoint:** `POST /mcp/tools/ocr_document`

Execute the OCR tool:

```bash
curl -X POST http://ocr-mcp-server:8080/mcp/tools/ocr_document \
  -H "Content-Type: application/json" \
  -d '{
    "document_path": "/mnt/documents/claim_123.pdf",
    "document_type": "claim_form",
    "language": "eng"
  }'
```

**Response:**

```json
{
  "success": true,
  "raw_text": "Claim Number: 12345...",
  "structured_data": {
    "fields": {
      "claim_number": {"value": "12345", "confidence": 0.95},
      "claimant_name": {"value": "John Doe", "confidence": 0.92}
    },
    "overall_confidence": 0.93
  },
  "confidence": 0.89,
  "errors": []
}
```

## Tool Definition

```json
{
  "type": "function",
  "function": {
    "name": "ocr_document",
    "description": "Extract text from document images or PDFs using OCR and validate with LLM",
    "parameters": {
      "type": "object",
      "properties": {
        "document_path": {
          "type": "string",
          "description": "Absolute path to the document file"
        },
        "document_type": {
          "type": "string",
          "enum": ["claim_form", "invoice", "medical_record", "id_card", "other"],
          "default": "claim_form"
        },
        "language": {
          "type": "string",
          "default": "eng",
          "description": "OCR language code (eng, fra, spa, etc.)"
        }
      },
      "required": ["document_path"]
    }
  }
}
```

## Supported Formats

- **PDF** (`.pdf`)
- **Images** (`.jpg`, `.jpeg`, `.png`, `.tiff`, `.bmp`)

## Supported Languages

Tesseract OCR supports 100+ languages:
- `eng` - English
- `fra` - French
- `spa` - Spanish
- `deu` - German
- `ita` - Italian
- `por` - Portuguese
- `chi_sim` - Chinese Simplified
- `jpn` - Japanese
- `ara` - Arabic

Full list: https://github.com/tesseract-ocr/tessdata

## Document Types

The `document_type` parameter optimizes field extraction:

| Type | Expected Fields |
|------|----------------|
| `claim_form` | claim_number, claimant_name, date_of_service, provider_name, diagnosis, amount |
| `invoice` | invoice_number, date, vendor_name, total_amount, line_items |
| `medical_record` | patient_name, date_of_birth, diagnosis, treatment, provider |
| `id_card` | name, id_number, date_of_birth, address |
| `other` | key_information (generic extraction) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LLAMASTACK_ENDPOINT` | `http://llamastack.claims-demo.svc.cluster.local:8321` | LlamaStack API endpoint |
| `LLM_MODEL` | `llama-instruct-32-3b` | LLM model for validation |

## Dependencies

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
pytesseract==0.3.10
Pillow==10.2.0
pdf2image==1.17.0
httpx==0.26.0
pydantic==2.5.3
sse-starlette==1.8.2
```

## Local Development

### Prerequisites

```bash
# Install Tesseract OCR
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# RHEL/CentOS
sudo dnf install tesseract
```

### Run Server

```bash
cd backend/mcp_servers/ocr_server

# Install dependencies
pip install -r requirements.txt

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
# data: {"tools": [...]}
#
# event: ping
# data: {"status": "alive", ...}
```

### Test OCR Tool

```bash
# Prepare a test document
echo "Test Document" > /tmp/test.txt
# Or use a real PDF/image

# Execute OCR
curl -X POST http://localhost:8080/mcp/tools/ocr_document \
  -H "Content-Type: application/json" \
  -d '{
    "document_path": "/tmp/test.pdf",
    "document_type": "claim_form"
  }'
```

## Docker Build

```bash
# Build image
docker build -t ocr-mcp-server:latest .

# Run container
docker run -p 8080:8080 \
  -e LLAMASTACK_ENDPOINT=http://llamastack:8321 \
  -v /path/to/documents:/mnt/documents:ro \
  ocr-mcp-server:latest
```

## OpenShift Deployment

```bash
# Build on OpenShift
oc start-build ocr-mcp-server --from-dir=. --follow -n claims-demo

# Deploy
oc apply -f ../../../openshift/deployments/ocr-server-deployment.yaml
oc apply -f ../../../openshift/services/ocr-server-service.yaml
```

## Health Checks

### Liveness Probe

```bash
curl http://ocr-mcp-server:8080/health/live
```

Response:
```json
{
  "status": "alive",
  "service": "mcp-ocr-server",
  "version": "2.0.0",
  "mcp_protocol": "sse",
  "tools_count": 1
}
```

### Readiness Probe

```bash
curl http://ocr-mcp-server:8080/health/ready
```

Response (when Tesseract is available):
```json
{
  "status": "ready",
  "service": "mcp-ocr-server",
  "version": "2.0.0",
  "mcp_protocol": "sse",
  "tools_count": 1
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
          - name: ocr-server
            uri: sse://ocr-mcp-server.claims-demo.svc.cluster.local:8080/mcp/sse
            tools:
              - ocr_document

tool_groups:
  - toolgroup_id: claims-processing
    provider_id: model-context-protocol
    tools:
      - name: ocr-server::ocr_document
```

### 2. LlamaStack Discovery

When LlamaStack starts, it:
1. Connects to `sse://ocr-mcp-server:8080/mcp/sse`
2. Receives `event: tools` with `ocr_document` definition
3. Registers the tool automatically
4. Maintains persistent SSE connection (keep-alive)

### 3. Agent Usage

```python
# Create agent with OCR tool
agent_config = {
    "model": "llama-instruct-32-3b",
    "tools": ["claims-processing"],  # Includes ocr_document
    "instructions": "Extract text from the claim document and process it."
}

# Run agent turn
result = await llamastack.run_agent_turn(
    session_id=session_id,
    messages=[{
        "role": "user",
        "content": "Process document at /mnt/documents/claim_123.pdf"
    }]
)

# Agent automatically calls ocr_document tool
# LlamaStack routes to: POST /mcp/tools/ocr_document
# Returns OCR result to agent
```

## Monitoring

### Logs

```bash
# View logs
oc logs -n claims-demo deployment/ocr-mcp-server --tail=100 -f

# Filter for SSE connections
oc logs -n claims-demo deployment/ocr-mcp-server | grep "SSE"

# Filter for tool executions
oc logs -n claims-demo deployment/ocr-mcp-server | grep "Executing ocr_document"
```

### Metrics

Key metrics to monitor:
- SSE connections (should be persistent)
- Tool execution count
- OCR confidence scores
- LLM validation success rate
- Processing time per document

## Troubleshooting

### SSE Connection Drops

**Symptom:** LlamaStack can't discover tools

**Solution:**
```bash
# Check if server is running
oc get pods -n claims-demo -l app=ocr-mcp-server

# Test SSE endpoint
curl -N http://ocr-mcp-server.claims-demo.svc.cluster.local:8080/mcp/sse

# Check firewall/proxy settings (SSE requires persistent HTTP connections)
```

### Tesseract Not Found

**Symptom:** Readiness probe fails with "Tesseract not ready"

**Solution:**
```bash
# Verify Tesseract is installed in container
oc exec -it deployment/ocr-mcp-server -- tesseract --version

# Rebuild image if missing
```

### Low OCR Confidence

**Symptom:** OCR confidence < 0.7

**Solutions:**
- Use higher quality images (300+ DPI)
- Ensure document is not skewed
- Try different language codes
- Pre-process images (deskew, denoise)

## Migration from Legacy Server

The old `server.py` (HTTP-only) is kept for backward compatibility:

**Old endpoint (deprecated):**
```
POST /ocr_document
```

**New MCP endpoints:**
```
GET  /mcp/sse                  # Tool discovery
POST /mcp/tools/ocr_document   # Tool execution
```

Clients should migrate to use **LlamaStack Agents API** instead of calling OCR server directly.

## References

- [Model Context Protocol Specification](https://spec.modelcontextprotocol.io/)
- [Server-Sent Events (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [Tesseract OCR Documentation](https://tesseract-ocr.github.io/)
- [LlamaStack Documentation](https://llamastack.github.io/)

## Version History

- **2.0.0** - MCP protocol with SSE, tool discovery, LlamaStack integration
- **1.0.0** - Legacy HTTP server (backward compatibility)
