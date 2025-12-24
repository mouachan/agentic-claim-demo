"""
MCP RAG Server - Model Context Protocol server with SSE for RAG operations

This server exposes RAG (Retrieval-Augmented Generation) functionality via MCP using SSE.
LlamaStack connects to /mcp/sse to discover 3 tools:
- retrieve_user_info
- retrieve_similar_claims
- search_knowledge_base
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from rag_logic import (
    retrieve_user_info_logic,
    retrieve_similar_claims_logic,
    search_knowledge_base_logic
)

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="MCP RAG Server",
    description="Model Context Protocol server for RAG operations with SSE",
    version="2.0.0",
)

# MCP Tool Definitions
MCP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_user_info",
            "description": "Retrieve user information and insurance contracts using vector similarity search. Returns user profile data and relevant contract documents based on the query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier (UUID or user ID)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query to find relevant user contracts (e.g., 'medical coverage', 'emergency services')"
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                        "description": "Number of contracts to retrieve"
                    },
                    "include_contracts": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to include contract documents in results"
                    }
                },
                "required": ["user_id", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_similar_claims",
            "description": "Find similar historical claims using vector similarity search. Helps identify precedents and patterns in claim processing. Returns claims with similar content, outcomes, and processing times.",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_text": {
                        "type": "string",
                        "description": "Text content of the current claim to find similar cases for"
                    },
                    "claim_type": {
                        "type": "string",
                        "description": "Optional filter by claim type (medical, auto, property, etc.)"
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Number of similar claims to retrieve"
                    },
                    "min_similarity": {
                        "type": "number",
                        "default": 0.7,
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Minimum similarity score threshold (0.0 to 1.0)"
                    }
                },
                "required": ["claim_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search the knowledge base for policy information, guidelines, and rules. Uses vector search to find relevant documents and synthesizes an answer using LLM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for knowledge base (e.g., 'what is covered under emergency medical services?')"
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters for search (category, tags, etc.)"
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                        "description": "Number of knowledge base articles to retrieve"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


# Pydantic Models
class RetrieveUserInfoRequest(BaseModel):
    user_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    include_contracts: bool = True


class RetrieveSimilarClaimsRequest(BaseModel):
    claim_text: str
    claim_type: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=50)
    min_similarity: float = Field(default=0.7, ge=0.0, le=1.0)


class SearchKnowledgeBaseRequest(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None
    top_k: int = Field(default=5, ge=1, le=20)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    mcp_protocol: str
    tools_count: int
    database_connected: bool = False


# ============================================================================
# MCP PROTOCOL ENDPOINTS (SSE)
# ============================================================================

@app.get("/mcp/sse")
async def mcp_sse_endpoint():
    """
    Server-Sent Events endpoint for MCP protocol.

    LlamaStack connects here to:
    1. Discover 3 RAG tools
    2. Maintain persistent connection
    3. Receive updates when tools change
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
                        "name": "rag-server",
                        "version": "2.0.0",
                        "protocol": "mcp-sse",
                        "capabilities": ["vector_search", "embeddings", "llm_synthesis"],
                        "database": "postgresql+pgvector"
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
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


# ============================================================================
# TOOL EXECUTION ENDPOINTS
# ============================================================================

@app.post("/mcp/tools/retrieve_user_info")
async def execute_retrieve_user_info(request: RetrieveUserInfoRequest) -> JSONResponse:
    """
    Execute retrieve_user_info tool.

    Called by LlamaStack when agent needs user information and contracts.
    """
    logger.info(f"Executing retrieve_user_info for user: {request.user_id}")

    try:
        result = await retrieve_user_info_logic(
            user_id=request.user_id,
            query=request.query,
            top_k=request.top_k,
            include_contracts=request.include_contracts
        )

        logger.info(f"Retrieved {len(result['contracts'])} contracts for user {request.user_id}")

        return JSONResponse(content=result, status_code=200)

    except Exception as e:
        logger.error(f"Error executing retrieve_user_info: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.post("/mcp/tools/retrieve_similar_claims")
async def execute_retrieve_similar_claims(request: RetrieveSimilarClaimsRequest) -> JSONResponse:
    """
    Execute retrieve_similar_claims tool.

    Called by LlamaStack when agent needs to find similar historical claims.
    """
    logger.info(f"Executing retrieve_similar_claims (query length: {len(request.claim_text)} chars)")

    try:
        similar_claims = await retrieve_similar_claims_logic(
            claim_text=request.claim_text,
            claim_type=request.claim_type,
            top_k=request.top_k,
            min_similarity=request.min_similarity
        )

        logger.info(f"Found {len(similar_claims)} similar claims")

        return JSONResponse(
            content={"similar_claims": similar_claims},
            status_code=200
        )

    except Exception as e:
        logger.error(f"Error executing retrieve_similar_claims: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


@app.post("/mcp/tools/search_knowledge_base")
async def execute_search_knowledge_base(request: SearchKnowledgeBaseRequest) -> JSONResponse:
    """
    Execute search_knowledge_base tool.

    Called by LlamaStack when agent needs policy information from knowledge base.
    """
    logger.info(f"Executing search_knowledge_base: {request.query}")

    try:
        result = await search_knowledge_base_logic(
            query=request.query,
            filters=request.filters,
            top_k=request.top_k
        )

        logger.info(f"Found {len(result['results'])} knowledge base articles")

        return JSONResponse(content=result, status_code=200)

    except Exception as e:
        logger.error(f"Error executing search_knowledge_base: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


# ============================================================================
# BACKWARD COMPATIBILITY (Legacy HTTP endpoints)
# ============================================================================

@app.post("/retrieve_user_info")
async def legacy_retrieve_user_info(request: RetrieveUserInfoRequest) -> JSONResponse:
    """Legacy endpoint for backward compatibility."""
    logger.warning("Legacy /retrieve_user_info endpoint called. Consider migrating to LlamaStack Agents API.")
    return await execute_retrieve_user_info(request)


@app.post("/retrieve_similar_claims")
async def legacy_retrieve_similar_claims(request: RetrieveSimilarClaimsRequest) -> JSONResponse:
    """Legacy endpoint for backward compatibility."""
    logger.warning("Legacy /retrieve_similar_claims endpoint called. Consider migrating to LlamaStack Agents API.")
    return await execute_retrieve_similar_claims(request)


@app.post("/search_knowledge_base")
async def legacy_search_knowledge_base(request: SearchKnowledgeBaseRequest) -> JSONResponse:
    """Legacy endpoint for backward compatibility."""
    logger.warning("Legacy /search_knowledge_base endpoint called. Consider migrating to LlamaStack Agents API.")
    return await execute_search_knowledge_base(request)


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.get("/health/live", response_model=HealthResponse)
async def liveness():
    """Kubernetes liveness probe."""
    return HealthResponse(
        status="alive",
        service="mcp-rag-server",
        version="2.0.0",
        mcp_protocol="sse",
        tools_count=len(MCP_TOOLS),
        database_connected=False
    )


@app.get("/health/ready", response_model=HealthResponse)
async def readiness():
    """
    Kubernetes readiness probe.

    Checks database connection before marking as ready.
    """
    try:
        from sqlalchemy import create_engine, text
        import os

        # Test database connection
        POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgresql.claims-demo.svc.cluster.local")
        POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
        POSTGRES_DB = os.getenv("POSTGRES_DB", "claims_db")
        POSTGRES_USER = os.getenv("POSTGRES_USER", "claims_user")
        POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ClaimsDemo2025!")

        DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        test_engine = create_engine(DATABASE_URL)

        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return HealthResponse(
            status="ready",
            service="mcp-rag-server",
            version="2.0.0",
            mcp_protocol="sse",
            tools_count=len(MCP_TOOLS),
            database_connected=True
        )

    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Database not ready: {str(e)}"
        )


@app.get("/")
async def root():
    """Root endpoint with server information."""
    return {
        "service": "MCP RAG Server",
        "version": "2.0.0",
        "protocol": "Model Context Protocol (MCP) with SSE",
        "status": "running",
        "endpoints": {
            "mcp_sse": "/mcp/sse",
            "tool_execution": "/mcp/tools/{tool_name}",
            "health_live": "/health/live",
            "health_ready": "/health/ready"
        },
        "tools": [tool["function"]["name"] for tool in MCP_TOOLS],
        "tools_detail": MCP_TOOLS,
        "database": {
            "type": "PostgreSQL + pgvector",
            "vector_dimension": 768,
            "embedding_model": "granite-embedding-125m"
        },
        "documentation": {
            "mcp_protocol": "Connect to /mcp/sse to discover tools via Server-Sent Events",
            "tool_execution": "POST to /mcp/tools/{tool_name} to execute RAG operations",
            "example": {
                "discover_tools": "curl -N http://rag-server:8080/mcp/sse",
                "retrieve_user": "curl -X POST http://rag-server:8080/mcp/tools/retrieve_user_info -d '{\"user_id\": \"...\", \"query\": \"...\"}'",
                "similar_claims": "curl -X POST http://rag-server:8080/mcp/tools/retrieve_similar_claims -d '{\"claim_text\": \"...\"}'"
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
    logger.info(f"Starting MCP RAG Server on port {port}")
    logger.info(f"MCP SSE endpoint: http://0.0.0.0:{port}/mcp/sse")
    logger.info(f"Tools available: {[t['function']['name'] for t in MCP_TOOLS]}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
