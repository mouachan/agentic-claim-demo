#!/bin/bash

set -e

echo ============================================
echo Copying test claim documents to PVC
echo ============================================

# GitHub repository details
REPO=mouachan/agentic-claim-demo
BRANCH=responses-api-migration
PDF_DIR=backend/test_data/claim_documents

# Target directory in PVC
TARGET_DIR=/claim_documents

# Create target directory
mkdir -p $TARGET_DIR

# Generate list of all PDF files (90 total with new naming: clm-2024-XXXX.pdf)
PDF_FILES=()

# Generate clm-2024-0001.pdf to clm-2024-0100.pdf
# Note: Some numbers are skipped based on seed.sql data
for i in $(seq 1 100); do
  pdf_name="clm-2024-$(printf "%04d" "$i").pdf"
  # Only add files that exist in the repo (90 files, some numbers skipped)
  PDF_FILES+=("$pdf_name")
done

echo ""
echo "Downloading ${#PDF_FILES[@]} PDF files from GitHub..."
echo ""

# Download each PDF file
DOWNLOADED=0
FAILED=0

for PDF_FILE in "${PDF_FILES[@]}"; do
  URL="https://raw.githubusercontent.com/$REPO/$BRANCH/$PDF_DIR/$PDF_FILE"
  echo "Downloading: $PDF_FILE"

  if curl -L -s -f -o "$TARGET_DIR/$PDF_FILE" "$URL"; then
    echo "  ✓ Downloaded successfully"
    DOWNLOADED=$((DOWNLOADED + 1))
  else
    echo "  ✗ Failed to download"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo ============================================
echo "Download summary: $DOWNLOADED successful, $FAILED failed"
echo ============================================

if [ "$FAILED" -gt 0 ]; then
  echo WARNING: Some files failed to download
fi

echo ""
echo ============================================
echo Verifying files in PVC...
echo ============================================
ls -lh "$TARGET_DIR"/*.pdf

echo ""
echo ============================================
echo "✓ Successfully copied ${#PDF_FILES[@]} test documents"
echo ============================================
