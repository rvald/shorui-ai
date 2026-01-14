"""
Compliance Tools

Tools for clinical transcript analysis, compliance reports, and audit logging.
All HTTP calls are synchronous - safe to use from any context.
"""
from __future__ import annotations

import time
import json
from typing import Any, Optional

# Support both package import and direct script execution
try:
    from ..core.tools import Tool
    from ..infrastructure.http_clients import IngestionClient
except ImportError:
    from core.tools import Tool
    from infrastructure.http_clients import IngestionClient


class AnalyzeClinicalTranscriptTool(Tool):
    """
    Submit a clinical transcript for PHI detection and HIPAA compliance analysis.
    
    By default, waits for processing to complete and returns the full compliance report.
    Set wait_for_result=False to just submit and get a job_id for manual polling.
    
    Example:
        tool = AnalyzeClinicalTranscriptTool()
        # Waits for completion (recommended)
        result = tool(file_path="/path/to/transcript.txt", project_id="my-project")
        
        # Just submit, don't wait
        result = tool(file_path="...", project_id="...", wait_for_result=False)
    """
    
    name = "analyze_clinical_transcript"
    description = (
        "Analyze a clinical transcript for HIPAA compliance. "
        "Detects PHI (Protected Health Information), identifies violations, "
        "and returns a complete compliance report with risk level and recommendations. "
        "By default waits for processing to complete (may take 5-30 seconds)."
    )
    inputs = {
        "file_path": {
            "type": "string",
            "description": "Path to the clinical transcript file (.txt)"
        },
        "project_id": {
            "type": "string",
            "description": "Project identifier for multi-tenancy"
        },
        "wait_for_result": {
            "type": "boolean",
            "description": "If true (default), wait for analysis to complete and return full report. If false, return immediately with job_id.",
            "nullable": True,
        }
    }
    output_type = "string"
    
    # Polling configuration
    POLL_INTERVAL_SECONDS = 2
    MAX_POLL_ATTEMPTS = 60  # 2 minutes max wait
    
    def __init__(self, client: Optional[IngestionClient] = None):
        self._client = client or IngestionClient()
    
    def forward(
        self,
        file_path: str,
        project_id: str,
        wait_for_result: Optional[bool] = True,
    ) -> str:
        """Submit transcript for analysis, optionally waiting for completion."""
        try:
            # Submit the transcript (sync call)
            result = self._client.analyze_transcript(
                file_path=file_path,
                project_id=project_id,
            )
            
            job_id = result.get("job_id", "unknown")
            
            # If not waiting, return immediately
            if not wait_for_result:
                return f"Transcript submitted. Job ID: {job_id}. Use get_compliance_report to check status."
            
            # Poll until complete (sync)
            return self._poll_until_complete(job_id)
            
        except FileNotFoundError:
            return f"Error: File not found: {file_path}"
        except Exception as e:
            return f"Error analyzing transcript: {e}"
    
    def _poll_until_complete(self, job_id: str) -> str:
        """Poll for job completion and return formatted result."""
        for attempt in range(self.MAX_POLL_ATTEMPTS):
            try:
                status_result = self._client.get_transcript_job_status(job_id)
                status = status_result.get("status", "unknown")
                
                if status == "completed":
                    return self._format_completed_result(job_id, status_result)
                elif status == "failed":
                    error = status_result.get("error", "Unknown error")
                    return f"Analysis failed for job {job_id}: {error}"
                
                # Still processing, wait and retry
                time.sleep(self.POLL_INTERVAL_SECONDS)
                
            except Exception as e:
                # Network error, retry
                if attempt < self.MAX_POLL_ATTEMPTS - 1:
                    time.sleep(self.POLL_INTERVAL_SECONDS)
                else:
                    return f"Error polling job status: {e}"
        
        return f"Timeout: Job {job_id} still processing after {self.MAX_POLL_ATTEMPTS * self.POLL_INTERVAL_SECONDS} seconds."
    
    def _format_completed_result(self, job_id: str, status_result: dict) -> str:
        """Format the completed analysis result definition into a rich markdown report."""
        result = status_result.get("result", {})
        
        transcript_id = result.get("transcript_id", job_id)
        phi_detected = result.get("phi_detected", 0)
        processing_time = result.get("processing_time_ms", 0)
        
        # Get compliance report if available
        report = result.get("compliance_report", {})
        
        # Handle case where report is flattened or missing standard keys
        if not report:
            # Fallback for alternative result structures
            risk_level = result.get("risk_level", "UNKNOWN")
            total_violations = result.get("violations", 0)
            sections = []
            
            # Try to build sections from 'findings' dict if present
            findings_dict = result.get("findings", {})
            if isinstance(findings_dict, dict):
                for title, data in findings_dict.items():
                    content = []
                    if isinstance(data, dict):
                        for k, v in data.items():
                            content.append(f"{k}: {v}")
                    elif isinstance(data, list):
                        content = data
                    else:
                        content = [str(data)]
                    
                    sections.append({
                        "title": title.replace("_", " ").title(),
                        "findings": content,
                        "severity": "INFO"
                    })
            
            # Add specific findings lists if they exist at top level
            if result.get("recommendations"):
                sections.append({
                    "title": "Recommendations",
                    "findings": [],
                    "recommendations": result.get("recommendations"),
                    "severity": "INFO"
                })
        else:
            # Standard ComplianceReport structure
            risk_level = report.get("overall_risk_level", "UNKNOWN")
            total_violations = report.get("total_violations", 0)
            sections = report.get("sections", [])

        # Start building Markdown output
        output = f"## 🩺 HIPAA Compliance Report\n\n"
        
        # Risk Badge
        risk_color = {
            "CRITICAL": "🔴", 
            "HIGH": "🟠", 
            "MEDIUM": "🟡", 
            "LOW": "🟢", 
            "UNKNOWN": "⚪"
        }.get(risk_level, "⚪")
        
        output += f"### Executive Summary\n\n"
        output += f"| Metric | Value |\n"
        output += f"| :--- | :--- |\n"
        output += f"| **Risk Level** | {risk_color} **{risk_level}** |\n"
        output += f"| **PHI Instances** | {phi_detected} |\n"
        output += f"| **Violations** | {total_violations} |\n"
        output += f"| **Transcript ID** | `{transcript_id}` |\n\n"

        # High level alert if High/Critical
        if risk_level in ["CRITICAL", "HIGH"]:
            output += f"> [!WARNING]\n"
            output += f"> This transcript contains **{risk_level}** severity compliance violations. Immediate remediation is required before sharing.\n\n"
        
        # Findings Sections
        if sections:
            output += f"### Detailed Findings\n"
            
            for section in sections:
                # Handle both object and dict access
                if isinstance(section, dict):
                    title = section.get("title", "Section")
                    severity = section.get("severity", "INFO")
                    findings = section.get("findings", [])
                    recommendations = section.get("recommendations", [])
                else:
                    # Assume object
                    title = getattr(section, "title", "Section")
                    severity = getattr(section, "severity", "INFO")
                    findings = getattr(section, "findings", [])
                    recommendations = getattr(section, "recommendations", [])

                # Section Header
                icon = "📝"
                if severity == "CRITICAL": icon = "🚫"
                elif severity == "HIGH": icon = "⚠️"
                
                output += f"\n#### {icon} {title}\n"
                
                if findings:
                    for finding in findings:
                        output += f"- {finding}\n"
                
                if recommendations:
                    output += "\n**Recommendations:**\n"
                    for rec in recommendations:
                        output += f"- ✅ {rec}\n"
        
        # Processing Info Footer
        output += f"\n---\n*Analysis completed in {processing_time/1000:.2f}s*"
        
        return output


class GetComplianceReportTool(Tool):
    """
    Retrieve the HIPAA compliance report for an analyzed transcript.
    
    Example:
        tool = GetComplianceReportTool()
        result = tool(transcript_id="abc-123")
    """
    
    name = "get_compliance_report"
    description = (
        "Get the HIPAA compliance report for a transcript. "
        "Returns PHI detection summary, risk assessment, and remediation recommendations."
    )
    inputs = {
        "transcript_id": {
            "type": "string",
            "description": "ID of the analyzed transcript"
        },
        "project_id": {
            "type": "string",
            "description": "Project identifier",
            "nullable": True,
        }
    }
    output_type = "string"
    
    def __init__(self, client: Optional[IngestionClient] = None):
        self._client = client or IngestionClient()
    
    def forward(
        self,
        transcript_id: str,
        project_id: Optional[str] = None,
    ) -> str:
        """Get compliance report."""
        try:
            result = self._client.get_compliance_report(
                transcript_id=transcript_id,
                project_id=project_id or "default",
            )
            
            # Extract basic metrics
            risk_level = result.get("overall_risk_level", result.get("risk_level", "UNKNOWN"))
            phi_detected = result.get("total_phi_detected", result.get("phi_detected", 0))
            violations = result.get("total_violations", result.get("violations", 0))

            output = ["## 🩺 HIPAA Compliance Report\n"]
            
            # Summary
            output.append("### Executive Summary\n")
            output.append("| Metric | Value |")
            output.append("| :--- | :--- |")
            output.append(f"| **Risk Level** | **{risk_level}** |")
            output.append(f"| **PHI Detected** | {phi_detected} |")
            output.append(f"| **Violations** | {violations} |")
            output.append(f"| **Transcript ID** | `{transcript_id}` |\n")

            if risk_level in ["CRITICAL", "HIGH"]:
                output.append("> [!WARNING]")
                output.append(f"> **{risk_level}** severity violations detected. Immediate remediation required.\n")

            # Findings
            # Handle list of section objects OR dict of findings
            sections = result.get("sections", [])
            findings_dict = result.get("findings", {})

            if sections:
                output.append("### Detailed Findings")
                for section in sections:
                    # Robust access to dict or object
                    if isinstance(section, dict):
                        title = section.get("title", "Section")
                        sev = section.get("severity", "INFO")
                        items = section.get("findings", [])
                    else:
                        title = getattr(section, "title", "Section")
                        sev = getattr(section, "severity", "INFO")
                        items = getattr(section, "findings", [])
                        
                    output.append(f"\n#### {title} ({sev})")
                    for item in items:
                        output.append(f"- {item}")
            
            elif findings_dict and isinstance(findings_dict, dict):
                output.append("### Detailed Findings")
                for title, content in findings_dict.items():
                    title_fmt = title.replace("_", " ").title()
                    output.append(f"\n#### 📝 {title_fmt}")
                    
                    if isinstance(content, list):
                        for item in content:
                            output.append(f"- {item}")
                    elif isinstance(content, dict):
                        for k, v in content.items():
                            output.append(f"- **{k}**: {v}")
                    else:
                         output.append(f"- {content}")
                         
            return "\n".join(output)
            
        except Exception as e:
            return f"Error retrieving report: {str(e)}"


class QueryAuditLogTool(Tool):
    """
    Search the HIPAA audit logs.
    
    Example:
        tool = QueryAuditLogTool()
        result = tool(event_type="PHI_ACCESSED", limit=10)
    """
    
    name = "query_audit_log"
    description = (
        "Search the HIPAA audit log for compliance events. "
        "Filter by event type: PHI_DETECTED, PHI_ACCESSED, PHI_EXPORTED, "
        "COMPLIANCE_DECISION, REPORT_GENERATED, USER_LOGIN."
    )
    inputs = {
        "event_type": {
            "type": "string",
            "description": "Filter by event type (e.g., 'PHI_DETECTED', 'PHI_ACCESSED')",
            "nullable": True,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of events to return (default: 20)",
            "nullable": True,
        }
    }
    output_type = "string"
    
    def __init__(self, client: Optional[IngestionClient] = None):
        self._client = client or IngestionClient()
    
    def forward(
        self,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Query audit log."""
        try:
            result = self._client.query_audit_log(
                event_type=event_type,
                limit=limit or 20,
            )
            
            events = result.get("events", [])
            total = result.get("total", len(events))
            
            if not events:
                return f"No audit events found" + (f" for type '{event_type}'" if event_type else "")
            
            output = f"Audit Log ({total} events):\n"
            for event in events[:10]:  # Limit display
                etype = event.get("event_type", "UNKNOWN")
                desc = event.get("description", "")[:60]
                timestamp = event.get("timestamp", "")[:19]  # Truncate to datetime
                output += f"- [{timestamp}] {etype}: {desc}\n"
            
            if total > 10:
                output += f"... and {total - 10} more events"
            
            return output
            
        except Exception as e:
            return f"Error querying audit log: {e}"


class LookupHIPAARegulationTool(Tool):
    """
    Look up specific HIPAA regulation text by topic or section ID.
    
    Uses semantic search over ingested HIPAA regulations to find
    relevant sections for compliance analysis.
    
    Example:
        tool = LookupHIPAARegulationTool()
        result = tool(query="SSN disclosure requirements")
        # Returns formatted regulation text with citations
    """
    
    name = "lookup_hipaa_regulation"
    description = (
        "Search HIPAA regulation text by topic or section ID. "
        "Use this to find specific regulatory requirements for compliance decisions. "
        "Examples: 'SSN disclosure', 'de-identification Safe Harbor', '164.514'."
    )
    inputs = {
        "query": {
            "type": "string",
            "description": (
                "Topic or section ID to search for. Can be a PHI type (e.g., 'SSN'), "
                "a concept (e.g., 'de-identification'), or a section number (e.g., '164.514')"
            )
        },
        "top_k": {
            "type": "integer",
            "description": "Number of regulation sections to return (default: 3)",
            "nullable": True,
        }
    }
    output_type = "string"
    
    def __init__(self, retriever=None):
        """
        Initialize the tool.
        
        Args:
            retriever: Optional RegulationRetriever instance. If None, creates one lazily.
        """
        self._retriever = retriever
        self._retriever_class = None  # Lazy import to avoid circular deps
    
    def _get_retriever(self):
        """Get or create the RegulationRetriever instance."""
        if self._retriever is None:
            # Lazy import to avoid circular dependencies
            if self._retriever_class is None:
                try:
                    from app.compliance.services.regulation_retriever import RegulationRetriever
                    self._retriever_class = RegulationRetriever
                except ImportError:
                    # Return a mock if the service is not available
                    return None
            self._retriever = self._retriever_class()
        return self._retriever
    
    def forward(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> str:
        """Look up HIPAA regulation text."""
        retriever = self._get_retriever()
        
        if retriever is None:
            return (
                "Error: RegulationRetriever service not available. "
                "Ensure HIPAA regulations have been ingested into Qdrant."
            )
        
        top_k = top_k or 3
        
        try:
            # Check if query looks like a section ID (e.g., "164.514")
            if query.replace(".", "").replace("-", "").isdigit() or query.startswith("164."):
                regulations = retriever.retrieve_by_section(query, top_k=top_k)
            else:
                # Semantic search by topic
                regulations = retriever._search(query, top_k=top_k)
            
            if not regulations:
                return f"No HIPAA regulations found for query: '{query}'"
            
            # Format results for the agent
            output = f"HIPAA Regulations for '{query}':\n\n"
            
            for i, reg in enumerate(regulations, 1):
                section_id = reg.get("section_id", "Unknown")
                title = reg.get("title", "")
                text = reg.get("text", "")[:400]  # Truncate long text
                source = reg.get("source", "")
                score = reg.get("relevance_score", 0)
                
                output += f"{i}. [{section_id}] {title}\n"
                output += f"   {text}"
                if len(reg.get("text", "")) > 400:
                    output += "..."
                output += f"\n   Source: {source} (relevance: {score:.2f})\n\n"
            
            return output.strip()
            
        except Exception as e:
            return f"Error looking up regulation: {e}"


class QueryHIPAARegulationsRAGTool(Tool):
    """
    Query HIPAA regulations using RAG (Retrieval-Augmented Generation).
    
    Uses the /rag/query endpoint which:
    1. Retrieves relevant regulation text from Qdrant
    2. Generates a grounded answer using LLM with the retrieved context
    3. Returns the answer with source citations
    
    This is preferred over LookupHIPAARegulationTool because:
    - Answers are grounded in actual regulation text
    - LLM synthesizes information from multiple sources
    - Sources are cited for verification
    
    Example:
        tool = QueryHIPAARegulationsRAGTool()
        result = tool(question="What are the 18 HIPAA identifiers?", project_id="default")
        # Returns grounded answer with sources
    """
    
    name = "query_hipaa_regulations"
    description = (
        "Ask a question about HIPAA regulations and get a grounded answer with sources. "
        "The answer is generated based on actual HIPAA regulation text, not general knowledge. "
        "Use for questions about Privacy Rule, Security Rule, de-identification, PHI handling, "
        "breach notification, patient rights, and other HIPAA topics."
    )
    inputs = {
        "question": {
            "type": "string",
            "description": "The HIPAA-related question to answer"
        },
        "project_id": {
            "type": "string",
            "description": "Project identifier (use 'default' if unsure)",
            "nullable": True,
        },
        "num_sources": {
            "type": "integer",
            "description": "Number of regulation sources to retrieve (default: 5)",
            "nullable": True,
        }
    }
    output_type = "string"
    
    def __init__(self, client=None):
        """
        Initialize the tool.
        
        Args:
            client: Optional RAGClient instance. If None, creates one lazily.
        """
        self._client = client
    
    def _get_client(self):
        """Get or create the RAGClient instance."""
        if self._client is None:
            try:
                from ..infrastructure.http_clients import RAGClient
            except ImportError:
                from infrastructure.http_clients import RAGClient
            self._client = RAGClient()
        return self._client
    
    def forward(
        self,
        question: str,
        project_id: Optional[str] = None,
        num_sources: Optional[int] = None,
    ) -> str:
        """Query HIPAA regulations and get a grounded answer."""
        client = self._get_client()
        
        # Always use hipaa_regulations collection for this tool
        # (ignore project_id - this tool is specifically for HIPAA regulations)
        collection = "hipaa_regulations"
        num_sources = num_sources or 5
        
        try:
            # Call RAG endpoint with hipaa_regulations collection
            result = client.query(
                query=question,
                project_id=collection,  # Uses hipaa_regulations
                k=num_sources,
                backend="openai",
            )
            
            answer = result.get("answer", "No answer generated")
            sources = result.get("sources", [])
            
            # Format response with sources
            output = f"## Answer\n\n{answer}\n\n"
            
            if sources:
                output += "## Sources\n\n"
                for i, source in enumerate(sources, 1):
                    filename = source.get("filename", "Unknown")
                    page = source.get("page_num", "?")
                    preview = source.get("content_preview", "")[:150]
                    output += f"{i}. **{filename}** (page {page})\n"
                    output += f"   {preview}...\n\n"
            
            return output.strip()
            
        except Exception as e:
            return f"Error querying HIPAA regulations: {e}"
