import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { claimsApi } from '../services/api'
import type { Claim, ClaimStatusResponse, ClaimDecision, ProcessingStepLog } from '../types'

export default function ClaimDetailPage() {
  const { claimId } = useParams<{ claimId: string }>()
  const [claim, setClaim] = useState<Claim | null>(null)
  const [status, setStatus] = useState<ClaimStatusResponse | null>(null)
  const [decision, setDecision] = useState<ClaimDecision | null>(null)
  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pollingInterval, setPollingInterval] = useState<number | null>(null)

  useEffect(() => {
    if (claimId) {
      loadClaimData()
    }
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [claimId])

  const loadClaimData = async () => {
    if (!claimId) return

    try {
      setLoading(true)
      setError(null)

      const [claimData, statusData] = await Promise.all([
        claimsApi.getClaim(claimId),
        claimsApi.getClaimStatus(claimId).catch(() => null)
      ])

      setClaim(claimData)
      setStatus(statusData)

      // Load decision if processed (completed, manual_review, or failed)
      if (['completed', 'manual_review', 'failed'].includes(claimData.status)) {
        try {
          const decisionData = await claimsApi.getClaimDecision(claimId)
          setDecision(decisionData)
        } catch (err) {
          console.error('Error loading decision:', err)
        }
      }

      // Start polling if processing
      if (claimData.status === 'processing') {
        startPolling()
      }
    } catch (err) {
      setError('Failed to load claim data')
      console.error('Error loading claim:', err)
    } finally {
      setLoading(false)
    }
  }

  const startPolling = () => {
    if (pollingInterval) return

    const interval = setInterval(async () => {
      if (!claimId) return

      try {
        const [claimData, statusData] = await Promise.all([
          claimsApi.getClaim(claimId),
          claimsApi.getClaimStatus(claimId)
        ])

        setClaim(claimData)
        setStatus(statusData)

        // Stop polling if no longer processing
        if (claimData.status !== 'processing') {
          stopPolling()

          // Load decision if processed (completed, manual_review, or failed)
          if (['completed', 'manual_review', 'failed'].includes(claimData.status)) {
            const decisionData = await claimsApi.getClaimDecision(claimId)
            setDecision(decisionData)
          }
        }
      } catch (err) {
        console.error('Error polling status:', err)
      }
    }, 2000) // Poll every 2 seconds

    setPollingInterval(interval)
  }

  const stopPolling = () => {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      setPollingInterval(null)
    }
  }

  const handleProcessClaim = async (workflowType: string = 'standard') => {
    if (!claimId) return

    try {
      setProcessing(true)
      setError(null)

      // Enable both OCR (now using fast EasyOCR) and RAG for full workflow
      await claimsApi.processClaim(claimId, {
        workflow_type: workflowType,
        skip_ocr: false,  // EasyOCR is fast (2-4s), no timeout issues
        enable_rag: true
      })

      // Reload claim and start polling
      await loadClaimData()
      startPolling()
    } catch (err) {
      setError('Failed to start claim processing')
      console.error('Error processing claim:', err)
    } finally {
      setProcessing(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending':
        return 'bg-yellow-100 text-yellow-800'
      case 'processing':
        return 'bg-purple-100 text-purple-800 animate-pulse'
      case 'completed':
        return 'bg-green-100 text-green-800'
      case 'failed':
        return 'bg-red-100 text-red-800'
      case 'manual_review':
        return 'bg-orange-100 text-orange-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getStepStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <svg className="h-5 w-5 text-green-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        )
      case 'processing':
        return (
          <svg className="animate-spin h-5 w-5 text-purple-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        )
      case 'failed':
        return (
          <svg className="h-5 w-5 text-red-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
        )
      default:
        return (
          <svg className="h-5 w-5 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
          </svg>
        )
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString()
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (error || !claim) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-800">{error || 'Claim not found'}</p>
        <Link to="/claims" className="text-blue-600 hover:text-blue-800 mt-2 inline-block">
          ← Back to Claims
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Navigation */}
      <Link to="/claims" className="text-blue-600 hover:text-blue-800 flex items-center">
        <svg className="h-5 w-5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
        </svg>
        Back to Claims
      </Link>

      {/* Claim Header */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-3xl font-bold text-gray-900">{claim.claim_number}</h2>
            <p className="mt-2 text-gray-600">Claim ID: {claim.id}</p>
          </div>
          <span className={`px-4 py-2 text-sm font-semibold rounded-full ${getStatusColor(claim.status)}`}>
            {claim.status.toUpperCase()}
          </span>
        </div>

        {/* Claim Subject - extracted from OCR if available */}
        {status && status.processing_steps.length > 0 && (
          (() => {
            const ocrStep = status.processing_steps.find((s: ProcessingStepLog) => s.step_name === 'ocr')
            const ocrData = ocrStep?.output_data?.structured_data?.fields
            if (ocrData) {
              const diagnosis = ocrData.diagnosis?.value || ocrData.service?.value
              const amount = ocrData.amount?.value
              if (diagnosis || amount) {
                return (
                  <div className="mt-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg">
                    <p className="text-xs text-gray-600 font-medium mb-1">CLAIM SUBJECT</p>
                    <p className="text-lg font-semibold text-gray-900">
                      {diagnosis || 'Medical Service'}
                      {amount && <span className="ml-2 text-blue-600">(${amount})</span>}
                    </p>
                    {ocrData.provider_name?.value && (
                      <p className="text-sm text-gray-600 mt-1">
                        Provider: {ocrData.provider_name.value}
                      </p>
                    )}
                    {ocrData.date_of_service?.value && (
                      <p className="text-sm text-gray-600">
                        Service Date: {ocrData.date_of_service.value}
                      </p>
                    )}
                  </div>
                )
              }
            }
            return null
          })()
        )}

        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-600">User ID</p>
            <p className="text-lg font-medium text-gray-900">{claim.user_id}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Claim Type</p>
            <p className="text-lg font-medium text-gray-900">{claim.claim_type || 'N/A'}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Submitted At</p>
            <p className="text-lg font-medium text-gray-900">{formatDate(claim.submitted_at)}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Document Path</p>
            <p className="text-lg font-medium text-gray-900 truncate">{claim.document_path}</p>
          </div>
          {claim.processed_at && (
            <>
              <div>
                <p className="text-sm text-gray-600">Processed At</p>
                <p className="text-lg font-medium text-gray-900">{formatDate(claim.processed_at)}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Total Processing Time</p>
                <p className="text-lg font-medium text-gray-900">
                  {claim.total_processing_time_ms
                    ? `${(claim.total_processing_time_ms / 1000).toFixed(2)}s`
                    : 'N/A'
                  }
                </p>
              </div>
            </>
          )}
        </div>

        {/* Process Actions */}
        {(claim.status === 'pending' || claim.status === 'failed') && (
          <div className="mt-6">
            <button
              onClick={() => handleProcessClaim('standard')}
              disabled={processing}
              className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-8 rounded-lg transition-colors disabled:opacity-50"
            >
              {processing ? 'Processing...' : 'Process Claim'}
            </button>
          </div>
        )}
      </div>

      {/* Processing Status */}
      {status && status.processing_steps.length > 0 && (
        <div className="bg-white shadow rounded-lg p-6">
          <h3 className="text-xl font-bold text-gray-900 mb-4">Processing Status</h3>

          {status.current_step && (
            <div className="mb-4 p-4 bg-blue-50 rounded-lg">
              <p className="text-sm text-gray-600">Current Step</p>
              <p className="text-lg font-medium text-gray-900">{status.current_step}</p>
              <div className="mt-2">
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${status.progress_percentage}%` }}
                  ></div>
                </div>
                <p className="text-sm text-gray-600 mt-1">{status.progress_percentage}% complete</p>
              </div>
            </div>
          )}

          <div className="space-y-4">
            {status.processing_steps.map((step: ProcessingStepLog, index: number) => (
              <div key={index} className="border border-gray-200 rounded-lg p-4">
                <div className="flex items-start">
                  <div className="flex-shrink-0 mt-1">
                    {getStepStatusIcon(step.status)}
                  </div>
                  <div className="ml-3 flex-1">
                    <div className="flex justify-between">
                      <h4 className="text-lg font-medium text-gray-900">{step.step_name}</h4>
                      <span className={`px-2 py-1 text-xs font-semibold rounded ${getStatusColor(step.status)}`}>
                        {step.status}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">Agent: {step.agent_name}</p>
                    <p className="text-sm text-gray-600">
                      Duration: {step.duration_ms ? `${(step.duration_ms / 1000).toFixed(2)}s` : 'In progress...'}
                    </p>
                    {step.started_at && (
                      <p className="text-sm text-gray-600">Started: {formatDate(step.started_at)}</p>
                    )}
                    {step.completed_at && (
                      <p className="text-sm text-gray-600">Completed: {formatDate(step.completed_at)}</p>
                    )}
                    {step.error_message && (
                      <div className="mt-2 p-2 bg-red-50 rounded">
                        <p className="text-sm text-red-800">Error: {step.error_message}</p>
                      </div>
                    )}
                    {step.output_data && step.step_name === 'ocr' && step.output_data.structured_data && (
                      <div className="mt-3 p-3 bg-blue-50 rounded-lg">
                        <p className="text-sm font-medium text-gray-700 mb-2">Extracted Information:</p>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          {Object.entries(step.output_data.structured_data.fields || {}).map(([key, value]: [string, any]) => (
                            <div key={key}>
                              <span className="text-gray-600">{key.replace(/_/g, ' ')}:</span>
                              <span className="ml-1 font-medium text-gray-900">{value.value || 'N/A'}</span>
                            </div>
                          ))}
                        </div>
                        <p className="text-xs text-gray-500 mt-2">
                          Confidence: {((step.output_data.confidence || 0) * 100).toFixed(0)}%
                        </p>
                      </div>
                    )}
                    {step.output_data && step.step_name === 'rag_retrieval' && step.output_data.user_info && (
                      <div className="mt-3 p-3 bg-green-50 rounded-lg">
                        <p className="text-sm font-medium text-gray-700 mb-2">Retrieved Information:</p>
                        <div className="text-sm space-y-1">
                          {step.output_data.user_info.user_info && (
                            <>
                              <p><span className="text-gray-600">User:</span> <span className="font-medium">{step.output_data.user_info.user_info.full_name || step.output_data.user_info.user_info.user_id}</span></p>
                              <p><span className="text-gray-600">Contracts found:</span> <span className="font-medium">{step.output_data.user_info.contracts?.length || 0}</span></p>
                            </>
                          )}
                          <p><span className="text-gray-600">Similar claims:</span> <span className="font-medium">{step.output_data.similar_claims?.length || 0}</span></p>
                        </div>
                      </div>
                    )}
                    {step.output_data && step.step_name === 'llm_decision' && (
                      <div className="mt-3 p-3 bg-purple-50 rounded-lg">
                        <p className="text-sm font-medium text-gray-700 mb-2">LLM Decision:</p>
                        <div className="text-sm space-y-1">
                          <p><span className="text-gray-600">Recommendation:</span> <span className={`font-bold ml-1 ${
                            step.output_data.recommendation === 'approve' ? 'text-green-600' :
                            step.output_data.recommendation === 'deny' ? 'text-red-600' :
                            'text-orange-600'
                          }`}>{step.output_data.recommendation?.toUpperCase()}</span></p>
                          <p><span className="text-gray-600">Confidence:</span> <span className="font-medium ml-1">{((step.output_data.confidence || 0) * 100).toFixed(0)}%</span></p>
                          {step.output_data.reasoning && (
                            <div className="mt-2 pt-2 border-t border-purple-200">
                              <p className="text-gray-600 mb-1">Reasoning:</p>
                              <p className="text-gray-800">{step.output_data.reasoning}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                    {step.output_data && !['ocr', 'rag_retrieval', 'llm_decision'].includes(step.step_name) && (
                      <details className="mt-2">
                        <summary className="text-sm text-blue-600 cursor-pointer hover:text-blue-800">
                          View Raw Output Data
                        </summary>
                        <pre className="mt-2 p-2 bg-gray-50 rounded text-xs overflow-auto max-h-60">
                          {JSON.stringify(step.output_data, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Decision */}
      {decision && (
        <div className="bg-white shadow rounded-lg p-6">
          <h3 className="text-xl font-bold text-gray-900 mb-4">Claim Decision</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <p className="text-sm text-gray-600">Decision</p>
              <p className={`text-2xl font-bold mt-1 ${
                decision.decision === 'approve' ? 'text-green-600' :
                decision.decision === 'deny' ? 'text-red-600' :
                'text-orange-600'
              }`}>
                {decision.decision.toUpperCase()}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Confidence</p>
              <p className="text-2xl font-bold mt-1 text-gray-900">
                {(decision.confidence * 100).toFixed(1)}%
              </p>
            </div>
          </div>

          <div className="mt-6">
            <p className="text-sm text-gray-600 mb-2">Reasoning</p>
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-gray-900">{decision.reasoning}</p>
            </div>
          </div>

          {decision.requires_manual_review && (
            <div className="mt-4 p-4 bg-orange-50 border border-orange-200 rounded-lg">
              <p className="text-orange-800 font-medium">⚠️ This claim requires manual review</p>
            </div>
          )}

          {decision.llm_model && (
            <div className="mt-4">
              <p className="text-sm text-gray-600">LLM Model: {decision.llm_model}</p>
              <p className="text-sm text-gray-600">Decided At: {formatDate(decision.decided_at)}</p>
            </div>
          )}

          {decision.relevant_policies && (
            <div className="mt-6">
              <p className="text-sm text-gray-600 font-medium mb-3">Relevant Policies:</p>
              <div className="space-y-2">
                {(Array.isArray(decision.relevant_policies) ? decision.relevant_policies : decision.relevant_policies.policies || []).map((policy: any, index: number) => (
                  <div key={index} className="p-3 bg-indigo-50 border border-indigo-200 rounded-lg">
                    <p className="text-sm text-gray-900">{typeof policy === 'string' ? policy : policy.section || policy.name || JSON.stringify(policy)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {decision.similar_claims && Object.keys(decision.similar_claims).length > 0 && (
            <details className="mt-4">
              <summary className="text-sm text-blue-600 cursor-pointer hover:text-blue-800 font-medium">
                View Similar Claims
              </summary>
              <pre className="mt-2 p-4 bg-gray-50 rounded text-xs overflow-auto">
                {JSON.stringify(decision.similar_claims, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* Claim Description & Document */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-xl font-bold text-gray-900 mb-4">Claim Details</h3>

        <div className="space-y-4">
          <div>
            <p className="text-sm text-gray-600 font-medium mb-2">Description</p>
            <p className="text-gray-900">
              {claim.claim_type === 'AUTO' && 'Auto insurance claim for vehicle damage or accident'}
              {claim.claim_type === 'HOME' && 'Home insurance claim for property damage or loss'}
              {claim.claim_type === 'MEDICAL' && 'Medical insurance claim for healthcare services'}
              {!claim.claim_type && 'Insurance claim'}
            </p>
          </div>

          <div>
            <p className="text-sm text-gray-600 font-medium mb-2">Submitted Document</p>
            <div className="flex items-center gap-3">
              <span className="text-gray-700">{claim.document_path.split('/').pop()}</span>
              <a
                href={`/api/v1/documents/${claim.id}/view`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                View PDF
              </a>
            </div>
          </div>

          {claim.metadata && claim.metadata.category && (
            <div>
              <p className="text-sm text-gray-600 font-medium mb-2">Category</p>
              <span className="inline-flex px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full">
                {claim.metadata.category.replace(/_/g, ' ')}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
