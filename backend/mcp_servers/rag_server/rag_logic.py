"""
RAG Logic - Retrieval-Augmented Generation for claims processing

Vector search and retrieval using PostgreSQL + pgvector
"""

import logging
import os
from typing import Dict, Any, List, Optional

import httpx
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from prompts import get_knowledge_base_synthesis_prompt

logger = logging.getLogger(__name__)

# Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgresql.claims-demo.svc.cluster.local")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "claims_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "claims_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ClaimsDemo2025!")
LLAMASTACK_ENDPOINT = os.getenv("LLAMASTACK_ENDPOINT", "http://llamastack.claims-demo.svc.cluster.local:8321")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "granite-embedding-125m")
VECTOR_DIMENSION = int(os.getenv("VECTOR_DIMENSION", "768"))

# Database connection
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine)


async def create_embedding(text: str) -> List[float]:
    """
    Create embedding using LlamaStack Embeddings API.

    Args:
        text: Text to embed

    Returns:
        List of floats representing the embedding vector
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LLAMASTACK_ENDPOINT}/v1/embeddings",
                json={
                    "model": EMBEDDING_MODEL,
                    "input": text
                }
            )

            if response.status_code == 200:
                result = response.json()
                # OpenAI-compatible format
                if "data" in result and len(result["data"]) > 0:
                    embedding = result["data"][0]["embedding"]
                else:
                    logger.error(f"Unexpected embedding response format: {result}")
                    raise Exception("Invalid embedding response format")

                logger.debug(f"Created embedding with dimension: {len(embedding)}")
                return embedding
            else:
                logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                raise Exception("Failed to create embedding")

    except Exception as e:
        logger.error(f"Error creating embedding: {str(e)}")
        raise


async def synthesize_with_llm(query: str, context: List[Dict[str, Any]]) -> str:
    """
    Synthesize answer from retrieved context using LLM.

    Args:
        query: User query
        context: Retrieved documents/context

    Returns:
        Synthesized answer
    """
    try:
        # Prepare context text
        context_text = "\n\n".join([
            f"Document {i+1} (Title: {doc.get('title', 'N/A')}):\n{doc.get('content', '')[:500]}"
            for i, doc in enumerate(context[:5])  # Limit to top 5
        ])

        # Use centralized prompt
        prompt = get_knowledge_base_synthesis_prompt(query, context_text)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LLAMASTACK_ENDPOINT}/v1/chat/completions",
                json={
                    "model": "llama-instruct-32-3b",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that synthesizes information from provided context."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.3,
                    "max_tokens": 512,
                }
            )

            if response.status_code == 200:
                result = response.json()
                answer = result.get("choices", [{}])[0].get("message", {}).get("content", "Unable to generate answer.")
                return answer
            else:
                return "Unable to synthesize answer from knowledge base."

    except Exception as e:
        logger.error(f"Error synthesizing answer: {str(e)}")
        return f"Error: {str(e)}"


async def retrieve_user_info_logic(
    user_id: str,
    query: str,
    top_k: int = 5,
    include_contracts: bool = True
) -> Dict[str, Any]:
    """
    Retrieve user information and contracts using vector search.

    Args:
        user_id: User identifier
        query: Search query for contracts
        top_k: Number of contracts to retrieve
        include_contracts: Whether to retrieve contracts

    Returns:
        Dict with user_info, contracts, similarity_scores, source_documents
    """
    try:
        # Create embedding for query
        query_embedding = await create_embedding(query)

        with SessionLocal() as session:
            # Get user basic info
            user_query = text("""
                SELECT id, user_id, email, full_name, date_of_birth, phone_number, address
                FROM users
                WHERE user_id = :user_id
            """)
            user_result = session.execute(user_query, {"user_id": user_id}).fetchone()

            if not user_result:
                raise Exception(f"User not found: {user_id}")

            user_info = dict(user_result._mapping)

            # Get user contracts with similarity search if requested
            contracts = []
            similarity_scores = []
            source_documents = []

            if include_contracts:
                # Vector search on contracts
                # Convert embedding to PostgreSQL vector format
                embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'

                contract_query = text("""
                    SELECT
                        id, contract_number, contract_type, coverage_amount,
                        full_text, key_terms, is_active,
                        COALESCE(1 - (embedding <=> CAST(:query_embedding AS vector)), 0.0) AS similarity
                    FROM user_contracts
                    WHERE user_id = :user_id AND is_active = true
                        AND embedding IS NOT NULL
                    ORDER BY COALESCE(embedding <=> CAST(:query_embedding AS vector), 999999)
                    LIMIT :top_k
                """)

                contract_results = session.execute(
                    contract_query,
                    {
                        "user_id": user_id,
                        "query_embedding": embedding_str,
                        "top_k": top_k
                    }
                ).fetchall()

                for row in contract_results:
                    contract = dict(row._mapping)
                    similarity_scores.append(contract.pop("similarity", 0.0))
                    contracts.append(contract)
                    source_documents.append(contract.get("contract_number", ""))

        logger.info(f"Retrieved info for user {user_id} with {len(contracts)} contracts")

        return {
            "user_info": user_info,
            "contracts": contracts,
            "similarity_scores": similarity_scores,
            "source_documents": source_documents
        }

    except Exception as e:
        logger.error(f"Error retrieving user info: {str(e)}")
        raise


async def retrieve_similar_claims_logic(
    claim_text: str,
    claim_type: Optional[str] = None,
    top_k: int = 10,
    min_similarity: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Find similar historical claims using vector similarity search.

    Args:
        claim_text: Text of the current claim
        claim_type: Optional filter by claim type
        top_k: Number of similar claims to retrieve
        min_similarity: Minimum similarity score (0.0 to 1.0)

    Returns:
        List of similar claims with metadata
    """
    try:
        # Create embedding for claim text
        claim_embedding = await create_embedding(claim_text)

        with SessionLocal() as session:
            # Vector search on claim documents
            # Convert embedding to PostgreSQL vector format
            embedding_str = '[' + ','.join(map(str, claim_embedding)) + ']'

            query = text("""
                SELECT
                    CAST(c.id AS text) as claim_id,
                    c.claim_number,
                    cd.raw_ocr_text as claim_text,
                    1 - (cd.embedding <=> CAST(:claim_embedding AS vector)) AS similarity,
                    c.status as outcome,
                    c.total_processing_time_ms
                FROM claim_documents cd
                JOIN claims c ON cd.claim_id = c.id
                WHERE 1 - (cd.embedding <=> CAST(:claim_embedding AS vector)) >= :min_similarity
                    AND (:claim_type IS NULL OR c.claim_type = :claim_type)
                    AND c.status IN ('completed', 'manual_review')
                ORDER BY cd.embedding <=> CAST(:claim_embedding AS vector)
                LIMIT :top_k
            """)

            results = session.execute(
                query,
                {
                    "claim_embedding": embedding_str,
                    "min_similarity": min_similarity,
                    "claim_type": claim_type,
                    "top_k": top_k
                }
            ).fetchall()

            similar_claims = [
                {
                    "claim_id": row.claim_id,
                    "claim_number": row.claim_number,
                    "claim_text": row.claim_text[:500] if row.claim_text else "",  # Truncate
                    "similarity_score": row.similarity,
                    "outcome": row.outcome,
                    "processing_time": row.total_processing_time_ms
                }
                for row in results
            ]

        logger.info(f"Found {len(similar_claims)} similar claims")

        return similar_claims

    except Exception as e:
        logger.error(f"Error retrieving similar claims: {str(e)}")
        raise


async def search_knowledge_base_logic(
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Search the knowledge base for relevant policy information.

    Args:
        query: Search query
        filters: Optional filters (not implemented yet)
        top_k: Number of results to retrieve

    Returns:
        Dict with results and synthesized answer
    """
    try:
        # Create embedding for query
        query_embedding = await create_embedding(query)

        with SessionLocal() as session:
            # Vector search on knowledge base
            # Convert embedding to PostgreSQL vector format
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'

            kb_query = text("""
                SELECT
                    CAST(id AS text),
                    title,
                    content,
                    category,
                    1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
                FROM knowledge_base
                WHERE is_active = true
                ORDER BY embedding <=> CAST(:query_embedding AS vector)
                LIMIT :top_k
            """)

            results = session.execute(
                kb_query,
                {
                    "query_embedding": embedding_str,
                    "top_k": top_k
                }
            ).fetchall()

            kb_results = [
                {
                    "id": row.id,
                    "title": row.title,
                    "content": row.content,
                    "category": row.category,
                    "similarity_score": row.similarity
                }
                for row in results
            ]

        # Synthesize answer from retrieved documents
        context = [{"title": r["title"], "content": r["content"]} for r in kb_results]
        synthesized_answer = await synthesize_with_llm(query, context)

        logger.info(f"Found {len(kb_results)} knowledge base articles")

        return {
            "results": kb_results,
            "synthesized_answer": synthesized_answer
        }

    except Exception as e:
        logger.error(f"Error searching knowledge base: {str(e)}")
        raise
