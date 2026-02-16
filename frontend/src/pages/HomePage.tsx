import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { claimsApi } from '../services/api'
import { tendersApi } from '../services/tenderApi'
import type { ClaimStatistics } from '../types'
import type { TenderStatistics } from '../types/tender'

export default function HomePage() {
  const [claimStats, setClaimStats] = useState<ClaimStatistics | null>(null)
  const [tenderStats, setTenderStats] = useState<TenderStatistics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStatistics()
  }, [])

  const loadStatistics = async () => {
    try {
      setLoading(true)
      const [claims, tenders] = await Promise.allSettled([
        claimsApi.getStatistics(),
        tendersApi.getStatistics()
      ])
      if (claims.status === 'fulfilled') setClaimStats(claims.value)
      if (tenders.status === 'fulfilled') setTenderStats(tenders.value)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-3xl font-bold text-gray-900">Agentic AI Platform</h2>
        <p className="mt-2 text-gray-600">
          Multi-Agent Processing Platform - LlamaStack, MCP Servers & OpenShift AI
        </p>
      </div>

      {/* Agent Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Claims Agent */}
        <div className="bg-white shadow rounded-lg p-6 border-t-4 border-blue-500">
          <div className="flex items-center mb-4">
            <div className="flex-shrink-0 bg-blue-500 rounded-md p-3">
              <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div className="ml-4">
              <h3 className="text-xl font-bold text-gray-900">Insurance Claims Agent</h3>
              <p className="text-sm text-gray-500">Automated claims processing & decision</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="bg-blue-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-blue-700">{claimStats?.total_claims || 0}</p>
              <p className="text-xs text-gray-600">Total</p>
            </div>
            <div className="bg-yellow-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-yellow-700">{claimStats?.pending_claims || 0}</p>
              <p className="text-xs text-gray-600">Pending</p>
            </div>
            <div className="bg-purple-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-purple-700">{claimStats?.processing_claims || 0}</p>
              <p className="text-xs text-gray-600">Processing</p>
            </div>
            <div className="bg-green-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-green-700">{claimStats?.completed_claims || 0}</p>
              <p className="text-xs text-gray-600">Completed</p>
            </div>
          </div>

          <Link
            to="/claims"
            className="block w-full text-center bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-lg transition-colors"
          >
            View Claims
          </Link>
        </div>

        {/* Tenders Agent */}
        <div className="bg-white shadow rounded-lg p-6 border-t-4 border-amber-500">
          <div className="flex items-center mb-4">
            <div className="flex-shrink-0 bg-amber-500 rounded-md p-3">
              <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
            </div>
            <div className="ml-4">
              <h3 className="text-xl font-bold text-gray-900">Appels d'Offres Agent</h3>
              <p className="text-sm text-gray-500">Analyse Go/No-Go automatisee</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="bg-amber-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-amber-700">{tenderStats?.total_tenders || 0}</p>
              <p className="text-xs text-gray-600">Total</p>
            </div>
            <div className="bg-yellow-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-yellow-700">{tenderStats?.pending_tenders || 0}</p>
              <p className="text-xs text-gray-600">En attente</p>
            </div>
            <div className="bg-orange-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-orange-700">{tenderStats?.processing_tenders || 0}</p>
              <p className="text-xs text-gray-600">En cours</p>
            </div>
            <div className="bg-green-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-green-700">{tenderStats?.completed_tenders || 0}</p>
              <p className="text-xs text-gray-600">Termines</p>
            </div>
          </div>

          <Link
            to="/tenders"
            className="block w-full text-center bg-amber-600 hover:bg-amber-700 text-white font-medium py-3 px-4 rounded-lg transition-colors"
          >
            Voir les AOs
          </Link>
        </div>
      </div>

      {/* Shared Infrastructure */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Shared Infrastructure</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="border border-gray-200 rounded-lg p-4">
            <h4 className="font-semibold text-gray-900 mb-2">LlamaStack</h4>
            <p className="text-sm text-gray-600">Responses API with ReAct agent orchestration</p>
          </div>
          <div className="border border-gray-200 rounded-lg p-4">
            <h4 className="font-semibold text-gray-900 mb-2">OCR MCP Server</h4>
            <p className="text-sm text-gray-600">Document extraction with Tesseract & LLM validation</p>
          </div>
          <div className="border border-gray-200 rounded-lg p-4">
            <h4 className="font-semibold text-gray-900 mb-2">RAG MCP Server</h4>
            <p className="text-sm text-gray-600">Vector retrieval with pgvector for both agents</p>
          </div>
          <div className="border border-gray-200 rounded-lg p-4">
            <h4 className="font-semibold text-gray-900 mb-2">Guardrails</h4>
            <p className="text-sm text-gray-600">PII detection & content safety with TrustyAI</p>
          </div>
        </div>
      </div>

      <div className="text-center">
        <button
          onClick={loadStatistics}
          className="bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium py-2 px-6 rounded-lg transition-colors"
        >
          Refresh Statistics
        </button>
      </div>
    </div>
  )
}
