"""
MCP Orchestrator Server - Coordinates claims processing workflow
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Import prompts
from prompts import get_claim_decision_prompt

# Import intelligent orchestrator
from llamastack_agent_orchestrator import intelligent_orchestrate_with_llm

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="MCP Orchestrator Server",
    description="Orchestrates claims processing workflow",
    version="1.0.0",
)

# Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "claims_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "claims_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "claims_pass")

OCR_SERVER_URL = os.getenv("OCR_SERVER_URL", "http://localhost:8081")
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8082")
GUARDRAILS_SERVER_URL = os.getenv("GUARDRAILS_SERVER_URL", "http://localhost:8084")
# Use Mistral model from OpenShift AI - OpenAI compatible API
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "https://mistral-3-14b-instruct-edg-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/v1/chat/completions")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "mistral-3-14b-instruct")

MAX_PROCESSING_TIME = int(os.getenv("MAX_PROCESSING_TIME_SECONDS", "300"))
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))

# Database
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine)


# Enums
class WorkflowType(str, Enum):
    STANDARD = "standard"
    EXPEDITED = "expedited"
    MANUAL_REVIEW = "manual_review"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# Pydantic models
class ProcessingConfig(BaseModel):
    workflow_type: WorkflowType = WorkflowType.STANDARD
    skip_ocr: bool = False
    skip_guardrails: bool = False
    enable_rag: bool = True
    llm_decision_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class OrchestrateclaimProcessingRequest(BaseModel):
    claim_id: str
    document_path: str
    user_id: str
    processing_config: Optional[ProcessingConfig] = None


class ProcessingStepResult(BaseModel):
    step_name: str
    agent: str
    status: str
    duration_ms: int
    output: Dict[str, Any]
    error: Optional[str] = None


class FinalDecision(BaseModel):
    recommendation: str  # approve, deny, manual_review
    confidence: float
    reasoning: str
    relevant_policies: List[str]


class OrchestrateclaimProcessingResponse(BaseModel):
    claim_id: str
    status: str
    processing_steps: List[ProcessingStepResult]
    ocr_results: Optional[Dict[str, Any]] = None
    guardrails_results: Optional[Dict[str, Any]] = None
    rag_results: Optional[Dict[str, Any]] = None
    final_decision: Optional[FinalDecision] = None
    total_processing_time_ms: int
    warnings: List[str] = Field(default_factory=list)


class GetProcessingStatusRequest(BaseModel):
    claim_id: str


class GetProcessingStatusResponse(BaseModel):
    claim_id: str
    status: str
    current_step: str
    progress_percentage: float
    estimated_completion_time: Optional[str]


class HealthResponse(BaseModel):
    status: str
    service: str


# Helper functions
async def call_mcp_server(
    server_url: str,
    endpoint: str,
    payload: Dict[str, Any],
    timeout: int = 30
) -> Dict[str, Any]:
    """Call another MCP server."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{server_url}/{endpoint}", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Error calling {server_url}/{endpoint}: {str(e)}")
        raise


async def log_processing_step(
    claim_id: str,
    step: str,
    agent_name: str,
    status: str,
    duration_ms: int,
    output_data: Dict[str, Any],
    error_message: Optional[str] = None
):
    """Log processing step to database."""
    try:
        import json
        with SessionLocal() as session:
            # Convert output_data to JSON string
            output_json = json.dumps(output_data) if output_data else '{}'

            session.execute(
                text("""
                    INSERT INTO processing_logs
                    (claim_id, step, agent_name, status, duration_ms, output_data, error_message, completed_at)
                    VALUES (:claim_id, :step, :agent_name, :status, :duration_ms, CAST(:output_data AS jsonb), :error_message, NOW())
                """),
                {
                    "claim_id": claim_id,
                    "step": step,
                    "agent_name": agent_name,
                    "status": status,
                    "duration_ms": duration_ms,
                    "output_data": output_json,
                    "error_message": error_message
                }
            )
            session.commit()
    except Exception as e:
        logger.error(f"Error logging processing step: {str(e)}")


async def update_claim_status(claim_id: str, status: str, processing_time_ms: Optional[int] = None):
    """Update claim status in database."""
    try:
        with SessionLocal() as session:
            if processing_time_ms:
                query = text("""
                    UPDATE claims
                    SET status = :status, processed_at = NOW(), total_processing_time_ms = :processing_time_ms
                    WHERE id = :claim_id
                """)
                session.execute(query, {
                    "claim_id": claim_id,
                    "status": status,
                    "processing_time_ms": processing_time_ms
                })
            else:
                query = text("""
                    UPDATE claims SET status = :status WHERE id = :claim_id
                """)
                session.execute(query, {"claim_id": claim_id, "status": status})

            session.commit()
    except Exception as e:
        logger.error(f"Error updating claim status: {str(e)}")


async def make_final_decision(
    claim_id: str,
    user_id: str,
    ocr_results: Dict[str, Any],
    rag_results: Dict[str, Any],
    user_contracts: List[Dict[str, Any]]
) -> FinalDecision:
    """Make final claim decision using LLM."""
    try:
        # Prepare data for prompt - keep it concise to avoid timeouts
        import json
        # Extract key OCR fields only
        if ocr_results and 'structured_data' in ocr_results:
            structured = ocr_results.get('structured_data', {})
            ocr_summary = {
                "claim_number": structured.get('fields', {}).get('claim_number', {}).get('value'),
                "amount": structured.get('fields', {}).get('amount', {}).get('value'),
                "service": structured.get('fields', {}).get('diagnosis', {}).get('value'),
                "date": structured.get('fields', {}).get('date_of_service', {}).get('value')
            }
            ocr_data = json.dumps(ocr_summary, indent=2)
        else:
            ocr_data = "No OCR data available"

        # Summarize contracts (limit to 3)
        contracts_summary = [
            {
                "type": c.get("contract_type"),
                "coverage": c.get("coverage_amount"),
                "active": c.get("is_active")
            } for c in (user_contracts[:3] if user_contracts else [])
        ]
        contracts_data = json.dumps(contracts_summary, indent=2) if contracts_summary else "No active contracts"

        # Summarize similar claims (limit to 3)
        if rag_results and 'similar_claims' in rag_results:
            claims_summary = [
                {
                    "outcome": c.get("outcome"),
                    "similarity": round(c.get("similarity_score", 0), 2)
                } for c in (rag_results.get('similar_claims', [])[:3])
            ]
            similar_claims_data = json.dumps(claims_summary, indent=2) if claims_summary else "No similar claims"
        else:
            similar_claims_data = "No similar claims"

        # Use centralized prompt
        prompt = get_claim_decision_prompt(
            claim_id=claim_id,
            user_id=user_id,
            ocr_data=ocr_data,
            user_contracts=contracts_data,
            similar_claims=similar_claims_data,
            guardrails_results="No issues detected"
        )

        async with httpx.AsyncClient(timeout=90.0) as client:
            # Use OpenAI-compatible API format
            response = await client.post(
                LLM_ENDPOINT,
                json={
                    "model": LLM_MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": "You are an expert insurance claims processor. Respond ONLY with valid JSON, no additional text."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1024,
                }
            )

            if response.status_code == 200:
                result = response.json()
                import json
                try:
                    # Extract content from OpenAI format response
                    generated_text = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                    logger.info(f"LLM response: {generated_text[:200]}")

                    # Try to extract JSON from the response (may have markdown code blocks)
                    if "```json" in generated_text:
                        # Extract JSON from markdown code block
                        json_start = generated_text.find("```json") + 7
                        json_end = generated_text.find("```", json_start)
                        generated_text = generated_text[json_start:json_end].strip()
                    elif "```" in generated_text:
                        # Extract from generic code block
                        json_start = generated_text.find("```") + 3
                        json_end = generated_text.find("```", json_start)
                        generated_text = generated_text[json_start:json_end].strip()

                    decision_data = json.loads(generated_text)

                    # Convert reasoning to string if it's a dict
                    if isinstance(decision_data.get("reasoning"), dict):
                        decision_data["reasoning"] = json.dumps(decision_data["reasoning"])

                    return FinalDecision(**decision_data)
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to parse LLM decision: {str(e)}, response: {generated_text[:200]}")
                    # Fallback decision
                    return FinalDecision(
                        recommendation="manual_review",
                        confidence=0.5,
                        reasoning="Unable to parse LLM decision, flagging for manual review",
                        relevant_policies=[]
                    )
            else:
                logger.error(f"LLM request failed: {response.status_code} - {response.text[:200]}")
                return FinalDecision(
                    recommendation="manual_review",
                    confidence=0.0,
                    reasoning="LLM unavailable, requires manual review",
                    relevant_policies=[]
                )

    except Exception as e:
        logger.error(f"Error making final decision: {str(e)}")
        return FinalDecision(
            recommendation="manual_review",
            confidence=0.0,
            reasoning=f"Error: {str(e)}",
            relevant_policies=[]
        )


# API Endpoints
@app.post("/orchestrate_claim_processing", response_model=OrchestrateclaimProcessingResponse)
async def orchestrate_claim_processing(
    request: OrchestrateclaimProcessingRequest
) -> OrchestrateclaimProcessingResponse:
    """
    Orchestrate the complete claims processing workflow using LlamaStack intelligent orchestration.

    LlamaStack decides which tools to call, in what order, and when to stop.
    Guardrails are handled automatically by LlamaStack.

    MCP Tool: orchestrate_claim_processing
    """
    try:
        # Update claim status to processing
        await update_claim_status(request.claim_id, "processing")

        # Get claim type from database
        with SessionLocal() as session:
            claim_query = text("SELECT claim_type FROM claims WHERE id = :claim_id")
            result = session.execute(claim_query, {"claim_id": request.claim_id}).fetchone()
            claim_type = result[0] if result else "UNKNOWN"

        # Call intelligent orchestrator using direct LLM tool calling
        # The LLM will decide which agents to call and in what order!
        logger.info(f"Starting intelligent orchestration for claim {request.claim_id}")

        orchestration_result = await intelligent_orchestrate_with_llm(
            claim_id=request.claim_id,
            document_path=request.document_path,
            user_id=request.user_id,
            claim_type=claim_type
        )

        # Log all processing steps to database
        for step in orchestration_result.get("processing_steps", []):
            await log_processing_step(
                request.claim_id,
                step.get("step_name"),
                step.get("agent_name"),
                step.get("status"),
                step.get("duration_ms"),
                step.get("output_data", {}),
                step.get("error")
            )

        # Update claim status based on orchestration result
        final_status = orchestration_result.get("status", "failed")
        total_duration = orchestration_result.get("total_processing_time_ms", 0)
        await update_claim_status(request.claim_id, final_status, total_duration)

        logger.info(f"Intelligent orchestration completed for claim {request.claim_id} in {total_duration}ms")

        # Return response
        return OrchestrateclaimProcessingResponse(
            claim_id=request.claim_id,
            status=final_status,
            processing_steps=[ProcessingStepResult(**step) for step in orchestration_result.get("processing_steps", [])],
            ocr_results=None,  # Individual results are in processing_steps
            guardrails_results=None,  # Handled automatically by LlamaStack
            rag_results=None,  # Individual results are in processing_steps
            final_decision=FinalDecision(**orchestration_result["final_decision"]) if orchestration_result.get("final_decision") else None,
            total_processing_time_ms=total_duration,
            warnings=orchestration_result.get("warnings", [])
        )

    except Exception as e:
        logger.error(f"Intelligent orchestration failed for claim {request.claim_id}: {str(e)}")
        await update_claim_status(request.claim_id, "failed")
        raise HTTPException(status_code=500, detail=str(e))


# Keep the old static orchestration code commented for reference
"""
# OLD STATIC ORCHESTRATION CODE (REPLACED BY LLAMASTACK INTELLIGENT ORCHESTRATION)
async def old_static_orchestrate(request):
    # Step 1: OCR Processing
        if not config.skip_ocr:
            step_start = datetime.now()
            try:
                logger.info(f"Step 1: OCR processing for claim {request.claim_id}")
                ocr_results = await call_mcp_server(
                    OCR_SERVER_URL,
                    "ocr_document",
                    {
                        "document_path": request.document_path,
                        "document_type": "claim_form",
                        "language": "eng"
                    }
                )
                step_duration = int((datetime.now() - step_start).total_seconds() * 1000)

                processing_steps.append(ProcessingStepResult(
                    step_name="ocr",
                    agent="ocr-server",
                    status="completed",
                    duration_ms=step_duration,
                    output=ocr_results
                ))

                await log_processing_step(
                    request.claim_id, "ocr", "ocr-server",
                    "completed", step_duration, ocr_results
                )

            except Exception as e:
                logger.error(f"OCR step failed: {str(e)}")
                warnings.append(f"OCR failed: {str(e)}")
                processing_steps.append(ProcessingStepResult(
                    step_name="ocr",
                    agent="ocr-server",
                    status="failed",
                    duration_ms=0,
                    output={},
                    error=str(e)
                ))

        # Step 2: Guardrails Check
        if not config.skip_guardrails and ocr_results:
            step_start = datetime.now()
            try:
                logger.info(f"Step 2: Guardrails check for claim {request.claim_id}")

                # Extract text to check for sensitive data
                raw_text = ocr_results.get("raw_text", "")
                structured_data = ocr_results.get("structured_data", {})

                # Call guardrails server
                guardrails_results = await call_mcp_server(
                    GUARDRAILS_SERVER_URL,
                    "check_sensitive_data",
                    {
                        "text": raw_text[:5000],  # Limit text size
                        "structured_data": structured_data
                    },
                    timeout=30
                )

                step_duration = int((datetime.now() - step_start).total_seconds() * 1000)

                processing_steps.append(ProcessingStepResult(
                    step_name="guardrails",
                    agent="guardrails-server",
                    status="completed",
                    duration_ms=step_duration,
                    output=guardrails_results if guardrails_results else {"cleared": True, "has_pii": False}
                ))

                await log_processing_step(
                    request.claim_id, "guardrails", "guardrails-server",
                    "completed", step_duration, guardrails_results if guardrails_results else {}
                )

            except Exception as e:
                logger.error(f"Guardrails step failed: {str(e)}")
                warnings.append(f"Guardrails check failed: {str(e)}")
                # Add failed step to show in UI
                processing_steps.append(ProcessingStepResult(
                    step_name="guardrails",
                    agent="guardrails-server",
                    status="failed",
                    duration_ms=0,
                    output={},
                    error=str(e)
                ))

        # Step 3: RAG - Retrieve user info and similar claims
        if config.enable_rag:
            step_start = datetime.now()
            try:
                logger.info(f"Step 3: RAG retrieval for claim {request.claim_id}")

                # Get user info
                user_info_response = await call_mcp_server(
                    RAG_SERVER_URL,
                    "retrieve_user_info",
                    {
                        "user_id": request.user_id,
                        "query": "active insurance contracts and coverage",
                        "top_k": 5,
                        "include_contracts": True
                    },
                    timeout=60
                )

                # Get similar claims
                claim_text = ocr_results.get("raw_text", "") if ocr_results else ""
                similar_claims_response = await call_mcp_server(
                    RAG_SERVER_URL,
                    "retrieve_similar_claims",
                    {
                        "claim_text": claim_text[:1000],  # Limit text size
                        "top_k": 10,
                        "min_similarity": 0.7
                    },
                    timeout=60
                )

                rag_results = {
                    "user_info": user_info_response if user_info_response else {},
                    "similar_claims": similar_claims_response.get("similar_claims", []) if similar_claims_response else []
                }

                step_duration = int((datetime.now() - step_start).total_seconds() * 1000)

                processing_steps.append(ProcessingStepResult(
                    step_name="rag_retrieval",
                    agent="rag-server",
                    status="completed",
                    duration_ms=step_duration,
                    output=rag_results
                ))

                await log_processing_step(
                    request.claim_id, "rag_retrieval", "rag-server",
                    "completed", step_duration, rag_results
                )

            except Exception as e:
                logger.error(f"RAG step failed: {str(e)}")
                warnings.append(f"RAG retrieval failed: {str(e)}")
                rag_results = {"user_info": {}, "similar_claims": []}

        # Step 4: Final Decision with LLM
        if ocr_results and rag_results:
            step_start = datetime.now()
            try:
                logger.info(f"Step 4: Final decision for claim {request.claim_id}")

                user_contracts = rag_results.get("user_info", {}).get("contracts", [])
                final_decision = await make_final_decision(
                    claim_id=request.claim_id,
                    user_id=request.user_id,
                    ocr_results=ocr_results,
                    rag_results=rag_results,
                    user_contracts=user_contracts
                )

                step_duration = int((datetime.now() - step_start).total_seconds() * 1000)

                processing_steps.append(ProcessingStepResult(
                    step_name="llm_decision",
                    agent="llamastack",
                    status="completed",
                    duration_ms=step_duration,
                    output=final_decision.dict()
                ))

                await log_processing_step(
                    request.claim_id, "llm_decision", "llamastack",
                    "completed", step_duration, final_decision.dict()
                )

            except Exception as e:
                logger.error(f"Final decision step failed: {str(e)}")
                warnings.append(f"Final decision failed: {str(e)}")
                final_decision = FinalDecision(
                    recommendation="manual_review",
                    confidence=0.0,
                    reasoning=f"Error: {str(e)}",
                    relevant_policies=[]
                )

        # Calculate total processing time
        total_duration = int((datetime.now() - start_time).total_seconds() * 1000)

        # Update claim status
        final_status = "completed" if final_decision else "failed"
        await update_claim_status(request.claim_id, final_status, total_duration)

        logger.info(f"Completed processing claim {request.claim_id} in {total_duration}ms")

        return OrchestrateclaimProcessingResponse(
            claim_id=request.claim_id,
            status=final_status,
            processing_steps=processing_steps,
            ocr_results=ocr_results,
            guardrails_results=guardrails_results,
            rag_results=rag_results,
            final_decision=final_decision,
            total_processing_time_ms=total_duration,
            warnings=warnings
        )

    except Exception as e:
        logger.error(f"Orchestration failed for claim {request.claim_id}: {str(e)}")
        await update_claim_status(request.claim_id, "failed")
        raise HTTPException(status_code=500, detail=str(e))
"""


@app.post("/get_processing_status", response_model=GetProcessingStatusResponse)
async def get_processing_status(request: GetProcessingStatusRequest) -> GetProcessingStatusResponse:
    """
    Get the current status of claim processing.

    MCP Tool: get_processing_status
    """
    try:
        with SessionLocal() as session:
            # Get claim status
            claim_query = text("""
                SELECT status, created_at FROM claims WHERE id = :claim_id
            """)
            claim = session.execute(claim_query, {"claim_id": request.claim_id}).fetchone()

            if not claim:
                raise HTTPException(status_code=404, detail="Claim not found")

            # Get latest processing step
            step_query = text("""
                SELECT step, status
                FROM processing_logs
                WHERE claim_id = :claim_id
                ORDER BY created_at DESC
                LIMIT 1
            """)
            latest_step = session.execute(step_query, {"claim_id": request.claim_id}).fetchone()

            current_step = latest_step.step if latest_step else "pending"
            step_status = latest_step.status if latest_step else "pending"

            # Calculate progress
            step_order = {"pending": 0, "ocr": 25, "guardrails": 50, "rag_retrieval": 75, "llm_decision": 100}
            progress = step_order.get(current_step, 0)

            return GetProcessingStatusResponse(
                claim_id=request.claim_id,
                status=claim.status,
                current_step=current_step,
                progress_percentage=progress,
                estimated_completion_time=None
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting processing status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/live", response_model=HealthResponse)
async def liveness():
    """Liveness probe."""
    return HealthResponse(status="alive", service="mcp-orchestrator-server")


@app.get("/health/ready", response_model=HealthResponse)
async def readiness():
    """Readiness probe."""
    try:
        # Check database connection
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))

        return HealthResponse(status="ready", service="mcp-orchestrator-server")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Not ready: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "MCP Orchestrator Server",
        "version": "1.0.0",
        "status": "running",
        "tools": ["orchestrate_claim_processing", "get_processing_status"]
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
