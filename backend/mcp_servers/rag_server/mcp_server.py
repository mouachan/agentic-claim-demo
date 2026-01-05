"""
MCP RAG Server - Using FastMCP SDK
Direct function calls (no HTTP overhead)
"""

import os
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Import backend functions
from server import (
    retrieve_user_info,
    retrieve_similar_claims,
    search_knowledge_base,
    RetrieveUserInfoRequest,
    RetrieveSimilarClaimsRequest,
    SearchKnowledgeBaseRequest
)

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP("rag-server")


@mcp.tool()
async def retrieve_user_info_tool(user_id: str, query: str, top_k: int = 5) -> str:
    """
    Retrieve user information and insurance contracts using vector similarity search.

    Args:
        user_id: User identifier (UUID or user ID)
        query: Search query to find relevant user contracts
        top_k: Number of contracts to retrieve (default: 5)

    Returns:
        JSON string with user info, contracts, and similarity scores
    """
    logger.info(f"retrieve_user_info called: user_id={user_id}, query={query}, top_k={top_k}")

    try:
        request = RetrieveUserInfoRequest(
            user_id=user_id,
            query=query,
            top_k=top_k
        )
        response = await retrieve_user_info(request)
        return response.model_dump_json()
    except Exception as e:
        logger.error(f"Error in retrieve_user_info: {e}")
        return f'{{"error": "Failed to retrieve user info: {str(e)}"}}'


@mcp.tool()
async def retrieve_similar_claims_tool(
    claim_text: str,
    claim_type: Optional[str] = None,
    top_k: int = 10,
    min_similarity: float = 0.7
) -> str:
    """
    Find similar historical claims using vector similarity search.

    Args:
        claim_text: Text content of the current claim to find similar cases for
        claim_type: Optional filter by claim type (medical, auto, property, etc.)
        top_k: Number of similar claims to retrieve (default: 10)
        min_similarity: Minimum similarity score threshold (default: 0.7)

    Returns:
        JSON string with similar claims, outcomes, and processing times
    """
    logger.info(f"retrieve_similar_claims called: claim_type={claim_type}, top_k={top_k}")

    try:
        request = RetrieveSimilarClaimsRequest(
            claim_text=claim_text,
            claim_type=claim_type,
            top_k=top_k,
            min_similarity=min_similarity
        )
        response = await retrieve_similar_claims(request)
        return response.model_dump_json()
    except Exception as e:
        logger.error(f"Error in retrieve_similar_claims: {e}")
        return f'{{"error": "Failed to retrieve similar claims: {str(e)}"}}'


@mcp.tool()
async def search_knowledge_base_tool(query: str, top_k: int = 5) -> str:
    """
    Search the knowledge base for policy information and guidelines.

    Args:
        query: Search query for knowledge base
        top_k: Number of articles to retrieve (default: 5)

    Returns:
        JSON string with results and synthesized answer
    """
    logger.info(f"search_knowledge_base called: query={query}, top_k={top_k}")

    try:
        request = SearchKnowledgeBaseRequest(
            query=query,
            top_k=top_k
        )
        response = await search_knowledge_base(request)
        return response.model_dump_json()
    except Exception as e:
        logger.error(f"Error in search_knowledge_base: {e}")
        return f'{{"error": "Failed to search knowledge base: {str(e)}"}}'


if __name__ == "__main__":
    import uvicorn

    # Get port from environment or use default
    port = int(os.getenv("PORT", "8080"))

    logger.info(f"Starting MCP RAG Server (FastMCP) on port {port}")

    # Run FastMCP server with SSE transport using uvicorn
    uvicorn.run(mcp.sse_app, host="0.0.0.0", port=port)
