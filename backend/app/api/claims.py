"""
Claims API endpoints.
"""

import logging
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    Start processing a claim through the MCP orchestrator.
    """
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

        # Call orchestrator MCP server
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(
                    f"{settings.orchestrator_server_url}/orchestrate_claim_processing",
                    json={
                        "claim_id": str(claim_id),
                        "document_path": claim.document_path,
                        "user_id": claim.user_id,
                        "processing_config": {
                            "workflow_type": process_request.workflow_type,
                            "skip_ocr": process_request.skip_ocr,
                            "skip_guardrails": process_request.skip_guardrails,
                            "enable_rag": process_request.enable_rag
                        }
                    }
                )

                if response.status_code == 200:
                    orchestrator_result = response.json()

                    # Update claim with results
                    claim.status = models.ClaimStatus.completed if orchestrator_result.get("status") == "completed" else models.ClaimStatus.failed
                    claim.total_processing_time_ms = orchestrator_result.get("total_processing_time_ms")

                    # Create decision record if available
                    if orchestrator_result.get("final_decision"):
                        decision_data = orchestrator_result["final_decision"]
                        decision = models.ClaimDecision(
                            claim_id=claim_id,
                            decision=decision_data.get("recommendation"),
                            confidence=decision_data.get("confidence"),
                            reasoning=decision_data.get("reasoning"),
                            relevant_policies={"policies": decision_data.get("relevant_policies", [])},
                            llm_model="llama-3.1-8b-instruct",
                            requires_manual_review=(decision_data.get("recommendation") == "manual_review")
                        )
                        db.add(decision)

                    await db.commit()

                    logger.info(f"Claim {claim_id} processed successfully")
                    return schemas.ProcessClaimResponse(
                        claim_id=claim_id,
                        status=claim.status.value,
                        message="Processing completed",
                        processing_started_at=claim.submitted_at
                    )
                else:
                    claim.status = models.ClaimStatus.failed
                    await db.commit()
                    raise HTTPException(
                        status_code=500,
                        detail=f"Orchestrator error: {response.status_code}"
                    )

            except httpx.RequestError as e:
                claim.status = models.ClaimStatus.failed
                await db.commit()
                logger.error(f"Error calling orchestrator: {str(e)}")
                raise HTTPException(
                    status_code=503,
                    detail=f"Orchestrator unavailable: {str(e)}"
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
    Get the current processing status of a claim.
    """
    try:
        # Get claim
        claim_query = select(models.Claim).where(models.Claim.id == claim_id)
        claim_result = await db.execute(claim_query)
        claim = claim_result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        # Get processing logs
        logs_query = (
            select(models.ProcessingLog)
            .where(models.ProcessingLog.claim_id == claim_id)
            .order_by(models.ProcessingLog.started_at.desc())
        )
        logs_result = await db.execute(logs_query)
        logs = logs_result.scalars().all()

        # Determine current step and progress
        step_order = {
            "ocr": 25,
            "guardrails": 50,
            "rag_retrieval": 75,
            "llm_decision": 100
        }

        current_step = None
        progress = 0

        if logs:
            latest_log = logs[0]
            current_step = latest_log.step.value if hasattr(latest_log.step, 'value') else str(latest_log.step)
            progress = step_order.get(current_step, 0)

        processing_steps = [
            schemas.ProcessingStepLog(
                step_name=log.step.value if hasattr(log.step, 'value') else str(log.step),
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
