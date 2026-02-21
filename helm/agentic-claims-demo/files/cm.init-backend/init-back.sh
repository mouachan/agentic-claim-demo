#!/bin/bash

set -e

echo ============================================
echo Copying test documents to PVC
echo ============================================

# GitHub repository details
REPO=mouachan/agentic-claim-demo
BRANCH=main
CLAIMS_DIR=backend/test_data/claim_documents
TENDERS_DIR=backend/test_data/tender_documents

# Target directories in PVC
CLAIMS_TARGET=/claim_documents
TENDERS_TARGET=/claim_documents/ao

# Create target directories
mkdir -p $CLAIMS_TARGET
mkdir -p $TENDERS_TARGET

DOWNLOADED=0
FAILED=0

# ===========================================
# Claims (50 files)
# ===========================================
CLAIM_FILES=()

# Auto claims (20 files: claim_auto_001 to claim_auto_020)
for i in {1..20}; do
  CLAIM_FILES+=("claim_auto_$(printf "%03d" "$i").pdf")
done

# Home claims (15 files: claim_home_001 to claim_home_015)
for i in {1..15}; do
  CLAIM_FILES+=("claim_home_$(printf "%03d" "$i").pdf")
done

# Medical claims (15 files: claim_medical_001 to claim_medical_015)
for i in {1..15}; do
  CLAIM_FILES+=("claim_medical_$(printf "%03d" "$i").pdf")
done

echo ""
echo "Downloading ${#CLAIM_FILES[@]} claim PDFs from GitHub..."
echo ""

for PDF_FILE in "${CLAIM_FILES[@]}"; do
  URL="https://raw.githubusercontent.com/$REPO/$BRANCH/$CLAIMS_DIR/$PDF_FILE"
  echo "Downloading: $PDF_FILE"

  if curl -L -s -f -o "$CLAIMS_TARGET/$PDF_FILE" "$URL"; then
    echo "  ✓ Downloaded successfully"
    DOWNLOADED=$((DOWNLOADED + 1))
  else
    echo "  ✗ Failed to download"
    FAILED=$((FAILED + 1))
  fi
done

# ===========================================
# Tenders (5 files)
# ===========================================
TENDER_FILES=(
  "ao_2026_0042.pdf"
  "ao_2026_0043.pdf"
  "ao_2026_0044.pdf"
  "ao_2026_0045.pdf"
  "ao_2026_0046.pdf"
)

echo ""
echo "Downloading ${#TENDER_FILES[@]} tender PDFs from GitHub..."
echo ""

for PDF_FILE in "${TENDER_FILES[@]}"; do
  URL="https://raw.githubusercontent.com/$REPO/$BRANCH/$TENDERS_DIR/$PDF_FILE"
  echo "Downloading: $PDF_FILE"

  if curl -L -s -f -o "$TENDERS_TARGET/$PDF_FILE" "$URL"; then
    echo "  ✓ Downloaded successfully"
    DOWNLOADED=$((DOWNLOADED + 1))
  else
    echo "  ✗ Failed to download"
    FAILED=$((FAILED + 1))
  fi
done

# ===========================================
# Summary
# ===========================================
TOTAL=$((${#CLAIM_FILES[@]} + ${#TENDER_FILES[@]}))

echo ""
echo ============================================
echo "Download summary: $DOWNLOADED successful, $FAILED failed (total: $TOTAL)"
echo ============================================

if [ "$FAILED" -gt 0 ]; then
  echo WARNING: Some files failed to download
fi

echo ""
echo ============================================
echo Verifying files in PVC...
echo ============================================
echo "Claims:"
ls -lh "$CLAIMS_TARGET"/*.pdf
echo ""
echo "Tenders:"
ls -lh "$TENDERS_TARGET"/*.pdf

echo ""
echo ============================================
echo "✓ Successfully copied $TOTAL test documents (claims + tenders)"
echo ============================================
