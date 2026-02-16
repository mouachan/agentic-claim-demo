"""
Tender Service - Business logic for tenders (Appels d'Offres) processing.

Uses agent services for AI orchestration while keeping
business logic separate and testable.

Follows the same pattern as ClaimService but adapted for
Vinci AO Go/No-Go decision support.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import tender as models
from app.core.config import settings
from app.llamastack.ao_prompts import (
    AO_PROCESSING_AGENT_INSTRUCTIONS,
    AO_USER_MESSAGE_TEMPLATE,
)
from .agent.responses_orchestrator import ResponsesOrchestrator
from .agent.context_builder import ContextBuilder
from .agent.response_parser import ResponseParser

logger = logging.getLogger(__name__)


class TenderService:
    """Service for tender processing business logic."""

    def __init__(
        self,
        orchestrator: Optional[ResponsesOrchestrator] = None,
        context_builder: Optional[ContextBuilder] = None,
        response_parser: Optional[ResponseParser] = None,
    ):
        """
        Initialize tender service.

        Args:
            orchestrator: Responses orchestrator
            context_builder: Context builder
            response_parser: Response parser
        """
        self.orchestrator = orchestrator or ResponsesOrchestrator()
        self.context_builder = context_builder or ContextBuilder()
        self.response_parser = response_parser or ResponseParser()

    async def get_tender_by_id(
        self,
        db: AsyncSession,
        tender_id: str,
    ) -> Optional[models.Tender]:
        """
        Get tender by ID.

        Args:
            db: Database session
            tender_id: Tender identifier

        Returns:
            Tender model or None
        """
        result = await db.execute(
            select(models.Tender).where(models.Tender.id == tender_id)
        )
        return result.scalar_one_or_none()

    async def build_tender_context(
        self,
        db: AsyncSession,
        tender: models.Tender,
    ) -> Dict[str, Any]:
        """
        Build complete context for tender processing.

        Args:
            db: Database session
            tender: Tender model

        Returns:
            Complete tender context with OCR and RAG data
        """
        context = {
            "entity_type": "tender",
            "entity_id": str(tender.id),
            "entity_data": {
                "entity_id": tender.entity_id,
                "tender_number": tender.tender_number,
                "tender_type": tender.tender_type,
                "document_path": tender.document_path,
                "status": tender.status.value,
                "submitted_at": (
                    tender.submitted_at.isoformat() if tender.submitted_at else None
                ),
            },
        }

        # Add OCR data if available
        ocr_result = await db.execute(
            select(models.TenderDocument)
            .where(models.TenderDocument.tender_id == tender.id)
            .order_by(models.TenderDocument.created_at.desc())
            .limit(1)
        )
        tender_doc = ocr_result.scalar_one_or_none()

        if tender_doc:
            ocr_context = self.context_builder.extract_ocr_context(
                {
                    "raw_ocr_text": tender_doc.raw_ocr_text,
                    "structured_data": tender_doc.structured_data,
                }
            )
            context["additional_context"] = {"OCR Data": ocr_context}

        return context

    async def process_tender_with_agent(
        self,
        db: AsyncSession,
        tender_id: str,
        agent_config: Dict[str, Any],
        tools: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Process tender using an agent.

        Args:
            db: Database session
            tender_id: Tender identifier
            agent_config: Agent configuration
            tools: Optional list of tools to enable

        Returns:
            Processing result with decision

        Raises:
            ValueError: If tender not found
            Exception: If processing fails
        """
        # Get tender
        tender = await self.get_tender_by_id(db, tender_id)
        if not tender:
            raise ValueError(f"Tender {tender_id} not found")

        # Update status
        tender.status = models.TenderStatus.processing
        await db.commit()

        try:
            # Build context
            context = await self.build_tender_context(db, tender)

            # Build processing message
            context_str = self.context_builder.build_processing_context(
                entity_type="tender",
                entity_id=str(tender_id),
                entity_data=context["entity_data"],
                additional_context=context.get("additional_context"),
            )

            processing_message = f"{AO_USER_MESSAGE_TEMPLATE}\n\n{context_str}"

            # Process with Responses API (automatic tool execution)
            result = await self.orchestrator.process_with_agent(
                agent_config=agent_config,
                input_message=processing_message,
                tools=tools,
                session_name=f"tender_{tender.tender_number}_{datetime.now().isoformat()}",
            )

            # Parse decision
            response_content = result.get("output", "")
            logger.info(f"Raw LLM output ({len(response_content)} chars): {response_content[:500]}")
            decision_data = self.response_parser.parse_decision(response_content)
            logger.info(f"Parsed decision: recommendation={decision_data.get('recommendation')}, confidence={decision_data.get('confidence')}")

            # Extract processing steps from tool_calls
            tool_calls = result.get("tool_calls", [])
            processing_steps = []

            for tc in tool_calls:
                tool_name = tc.get("name", "unknown")

                # Map tool to agent name
                if "ocr" in tool_name.lower():
                    agent_name = "ocr-agent"
                elif tool_name in [
                    "retrieve_similar_references",
                    "retrieve_historical_tenders",
                    "retrieve_capabilities",
                ]:
                    agent_name = "rag-agent"
                else:
                    agent_name = "unknown"

                # Parse output and extract timing
                output_data = None
                duration_ms = None

                if tc.get("output"):
                    try:
                        import json as json_lib

                        output_data = json_lib.loads(tc["output"])

                        # Extract processing time if available in tool output
                        if (
                            isinstance(output_data, dict)
                            and "processing_time_seconds" in output_data
                        ):
                            duration_ms = int(
                                output_data["processing_time_seconds"] * 1000
                            )
                    except Exception:
                        output_data = {"raw_text": tc["output"]}

                processing_steps.append(
                    {
                        "step_name": tool_name,
                        "agent_name": agent_name,
                        "status": "failed" if tc.get("error") else "completed",
                        "output_data": output_data,
                        "error_message": tc.get("error"),
                        "duration_ms": duration_ms,
                    }
                )

            # Update tender status based on decision
            recommendation = decision_data.get("recommendation", "manual_review")
            if recommendation == "go":
                tender.status = models.TenderStatus.completed
            elif recommendation == "no_go":
                tender.status = models.TenderStatus.failed
            elif recommendation == "a_approfondir":
                tender.status = models.TenderStatus.manual_review
            else:
                tender.status = models.TenderStatus.manual_review

            # Calculate processing time from sum of step durations
            tender.processed_at = datetime.now(timezone.utc)

            # Sum all step durations to get accurate total processing time
            total_duration_ms = sum(
                step.get("duration_ms", 0)
                for step in processing_steps
                if step.get("duration_ms")
            )
            tender.total_processing_time_ms = (
                total_duration_ms if total_duration_ms > 0 else None
            )

            # Save processing metadata (reassign dict to trigger SQLAlchemy change detection)
            updated_metadata = dict(tender.tender_metadata or {})
            updated_metadata["response_id"] = result.get("response_id")
            updated_metadata["processing_steps"] = processing_steps
            updated_metadata["usage"] = result.get("usage", {})
            tender.tender_metadata = updated_metadata

            await db.commit()

            return {
                "response_id": result.get("response_id"),
                "decision": decision_data,
                "tender_status": tender.status.value,
                "processing_steps": processing_steps,
                "tool_calls": tool_calls,
                "usage": result.get("usage", {}),
            }

        except Exception as e:
            logger.error(
                f"Error processing tender {tender_id}: {e}", exc_info=True
            )
            tender.status = models.TenderStatus.failed
            await db.commit()
            raise

    async def save_decision(
        self,
        db: AsyncSession,
        tender_id: str,
        decision_data: Dict[str, Any],
    ) -> models.TenderDecision:
        """
        Save tender decision to database.

        Args:
            db: Database session
            tender_id: Tender identifier
            decision_data: Decision data from agent

        Returns:
            Created TenderDecision model
        """
        recommendation = decision_data.get("recommendation", "a_approfondir")

        # Map recommendation string to TenderDecisionType enum
        decision_type_map = {
            "go": models.TenderDecisionType.go,
            "no_go": models.TenderDecisionType.no_go,
            "a_approfondir": models.TenderDecisionType.a_approfondir,
        }
        decision_type = decision_type_map.get(
            recommendation, models.TenderDecisionType.a_approfondir
        )

        # Delete any existing decision for this tender to avoid duplicates
        existing = await db.execute(
            select(models.TenderDecision).where(
                models.TenderDecision.tender_id == tender_id
            )
        )
        for old in existing.scalars().all():
            await db.delete(old)
        await db.flush()

        decision = models.TenderDecision(
            tender_id=tender_id,
            # Initial system decision
            initial_decision=decision_type,
            initial_confidence=decision_data.get("confidence", 0.0),
            initial_reasoning=decision_data.get("reasoning", ""),
            initial_decided_at=datetime.now(timezone.utc),
            # Legacy fields
            decision=decision_type,
            confidence=decision_data.get("confidence", 0.0),
            reasoning=decision_data.get("reasoning", ""),
            # Supporting analysis
            risk_analysis=decision_data.get("risk_analysis"),
            similar_references=decision_data.get("similar_references"),
            historical_ao_analysis=decision_data.get("historical_ao_analysis"),
            internal_capabilities=decision_data.get("internal_capabilities"),
            # LLM details
            llm_model=settings.llamastack_default_model,
            requires_manual_review=(
                recommendation == "a_approfondir"
            ),
        )

        db.add(decision)
        await db.commit()
        await db.refresh(decision)

        logger.info(
            f"Decision saved for tender {tender_id}: {decision_type.value}"
        )

        return decision
