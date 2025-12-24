-- Sample seed data for Claims Demo
-- This creates sample users, contracts, claims, and knowledge base articles

-- ============================================================================
-- SAMPLE USERS
-- ============================================================================
INSERT INTO users (user_id, email, full_name, date_of_birth, phone_number, address, is_active) VALUES
('USER001', 'john.doe@example.com', 'John Doe', '1985-03-15', '555-0101', '{"street": "123 Main St", "city": "Springfield", "state": "IL", "zip": "62701"}'::jsonb, true),
('USER002', 'jane.smith@example.com', 'Jane Smith', '1990-07-22', '555-0102', '{"street": "456 Oak Ave", "city": "Chicago", "state": "IL", "zip": "60601"}'::jsonb, true),
('USER003', 'bob.johnson@example.com', 'Bob Johnson', '1978-11-30', '555-0103', '{"street": "789 Pine Rd", "city": "Naperville", "state": "IL", "zip": "60540"}'::jsonb, true);

-- ============================================================================
-- SAMPLE CONTRACTS
-- ============================================================================
INSERT INTO user_contracts (user_id, contract_number, contract_type, start_date, end_date, coverage_amount, premium_amount, payment_frequency, full_text, key_terms, is_active) VALUES
('USER001', 'CNT-2024-001', 'Health Insurance', '2024-01-01', '2024-12-31', 100000.00, 500.00, 'monthly',
 'This health insurance policy covers medical expenses including hospitalization, surgery, and prescription medications. Deductible: $1000. Co-pay: $25 per visit.',
 '{"deductible": 1000, "copay": 25, "max_out_of_pocket": 5000}'::jsonb,
 true),

('USER001', 'CNT-2024-002', 'Auto Insurance', '2024-01-01', '2024-12-31', 50000.00, 150.00, 'monthly',
 'Comprehensive auto insurance covering collision, liability, and comprehensive damage. Deductible: $500.',
 '{"deductible": 500, "liability_limit": 100000, "collision_coverage": true}'::jsonb,
 true),

('USER002', 'CNT-2024-003', 'Health Insurance', '2024-01-01', '2024-12-31', 150000.00, 650.00, 'monthly',
 'Premium health insurance with enhanced coverage for specialists and prescription drugs. Deductible: $500. Co-pay: $15 per visit.',
 '{"deductible": 500, "copay": 15, "max_out_of_pocket": 3000, "specialist_coverage": true}'::jsonb,
 true),

('USER003', 'CNT-2024-004', 'Home Insurance', '2024-01-01', '2024-12-31', 300000.00, 200.00, 'monthly',
 'Homeowners insurance covering dwelling, personal property, and liability. Deductible: $1000.',
 '{"deductible": 1000, "dwelling_coverage": 300000, "personal_property": 100000}'::jsonb,
 true);

-- ============================================================================
-- SAMPLE CLAIMS
-- ============================================================================
INSERT INTO claims (user_id, claim_number, claim_type, document_path, status, submitted_at) VALUES
('USER001', 'CLM-2024-0001', 'Medical', '/documents/claims/2024/medical_claim_001.pdf', 'pending', '2024-12-01 10:30:00'),
('USER001', 'CLM-2024-0002', 'Auto', '/documents/claims/2024/auto_claim_002.pdf', 'processing', '2024-12-05 14:15:00'),
('USER002', 'CLM-2024-0003', 'Medical', '/documents/claims/2024/medical_claim_003.pdf', 'completed', '2024-11-28 09:00:00'),
('USER003', 'CLM-2024-0004', 'Home', '/documents/claims/2024/home_claim_004.pdf', 'pending', '2024-12-10 11:45:00');

-- ============================================================================
-- SAMPLE KNOWLEDGE BASE ARTICLES
-- ============================================================================
INSERT INTO knowledge_base (title, content, category, tags, is_active, effective_date) VALUES
('Medical Claim Submission Guidelines',
 'All medical claims must be submitted within 90 days of service. Required documents include: itemized bill, diagnosis codes (ICD-10), procedure codes (CPT), and proof of payment. Claims exceeding $5000 require prior authorization.',
 'Claims Processing',
 ARRAY['medical', 'submission', 'guidelines'],
 true,
 '2024-01-01'),

('Covered Medical Services',
 'Covered services include: primary care visits, specialist consultations, emergency room visits, hospitalization, surgery, prescription medications (formulary), preventive care, and diagnostic tests. Exclusions: cosmetic procedures, experimental treatments.',
 'Coverage',
 ARRAY['medical', 'coverage', 'benefits'],
 true,
 '2024-01-01'),

('Auto Insurance Claim Process',
 'Steps for filing an auto insurance claim: 1) Report accident immediately, 2) Gather information (photos, police report, witness statements), 3) Submit claim form within 30 days, 4) Arrange vehicle inspection, 5) Receive approval and payment.',
 'Claims Processing',
 ARRAY['auto', 'process', 'steps'],
 true,
 '2024-01-01'),

('Deductible and Co-payment Policy',
 'Deductible is the amount you pay before insurance coverage begins. Once met, you pay co-payments for services. Co-payments are fixed amounts ($15-$50) depending on service type. Deductible resets annually on January 1st.',
 'Policy Terms',
 ARRAY['deductible', 'copay', 'terms'],
 true,
 '2024-01-01'),

('Prior Authorization Requirements',
 'Services requiring prior authorization: MRI/CT scans, surgeries, specialist referrals, durable medical equipment, home health care, and medications over $500. Submit authorization request 10 business days before service.',
 'Authorization',
 ARRAY['prior auth', 'approval', 'requirements'],
 true,
 '2024-01-01'),

('Prescription Drug Coverage',
 'Prescription drugs are covered according to the formulary tier system: Tier 1 (generic) - $10 copay, Tier 2 (preferred brand) - $30 copay, Tier 3 (non-preferred brand) - $60 copay. Mail order available for 90-day supply.',
 'Coverage',
 ARRAY['prescription', 'drugs', 'formulary'],
 true,
 '2024-01-01');

-- ============================================================================
-- SAMPLE CLAIM DOCUMENTS (without embeddings for now)
-- ============================================================================
INSERT INTO claim_documents (claim_id, document_type, file_path, file_size_bytes, mime_type, raw_ocr_text, structured_data, ocr_confidence)
SELECT
    c.id,
    'claim_form',
    c.document_path,
    125000,
    'application/pdf',
    'MEDICAL CLAIM FORM\nPatient: John Doe\nDate of Service: 11/15/2024\nProvider: Springfield Medical Center\nDiagnosis: Annual Physical Exam\nTotal Amount: $250.00\nInsurance: Health Plan A',
    '{"patient_name": "John Doe", "service_date": "2024-11-15", "provider": "Springfield Medical Center", "diagnosis": "Annual Physical", "amount": 250.00}'::jsonb,
    0.95
FROM claims c
WHERE c.claim_number = 'CLM-2024-0001';

-- ============================================================================
-- SAMPLE PROCESSING LOGS
-- ============================================================================
INSERT INTO processing_logs (claim_id, step, agent_name, started_at, completed_at, duration_ms, status, output_data, confidence_score)
SELECT
    c.id,
    'ocr',
    'ocr-server',
    '2024-12-05 14:15:30',
    '2024-12-05 14:15:42',
    12000,
    'completed',
    '{"text_extracted": true, "confidence": 0.95}'::jsonb,
    0.95
FROM claims c
WHERE c.claim_number = 'CLM-2024-0002';

-- ============================================================================
-- NOTES
-- ============================================================================
-- Embeddings need to be generated by the application using LlamaStack
-- The embedding fields are intentionally left NULL and will be populated
-- by the RAG server during initialization or when documents are processed

COMMENT ON TABLE users IS 'Sample users for testing';
COMMENT ON TABLE user_contracts IS 'Sample insurance contracts';
COMMENT ON TABLE claims IS 'Sample claims in various states';
COMMENT ON TABLE knowledge_base IS 'Sample policy and procedure documents';
