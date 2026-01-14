#!/usr/bin/env python3
"""
End-to-End Test Suite for Shorui-AI

Tests the complete application flow:
1. Health checks for all services
2. Document ingestion (HIPAA regulations)
3. RAG query with citations
4. Clinical transcript analysis with PHI detection
5. Agent conversation flow

Usage:
    uv run poe e2e           # Run all e2e tests
    uv run poe e2e-quick     # Run quick smoke tests only

Prerequisites:
    - Docker services running: uv run poe start
    - HIPAA regulations seeded: uv run poe seed
"""

import os
import sys
import time
import json
import requests
from pathlib import Path

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:8082")
PROJECT_ID = "e2e-test"
TIMEOUT = 120


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def log(msg: str, color: str = ""):
    """Print with timestamp and optional color."""
    timestamp = time.strftime("%H:%M:%S")
    if color:
        print(f"{color}[{timestamp}] {msg}{Colors.RESET}")
    else:
        print(f"[{timestamp}] {msg}")


def success(msg: str):
    log(f"✓ {msg}", Colors.GREEN)


def error(msg: str):
    log(f"✗ {msg}", Colors.RED)


def info(msg: str):
    log(f"→ {msg}", Colors.BLUE)


def section(title: str):
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")


# =============================================================================
# Health Checks
# =============================================================================

def test_health_checks():
    """Test that all services are healthy."""
    section("1. Health Checks")
    
    endpoints = [
        ("/health", "Main API"),
        ("/ingest/health", "Ingestion Service"),
        ("/rag/health", "RAG Service"),
    ]
    
    all_healthy = True
    for endpoint, name in endpoints:
        try:
            response = requests.get(f"{API_URL}{endpoint}", timeout=10)
            if response.status_code == 200:
                success(f"{name} is healthy")
            else:
                error(f"{name} returned {response.status_code}")
                all_healthy = False
        except requests.exceptions.RequestException as e:
            error(f"{name} unreachable: {e}")
            all_healthy = False
    
    return all_healthy


# =============================================================================
# RAG Query Tests
# =============================================================================

def test_rag_search():
    """Test RAG search functionality."""
    section("2. RAG Search")
    
    query = "What are the 18 HIPAA identifiers?"
    info(f"Searching: '{query}'")
    
    try:
        response = requests.get(
            f"{API_URL}/rag/search",
            params={"query": query, "project_id": "default", "k": 3},
            timeout=30,
        )
        
        if response.status_code == 200:
            results = response.json()
            result_count = len(results.get("results", []))
            success(f"Search returned {result_count} results")
            
            if result_count > 0:
                top_result = results["results"][0]
                info(f"Top result score: {top_result.get('score', 'N/A'):.3f}")
                return True
            else:
                log("Warning: No results found. Have you run 'uv run poe seed'?", Colors.YELLOW)
                return False
        else:
            error(f"Search failed: {response.status_code} - {response.text[:100]}")
            return False
            
    except requests.exceptions.RequestException as e:
        error(f"Search request failed: {e}")
        return False


def test_rag_query():
    """Test full RAG query with LLM answer generation."""
    section("3. RAG Query (with LLM)")
    
    query = "What is the minimum necessary standard in HIPAA?"
    info(f"Querying: '{query}'")
    
    try:
        response = requests.post(
            f"{API_URL}/rag/query",
            json={
                "query": query,
                "project_id": "default",
                "k": 3,
            },
            timeout=60,
        )
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            
            if answer:
                success(f"Generated answer ({len(answer)} chars)")
                info(f"Sources used: {len(sources)}")
                # Print first 200 chars of answer
                print(f"\n   Answer preview: {answer[:200]}...")
                return True
            else:
                error("Empty answer received")
                return False
        else:
            error(f"Query failed: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        error(f"Query request failed: {e}")
        return False


# =============================================================================
# Transcript Analysis Tests
# =============================================================================

def test_transcript_analysis():
    """Test clinical transcript PHI detection."""
    section("4. Clinical Transcript Analysis")
    
    # Use sample transcript if available
    transcript_path = Path("sample_transcript.txt")
    
    if not transcript_path.exists():
        log("sample_transcript.txt not found, using inline test data", Colors.YELLOW)
        transcript_text = """
        Patient Name: John Smith
        DOB: 03/15/1985
        SSN: 123-45-6789
        MRN: 12345678
        
        Doctor: How are you feeling today?
        Patient: I've been experiencing headaches.
        """
        filename = "e2e_test_transcript.txt"
    else:
        transcript_text = transcript_path.read_text()
        filename = "sample_transcript.txt"
    
    info(f"Analyzing transcript ({len(transcript_text)} chars)")
    
    try:
        # Use multipart form upload (matching the actual API)
        files = {"file": (filename, transcript_text.encode("utf-8"), "text/plain")}
        data = {"project_id": PROJECT_ID}
        
        response = requests.post(
            f"{API_URL}/ingest/clinical-transcripts",
            files=files,
            data=data,
            timeout=TIMEOUT,
        )
        
        if response.status_code in (200, 202):
            result = response.json()
            job_id = result.get("job_id")
            
            if job_id:
                success(f"Transcript submitted: job_id={job_id}")
                
                # Poll for completion
                info("Waiting for analysis...")
                return wait_for_transcript_job(job_id)
            else:
                # Synchronous response
                phi_count = result.get("phi_detected", 0)
                success(f"PHI detected: {phi_count} instances")
                return True
        else:
            error(f"Transcript submission failed: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        error(f"Transcript request failed: {e}")
        return False


def wait_for_transcript_job(job_id: str, timeout: int = 120) -> bool:
    """Poll for transcript analysis completion."""
    start = time.time()
    
    while time.time() - start < timeout:
        try:
            response = requests.get(
                f"{API_URL}/ingest/clinical-transcripts/jobs/{job_id}",
                timeout=10,
            )
            
            if response.status_code == 200:
                status = response.json()
                state = status.get("status", "unknown")
                
                if state == "completed":
                    phi_count = status.get("result", {}).get("phi_detected", 0)
                    success(f"Analysis complete - PHI detected: {phi_count}")
                    return True
                elif state == "failed":
                    error(f"Analysis failed: {status.get('error')}")
                    return False
                else:
                    time.sleep(2)
            else:
                time.sleep(2)
                
        except requests.exceptions.RequestException:
            time.sleep(2)
    
    error(f"Timeout waiting for transcript analysis")
    return False


# =============================================================================
# Agent Tests
# =============================================================================

def test_agent_session():
    """Test agent conversation flow."""
    section("5. Agent Conversation")
    
    # Create session
    info("Creating agent session...")
    
    try:
        response = requests.post(f"{API_URL}/agent/sessions", timeout=10)
        
        if response.status_code != 200:
            error(f"Failed to create session: {response.status_code}")
            return False
        
        session_id = response.json().get("session_id")
        success(f"Session created: {session_id[:8]}...")
        
        # Send a message
        message = "What are the penalties for HIPAA violations?"
        info(f"Sending message: '{message}'")
        
        response = requests.post(
            f"{API_URL}/agent/sessions/{session_id}/messages",
            data={"message": message, "project_id": "default"},
            timeout=90,
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("content", "")
            steps = result.get("steps", [])
            
            success(f"Agent responded ({len(content)} chars, {len(steps)} steps)")
            
            if content:
                print(f"\n   Response preview: {content[:200]}...")
            
            return True
        else:
            error(f"Agent message failed: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        error(f"Agent request failed: {e}")
        return False


# =============================================================================
# Quick Smoke Test
# =============================================================================

def run_smoke_tests():
    """Run quick smoke tests (health only)."""
    section("Smoke Tests")
    
    results = {
        "health": test_health_checks(),
    }
    
    return results


# =============================================================================
# Full E2E Test Suite
# =============================================================================

def run_full_e2e():
    """Run complete end-to-end test suite."""
    print(f"\n{Colors.BOLD}🧪 Shorui-AI End-to-End Test Suite{Colors.RESET}")
    print(f"API URL: {API_URL}\n")
    
    results = {}
    
    # 1. Health checks
    results["health"] = test_health_checks()
    if not results["health"]:
        error("Health checks failed - aborting remaining tests")
        return results
    
    # 2. RAG Search
    results["rag_search"] = test_rag_search()
    
    # 3. RAG Query (if search worked)
    if results["rag_search"]:
        results["rag_query"] = test_rag_query()
    else:
        log("Skipping RAG query (search failed)", Colors.YELLOW)
        results["rag_query"] = False
    
    # 4. Transcript Analysis
    results["transcript"] = test_transcript_analysis()
    
    # 5. Agent
    results["agent"] = test_agent_session()
    
    # Summary
    section("Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test, passed_test in results.items():
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if passed_test else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  {test}: {status}")
    
    print()
    if passed == total:
        success(f"All {total} tests passed! 🎉")
    else:
        error(f"{passed}/{total} tests passed")
    
    return results


# =============================================================================
# Main
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Shorui-AI E2E Tests")
    parser.add_argument("--quick", action="store_true", help="Run quick smoke tests only")
    parser.add_argument("--url", default=None, help="API base URL")
    args = parser.parse_args()
    
    global API_URL
    if args.url:
        API_URL = args.url
    
    if args.quick:
        results = run_smoke_tests()
    else:
        results = run_full_e2e()
    
    # Exit with error code if any test failed
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
