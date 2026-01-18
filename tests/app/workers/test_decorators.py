import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings, HealthCheck
from app.workers.decorators import track_job_ledger

@pytest.fixture
def mock_ledger():
    with patch("app.workers.decorators.JobLedgerService") as mock:
        instance = mock.return_value
        instance.check_idempotency.return_value = None # Default: not processed
        instance.compute_content_hash.return_value = "hash-123"
        yield instance

class TestJobLedgerDecorator:
    
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        job_id=st.text(min_size=1),
        project_id=st.text(min_size=1),
        filename=st.text(min_size=1),
        content_text=st.text()
    )
    def test_ledger_success_flow(self, mock_ledger, job_id, project_id, filename, content_text):
        """Property test: Ensure ledger completes on success for any valid input."""
        mock_ledger.reset_mock()
        
        mock_func = MagicMock()
        mock_func.return_value = {"chunks_created": 42}

        
        @track_job_ledger(content_arg="text")
        def decorated_task(self, job_id, text, project_id, filename):
            return mock_func(self, job_id, text, project_id, filename)
            
        instance = MagicMock()
        result = decorated_task(instance, job_id=job_id, text=content_text, project_id=project_id, filename=filename)
        
        # Verify Ledger Flow
        mock_ledger.create_job.assert_called_once()
        mock_ledger.update_status.assert_called_with(job_id, "processing", progress=10)
        mock_ledger.complete_job.assert_called_once_with(job_id, items_indexed=42)
        mock_ledger.fail_job.assert_not_called()
        
        assert result == {"chunks_created": 42}

    def test_ledger_exception_flow(self, mock_ledger):
        """Unit test: Ensure ledger fails on exception."""
        
        @track_job_ledger(content_arg="text")
        def failing_task(self, job_id, text, project_id, filename):
            raise ValueError("Boom!")
            
        instance = MagicMock()
        with pytest.raises(ValueError):
            failing_task(instance, job_id="j1", text="t", project_id="p1", filename="f1")
            
        mock_ledger.create_job.assert_called_once()
        mock_ledger.fail_job.assert_called_once()
        
        # Check args robustly (positional or keyword)
        call_args = mock_ledger.fail_job.call_args
        # call_args is (args, kwargs)
        # We passed fail_job(job_id, error=...)
        # So job_id could be in args[0] OR kwargs['job_id'] depending on how it was called
        
        # In decorators.py: ledger_service.fail_job(job_id, error=str(e))
        # This is strictly 1 pos arg, 1 kwarg.
        
        pos_args, kw_args = call_args
        assert pos_args[0] == "j1"
        assert "Boom!" in str(kw_args['error'])
        mock_ledger.complete_job.assert_not_called()

    def test_idempotency_skip(self, mock_ledger):
        """Unit test: Ensure task is skipped if idempotency check passes."""
        
        mock_ledger.check_idempotency.return_value = {"status": "completed", "job_id": "old-job"}
        
        mock_func = MagicMock()
        
        @track_job_ledger(content_arg="text")
        def task(self, job_id, text, project_id, filename):
            return mock_func()
            
        instance = MagicMock()
        result = task(instance, job_id="j2", text="t", project_id="p1", filename="f1")
        
        assert result["status"] == "skipped"
        assert result["existing_job_id"] == "old-job"
        
        mock_ledger.create_job.assert_not_called()
        mock_func.assert_not_called()
