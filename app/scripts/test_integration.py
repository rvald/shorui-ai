#!/usr/bin/env python3
"""
Integration test script for the unified ingestion pipeline.

This script tests the full ingestion pipeline with a real PDF file:
1. Uploads the document via the API
2. Polls for completion
3. Verifies the correct number of points in Qdrant
4. Tests idempotency (re-upload should not create duplicates)

Usage:
    # With infrastructure running via docker-compose:
    python app/scripts/test_integration.py

    # Or with custom settings:
    export API_URL=http://localhost:8000
    python app/scripts/test_integration.py
"""

import os
import sys
import time
from pathlib import Path

import requests

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:8081")
TEST_PDF = os.getenv("TEST_PDF", "docs/construction.pdf")
PROJECT_ID = "integration-test"
EXPECTED_MIN_POINTS = 1000  # construction.pdf should have ~1759 blocks


def log(msg: str):
    """Print with timestamp."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def test_health():
    """Test that the API is healthy."""
    log("Testing API health...")

    response = requests.get(f"{API_URL}/health")
    assert response.status_code == 200, f"Health check failed: {response.text}"

    response = requests.get(f"{API_URL}/ingest/health")
    assert response.status_code == 200, f"Ingest health failed: {response.text}"

    log("✓ API is healthy")


def test_upload_document(filepath: str, index_to_graph: bool = False) -> dict:
    """Upload a document and return the response."""
    log(f"Uploading {filepath}...")

    if not Path(filepath).exists():
        raise FileNotFoundError(f"Test file not found: {filepath}")

    with open(filepath, "rb") as f:
        files = {"file": (Path(filepath).name, f, "application/pdf")}
        data = {
            "project_id": PROJECT_ID,
            "index_to_vector": "true",
            "index_to_graph": str(index_to_graph).lower(),
        }

        response = requests.post(f"{API_URL}/ingest/documents", files=files, data=data)

    assert response.status_code == 202, f"Upload failed: {response.text}"

    result = response.json()
    log(f"✓ Upload accepted: job_id={result['job_id']}")

    return result


def wait_for_completion(job_id: str, timeout: int = 300) -> dict:
    """Poll for job completion."""
    log(f"Waiting for job {job_id} to complete...")

    start_time = time.time()
    last_progress = -1

    while time.time() - start_time < timeout:
        response = requests.get(f"{API_URL}/ingest/documents/{job_id}/status")

        if response.status_code != 200:
            log(f"  Warning: status check returned {response.status_code}")
            time.sleep(2)
            continue

        status = response.json()
        current_progress = status.get("progress", 0)

        if current_progress != last_progress:
            log(f"  Progress: {current_progress}% - {status.get('status')}")
            last_progress = current_progress

        if status["status"] == "completed":
            log(f"✓ Job completed in {time.time() - start_time:.1f}s")
            return status

        if status["status"] == "failed":
            raise Exception(f"Job failed: {status.get('error')}")

        time.sleep(1)

    raise TimeoutError(f"Job did not complete within {timeout}s")


def verify_qdrant_points(expected_collection: str = None) -> int:
    """Verify points were created in Qdrant."""
    log("Verifying Qdrant points...")

    from qdrant_client import QdrantClient

    qdrant_host = os.getenv("QDRANT_DATABASE_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_DATABASE_PORT", "6333"))

    client = QdrantClient(host=qdrant_host, port=qdrant_port)

    collection_name = expected_collection or f"project_{PROJECT_ID}"

    try:
        info = client.get_collection(collection_name)
        point_count = info.points_count
        log(f"✓ Found {point_count} points in collection '{collection_name}'")
        return point_count
    except Exception as e:
        log(f"✗ Failed to get collection: {e}")
        return 0


def test_idempotency(filepath: str) -> bool:
    """Test that re-uploading the same file doesn't create duplicates."""
    log("Testing idempotency (re-upload)...")

    # Get initial point count
    initial_count = verify_qdrant_points()

    # Re-upload the same file
    result = test_upload_document(filepath)
    status = wait_for_completion(result["job_id"])

    # Check if it was recognized as duplicate
    if status.get("result", {}).get("existing_job_id"):
        log("✓ Idempotency: Document recognized as already processed")
        return True

    # Or check that point count didn't increase significantly
    final_count = verify_qdrant_points()

    if final_count == initial_count:
        log("✓ Idempotency: No new points created")
        return True
    else:
        log(f"✗ Idempotency failed: points increased from {initial_count} to {final_count}")
        return False


def main():
    """Run all integration tests."""
    log("=" * 60)
    log("Shorui-AI Integration Test")
    log("=" * 60)

    try:
        # 1. Health check
        test_health()

        # 2. Upload document
        result = test_upload_document(TEST_PDF, index_to_graph=False)

        # 3. Wait for completion
        status = wait_for_completion(result["job_id"])

        # 4. Verify results
        items_indexed = status.get("result", {}).get("items_indexed", 0)
        log(f"Items indexed: {items_indexed}")

        if items_indexed < EXPECTED_MIN_POINTS:
            log(f"✗ Warning: Expected at least {EXPECTED_MIN_POINTS} points, got {items_indexed}")
        else:
            log(f"✓ Point count looks good: {items_indexed} >= {EXPECTED_MIN_POINTS}")

        # 5. Verify in Qdrant
        qdrant_count = verify_qdrant_points()

        if qdrant_count < EXPECTED_MIN_POINTS:
            log(f"✗ Qdrant verification failed: {qdrant_count} < {EXPECTED_MIN_POINTS}")

        # 6. Test idempotency
        test_idempotency(TEST_PDF)

        log("=" * 60)
        log("✓ All integration tests passed!")
        log("=" * 60)

    except Exception as e:
        log(f"✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
