// Type definitions for Claims Demo

export interface Claim {
  id: string
  user_id: string
  claim_number: string
  claim_type?: string
  document_path: string
  status: ClaimStatus
  submitted_at: string
  processed_at?: string
  total_processing_time_ms?: number
  metadata?: Record<string, any>
  created_at: string
  updated_at: string
}

export type ClaimStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'manual_review'

export interface ProcessingStepLog {
  step_name: string
  agent_name: string
  status: string
  duration_ms: number
  started_at: string
  completed_at?: string
  output_data?: Record<string, any>
  error_message?: string
}

export interface ClaimStatusResponse {
  claim_id: string
  status: ClaimStatus
  current_step?: string
  progress_percentage: number
  processing_steps: ProcessingStepLog[]
  estimated_completion_time?: string
}

export interface ClaimDecision {
  id: string
  claim_id: string
  decision: 'approve' | 'deny' | 'manual_review'
  confidence: number
  reasoning: string
  relevant_policies?: Record<string, any>
  similar_claims?: Record<string, any>
  user_contract_info?: Record<string, any>
  llm_model?: string
  requires_manual_review: boolean
  decided_at: string
}

export interface ClaimStatistics {
  total_claims: number
  pending_claims: number
  processing_claims: number
  completed_claims: number
  failed_claims: number
  manual_review_claims: number
  average_processing_time_ms?: number
}

export interface ProcessClaimRequest {
  workflow_type?: string
  skip_ocr?: boolean
  skip_guardrails?: boolean
  enable_rag?: boolean
}
