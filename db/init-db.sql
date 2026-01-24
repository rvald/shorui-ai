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
-- HIPAA Audit Events table (append-only for compliance)
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY,
    sequence_number SERIAL,
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
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_events_resource ON audit_events(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_user ON audit_events(user_id);
