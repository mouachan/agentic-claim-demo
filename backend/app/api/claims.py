"""
Claims API endpoints.

Endpoints:
- GET    /                        - List claims with pagination
- GET    /{claim_id}              - Get a specific claim
- POST   /                        - Create a new claim
- POST   /{claim_id}/process      - Process a claim with LlamaStack agent
- GET    /{claim_id}/status       - Get claim processing status
- GET    /{claim_id}/decision     - Get claim decision
- GET    /{claim_id}/logs         - Get processing logs
- GET    /statistics/overview     - Get claims statistics
- GET    /documents/{claim_id}/view - View claim document
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from llama_stack_client import AsyncLlamaStackClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api import schemas
from app.core.config import settings
from app.core.database import get_db
from app.models import claim as models
from app.llamastack.prompts import (
    CLAIMS_PROCESSING_AGENT_INSTRUCTIONS,
    USER_MESSAGE_OCR_ONLY_TEMPLATE,
    USER_MESSAGE_FULL_WORKFLOW_TEMPLATE,
    AGENT_CONFIG,
    format_prompt
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants
LLAMASTACK_TIMEOUT = 300.0  # 5 minutes for agent operations

# Tool to agent mapping (hardcoded for now)
# TODO: Make this configurable via ConfigMap
TOOL_AGENT_MAPPING = {
    "ocr_extract_claim_info": "ocr-agent",
    "ocr_document": "ocr-agent",
    "retrieve_user_info": "rag-agent",
    "retrieve_similar_claims": "rag-agent",
    "search_knowledge_base": "rag-agent",
}


# =============================================================================
# Utility Functions
# =============================================================================

def extract_json_from_text(text: str) -> Optional[dict]:
    """Extract JSON object from text that may contain other content."""
    if not text:
        return None
    
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON object in text using regex
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(json_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    
    # Try to find JSON between code blocks
    code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    code_matches = re.findall(code_block_pattern, text, re.DOTALL)
    
    for match in code_matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    
    return None


def parse_agent_decision(response_text: str) -> dict:
    """Parse agent response to extract decision data."""
    json_data = extract_json_from_text(response_text)
    
    if json_data:
        return {
            "recommendation": json_data.get("recommendation", json_data.get("decision", "manual_review")),
            "confidence": float(json_data.get("confidence", json_data.get("confidence_score", 0.5))),
            "reasoning": json_data.get("reasoning", json_data.get("explanation", response_text)),
            "relevant_policies": json_data.get("relevant_policies", json_data.get("policies", [])),
            "estimated_coverage_amount": json_data.get("estimated_coverage_amount", json_data.get("coverage", None))
        }
    
    # Fallback: infer decision from text
    response_lower = response_text.lower()
    
    if "approve" in response_lower or "approved" in response_lower:
        recommendation = "approve"
        confidence = 0.6
    elif "deny" in response_lower or "denied" in response_lower or "reject" in response_lower:
        recommendation = "deny"
        confidence = 0.6
    else:
        recommendation = "manual_review"
        confidence = 0.5
    
    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "reasoning": response_text,
        "relevant_policies": [],
        "estimated_coverage_amount": None
    }


async def create_llamastack_client() -> AsyncLlamaStackClient:
    """Create configured LlamaStack async client."""
    return AsyncLlamaStackClient(
        base_url=settings.llamastack_endpoint,
        timeout=LLAMASTACK_TIMEOUT
    )


# =============================================================================
# GET / - List Claims
# =============================================================================

@router.get("/", response_model=schemas.ClaimListResponse)
async def list_claims(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db)
):
    """List claims with pagination and optional filtering."""
    try:
        query = select(models.Claim)

        if status:
            query = query.where(models.Claim.status == status)
        if user_id:
            query = query.where(models.Claim.user_id == user_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and ordering
        offset = (page - 1) * page_size
        query = (
            query
            .order_by(models.Claim.submitted_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        result = await db.execute(query)
        claims = result.scalars().all()

        return schemas.ClaimListResponse(
            claims=[schemas.ClaimResponse.model_validate(c) for c in claims],
            total=total,
            page=page,
            page_size=page_size
        )

    except Exception as e:
        logger.error(f"Error listing claims: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GET /{claim_id} - Get Claim
# =============================================================================

@router.get("/{claim_id}", response_model=schemas.ClaimResponse)
async def get_claim(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific claim by ID."""
    try:
        query = select(models.Claim).where(models.Claim.id == claim_id)
        result = await db.execute(query)
        claim = result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        return schemas.ClaimResponse.model_validate(claim)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting claim: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# POST / - Create Claim
# =============================================================================

@router.post("/", response_model=schemas.ClaimResponse, status_code=201)
async def create_claim(
    claim_data: schemas.ClaimCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new claim."""
    try:
        new_claim = models.Claim(**claim_data.model_dump())
        db.add(new_claim)
        await db.commit()
        await db.refresh(new_claim)

        logger.info(f"Created new claim: {new_claim.id}")
        return schemas.ClaimResponse.model_validate(new_claim)

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating claim: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# POST /{claim_id}/process - Process Claim with LlamaStack Agent
# =============================================================================

@router.post("/{claim_id}/process", response_model=schemas.ProcessClaimResponse)
async def process_claim(
    claim_id: UUID,
    process_request: schemas.ProcessClaimRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Process a claim using LlamaStack Responses API.

    The agent will:
    1. Extract document info via OCR
    2. Retrieve user contracts via RAG
    3. Find similar historical claims
    4. Make a decision (approve/deny/manual_review)
    """
    response_id = None
    start_time = time.time()

    try:
        # Step 1: Get and validate claim
        query = select(models.Claim).where(models.Claim.id == claim_id)
        result = await db.execute(query)
        claim = result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        if claim.status == models.ClaimStatus.processing:
            raise HTTPException(status_code=409, detail="Claim is already being processed")

        # Update status to processing
        claim.status = models.ClaimStatus.processing
        await db.commit()

        # Store claim data for agent message
        claim_user_id = claim.user_id
        claim_document_path = claim.document_path
        claim_type = getattr(claim, 'claim_type', 'general')
        claim_submitted_at = claim.submitted_at

        # Step 2: Prepare tools for Responses API
        try:
            tools = []
            if not process_request.skip_ocr:
                tools.append({
                    "type": "mcp",
                    "server_url": "http://ocr-server-service.claims-demo.svc.cluster.local:3001",
                    "server_label": "ocr-server"
                })
            if process_request.enable_rag:
                tools.append({
                    "type": "mcp",
                    "server_url": "http://rag-server-service.claims-demo.svc.cluster.local:3002",
                    "server_label": "rag-server"
                })

            async with httpx.AsyncClient(timeout=60.0) as http_client:
                logger.info(f"Processing claim {claim_id} using Responses API...")
                logger.info(f"Agent config loaded: {AGENT_CONFIG}")
                logger.info(f"Tools: {tools}")
                logger.info(f"=== AGENT INSTRUCTIONS (FULL) ===\n{CLAIMS_PROCESSING_AGENT_INSTRUCTIONS}\n=== END INSTRUCTIONS ===")

                # Step 3: Execute agent - Load user message from template
                if not process_request.enable_rag and not process_request.skip_ocr:
                    # OCR-only mode
                    user_message = format_prompt(
                        USER_MESSAGE_OCR_ONLY_TEMPLATE,
                        document_path=claim_document_path
                    )
                else:
                    # Full workflow mode
                    user_message = format_prompt(
                        USER_MESSAGE_FULL_WORKFLOW_TEMPLATE,
                        claim_id=claim_id,
                        user_id=claim_user_id,
                        document_path=claim_document_path,
                        claim_type=claim_type,
                        skip_ocr=process_request.skip_ocr,
                        enable_rag=process_request.enable_rag
                    )

                logger.info(f"=== USER MESSAGE ===\n{user_message}\n=== END USER MESSAGE ===")
                logger.info("Starting Responses API execution...")
                final_response = ""
                tool_execution_count = 0
                processing_steps = []

                # Execute using Responses API with streaming
                async with http_client.stream(
                    "POST",
                    f"{settings.llamastack_endpoint}/v1/responses",
                    json={
                        "model": settings.llamastack_default_model,
                        "input": user_message,
                        "instructions": CLAIMS_PROCESSING_AGENT_INSTRUCTIONS,
                        "tools": tools,
                        "stream": True
                    },
                    timeout=180.0
                ) as response:
                    if response.status_code != 200:
                        raise ValueError(f"Failed to execute turn: {response.text}")

                    async for line in response.aiter_lines():
                        if not line.strip() or not line.startswith("data: "):
                            continue

                        data = line[6:]  # Remove "data: " prefix
                        try:
                            event = json.loads(data)
                            if not isinstance(event, dict):
                                continue

                            # Capture response_id if present
                            if "id" in event and not response_id:
                                response_id = event["id"]
                                logger.info(f"Captured response_id: {response_id}")
                                # Save response_id immediately for tracking
                                if not claim.claim_metadata:
                                    claim.claim_metadata = {}
                                claim.claim_metadata["llamastack_response_id"] = response_id
                                claim.claim_metadata["processing_steps"] = []
                                flag_modified(claim, "claim_metadata")
                                await db.commit()

                            # Parse SSE event payload
                            if "event" not in event:
                                continue

                            payload = event["event"].get("payload", {})
                            step_type = payload.get("step_type")
                            event_type = payload.get("event_type")

                            # Debug: log all events
                            logger.info(f"SSE Event - step_type: {step_type}, event_type: {event_type}")

                            # Track tool executions
                            if step_type == "tool_execution":
                                if event_type == "step_start":
                                    tool_execution_count += 1
                                    # Log entire payload to find tool name
                                    logger.info(f"Tool execution #{tool_execution_count} - step_start payload keys: {payload.keys()}")

                                    # Try multiple places where tool name might be
                                    tool_name = None
                                    step_details = payload.get("step_details", {})
                                    tool_calls = step_details.get("tool_calls", [])

                                    if tool_calls and len(tool_calls) > 0:
                                        tool_name = tool_calls[0].get("tool_name")

                                    # Also check top-level payload
                                    if not tool_name and "tool_name" in payload:
                                        tool_name = payload.get("tool_name")

                                    if tool_name:
                                        logger.info(f"Tool execution #{tool_execution_count} started: {tool_name}")
                                    else:
                                        logger.info(f"Tool execution #{tool_execution_count} started (name not yet available)")
                                elif event_type == "step_complete":
                                    step_details = payload.get("step_details", {})
                                    tool_calls = step_details.get("tool_calls", [])
                                    tool_responses = step_details.get("tool_responses", [])

                                    # Save each completed step in real-time
                                    for tool_call in tool_calls:
                                        tool_name = tool_call.get('tool_name')
                                        logger.info(f"  Tool completed: {tool_name}")

                                        # Add step to metadata for real-time tracking
                                        step_record = {
                                            "tool_name": tool_name,
                                            "completed_at": datetime.now(timezone.utc).isoformat()
                                        }

                                        if not claim.claim_metadata:
                                            claim.claim_metadata = {}
                                        if "processing_steps" not in claim.claim_metadata:
                                            claim.claim_metadata["processing_steps"] = []

                                        claim.claim_metadata["processing_steps"].append(step_record)
                                        flag_modified(claim, "claim_metadata")
                                        await db.commit()
                                        logger.info(f"Saved step to DB: {tool_name}")

                                    for tool_response in tool_responses:
                                        content = tool_response.get("content", "")
                                        # Truncate long responses for logging
                                        content_preview = content[:500] if len(content) > 500 else content
                                        logger.info(f"  Tool response: {content_preview}")

                            # Collect inference text (streaming)
                            elif step_type == "inference":
                                if event_type == "step_progress":
                                    delta = payload.get("delta", {})
                                    if delta.get("type") == "text":
                                        text_chunk = delta.get("text", "")
                                        final_response += text_chunk
                                elif event_type == "step_complete":
                                    step_details = payload.get("step_details", {})
                                    # Extract text from model_response
                                    model_response = step_details.get("model_response", {})
                                    if isinstance(model_response, dict):
                                        content = model_response.get("content", "")
                                        if content:
                                            logger.info(f"Got model_response content: {len(str(content))} chars")
                                            final_response += str(content)
                                    # Also try legacy 'text' field for compatibility
                                    text_chunk = step_details.get("text", "")
                                    if text_chunk:
                                        logger.info(f"Got text from step_complete: {len(text_chunk)} chars")
                                        final_response += text_chunk

                            # Get final response from turn_complete (according to LlamaStack docs)
                            elif event_type == "turn_complete":
                                turn_data = payload.get("turn", {})
                                output_message = turn_data.get("output_message", {})
                                content = output_message.get("content", "")
                                if content and not final_response:
                                    # Use turn_complete content if we didn't get it from streaming
                                    final_response = str(content)
                                    logger.info(f"Got response from turn_complete: {len(final_response)} chars")

                        except json.JSONDecodeError:
                            continue

                logger.info(f"Agent completed. Tools used: {tool_execution_count}, Response: {len(final_response)} chars")

                # Step 4: Parse response and update claim
                if not final_response.strip():
                    logger.warning("Empty response from agent")
                    decision_data = {
                        "recommendation": "manual_review",
                        "confidence": 0.0,
                        "reasoning": "Agent returned empty response"
                    }
                else:
                    decision_data = parse_agent_decision(final_response)

                processing_time_ms = int((time.time() - start_time) * 1000)

                await db.refresh(claim)

                # Store final metadata
                if not claim.claim_metadata:
                    claim.claim_metadata = {}
                claim.claim_metadata["llamastack_response_id"] = response_id
                claim.claim_metadata["tool_execution_count"] = tool_execution_count
                flag_modified(claim, "claim_metadata")

                # Update status
                recommendation = decision_data.get("recommendation", "manual_review")
                if recommendation == "approve":
                    claim.status = models.ClaimStatus.completed
                elif recommendation == "deny":
                    claim.status = models.ClaimStatus.failed
                else:
                    claim.status = models.ClaimStatus.manual_review

                claim.total_processing_time_ms = processing_time_ms
                claim.processed_at = datetime.now(timezone.utc)

                # Create decision record
                decision = models.ClaimDecision(
                    claim_id=claim_id,
                    decision=recommendation,
                    confidence=decision_data.get("confidence", 0.0),
                    reasoning=decision_data.get("reasoning", ""),
                    relevant_policies={
                        "policies": decision_data.get("relevant_policies", []),
                        "estimated_coverage": decision_data.get("estimated_coverage_amount")
                    },
                    llm_model=settings.llamastack_default_model,
                    requires_manual_review=(recommendation == "manual_review")
                )
                db.add(decision)
                await db.commit()

                logger.info(f"Claim {claim_id} processed: {recommendation}")

                return schemas.ProcessClaimResponse(
                    claim_id=claim_id,
                    status=claim.status.value,
                    message=f"Processing completed: {recommendation}",
                    processing_started_at=claim_submitted_at
                )

        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to LlamaStack: {e}")
            claim.status = models.ClaimStatus.failed
            await db.commit()
            raise HTTPException(status_code=503, detail=f"Cannot connect to LlamaStack: {str(e)}")
        except httpx.TimeoutException as e:
            logger.error(f"LlamaStack request timed out: {e}")
            raise HTTPException(status_code=504, detail="Agent processing timed out")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing claim {claim_id}: {str(e)}", exc_info=True)
        try:
            await db.rollback()
            result = await db.execute(select(models.Claim).where(models.Claim.id == claim_id))
            claim = result.scalar_one_or_none()
            if claim:
                claim.status = models.ClaimStatus.failed
                await db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update claim status: {db_error}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GET /{claim_id}/status - Get Claim Status
# =============================================================================

@router.get("/{claim_id}/status", response_model=schemas.ClaimStatusResponse)
async def get_claim_status(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get the current processing status of a claim."""
    try:
        claim_query = select(models.Claim).where(models.Claim.id == claim_id)
        claim_result = await db.execute(claim_query)
        claim = claim_result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        # Read processing steps from claim metadata (saved in real-time during processing)
        processing_steps = []
        current_step = None
        progress = 0.0

        if claim.claim_metadata and "processing_steps" in claim.claim_metadata:
            steps_data = claim.claim_metadata["processing_steps"]
            for step_data in steps_data:
                tool_name = step_data.get("tool_name", "unknown")

                # Map to agent names using configurable mapping
                agent_name = TOOL_AGENT_MAPPING.get(tool_name, "unknown")

                processing_steps.append(schemas.ProcessingStepLog(
                    step_name=tool_name,
                    agent_name=agent_name,
                    status="completed",
                    duration_ms=0,
                    started_at=None,
                    completed_at=step_data.get("completed_at"),
                    output_data=None,
                    error_message=None
                ))

        # Determine progress - Check claim status first
        if claim.status in [models.ClaimStatus.completed, models.ClaimStatus.failed, models.ClaimStatus.manual_review]:
            progress = 100.0
        elif processing_steps:
            current_step = processing_steps[-1].step_name
            # Map tool names to progress percentages
            step_progress = {
                "ocr_extract_claim_info": 25,
                "retrieve_user_info": 50,
                "search_knowledge_base": 75,
                "retrieve_similar_claims": 75,
            }
            progress = step_progress.get(current_step, 50)
        else:
            progress = 0.0

        return schemas.ClaimStatusResponse(
            claim_id=claim_id,
            status=claim.status,
            current_step=current_step,
            progress_percentage=progress,
            processing_steps=processing_steps,
            estimated_completion_time=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting claim status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GET /{claim_id}/decision - Get Claim Decision
# =============================================================================

@router.get("/{claim_id}/decision", response_model=schemas.ClaimDecisionResponse)
async def get_claim_decision(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get the decision details for a processed claim."""
    try:
        query = (
            select(models.ClaimDecision)
            .where(models.ClaimDecision.claim_id == claim_id)
            .order_by(models.ClaimDecision.created_at.desc())
        )
        result = await db.execute(query)
        decision = result.scalar_one_or_none()

        if not decision:
            raise HTTPException(status_code=404, detail="No decision found for this claim")

        return schemas.ClaimDecisionResponse(
            id=decision.id,
            claim_id=decision.claim_id,
            decision=decision.decision,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
            relevant_policies=decision.relevant_policies,
            similar_claims=decision.similar_claims,
            user_contract_info=decision.user_contract_info,
            llm_model=decision.llm_model,
            requires_manual_review=decision.requires_manual_review,
            decided_at=decision.created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting claim decision: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GET /{claim_id}/logs - Get Claim Logs
# =============================================================================

@router.get("/{claim_id}/logs", response_model=schemas.ClaimLogsResponse)
async def get_claim_logs(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get processing logs for a claim from LlamaStack session history."""
    try:
        # Get claim to check metadata
        claim_query = select(models.Claim).where(models.Claim.id == claim_id)
        claim_result = await db.execute(claim_query)
        claim = claim_result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        processing_logs = []

        # Get agent_id and session_id from claim metadata
        agent_id = claim.claim_metadata.get("llamastack_agent_id") if claim.claim_metadata else None
        session_id = claim.claim_metadata.get("llamastack_session_id") if claim.claim_metadata else None

        # Fetch LlamaStack session history if available
        if agent_id and session_id:
            try:
                async with httpx.AsyncClient(timeout=30.0) as http_client:
                    response = await http_client.get(
                        f"{settings.llamastack_endpoint}/v1/agents/{agent_id}/session/{session_id}"
                    )

                    if response.status_code == 200:
                        session_data = response.json()
                        turns = session_data.get("turns", [])

                        for turn in turns:
                            steps = turn.get("steps", [])
                            for step in steps:
                                step_type = step.get("step_type")

                                # Only extract tool_execution steps (skip inference steps)
                                if step_type == "tool_execution":
                                    # LlamaStack puts tool data directly in step
                                    tool_calls = step.get("tool_calls", [])
                                    tool_responses = step.get("tool_responses", [])

                                    for i, tool_call in enumerate(tool_calls):
                                        tool_name = tool_call.get("tool_name", "unknown")

                                        # Keep exact tool names for better frontend display
                                        step_name = tool_name

                                        # Map to agent names using configurable mapping
                                        agent_name = TOOL_AGENT_MAPPING.get(tool_name, "unknown")

                                        # Get output data from tool_responses
                                        output_data = None
                                        if i < len(tool_responses):
                                            tool_resp = tool_responses[i]
                                            if isinstance(tool_resp, dict):
                                                # Content is in tool_resp.content which is a list
                                                content_list = tool_resp.get("content", [])
                                                if content_list and len(content_list) > 0:
                                                    # Extract text from first content item
                                                    first_content = content_list[0]
                                                    if isinstance(first_content, dict) and "text" in first_content:
                                                        text_content = first_content["text"]
                                                        # Try to parse as JSON
                                                        try:
                                                            output_data = json.loads(text_content)
                                                        except:
                                                            output_data = {"raw_text": text_content}
                                                    else:
                                                        output_data = first_content
                                            else:
                                                output_data = str(tool_resp)

                                        processing_logs.append(schemas.ProcessingStepLog(
                                            step_name=step_name,
                                            agent_name=agent_name,
                                            status="completed",
                                            duration_ms=0,
                                            started_at=step.get("started_at"),
                                            completed_at=step.get("completed_at"),
                                            output_data=output_data,
                                            error_message=None
                                        ))

            except Exception as e:
                logger.warning(f"Could not fetch LlamaStack session history: {str(e)}")

        return schemas.ClaimLogsResponse(
            claim_id=claim_id,
            logs=processing_logs
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting claim logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GET /statistics/overview - Get Claims Statistics
# =============================================================================

@router.get("/statistics/overview", response_model=schemas.ClaimStatistics)
async def get_claim_statistics(db: AsyncSession = Depends(get_db)):
    """Get overall claims statistics."""
    try:
        status_counts = {}
        status_values = ["pending", "processing", "completed", "failed", "manual_review"]
        
        for status_value in status_values:
            query = select(func.count()).where(models.Claim.status == status_value)
            result = await db.execute(query)
            status_counts[status_value] = result.scalar() or 0

        avg_query = select(func.avg(models.Claim.total_processing_time_ms)).where(
            models.Claim.total_processing_time_ms.isnot(None)
        )
        avg_result = await db.execute(avg_query)
        avg_processing_time = avg_result.scalar()

        return schemas.ClaimStatistics(
            total_claims=sum(status_counts.values()),
            pending_claims=status_counts.get("pending", 0),
            processing_claims=status_counts.get("processing", 0),
            completed_claims=status_counts.get("completed", 0),
            failed_claims=status_counts.get("failed", 0),
            manual_review_claims=status_counts.get("manual_review", 0),
            average_processing_time_ms=avg_processing_time
        )

    except Exception as e:
        logger.error(f"Error getting statistics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GET /documents/{claim_id}/view - View Claim Document
# =============================================================================

@router.get("/documents/{claim_id}/view")
async def view_claim_document(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """View claim document PDF."""
    try:
        result = await db.execute(
            select(models.Claim).where(models.Claim.id == claim_id)
        )
        claim = result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        if not claim.document_path:
            raise HTTPException(status_code=404, detail="No document associated with this claim")

        if not os.path.exists(claim.document_path):
            raise HTTPException(status_code=404, detail="Document file not found")

        return FileResponse(
            claim.document_path,
            media_type="application/pdf",
            filename=os.path.basename(claim.document_path)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing document: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))