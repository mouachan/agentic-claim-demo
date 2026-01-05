"""
MCP RAG Server - Centralized via LlamaStack
All vector operations go through LlamaStack APIs
"""

import asyncio
import logging
import os
import time
from typing import Dict, Any, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Import prompts
from prompts import get_knowledge_base_synthesis_prompt

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="MCP RAG Server (LlamaStack-based)",
    description="Vector search and retrieval via LlamaStack",
    version="2.0.0",
)

# Configuration
LLAMASTACK_ENDPOINT = os.getenv("LLAMASTACK_ENDPOINT", "http://localhost:8321")
VECTOR_STORE_NAME = os.getenv("VECTOR_STORE_NAME", "claims_vector_db")

# Global vector_store_id (retrieved at startup)
_vector_store_id: Optional[str] = None


# Pydantic models
class RetrieveUserInfoRequest(BaseModel):
    user_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=20)


class RetrieveUserInfoResponse(BaseModel):
    user_info: Dict[str, Any]
    contracts: List[Dict[str, Any]]
    similarity_scores: List[float]
    source_documents: List[str]


class RetrieveSimilarClaimsRequest(BaseModel):
    claim_text: str
    claim_type: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=50)
    min_similarity: float = Field(default=0.7, ge=0.0, le=1.0)


class SimilarClaim(BaseModel):
    claim_id: str
    claim_number: str
    claim_text: str
    similarity_score: float
    outcome: Optional[str]
    processing_time: Optional[int]


class RetrieveSimilarClaimsResponse(BaseModel):
    similar_claims: List[SimilarClaim]


class SearchKnowledgeBaseRequest(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeBaseResult(BaseModel):
    id: str
    title: str
    content: str
    similarity_score: float
    category: Optional[str]


class SearchKnowledgeBaseResponse(BaseModel):
    results: List[KnowledgeBaseResult]
    synthesized_answer: str


class HealthResponse(BaseModel):
    status: str
    service: str


# Helper functions
async def get_vector_store_id() -> str:
    """Get vector_store_id by name from LlamaStack."""
    global _vector_store_id

    if _vector_store_id:
        return _vector_store_id

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{LLAMASTACK_ENDPOINT}/v1/vector_stores",
                params={"name": VECTOR_STORE_NAME}
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("data") and len(data["data"]) > 0:
                    _vector_store_id = data["data"][0]["id"]
                    logger.info(f"Retrieved vector_store_id: {_vector_store_id}")
                    return _vector_store_id
                else:
                    raise ValueError(f"Vector store '{VECTOR_STORE_NAME}' not found")
            else:
                raise Exception(f"Failed to get vector_store: {response.status_code}")
    except Exception as e:
        logger.error(f"Error getting vector_store_id: {str(e)}")
        raise


async def vector_search_llamastack(
    query: str,
    collection: str,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Perform vector search via LlamaStack API.
    LlamaStack handles embedding creation and vector search.
    """
    try:
        vector_store_id = await get_vector_store_id()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LLAMASTACK_ENDPOINT}/v1/vector-io/query",
                json={
                    "vector_db_id": vector_store_id,
                    "query": query,
                    "k": top_k,
                    # Note: LlamaStack doesn't support collection/filters in query params yet
                    # We filter results by metadata after retrieval
                }
            )

            if response.status_code == 200:
                result = response.json()
                chunks = result.get("chunks", [])

                # Filter by collection and other filters
                filtered_chunks = []
                for chunk in chunks:
                    metadata = chunk.get("metadata", {})

                    # Check collection
                    if metadata.get("collection") != collection:
                        continue

                    # Check filters
                    if filters:
                        match = True
                        for key, value in filters.items():
                            if metadata.get(key) != value:
                                match = False
                                break
                        if not match:
                            continue

                    filtered_chunks.append({
                        "id": metadata.get("id"),
                        "text": chunk.get("content", ""),
                        "score": chunk.get("score", 0.0),
                        "metadata": metadata
                    })

                return filtered_chunks[:top_k]
            else:
                logger.error(f"LlamaStack vector search error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Vector search failed: {response.status_code}"
                )

    except Exception as e:
        logger.error(f"Error calling LlamaStack vector search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Vector search error: {str(e)}")


async def synthesize_with_llm(query: str, context: List[Dict[str, Any]]) -> str:
    """Synthesize answer from retrieved context using LlamaStack."""
    try:
        # Prepare context text
        context_text = "\n\n".join([
            f"Document {i+1} (Title: {doc.get('title', 'N/A')}):\n{doc.get('content', '')[:500]}"
            for i, doc in enumerate(context[:5])
        ])

        # Use centralized prompt
        prompt = get_knowledge_base_synthesis_prompt(query, context_text)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LLAMASTACK_ENDPOINT}/inference/generate",
                json={
                    "model": "llama-instruct-32-3b",
                    "prompt": prompt,
                    "temperature": 0.3,
                    "max_tokens": 512,
                }
            )

            if response.status_code == 200:
                result = response.json()
                answer = result.get("generated_text", "Unable to generate answer.")
                return answer
            else:
                return "Unable to synthesize answer from knowledge base."

    except Exception as e:
        logger.error(f"Error synthesizing answer: {str(e)}")
        return f"Error: {str(e)}"


# API Endpoints
@app.post("/retrieve_user_info", response_model=RetrieveUserInfoResponse)
async def retrieve_user_info(request: RetrieveUserInfoRequest) -> RetrieveUserInfoResponse:
    """
    Retrieve user information and contracts using LlamaStack vector search.

    MCP Tool: retrieve_user_info
    """
    # ============== TIMING START ==============
    start_time = time.time()
    logger.info(f"⏱️  RAG RETRIEVE_USER_INFO STARTED for user: {request.user_id}")

    try:
        # Search user contracts via LlamaStack
        search_start = time.time()
        results = await vector_search_llamastack(
            query=request.query,
            collection="user_contracts",
            top_k=request.top_k,
            filters={"user_id": request.user_id, "is_active": True}
        )
        search_time = time.time() - search_start
        logger.info(f"⏱️  Vector search completed in {search_time:.2f}s ({len(results)} results)")

        contracts = []
        similarity_scores = []
        source_documents = []

        for result in results:
            metadata = result.get("metadata", {})
            contracts.append({
                "id": result.get("id"),
                "contract_number": metadata.get("contract_number"),
                "contract_type": metadata.get("contract_type"),
                "coverage_amount": metadata.get("coverage_amount"),
                "is_active": metadata.get("is_active"),
            })
            similarity_scores.append(result.get("score", 0.0))
            source_documents.append(metadata.get("contract_number", ""))

        # Get basic user info (could also be via vector search or direct DB)
        user_info = {
            "user_id": request.user_id,
            # Add more user info if available
        }

        # ============== TIMING END ==============
        total_time = time.time() - start_time
        logger.info(f"⏱️  RAG RETRIEVE_USER_INFO COMPLETED in {total_time:.2f}s for user {request.user_id} ({len(contracts)} contracts)")

        # Check if we exceeded 10s timeout threshold
        if total_time > 10.0:
            logger.warning(f"⚠️  RAG TOO SLOW: {total_time:.2f}s > 10s LlamaStack timeout!")

        return RetrieveUserInfoResponse(
            user_info=user_info,
            contracts=contracts,
            similarity_scores=similarity_scores,
            source_documents=source_documents
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/retrieve_similar_claims", response_model=RetrieveSimilarClaimsResponse)
async def retrieve_similar_claims(request: RetrieveSimilarClaimsRequest) -> RetrieveSimilarClaimsResponse:
    """
    Find similar historical claims using LlamaStack vector search.

    MCP Tool: retrieve_similar_claims
    """
    # ============== TIMING START ==============
    start_time = time.time()
    logger.info(f"⏱️  RAG RETRIEVE_SIMILAR_CLAIMS STARTED (type: {request.claim_type}, top_k: {request.top_k})")

    try:
        # Search similar claims via LlamaStack
        filters = {}
        if request.claim_type:
            filters["claim_type"] = request.claim_type
        filters["status"] = {"$in": ["completed", "manual_review"]}

        search_start = time.time()
        results = await vector_search_llamastack(
            query=request.claim_text,
            collection="claim_documents",
            top_k=request.top_k,
            filters=filters
        )
        search_time = time.time() - search_start
        logger.info(f"⏱️  Vector search completed in {search_time:.2f}s ({len(results)} results)")

        similar_claims = []
        for result in results:
            similarity = result.get("score", 0.0)
            if similarity >= request.min_similarity:
                metadata = result.get("metadata", {})
                similar_claims.append(SimilarClaim(
                    claim_id=result.get("id", ""),
                    claim_number=metadata.get("claim_number", ""),
                    claim_text=result.get("text", "")[:500],  # Truncate
                    similarity_score=similarity,
                    outcome=metadata.get("status"),
                    processing_time=metadata.get("processing_time_ms")
                ))

        # ============== TIMING END ==============
        total_time = time.time() - start_time
        logger.info(f"⏱️  RAG RETRIEVE_SIMILAR_CLAIMS COMPLETED in {total_time:.2f}s ({len(similar_claims)} similar claims found)")

        # Check if we exceeded 10s timeout threshold
        if total_time > 10.0:
            logger.warning(f"⚠️  RAG TOO SLOW: {total_time:.2f}s > 10s LlamaStack timeout!")

        return RetrieveSimilarClaimsResponse(similar_claims=similar_claims)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving similar claims: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search_knowledge_base", response_model=SearchKnowledgeBaseResponse)
async def search_knowledge_base(request: SearchKnowledgeBaseRequest) -> SearchKnowledgeBaseResponse:
    """
    Search the knowledge base using LlamaStack vector search.

    MCP Tool: search_knowledge_base
    """
    try:
        # Search knowledge base via LlamaStack
        results = await vector_search_llamastack(
            query=request.query,
            collection="knowledge_base",
            top_k=request.top_k,
            filters={"is_active": True}
        )

        kb_results = []
        for result in results:
            metadata = result.get("metadata", {})
            kb_results.append(KnowledgeBaseResult(
                id=result.get("id", ""),
                title=metadata.get("title", ""),
                content=result.get("text", ""),
                category=metadata.get("category"),
                similarity_score=result.get("score", 0.0)
            ))

        # Synthesize answer from retrieved documents
        context = [{"title": r.title, "content": r.content} for r in kb_results]
        synthesized_answer = await synthesize_with_llm(request.query, context)

        logger.info(f"Found {len(kb_results)} knowledge base articles via LlamaStack")

        return SearchKnowledgeBaseResponse(
            results=kb_results,
            synthesized_answer=synthesized_answer
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching knowledge base: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/live", response_model=HealthResponse)
async def liveness():
    """Liveness probe."""
    return HealthResponse(
        status="alive",
        service="mcp-rag-server-llamastack"
    )


@app.get("/health/ready", response_model=HealthResponse)
async def readiness():
    """Readiness probe."""
    try:
        # Check if LlamaStack is accessible
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{LLAMASTACK_ENDPOINT}/health")
            if response.status_code == 200:
                return HealthResponse(
                    status="ready",
                    service="mcp-rag-server-llamastack"
                )
            else:
                raise HTTPException(status_code=503, detail="LlamaStack not ready")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LlamaStack not ready: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "MCP RAG Server (LlamaStack-based)",
        "version": "2.0.0",
        "status": "running",
        "centralized": "All operations via LlamaStack",
        "tools": ["retrieve_user_info", "retrieve_similar_claims", "search_knowledge_base"]
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
