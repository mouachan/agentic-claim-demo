"""
MCP OCR Server - Model Context Protocol server with SSE for OCR processing

This server exposes OCR functionality via the MCP (Model Context Protocol) using Server-Sent Events (SSE).
LlamaStack connects to the /mcp/sse endpoint to discover available tools.
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from server import ocr_document, OCRRequest

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="MCP OCR Server",
    description="Model Context Protocol server for OCR processing with SSE",
    version="2.0.0",
)

# MCP Tool Definitions
MCP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ocr_document",
            "description": "Extract text from document images or PDFs using OCR and validate with LLM. Supports multiple formats (PDF, JPG, PNG, TIFF) and languages. Returns structured data with confidence scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_path": {
                        "type": "string",
                        "description": "Absolute path to the document file (PDF, JPG, PNG, TIFF, BMP)"
                    },
                    "document_type": {
                        "type": "string",
                        "enum": ["claim_form", "invoice", "medical_record", "id_card", "other"],
                        "default": "claim_form",
                        "description": "Type of document to optimize field extraction"
                    },
                    "language": {
                        "type": "string",
                        "default": "eng",
                        "description": "OCR language code (eng, fra, spa, deu, etc.)"
                    }
                },
                "required": ["document_path"]
            }
        }
    }
]


# Pydantic Models
class ToolExecutionRequest(BaseModel):
    """Request model for tool execution."""
    document_path: str = Field(..., description="Path to document file")
    document_type: str = Field(default="claim_form", description="Type of document")
    language: str = Field(default="eng", description="OCR language code")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str
    mcp_protocol: str
    tools_count: int


# ============================================================================
# MCP PROTOCOL ENDPOINTS (SSE)
# ============================================================================

@app.get("/sse")
async def mcp_sse_endpoint():
    """
    Server-Sent Events endpoint for MCP protocol.

    This endpoint is used by LlamaStack to:
    1. Discover available tools (ocr_document)
    2. Maintain a persistent connection (keep-alive)
    3. Receive updates when tools change

    LlamaStack connects here and receives a stream of events:
    - event: tools (list of available tools)
    - event: ping (keep-alive every 30 seconds)
    - event: update (when tools are added/removed)
    """
    logger.info("LlamaStack connected to MCP SSE endpoint")

    async def event_generator():
        """Generate SSE events for MCP protocol."""
        try:
            # 1. Send tools list on connection
            yield {
                "event": "tools",
                "data": json.dumps({
                    "tools": MCP_TOOLS,
                    "server_info": {
                        "name": "ocr-server",
                        "version": "2.0.0",
                        "protocol": "mcp-sse",
                        "capabilities": ["ocr", "pdf_processing", "llm_validation"]
                    }
                })
            }
            logger.info(f"Sent {len(MCP_TOOLS)} tools to LlamaStack")

            # 2. Keep-alive loop (ping every 30 seconds)
            while True:
                await asyncio.sleep(30)
                yield {
                    "event": "ping",
                    "data": json.dumps({
                        "status": "alive",
                        "timestamp": time.time(),
                        "tools_count": len(MCP_TOOLS)
                    })
                }
                logger.debug("Sent keep-alive ping to LlamaStack")

        except asyncio.CancelledError:
            logger.info("LlamaStack disconnected from MCP SSE endpoint")
            raise
        except Exception as e:
            logger.error(f"Error in SSE event generator: {str(e)}")
            raise

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive"
        }
    )


# ============================================================================
# TOOL EXECUTION ENDPOINTS
# ============================================================================

@app.post("/mcp/tools/ocr_document")
async def execute_ocr_document(request: ToolExecutionRequest) -> JSONResponse:
    """
    Execute the ocr_document tool.

    Called by LlamaStack when an agent needs to perform OCR.

    Args:
        request: Tool execution parameters

    Returns:
        OCR result with raw text, structured data, and confidence score
    """
    logger.info(f"Executing ocr_document tool for: {request.document_path}")

    try:
        # Convert ToolExecutionRequest to OCRRequest
        ocr_request = OCRRequest(
            document_path=request.document_path,
            document_type=request.document_type,
            language=request.language
        )

        # Call the ocr_document function
        result = await ocr_document(ocr_request)

        logger.info(f"OCR completed with success: {result.success}")

        return JSONResponse(
            content=result.model_dump(),
            status_code=200 if result.success else 500
        )

    except Exception as e:
        logger.error(f"Error executing ocr_document: {str(e)}")
        return JSONResponse(
            content={
                "success": False,
                "raw_text": None,
                "structured_data": None,
                "confidence": 0.0,
                "errors": [str(e)]
            },
            status_code=500
        )


# ============================================================================
# BACKWARD COMPATIBILITY (Legacy HTTP endpoint)
# ============================================================================

@app.post("/ocr_document")
async def legacy_ocr_document(request: ToolExecutionRequest) -> JSONResponse:
    """
    Legacy HTTP endpoint for backward compatibility.

    This endpoint maintains compatibility with existing clients that call
    the OCR server directly without going through LlamaStack.

    New clients should use LlamaStack Agents API instead.
    """
    logger.warning("Legacy /ocr_document endpoint called. Consider migrating to LlamaStack Agents API.")
    return await execute_ocr_document(request)


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.get("/health/live", response_model=HealthResponse)
async def liveness():
    """Kubernetes liveness probe."""
    return HealthResponse(
        status="alive",
        service="mcp-ocr-server",
        version="2.0.0",
        mcp_protocol="sse",
        tools_count=len(MCP_TOOLS)
    )


@app.get("/health/ready", response_model=HealthResponse)
async def readiness():
    """
    Kubernetes readiness probe.

    Checks that Tesseract OCR is available before marking as ready.
    """
    try:
        import pytesseract
        pytesseract.get_tesseract_version()

        return HealthResponse(
            status="ready",
            service="mcp-ocr-server",
            version="2.0.0",
            mcp_protocol="sse",
            tools_count=len(MCP_TOOLS)
        )
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Tesseract not ready: {str(e)}"
        )


@app.get("/")
async def root():
    """Root endpoint with server information."""
    return {
        "service": "MCP OCR Server",
        "version": "2.0.0",
        "protocol": "Model Context Protocol (MCP) with SSE",
        "status": "running",
        "endpoints": {
            "mcp_sse": "/sse",
            "tool_execution": "/mcp/tools/{tool_name}",
            "health_live": "/health/live",
            "health_ready": "/health/ready"
        },
        "tools": [tool["function"]["name"] for tool in MCP_TOOLS],
        "tools_detail": MCP_TOOLS,
        "documentation": {
            "mcp_protocol": "Connect to /sse to discover tools via Server-Sent Events",
            "tool_execution": "POST to /mcp/tools/ocr_document to execute OCR",
            "example": {
                "discover_tools": "curl -N http://ocr-server:8080/sse",
                "execute_tool": "curl -X POST http://ocr-server:8080/mcp/tools/ocr_document -d '{\"document_path\": \"/path/to/doc.pdf\"}'"
            }
        }
    }


@app.get("/mcp/tools")
async def list_tools():
    """
    List all available MCP tools.

    Alternative to SSE for simple tool discovery (non-streaming).
    """
    return {
        "tools": MCP_TOOLS,
        "count": len(MCP_TOOLS)
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    logger.info(f"Starting MCP OCR Server on port {port}")
    logger.info(f"MCP SSE endpoint: http://0.0.0.0:{port}/sse")
    logger.info(f"Tools available: {[t['function']['name'] for t in MCP_TOOLS]}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
