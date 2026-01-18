"""
Clinical Transcript analysis tool

This tool is used to analyze clinical transcripts and provide a summary of potential violations.
"""
import time
from langchain_core.tools import tool
from typing import Optional
from ..infrastructure.clients import ComplianceClient
from loguru import logger


class ClinicalTranscriptAnalysis:
    """
    Submit a clinical transcript for PHI detection and HIPAA compliance analysis.
    
    By default, waits for processing to complete and returns the full compliance report.
    Set wait_for_result=False to just submit and get a job_id for manual polling.
    
    Example:
        tool = ClinicalTranscriptAnalysis()
        result = tool.forward(file_path="/path/to/transcript.txt", project_id="my-project")
    """
    
    name = "analyze_clinical_transcript"
    description = (
        "Analyze a clinical transcript for HIPAA compliance. "
        "Detects PHI (Protected Health Information), identifies violations, "
        "and returns a complete compliance report with risk level and recommendations."
    )
    
    # Polling configuration
    POLL_INTERVAL_SECONDS = 2
    MAX_POLL_ATTEMPTS = 60  # 2 minutes max wait
    
    def __init__(self, client: Optional[ComplianceClient] = None):
        self._client = client or ComplianceClient()
    
    def forward(
        self,
        file_path: str,
        project_id: str,
        wait_for_result: bool = True,
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
        """Poll for job completion and return result."""
        for attempt in range(self.MAX_POLL_ATTEMPTS):
            try:
                status_result = self._client.get_transcript_job_status(job_id)
                status = status_result.get("status", "unknown")
                
                if status == "completed":
                    # Return the result directly - let the LLM format it
                    result = status_result.get("result", {})
                    return str(result)
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


@tool
def analyze_clinical_transcript(
    file_path: str,
    project_id: str = "default",
) -> str:
    """
    Analyze a clinical transcript for HIPAA compliance.
    
    Use this tool when a user provides a file path to a clinical transcript.
    Detects PHI (Protected Health Information) such as:
    - Patient names, SSNs, dates of birth
    - Medical record numbers, phone numbers
    - Addresses, email addresses
    
    Returns a compliance report with:
    - Risk level (LOW, MEDIUM, HIGH, CRITICAL)
    - List of PHI instances found
    - Remediation recommendations
    
    Args:
        file_path: Path to the clinical transcript file
        project_id: Project identifier (default: "default")
        
    Returns:
        Compliance report with PHI findings and recommendations
    """
    try: 
        clinical_analysis = ClinicalTranscriptAnalysis()
        result = clinical_analysis.forward(file_path, project_id)
        return result
    except Exception as e:
        logger.error(f"Error analyzing transcript: {e}")
        return (
            "ANALYSIS_ERROR: An error occurred while analyzing the transcript. "
            "You MUST tell the user there was an error and you cannot provide compliance guidance without the transcript. "
            "DO NOT use training data to answer. Suggest the user try again or contact support."
        )