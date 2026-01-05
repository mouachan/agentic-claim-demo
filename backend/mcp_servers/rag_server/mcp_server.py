"""
MCP RAG Server - Model Context Protocol server with SSE
FIXED: Uses proper MCP JSON-RPC 2.0 protocol
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from server import (
    retrieve_user_info,
    retrieve_similar_claims,
    search_knowledge_base,
    RetrieveUserInfoRequest,
    RetrieveSimilarClaimsRequest,
    SearchKnowledgeBaseRequest,
    LLAMASTACK_ENDPOINT
)

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="MCP RAG Server",
    description="Model Context Protocol server for RAG operations",
    version="3.0.0",
)

# MCP Tool Definitions (MCP Standard format)
MCP_TOOLS = [
    {
        "name": "retrieve_user_info",
        "description": "Retrieve user information and insurance contracts using vector similarity search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "User identifier (UUID or user ID)"
                },
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant user contracts"
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of contracts to retrieve"
                }
            },
            "required": ["user_id", "query"]
        }
    },
    {
        "name": "retrieve_similar_claims",
        "description": "Find similar historical claims using vector similarity search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_text": {
                    "type": "string",
                    "description": "Text content of the current claim"
                },
                "claim_type": {
                    "type": "string",
                    "description": "Optional filter by claim type"
                },
                "top_k": {
                    "type": "integer",
                    "default": 10,
                    "description": "Number of similar claims to retrieve"
                },
                "min_similarity": {
                    "type": "number",
                    "default": 0.7,
                    "description": "Minimum similarity score threshold"
                }
            },
            "required": ["claim_text"]
        }
    },
    {
        "name": "search_knowledge_base",
        "description": "Search the knowledge base for policy information and guidelines.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for knowledge base"
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of articles to retrieve"
                }
            },
            "required": ["query"]
        }
    }
]

# Server info for MCP
SERVER_INFO = {
    "name": "rag-server",
    "version": "3.0.0",
    "protocolVersion": "2024-11-05"
}

SERVER_CAPABILITIES = {
    "tools": {"listChanged": False}
}


# ============================================================================
# MCP JSON-RPC MESSAGE HANDLING
# ============================================================================

async def handle_jsonrpc_message(message: dict) -> dict:
    """
    Handle incoming JSON-RPC 2.0 messages from MCP client.
    """
    method = message.get("method", "")
    msg_id = message.get("id")
    params = message.get("params", {})

    logger.info(f"MCP Request: method={method}, id={msg_id}")

    try:
        # Initialize
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": SERVER_INFO,
                    "capabilities": SERVER_CAPABILITIES
                }
            }

        # List tools
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": MCP_TOOLS
                }
            }

        # Call tool
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            result = await execute_tool(tool_name, arguments)

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, default=str)
                        }
                    ]
                }
            }

        # Ping (keep-alive)
        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {}
            }

        # Notifications (no response needed)
        elif method == "notifications/initialized":
            logger.info("MCP client initialized")
            return None  # No response for notifications

        else:
            logger.warning(f"Unknown MCP method: {method}")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

    except Exception as e:
        logger.error(f"Error handling MCP message: {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }


async def execute_tool(tool_name: str, arguments: dict) -> dict:
    """Execute a tool and return the result."""
    logger.info(f"Executing tool: {tool_name} with args: {arguments}")

    try:
        if tool_name == "retrieve_user_info":
            request = RetrieveUserInfoRequest(
                user_id=arguments["user_id"],
                query=arguments["query"],
                top_k=arguments.get("top_k", 5)
            )
            result = await retrieve_user_info(request)
            return result.model_dump()

        elif tool_name == "retrieve_similar_claims":
            request = RetrieveSimilarClaimsRequest(
                claim_text=arguments["claim_text"],
                claim_type=arguments.get("claim_type"),
                top_k=arguments.get("top_k", 10),
                min_similarity=arguments.get("min_similarity", 0.7)
            )
            result = await retrieve_similar_claims(request)
            return result.model_dump()

        elif tool_name == "search_knowledge_base":
            request = SearchKnowledgeBaseRequest(
                query=arguments["query"],
                top_k=arguments.get("top_k", 5)
            )
            result = await search_knowledge_base(request)
            return result.model_dump()

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        raise


# ============================================================================
# SSE ENDPOINT (MCP Standard)
# ============================================================================

# Store for pending messages per session
pending_messages: Dict[str, asyncio.Queue] = {}


@app.get("/sse")
async def mcp_sse_endpoint(request: Request):
    """
    SSE endpoint for MCP protocol.

    This endpoint:
    1. Creates a unique session
    2. Sends the session endpoint URL
    3. Waits for JSON-RPC responses to send back
    """
    session_id = str(uuid.uuid4())
    pending_messages[session_id] = asyncio.Queue()

    logger.info(f"MCP SSE connection opened: session={session_id}")

    async def event_generator():
        try:
            # Send endpoint URL for POST messages
            # LlamaStack will POST JSON-RPC messages to this URL
            base_url = str(request.base_url).rstrip("/")
            endpoint_url = f"{base_url}/sse/message?session_id={session_id}"

            yield f"event: endpoint\ndata: {endpoint_url}\n\n"
            logger.info(f"Sent endpoint URL: {endpoint_url}")

            # Wait for and send responses
            while True:
                try:
                    # Wait for messages with timeout for keep-alive
                    message = await asyncio.wait_for(
                        pending_messages[session_id].get(),
                        timeout=30.0
                    )
                    yield f"event: message\ndata: {json.dumps(message)}\n\n"
                    logger.debug(f"Sent SSE message: {message.get('id', 'notification')}")

                except asyncio.TimeoutError:
                    # Send keep-alive comment
                    yield ": keep-alive\n\n"

        except asyncio.CancelledError:
            logger.info(f"MCP SSE connection closed: session={session_id}")
        finally:
            # Cleanup
            if session_id in pending_messages:
                del pending_messages[session_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/sse/message")
async def mcp_message_endpoint(request: Request, session_id: str):
    """
    Receive JSON-RPC messages from MCP client.

    LlamaStack POSTs JSON-RPC requests here, and we queue responses
    to be sent via the SSE stream.
    """
    if session_id not in pending_messages:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        body = await request.json()
        logger.info(f"Received MCP message: {body.get('method', 'unknown')}")

        # Handle the JSON-RPC message
        response = await handle_jsonrpc_message(body)

        # Queue response for SSE stream (if not a notification)
        if response is not None:
            await pending_messages[session_id].put(response)

        return JSONResponse({"status": "accepted"})

    except Exception as e:
        logger.error(f"Error processing MCP message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ALTERNATIVE: SIMPLE SSE (for clients that don't support full MCP)
# ============================================================================

@app.get("/sse/simple")
async def simple_sse_endpoint():
    """
    Simplified SSE that just lists tools on connection.
    Some MCP clients may work better with this simpler approach.
    """
    logger.info("Simple SSE connection opened")

    async def event_generator():
        try:
            # Send tools immediately
            tools_message = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "result": {"tools": MCP_TOOLS}
            }
            yield f"event: message\ndata: {json.dumps(tools_message)}\n\n"

            # Keep-alive loop
            while True:
                await asyncio.sleep(30)
                yield ": keep-alive\n\n"

        except asyncio.CancelledError:
            logger.info("Simple SSE connection closed")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.get("/health/live")
async def liveness():
    return {"status": "alive", "service": "mcp-rag-server", "version": "3.0.0"}


@app.get("/health/ready")
async def readiness():
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{LLAMASTACK_ENDPOINT}/v1/health")
            if response.status_code == 200:
                return {"status": "ready", "service": "mcp-rag-server"}
    except:
        pass
    raise HTTPException(status_code=503, detail="LlamaStack not ready")


@app.get("/")
async def root():
    return {
        "service": "MCP RAG Server",
        "version": "3.0.0",
        "protocol": "MCP JSON-RPC 2.0 over SSE",
        "endpoints": {
            "sse": "/sse (full MCP protocol)",
            "sse_simple": "/sse/simple (simplified)",
            "message": "/sse/message?session_id=X (POST JSON-RPC)"
        },
        "tools": [t["name"] for t in MCP_TOOLS]
    }


@app.get("/mcp/tools")
async def list_tools():
    """REST endpoint to list tools (for debugging)."""
    return {"tools": MCP_TOOLS, "count": len(MCP_TOOLS)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    logger.info(f"Starting MCP RAG Server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
