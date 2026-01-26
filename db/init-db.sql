-- Creates tables for job tracking and dead letter queue
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Canonical Jobs table (replaces ingestion_jobs usage)
CREATE TABLE IF NOT EXISTS jobs (
    job_id UUID PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(255) NOT NULL,
    job_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    idempotency_key VARCHAR(128),
    request_id VARCHAR(255),
    error_code VARCHAR(100),
    error_message_safe TEXT,
    error_debug_id VARCHAR(255),
    input_artifacts JSONB,
    result_artifacts JSONB,
    raw_pointer TEXT,
    processed_pointer TEXT,
    result_pointer TEXT,
    content_type TEXT,
    document_type TEXT,
    byte_size BIGINT,
    items_indexed INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_tenant_project ON jobs(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_type_status ON jobs(job_type, status);
CREATE INDEX IF NOT EXISTS idx_jobs_idempotency ON jobs(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at_jobs ON jobs(created_at DESC);

-- Artifacts registry table
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id UUID PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(255) NOT NULL,
    artifact_type VARCHAR(100) NOT NULL,
    storage_backend VARCHAR(50) NOT NULL,
    storage_pointer TEXT NOT NULL,
    content_type TEXT,
    byte_size BIGINT,
    sha256 VARCHAR(64),
    schema_version VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by_job_id UUID
);

CREATE INDEX IF NOT EXISTS idx_artifacts_tenant_project ON artifacts(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(created_by_job_id);

-- Dead Letter Queue table
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL,
    error TEXT,
    traceback TEXT,
    failed_at TIMESTAMP DEFAULT NOW(),
    reviewed BOOLEAN DEFAULT FALSE,
    reviewed_at TIMESTAMP,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    notes TEXT
);

-- Create indexes for DLQ
CREATE INDEX IF NOT EXISTS idx_dlq_job_id ON dead_letter_queue(job_id);
CREATE INDEX IF NOT EXISTS idx_dlq_failed_at ON dead_letter_queue(failed_at DESC);
CREATE INDEX IF NOT EXISTS idx_dlq_unreviewed ON dead_letter_queue(reviewed) WHERE NOT reviewed;

-- =============================================================================
-- Clinical Transcripts table (metadata + pointer to encrypted storage)
-- No PHI stored here - raw text is in MinIO via storage_pointer
-- =============================================================================
CREATE TABLE IF NOT EXISTS transcripts (
    transcript_id UUID PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(255) NOT NULL,
    filename VARCHAR(512),
    storage_pointer TEXT NOT NULL,
    byte_size BIGINT,
    text_length INT,
    file_hash VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by_job_id UUID
);

CREATE INDEX IF NOT EXISTS idx_transcripts_tenant_project ON transcripts(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_job ON transcripts(created_by_job_id);

-- =============================================================================
-- Compliance Reports table (JSONB report data - no raw PHI)
-- Contains risk levels, counts, findings, recommendations
-- =============================================================================
CREATE TABLE IF NOT EXISTS compliance_reports (
    report_id UUID PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(255) NOT NULL,
    transcript_id UUID NOT NULL REFERENCES transcripts(transcript_id),
    overall_risk_level VARCHAR(20),
    total_phi_detected INT DEFAULT 0,
    total_violations INT DEFAULT 0,
    report_json JSONB,
    schema_version VARCHAR(50) DEFAULT '1.0',
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by_job_id UUID
);

CREATE INDEX IF NOT EXISTS idx_compliance_reports_tenant_project ON compliance_reports(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_compliance_reports_transcript ON compliance_reports(transcript_id);
CREATE INDEX IF NOT EXISTS idx_compliance_reports_job ON compliance_reports(created_by_job_id);

-- =============================================================================
-- HIPAA Audit Events table (append-only for compliance)
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY,
    sequence_number SERIAL,
    tenant_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    user_id VARCHAR(100),
    user_ip VARCHAR(45),
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    previous_hash VARCHAR(64),
    event_hash VARCHAR(64) NOT NULL
);

-- Create indexes for audit queries
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_project ON audit_events(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_events_resource ON audit_events(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_user ON audit_events(user_id);

-- =============================================================================
-- Tenants table (organizations)
-- =============================================================================
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Default tenant for development/migration
INSERT INTO tenants (tenant_id, name) VALUES ('default', 'Default Tenant')
ON CONFLICT (tenant_id) DO NOTHING;

-- =============================================================================
-- API Keys table (stores hashed keys for authentication)
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    key_id UUID PRIMARY KEY,
    key_hash VARCHAR(64) NOT NULL UNIQUE,   -- SHA-256 of the raw key
    key_prefix VARCHAR(12) NOT NULL,         -- First 12 chars for identification
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    name VARCHAR(255),                        -- Human-readable identifier
    scopes TEXT[] NOT NULL,                   -- Array of permission scopes
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,                   -- Optional expiration
    last_used_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);

-- =============================================================================
-- Users table (email/password authentication)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,  -- bcrypt hash
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);

-- =============================================================================
-- Refresh Tokens table (for JWT refresh flow)
-- =============================================================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 of token
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);
