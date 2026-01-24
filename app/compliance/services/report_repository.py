"""
ReportRepository: CRUD operations for compliance report records.

Stores report metadata and JSONB content.
No raw PHI is stored - only counts, risk levels, findings, and recommendations.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from shorui_core.domain.hipaa_schemas import ComplianceReport
from shorui_core.infrastructure.postgres import get_db_connection


SCHEMA_VERSION = "1.0"


class ReportRepository:
    """
    Repository for compliance report records in PostgreSQL.
    
    Stores report as JSONB - contains risk assessment and recommendations,
    but no raw PHI text or detected values.
    """

    def create(
        self,
        *,
        tenant_id: str,
        project_id: str,
        transcript_id: str,
        report: ComplianceReport,
        job_id: Optional[str] = None,
    ) -> str:
        """
        Create a new compliance report record.
        
        Args:
            tenant_id: Tenant namespace
            project_id: Project identifier
            transcript_id: Associated transcript ID
            report: ComplianceReport domain object
            job_id: Job that created this report
            
        Returns:
            report_id (UUID string)
        """
        report_id = report.id or str(uuid.uuid4())
        
        # Build JSONB content - exclude any raw PHI
        report_json = {
            "sections": [
                {
                    "title": s.title,
                    "findings": s.findings,
                    "recommendations": s.recommendations,
                    "severity": s.severity,
                }
                for s in report.sections
            ],
            "transcript_ids": report.transcript_ids,
        }

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO compliance_reports (
                    report_id, tenant_id, project_id, transcript_id,
                    overall_risk_level, total_phi_detected, total_violations,
                    report_json, schema_version, generated_at, created_by_job_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    report_id,
                    tenant_id,
                    project_id,
                    transcript_id,
                    report.overall_risk_level,
                    report.total_phi_detected,
                    report.total_violations,
                    json.dumps(report_json),
                    SCHEMA_VERSION,
                    report.generated_at or datetime.utcnow(),
                    job_id,
                ),
            )
            conn.commit()

        logger.info(
            f"Created compliance report {report_id} for transcript={transcript_id}"
        )
        return report_id

    def get_by_id(self, report_id: str) -> dict[str, Any] | None:
        """Get report by ID."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT report_id, tenant_id, project_id, transcript_id,
                       overall_risk_level, total_phi_detected, total_violations,
                       report_json, schema_version, generated_at, created_by_job_id
                FROM compliance_reports
                WHERE report_id = %s
                """,
                (report_id,),
            )
            row = cursor.fetchone()

        return self._row_to_dict(row)

    def get_by_transcript_id(self, transcript_id: str) -> dict[str, Any] | None:
        """Get the most recent report for a transcript."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT report_id, tenant_id, project_id, transcript_id,
                       overall_risk_level, total_phi_detected, total_violations,
                       report_json, schema_version, generated_at, created_by_job_id
                FROM compliance_reports
                WHERE transcript_id = %s
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (transcript_id,),
            )
            row = cursor.fetchone()

        return self._row_to_dict(row)

    def _row_to_dict(self, row: tuple | None) -> dict[str, Any] | None:
        """Convert database row to dictionary."""
        if not row:
            return None

        report_json = row[7]
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except Exception:
                report_json = {}

        return {
            "report_id": str(row[0]),
            "tenant_id": row[1],
            "project_id": row[2],
            "transcript_id": str(row[3]),
            "overall_risk_level": row[4],
            "total_phi_detected": row[5],
            "total_violations": row[6],
            "report_json": report_json,
            "schema_version": row[8],
            "generated_at": row[9],
            "created_by_job_id": str(row[10]) if row[10] else None,
        }


def get_report_repository() -> ReportRepository:
    """Factory function for ReportRepository."""
    return ReportRepository()
