"""
Pydantic schemas for API requests and responses.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# Claims Schemas
# ============================================================================
class ClaimBase(BaseModel):
    user_id: str
    claim_number: str
    claim_type: Optional[str] = None
    document_path: str


class ClaimCreate(ClaimBase):
    pass


class ClaimUpdate(BaseModel):
    status: Optional[str] = None
    claim_metadata: Optional[Dict[str, Any]] = Field(default=None, serialization_alias="metadata")


class ClaimResponse(ClaimBase):
    id: UUID
    status: str
    submitted_at: datetime
    processed_at: Optional[datetime] = None
    total_processing_time_ms: Optional[int] = None
    claim_metadata: Dict[str, Any] = Field(default_factory=dict, serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class ClaimListResponse(BaseModel):
    claims: List[ClaimResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Processing Schemas
# ============================================================================
class ProcessClaimRequest(BaseModel):
    workflow_type: str = Field(default="standard", description="Workflow type: standard, expedited, manual_review")
    skip_ocr: bool = False
    skip_guardrails: bool = False
    enable_rag: bool = True


class ProcessingStepLog(BaseModel):
    step_name: str
    agent_name: str
    status: str
    duration_ms: int
    started_at: datetime
    completed_at: Optional[datetime]
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class ProcessClaimResponse(BaseModel):
    claim_id: UUID
    status: str
    message: str
    processing_started_at: datetime


class ClaimStatusResponse(BaseModel):
    claim_id: UUID
    status: str
    current_step: Optional[str]
    progress_percentage: float
    processing_steps: List[ProcessingStepLog]
    estimated_completion_time: Optional[datetime]


class ClaimLogsResponse(BaseModel):
    claim_id: UUID
    logs: List[ProcessingStepLog]


# ============================================================================
# Decision Schemas
# ============================================================================
class ClaimDecisionResponse(BaseModel):
    id: UUID
    claim_id: UUID
    decision: str
    confidence: float
    reasoning: str
    relevant_policies: Optional[Dict[str, Any]] = None
    similar_claims: Optional[Dict[str, Any]] = None
    user_contract_info: Optional[Dict[str, Any]] = None
    llm_model: Optional[str]
    requires_manual_review: bool
    decided_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Document Schemas
# ============================================================================
class DocumentUploadResponse(BaseModel):
    document_id: UUID
    file_path: str
    file_size_bytes: int
    mime_type: str
    uploaded_at: datetime


class DocumentResponse(BaseModel):
    id: UUID
    claim_id: UUID
    document_type: Optional[str]
    file_path: str
    file_size_bytes: Optional[int]
    mime_type: Optional[str]
    raw_ocr_text: Optional[str]
    structured_data: Optional[Dict[str, Any]]
    ocr_confidence: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# User Schemas
# ============================================================================
class UserResponse(BaseModel):
    id: UUID
    user_id: str
    email: Optional[str]
    full_name: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserContractResponse(BaseModel):
    id: UUID
    user_id: str
    contract_number: str
    contract_type: Optional[str]
    coverage_amount: Optional[float]
    premium_amount: Optional[float]
    is_active: bool
    start_date: Optional[datetime]
    end_date: Optional[datetime]

    class Config:
        from_attributes = True


# ============================================================================
# Statistics Schemas
# ============================================================================
class ClaimStatistics(BaseModel):
    total_claims: int
    pending_claims: int
    processing_claims: int
    completed_claims: int
    failed_claims: int
    manual_review_claims: int
    average_processing_time_ms: Optional[float]


# ============================================================================
# Error Schemas
# ============================================================================
class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
