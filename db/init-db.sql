-- Database initialization script for Shorui-AI
-- Creates tables for job tracking and dead letter queue

-- Ingestion Jobs table
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    filename VARCHAR(500) NOT NULL,
    storage_path VARCHAR(1000),
    content_hash VARCHAR(64),
    status VARCHAR(50) DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    error TEXT,
    items_indexed INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    completed_at TIMESTAMP,
    failed_at TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON ingestion_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_content_hash ON ingestion_jobs(content_hash);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON ingestion_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON ingestion_jobs(created_at DESC);

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
