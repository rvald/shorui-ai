#!/usr/bin/env python3
"""
HIPAA Report Agent Example

Demonstrates how to use the ReActAgent with compliance tools to analyze
clinical transcripts and generate HIPAA compliance reports.

Run with:
    cd agents/react_agent
    python hipaa_report_example.py             # Uses mock model
    python hipaa_report_example.py --openai    # Uses OpenAI API (requires OPENAI_API_KEY)

Prerequisites:
    - Docker Compose services running (for real API calls with --openai)
    - OPENAI_API_KEY environment variable set (for --openai mode)
"""

import argparse
import sys
from pathlib import Path

# Add parent directory for package imports
sys.path.insert(0, str(Path(__file__).parent))
# Add project root for app imports
sys.path.insert(0, str(Path(__file__).parents[2]))

from agent import ReActAgent
from core.models import MockModel, ChatMessage, ChatMessageToolCall, ToolCallFunction
from tools import (
    AnalyzeClinicalTranscriptTool,
    GetComplianceReportTool,
    LookupHIPAARegulationTool,
    QueryAuditLogTool,
)


def create_mock_hipaa_responses():
    """
    Create mock LLM responses for the HIPAA report workflow.
    
    The mock simulates a realistic agent reasoning through:
    1. Analyzing a transcript
    2. Getting the compliance report
    3. Looking up relevant regulations
    4. Providing a final answer
    """
    return [
        # Step 1: Analyze the transcript
        ChatMessage(
            role="assistant",
            content=(
                "I need to analyze the clinical transcript for HIPAA compliance. "
                "First, I'll submit it for PHI detection and compliance analysis."
            ),
            tool_calls=[
                ChatMessageToolCall(
                    id="call_001",
                    function=ToolCallFunction(
                        name="analyze_clinical_transcript",
                        arguments={
                            "file_path": "/home/rvald/shorui-ai/sample_transcript.txt",
                            "project_id": "demo-project"
                        }
                    )
                )
            ]
        ),
        # Step 2: Get the compliance report
        ChatMessage(
            role="assistant",
            content=(
                "The transcript has been submitted. Now I'll retrieve the compliance report "
                "to see what PHI was detected and if there are any violations."
            ),
            tool_calls=[
                ChatMessageToolCall(
                    id="call_002",
                    function=ToolCallFunction(
                        name="get_compliance_report",
                        arguments={
                            "transcript_id": "transcript-001",
                            "project_id": "demo-project"
                        }
                    )
                )
            ]
        ),
        # Step 3: Look up regulations for SSN
        ChatMessage(
            role="assistant",
            content=(
                "I found SSN in the transcript which is a CRITICAL violation. "
                "Let me look up the specific HIPAA regulation for SSN handling."
            ),
            tool_calls=[
                ChatMessageToolCall(
                    id="call_003",
                    function=ToolCallFunction(
                        name="lookup_hipaa_regulation",
                        arguments={"query": "SSN disclosure de-identification"}
                    )
                )
            ]
        ),
        # Step 4: Final answer
        ChatMessage(
            role="assistant",
            content=(
                "I now have all the information needed to provide a comprehensive "
                "HIPAA compliance report."
            ),
            tool_calls=[
                ChatMessageToolCall(
                    id="call_004",
                    function=ToolCallFunction(
                        name="final_answer",
                        arguments={
                            "answer": """
## HIPAA Compliance Report

**Transcript:** patient_visit_001.txt  
**Risk Level:** HIGH  
**Requires Immediate Action:** YES

### PHI Detection Summary
- **Total PHI Found:** 4 instances
- **Violations:** 2

### Critical Findings

1. **SSN: 123-45-6789** (CRITICAL)
   - Regulation: 45 CFR 164.514(b)(2)(i)
   - Action Required: Remove or fully mask before any disclosure
   
2. **MRN: 12345678** (HIGH)
   - Regulation: 45 CFR 164.514(b)(2)(i)(L)
   - Action Required: Remove or replace with study-specific code

3. **Patient Name: John Smith** (MEDIUM - Context Dependent)
   - May be retained if for treatment/payment purposes
   - Recommendation: Review disclosure context

4. **DOB: 03/15/1985** (MEDIUM)
   - Regulation: 45 CFR 164.514(b)(2)(i)(C)
   - Action Required: Generalize to year only (1985)

### Remediation Summary
- 2 items require immediate redaction (SSN, MRN)
- Review context for patient name disclosure
- Reduce date specificity to year only
- Audit log entry created for compliance tracking
"""
                        }
                    )
                )
            ]
        ),
    ]


# Mock tools for demo mode (don't hit real APIs)
class MockAnalyzeTool:
    """Mock analyze tool that returns simulated results."""
    name = "analyze_clinical_transcript"
    description = AnalyzeClinicalTranscriptTool.description
    inputs = AnalyzeClinicalTranscriptTool.inputs
    output_type = "string"
    
    def forward(self, file_path: str, project_id: str) -> str:
        return f"Transcript submitted. Job ID: transcript-001. Status: completed"
    
    def __call__(self, **kwargs):
        return self.forward(**kwargs)
    
    def to_prompt_description(self):
        return f"Tool: {self.name}\nDescription: {self.description}"


class MockGetReportTool:
    """Mock get report tool that returns simulated results."""
    name = "get_compliance_report"
    description = GetComplianceReportTool.description
    inputs = GetComplianceReportTool.inputs
    output_type = "string"
    
    def forward(self, transcript_id: str, project_id: str = None) -> str:
        return """Compliance Report for transcript-001:
- Risk Level: HIGH
- PHI Detected: 4
- Violations: 2

Key Findings:
- SSN detected: CRITICAL violation (45 CFR 164.514(b)(2)(i))
- MRN detected: HIGH violation
- Patient name: Context-dependent
- DOB: Requires generalization"""
    
    def __call__(self, **kwargs):
        return self.forward(**kwargs)
    
    def to_prompt_description(self):
        return f"Tool: {self.name}\nDescription: {self.description}"


class MockLookupRegulationTool:
    """Mock regulation lookup tool."""
    name = "lookup_hipaa_regulation"
    description = LookupHIPAARegulationTool.description
    inputs = LookupHIPAARegulationTool.inputs
    output_type = "string"
    
    def forward(self, query: str, top_k: int = 3) -> str:
        return """HIPAA Regulations for 'SSN disclosure de-identification':

1. [164.514(b)(2)(i)] Safe Harbor De-identification Method
   The following identifiers of the individual must be removed:
   Social Security numbers. SSN is considered a direct identifier that
   can uniquely identify an individual and must be removed for Safe Harbor
   de-identification compliance.
   Source: 45 CFR 164.514 (relevance: 0.95)

2. [164.514(a)] Standard: De-identification of Protected Health Information
   Health information that does not identify an individual is not
   individually identifiable health information and is not PHI.
   Source: 45 CFR 164.514 (relevance: 0.88)"""
    
    def __call__(self, **kwargs):
        return self.forward(**kwargs)
    
    def to_prompt_description(self):
        return f"Tool: {self.name}\nDescription: {self.description}"


def run_mock_example():
    """Run a mock HIPAA report workflow."""
    print("\n" + "="*70)
    print("HIPAA Report Agent - Mock Demo")
    print("="*70)
    print("\nThis demo shows how the agent would analyze a clinical transcript")
    print("and generate a HIPAA compliance report.\n")
    
    model = MockModel(create_mock_hipaa_responses())
    
    agent = ReActAgent(
        tools=[
            MockAnalyzeTool(),
            MockGetReportTool(),
            MockLookupRegulationTool(),
        ],
        model=model,
        max_steps=6,
        verbose=True,
    )
    
    task = (
        "Analyze the clinical transcript at /home/rvald/shorui-ai/sample_transcript.txt "
        "for HIPAA compliance. Identify any PHI violations and provide a detailed "
        "compliance report with specific regulation citations."
    )
    
    result = agent.run(task)
    
    print(f"\n{'='*70}")
    print("FINAL REPORT")
    print("="*70)
    print(result.output)
    print(f"\n{'='*70}")
    print(f"✅ Success: {result.success}")
    print(f"📊 Steps taken: {len(result.steps)}")
    print("="*70)
    
    return result


def run_live_example():
    """Run with OpenAI API and real Shorui tools."""
    print("\n" + "="*70)
    print("HIPAA Report Agent - Live Mode (OpenAI)")
    print("="*70)
    
    try:
        from core.models import OpenAIModel
        model = OpenAIModel(model_id="gpt-4o-mini")
    except ValueError as e:
        print(f"Error: {e}")
        print("Set OPENAI_API_KEY environment variable.")
        return None
    except ImportError:
        print("Install openai package: pip install openai")
        return None
    
    # Use real tools (requires backend services)
    agent = ReActAgent(
        tools=[
            AnalyzeClinicalTranscriptTool(),
            GetComplianceReportTool(),
            LookupHIPAARegulationTool(),
            QueryAuditLogTool(),
        ],
        model=model,
        max_steps=8,
        verbose=True,
    )
    
    task = (
        "Analyze the clinical transcript at /home/rvald/shorui-ai/sample_transcript.txt "
        "for HIPAA compliance. Identify any PHI violations and provide a detailed "
        "compliance report with specific regulation citations."
    )
    
    result = agent.run(task)
    
    print(f"\n{'='*70}")
    print("FINAL REPORT")
    print("="*70)
    print(result.output)
    print(f"\n{'='*70}")
    print(f"✅ Success: {result.success}")
    print(f"📊 Steps taken: {len(result.steps)}")
    print("="*70)
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="HIPAA Report Agent Example",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python hipaa_report_example.py          # Run mock demo
  python hipaa_report_example.py --openai # Run with OpenAI (requires API key + backend)
        """
    )
    parser.add_argument(
        "--openai", 
        action="store_true", 
        help="Use OpenAI API with real backend services"
    )
    args = parser.parse_args()
    
    if args.openai:
        run_live_example()
    else:
        run_mock_example()


if __name__ == "__main__":
    main()
