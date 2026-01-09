"""
Compliance Report Service

Generates structured HIPAA compliance reports from PHI extraction results.
"""

from datetime import datetime
from typing import Optional

from loguru import logger

from shorui_core.domain.hipaa_schemas import (
    ComplianceReport,
    ComplianceReportSection,
    PHIExtractionResult,
    ViolationSeverity,
)


class ComplianceReportService:
    """
    Generate HIPAA compliance reports from PHI extraction results.
    
    Takes the output of PrivacyAwareExtractionService and produces
    a structured report with findings, recommendations, and risk assessment.
    
    Usage:
        service = ComplianceReportService()
        report = service.generate_report(
            transcript_id="abc123",
            extraction_result=phi_result
        )
    """
    
    def generate_report(
        self,
        transcript_id: str,
        extraction_result: PHIExtractionResult,
    ) -> ComplianceReport:
        """
        Generate a compliance report from PHI extraction results.
        
        Args:
            transcript_id: ID of the analyzed transcript
            extraction_result: Output from PrivacyAwareExtractionService.extract()
            
        Returns:
            ComplianceReport with sections, findings, and recommendations
        """
        logger.info(f"Generating compliance report for transcript {transcript_id}")
        
        phi_spans = extraction_result.phi_spans
        compliance_analysis = extraction_result.compliance_analysis
        
        # Count violations and determine severity
        total_violations = 0
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        
        for span in phi_spans:
            # Check if span has compliance metadata (enriched by LLM)
            if hasattr(span, 'is_violation') and span.is_violation:
                total_violations += 1
                severity = getattr(span, 'severity', 'MEDIUM')
                if severity in severity_counts:
                    severity_counts[severity] += 1
        
        # Also check compliance_analysis for additional insights
        if compliance_analysis:
            for analysis in compliance_analysis.phi_analyses:
                if analysis.is_violation:
                    total_violations = max(total_violations, 1)  # At least 1
                    if analysis.severity:
                        sev = analysis.severity.upper()
                        if sev in severity_counts:
                            severity_counts[sev] += 1
        
        # Determine overall risk level
        overall_risk_level = self._calculate_risk_level(severity_counts)
        
        # Build report sections
        sections = self._build_sections(phi_spans, compliance_analysis)
        
        report = ComplianceReport(
            total_phi_detected=len(phi_spans),
            total_violations=total_violations,
            overall_risk_level=overall_risk_level,
            sections=sections,
            transcript_ids=[transcript_id],
        )
        
        logger.info(f"Generated report: {overall_risk_level} risk, {total_violations} violations")
        return report
    
    def _calculate_risk_level(self, severity_counts: dict) -> str:
        """Determine overall risk level from severity counts."""
        if severity_counts["CRITICAL"] > 0:
            return "CRITICAL"
        elif severity_counts["HIGH"] >= 2:
            return "HIGH"
        elif severity_counts["HIGH"] >= 1 or severity_counts["MEDIUM"] >= 3:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _build_sections(
        self,
        phi_spans: list,
        compliance_analysis: Optional[object],
    ) -> list[ComplianceReportSection]:
        """Build report sections from PHI data."""
        sections = []
        
        # Section 1: PHI Detection Summary
        category_counts = {}
        for span in phi_spans:
            cat = span.category.value if hasattr(span.category, 'value') else str(span.category)
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        summary_findings = [
            f"Detected {len(phi_spans)} PHI instances across {len(category_counts)} categories",
        ]
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1])[:5]:
            summary_findings.append(f"{cat}: {count} instances")
        
        sections.append(ComplianceReportSection(
            title="PHI Detection Summary",
            findings=summary_findings,
            recommendations=["Review all detected PHI for appropriate handling"],
            severity="INFO",
        ))
        
        # Section 2: Critical Violations (if any)
        critical_findings = []
        critical_recommendations = []
        
        if compliance_analysis:
            for analysis in compliance_analysis.phi_analyses:
                if analysis.is_violation and analysis.severity in ["CRITICAL", "HIGH"]:
                    critical_findings.append(f"{analysis.reasoning}")
                    if analysis.recommended_action:
                        critical_recommendations.append(analysis.recommended_action)
        
        if critical_findings:
            sections.append(ComplianceReportSection(
                title="Critical Violations",
                findings=critical_findings[:5],  # Limit to top 5
                recommendations=list(set(critical_recommendations))[:3],
                severity="CRITICAL",
            ))
        
        # Section 3: Recommendations
        general_recommendations = [
            "Review transcript for de-identification before sharing",
            "Apply Safe Harbor method: remove all 18 PHI identifiers",
            "Document any authorized disclosures in audit log",
        ]
        
        sections.append(ComplianceReportSection(
            title="General Recommendations",
            findings=["HIPAA compliance review required"],
            recommendations=general_recommendations,
            severity="INFO",
        ))
        
        return sections
