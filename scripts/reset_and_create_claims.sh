#!/bin/bash

echo "════════════════════════════════════════════════════════════════"
echo "🗑️  CLEANING DATABASE..."
echo "════════════════════════════════════════════════════════════════"

# Delete all existing claims
oc exec postgresql-0 -n claims-demo -- psql -U claims_user -d claims_db -c "DELETE FROM claim_decisions; DELETE FROM processing_logs; DELETE FROM claims;"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📝 CREATING 10 PENDING CLAIMS..."
echo "════════════════════════════════════════════════════════════════"

BACKEND_URL="https://backend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/api/v1/claims/"

# Array to store claim IDs
declare -a CLAIMS

# Claim 1 - user_001 - T-bone collision
CLAIMS[1]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_001","claim_number":"CLM-2026-AUTO-001","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_001.pdf"}' | jq -r '.id')
echo "✓ Claim 1 created: ${CLAIMS[1]}"

# Claim 2 - user_002 - Multi-vehicle pileup
CLAIMS[2]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_002","claim_number":"CLM-2026-AUTO-002","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_002.pdf"}' | jq -r '.id')
echo "✓ Claim 2 created: ${CLAIMS[2]}"

# Claim 3 - user_003 - Parking lot collision (NO CONTRACTS)
CLAIMS[3]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_003","claim_number":"CLM-2026-AUTO-003","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_003.pdf"}' | jq -r '.id')
echo "✓ Claim 3 created: ${CLAIMS[3]}"

# Claim 4 - user_001 - T-bone collision
CLAIMS[4]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_001","claim_number":"CLM-2026-AUTO-004","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_001.pdf"}' | jq -r '.id')
echo "✓ Claim 4 created: ${CLAIMS[4]}"

# Claim 5 - user_002 - Multi-vehicle pileup
CLAIMS[5]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_002","claim_number":"CLM-2026-AUTO-005","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_002.pdf"}' | jq -r '.id')
echo "✓ Claim 5 created: ${CLAIMS[5]}"

# Claim 6 - user_003 - Parking lot collision (NO CONTRACTS)
CLAIMS[6]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_003","claim_number":"CLM-2026-AUTO-006","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_003.pdf"}' | jq -r '.id')
echo "✓ Claim 6 created: ${CLAIMS[6]}"

# Claim 7 - user_001 - T-bone collision
CLAIMS[7]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_001","claim_number":"CLM-2026-AUTO-007","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_001.pdf"}' | jq -r '.id')
echo "✓ Claim 7 created: ${CLAIMS[7]}"

# Claim 8 - user_002 - Multi-vehicle pileup
CLAIMS[8]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_002","claim_number":"CLM-2026-AUTO-008","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_002.pdf"}' | jq -r '.id')
echo "✓ Claim 8 created: ${CLAIMS[8]}"

# Claim 9 - user_001 - T-bone collision
CLAIMS[9]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_001","claim_number":"CLM-2026-AUTO-009","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_001.pdf"}' | jq -r '.id')
echo "✓ Claim 9 created: ${CLAIMS[9]}"

# Claim 10 - user_003 - Parking lot collision (NO CONTRACTS)
CLAIMS[10]=$(curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d '{"user_id":"user_003","claim_number":"CLM-2026-AUTO-010","claim_type":"AUTO","document_path":"/claim_documents/claim_auto_003.pdf"}' | jq -r '.id')
echo "✓ Claim 10 created: ${CLAIMS[10]}"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ SUCCESSFULLY CREATED 10 PENDING CLAIMS!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📊 CLAIM DETAILS:"
echo ""
echo "Claim 1 (user_001 - T-bone, $3,153)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[1]}"
echo ""
echo "Claim 2 (user_002 - Pileup, $6,497)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[2]}"
echo ""
echo "Claim 3 (user_003 - Parking, $6,793 - NO CONTRACTS)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[3]}"
echo ""
echo "Claim 4 (user_001 - T-bone, $3,153)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[4]}"
echo ""
echo "Claim 5 (user_002 - Pileup, $6,497)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[5]}"
echo ""
echo "Claim 6 (user_003 - Parking, $6,793 - NO CONTRACTS)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[6]}"
echo ""
echo "Claim 7 (user_001 - T-bone, $3,153)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[7]}"
echo ""
echo "Claim 8 (user_002 - Pileup, $6,497)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[8]}"
echo ""
echo "Claim 9 (user_001 - T-bone, $3,153)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[9]}"
echo ""
echo "Claim 10 (user_003 - Parking, $6,793 - NO CONTRACTS)"
echo "  https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims/${CLAIMS[10]}"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "🎯 MAIN CLAIMS LIST:"
echo "   https://frontend-claims-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/claims"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "💡 Expected outcomes:"
echo "   - Claims with user_001/user_002: Should APPROVE (have contracts)"
echo "   - Claims with user_003: Should MANUAL_REVIEW (no contracts)"
echo ""
