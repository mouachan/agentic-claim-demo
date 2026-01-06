"""
Claims API endpoints.
"""

import httpx
import json
import logging
import time
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api import schemas
from app.core.config import settings
from app.core.database import get_db
from app.models import claim as models

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=schemas.ClaimListResponse)
async def list_claims(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db)
):
    """
    List claims with pagination and optional filtering.
    """
    try:
        # Build query
        query = select(models.Claim)

        # Apply filters
        if status:
            # Use string directly, SQLAlchemy will handle enum conversion
            query = query.where(models.Claim.status == status)
        if user_id:
            query = query.where(models.Claim.user_id == user_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # Order by submission date
        query = query.order_by(models.Claim.submitted_at.desc())

        # Execute query
        result = await db.execute(query)
        claims = result.scalars().all()

        return schemas.ClaimListResponse(
            claims=[schemas.ClaimResponse.model_validate(c) for c in claims],
            total=total,
            page=page,
            page_size=page_size
        )

    except Exception as e:
        logger.error(f"Error listing claims: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{claim_id}", response_model=schemas.ClaimResponse)
async def get_claim(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific claim by ID.
    """
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
        logger.error(f"Error getting claim: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=schemas.ClaimResponse, status_code=201)
async def create_claim(
    claim_data: schemas.ClaimCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new claim.
    """
    try:
        new_claim = models.Claim(**claim_data.model_dump())
        db.add(new_claim)
        await db.commit()
        await db.refresh(new_claim)

        logger.info(f"Created new claim: {new_claim.id}")
        return schemas.ClaimResponse.model_validate(new_claim)

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating claim: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{claim_id}/process", response_model=schemas.ProcessClaimResponse)
async def process_claim(
    claim_id: UUID,
    process_request: schemas.ProcessClaimRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Start processing a claim using LlamaStack ReActAgent SDK.

    The ReActAgent uses a Thought-Action-Observation loop to:
    - Reason about the next step (Thought)
    - Execute a tool if necessary (Action)
    - Observe the result (Observation)
    - Repeat until reaching the final answer

    This version uses the llama-stack-client SDK with:
    - LlamaStackClient
    - Agent.create() with AgentConfig
    - EventLogger for event logging

    Note: For the HTTP Response API version (without SDK),
    see branch 'http-response-api'
    """
    import time
    import json
    import httpx
    from app.llamastack.prompts import CLAIMS_PROCESSING_AGENT_INSTRUCTIONS

    try:
        # Get the claim
        query = select(models.Claim).where(models.Claim.id == claim_id)
        result = await db.execute(query)
        claim = result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        # Update status to processing
        claim.status = models.ClaimStatus.processing
        await db.commit()

        # Track processing start time
        start_time = time.time()

        try:
            # Build MCP toolgroups list
            # Format: Array of toolgroup IDs (e.g., "mcp::rag-server")
            # These must match the toolgroups registered in LlamaStack config
            toolgroups = []
            if not process_request.skip_ocr:
                toolgroups.append("mcp::ocr-server")
            if process_request.enable_rag:
                toolgroups.append("mcp::rag-server")

            # Create Agent using HTTP API directly (v0.3.5+rhai0 format)
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Create agent
                agent_response = await client.post(
                    f"{settings.llamastack_endpoint}/v1/agents",
                    json={
                        "agent_config": {
                            "model": settings.llamastack_default_model,
                            "instructions": CLAIMS_PROCESSING_AGENT_INSTRUCTIONS,
                            "enable_session_persistence": True,
                            "toolgroups": toolgroups,
                            "tool_config": {
                                "tool_choice": "auto",
                                "tool_prompt_format": "json"
                            },
                            "max_infer_iters": 5,  # Reduced from 10 for faster processing
                            "sampling_params": {
                                "strategy": {"type": "greedy"},
                                "max_tokens": 1024  # Reduced from 2048 for faster generation
                            }
                        }
                    }
                )

                if agent_response.status_code != 200:
                    raise ValueError(f"Failed to create agent: {agent_response.text}")

                agent_id = agent_response.json()["agent_id"]
                logger.info(f"Created agent: {agent_id}")

                # Create session
                session_response = await client.post(
                    f"{settings.llamastack_endpoint}/v1/agents/{agent_id}/session",
                    json={"session_name": f"claim_{claim_id}"}
                )

                if session_response.status_code != 200:
                    raise ValueError(f"Failed to create session: {session_response.text}")

                session_id = session_response.json()["session_id"]
                logger.info(f"Created session: {session_id}")

                # Prepare user message
                user_message = f"""
Process this insurance claim:

Claim ID: {claim_id}
User ID: {claim.user_id}
Document Path: {claim.document_path}
Claim Type: {claim.claim_type if hasattr(claim, 'claim_type') else 'general'}

Please:
1. Extract all information from the document using OCR
2. Retrieve the user's insurance contracts and coverage details
3. Find similar historical claims for precedent
4. Determine if the claim should be approved, denied, or requires manual review
5. Provide detailed reasoning citing relevant policy sections

Workflow configuration:
- Skip OCR: {process_request.skip_ocr}
- Enable RAG retrieval: {process_request.enable_rag}
"""

                # Execute agent turn (streaming mode)
                logger.info("Starting agent execution...")

                final_response = ""
                tool_execution_count = 0

                async with client.stream(
                    "POST",
                    f"{settings.llamastack_endpoint}/v1/agents/{agent_id}/session/{session_id}/turn",
                    json={
                        "messages": [
                            {"role": "user", "content": user_message}
                        ],
                        "stream": True
                    },
                    timeout=180.0  # Increased from 120s to allow for complex processing
                ) as response:
                    if response.status_code != 200:
                        raise ValueError(f"Failed to execute turn: {response.text}")

                    async for line in response.aiter_lines():
                        if not line.strip() or not line.startswith("data: "):
                            continue

                        data = line[6:]  # Remove "data: " prefix
                        try:
                            event = json.loads(data)
                            if isinstance(event, dict) and "event" in event:
                                payload = event["event"].get("payload", {})
                                event_type = payload.get("event_type")
                                step_type = payload.get("step_type")

                                # Log tool execution for monitoring
                                if step_type == "tool_execution" and event_type == "step_complete":
                                    tool_execution_count += 1
                                    step_details = payload.get("step_details", {})
                                    tool_calls = step_details.get("tool_calls", [])
                                    logger.info(f"Tool execution #{tool_execution_count}: {len(tool_calls)} tool(s)")

                                # Collect final inference output
                                elif step_type == "inference" and event_type == "step_progress":
                                    delta = payload.get("delta", {})
                                    if delta.get("type") == "text":
                                        final_response += delta.get("text", "")

                        except json.JSONDecodeError:
                            pass

                logger.info(f"Agent execution completed. Tool executions: {tool_execution_count}")

                if not final_response.strip():
                    final_response = "The claim has been processed. Recommendation: manual_review"

            # Parse the agent's decision
            try:
                decision_data = json.loads(final_response) if "{" in final_response else {
                    "recommendation": "manual_review",
                    "confidence": 0.5,
                    "reasoning": final_response
                }
            except json.JSONDecodeError:
                logger.warning("Could not parse agent response as JSON, using fallback")
                decision_data = {
                    "recommendation": "manual_review",
                    "confidence": 0.5,
                    "reasoning": final_response
                }

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Store LlamaStack agent_id and session_id in claim metadata for later retrieval
            if not claim.claim_metadata:
                claim.claim_metadata = {}
            claim.claim_metadata["llamastack_agent_id"] = agent_id
            claim.claim_metadata["llamastack_session_id"] = session_id
            flag_modified(claim, "claim_metadata")  # Mark JSON field as modified for SQLAlchemy

            # Update claim based on recommendation
            recommendation = decision_data.get("recommendation", "manual_review")
            if recommendation == "approve":
                claim.status = models.ClaimStatus.completed
            elif recommendation == "deny":
                claim.status = models.ClaimStatus.failed
            else:  # manual_review
                claim.status = models.ClaimStatus.manual_review

            claim.total_processing_time_ms = processing_time_ms
            claim.processed_at = datetime.utcnow()

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

            logger.info(f"Claim {claim_id} processed via ReActAgent SDK: {recommendation}")
            return schemas.ProcessClaimResponse(
                claim_id=claim_id,
                status=claim.status.value,
                message=f"Processing completed: {recommendation}",
                processing_started_at=claim.submitted_at
            )

        except httpx.HTTPError as e:
            claim.status = models.ClaimStatus.failed
            await db.commit()
            logger.error(f"LlamaStack HTTP error: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to LlamaStack server: {str(e)}"
            )
        except ValueError as e:
            claim.status = models.ClaimStatus.failed
            await db.commit()
            logger.error(f"LlamaStack API error: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"LlamaStack API error: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error processing claim: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{claim_id}/status", response_model=schemas.ClaimStatusResponse)
async def get_claim_status(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current processing status of a claim using LlamaStack traceability.
    """
    try:
        # Get claim
        claim_query = select(models.Claim).where(models.Claim.id == claim_id)
        claim_result = await db.execute(claim_query)
        claim = claim_result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        # Get LlamaStack agent/session IDs from claim metadata
        agent_id = claim.claim_metadata.get("llamastack_agent_id") if claim.claim_metadata else None
        session_id = claim.claim_metadata.get("llamastack_session_id") if claim.claim_metadata else None

        processing_steps = []
        current_step = None
        progress = 0.0

        # If we have agent and session IDs, fetch history from LlamaStack
        if agent_id and session_id:
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    # Get session history from LlamaStack
                    response = await client.get(
                        f"{settings.llamastack_endpoint}/v1/agents/{agent_id}/session/{session_id}"
                    )

                    if response.status_code == 200:
                        session_data = response.json()
                        turns = session_data.get("turns", [])

                        # Parse turns to extract processing steps
                        for turn in turns:
                            steps = turn.get("steps", [])
                            for step in steps:
                                step_type = step.get("step_type")

                                if step_type == "tool_execution":
                                    # Extract tool execution details
                                    step_details = step.get("step_details", {})
                                    tool_calls = step_details.get("tool_calls", [])
                                    tool_responses = step_details.get("tool_responses", [])

                                    for i, tool_call in enumerate(tool_calls):
                                        tool_name = tool_call.get("tool_name", "unknown")

                                        # Map tool name to step
                                        step_name = "unknown"
                                        agent_name = "unknown"
                                        if "ocr" in tool_name.lower():
                                            step_name = "ocr"
                                            agent_name = "ocr-agent"
                                        elif "retrieve" in tool_name.lower() or "search" in tool_name.lower():
                                            step_name = "rag_retrieval"
                                            agent_name = "rag-agent"

                                        # Get corresponding response
                                        output_data = None
                                        if i < len(tool_responses):
                                            tool_resp = tool_responses[i]
                                            output_data = tool_resp.get("content") if isinstance(tool_resp, dict) else tool_resp

                                        processing_steps.append(schemas.ProcessingStepLog(
                                            step_name=step_name,
                                            agent_name=agent_name,
                                            status="completed",
                                            duration_ms=0,
                                            started_at=None,
                                            completed_at=None,
                                            output_data=output_data,
                                            error_message=None
                                        ))

                except Exception as e:
                    logger.warning(f"Could not fetch LlamaStack session history: {str(e)}")

        # Determine current step and progress
        step_order = {
            "ocr": 25,
            "rag_retrieval": 75,
            "llm_decision": 100
        }

        if processing_steps:
            current_step = processing_steps[-1].step_name
            progress = step_order.get(current_step, 50)
        elif claim.status == "completed" or claim.status == "failed" or claim.status == "manual_review":
            progress = 100.0

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
        logger.error(f"Error getting claim status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{claim_id}/decision", response_model=schemas.ClaimDecisionResponse)
async def get_claim_decision(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the decision details for a processed claim.
    """
    try:
        # Get the most recent decision
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
        logger.error(f"Error getting claim decision: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{claim_id}/logs", response_model=schemas.ClaimLogsResponse)
async def get_claim_logs(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get processing logs for a claim.
    """
    try:
        query = (
            select(models.ProcessingLog)
            .where(models.ProcessingLog.claim_id == claim_id)
            .order_by(models.ProcessingLog.started_at.asc())
        )
        result = await db.execute(query)
        logs = result.scalars().all()

        processing_logs = [
            schemas.ProcessingStepLog(
                step_name=log.step.value,
                agent_name=log.agent_name,
                status=log.status,
                duration_ms=log.duration_ms,
                started_at=log.started_at,
                completed_at=log.completed_at,
                output_data=log.output_data,
                error_message=log.error_message
            )
            for log in logs
        ]

        return schemas.ClaimLogsResponse(
            claim_id=claim_id,
            logs=processing_logs
        )

    except Exception as e:
        logger.error(f"Error getting claim logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{claim_id}/decision", response_model=schemas.ClaimDecisionResponse)
async def get_claim_decision(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the decision for a processed claim.
    """
    try:
        query = select(models.ClaimDecision).where(models.ClaimDecision.claim_id == claim_id)
        result = await db.execute(query)
        decision = result.scalar_one_or_none()

        if not decision:
            raise HTTPException(status_code=404, detail="Decision not found for this claim")

        return schemas.ClaimDecisionResponse.model_validate(decision)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting claim decision: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics/overview", response_model=schemas.ClaimStatistics)
async def get_claim_statistics(db: AsyncSession = Depends(get_db)):
    """
    Get overall claims statistics.
    """
    try:
        # Count by status
        status_counts = {}
        status_values = ["pending", "processing", "completed", "failed", "manual_review"]
        for status_value in status_values:
            query = select(func.count()).where(models.Claim.status == status_value)
            result = await db.execute(query)
            status_counts[status_value] = result.scalar()

        # Average processing time
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
        logger.error(f"Error getting statistics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{claim_id}/view")
async def view_claim_document(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """View claim document PDF."""
    try:
        from fastapi.responses import FileResponse
        import os

        # Get claim
        result = await db.execute(
            select(models.Claim).where(models.Claim.id == claim_id)
        )
        claim = result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        # Check if document exists
        if not claim.document_path or not os.path.exists(claim.document_path):
            raise HTTPException(status_code=404, detail="Document not found")

        # Return PDF file
        return FileResponse(
            claim.document_path,
            media_type="application/pdf",
            filename=os.path.basename(claim.document_path)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
