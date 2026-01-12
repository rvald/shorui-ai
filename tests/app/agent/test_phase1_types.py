"""
Unit Tests for Phase 1 Agent Modules

Tests for:
- app/agent/routing/types.py (RouteType, ExecutionPlan)
- app/agent/execution/base.py (ExecutionResult, BaseExecutor)
- app/agent/session/types.py (Message, Session)
- agents/react_agent/core/models.py (AsyncModel, OpenAIModel async)

Run with:
    cd /home/rvald/shorui-ai
    python -m pytest tests/app/agent/test_phase1_types.py -v
"""

import pytest
import asyncio
import json
from datetime import datetime
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

# Routing types
from app.agent.routing.types import RouteType, ExecutionPlan

# Execution types
from app.agent.execution.base import ExecutionResult, BaseExecutor

# Session types
from app.agent.session.types import Message, Session


# =============================================================================
# Routing Types Tests
# =============================================================================

class TestRouteType:
    """Tests for RouteType enum."""
    
    def test_route_type_values(self):
        """Test all RouteType enum values exist."""
        assert RouteType.DIRECT_TOOL == "direct_tool"
        assert RouteType.PROMPT_CHAIN == "prompt_chain"
        assert RouteType.LIGHT_AGENT == "light_agent"
        assert RouteType.FULL_AGENT == "full_agent"
    
    def test_route_type_is_string_enum(self):
        """Test RouteType is a string enum."""
        assert isinstance(RouteType.DIRECT_TOOL.value, str)
        assert str(RouteType.DIRECT_TOOL) == "RouteType.DIRECT_TOOL"


class TestExecutionPlan:
    """Tests for ExecutionPlan Pydantic model."""
    
    def test_minimal_execution_plan(self):
        """Test creating ExecutionPlan with only required fields."""
        plan = ExecutionPlan(
            route_type=RouteType.LIGHT_AGENT,
            executor_name="react"
        )
        
        assert plan.route_type == RouteType.LIGHT_AGENT
        assert plan.executor_name == "react"
        assert plan.model_id == "gpt-4o-mini"  # Default
        assert plan.max_steps == 5  # Default
        assert plan.confidence == 1.0  # Default
    
    def test_full_execution_plan(self):
        """Test creating ExecutionPlan with all fields."""
        plan = ExecutionPlan(
            route_type=RouteType.DIRECT_TOOL,
            executor_name="direct",
            model_id="none",
            max_steps=0,
            chain_name=None,
            tool_name="get_compliance_report",
            tool_args={"transcript_id": "abc-123"},
            confidence=0.95
        )
        
        assert plan.tool_name == "get_compliance_report"
        assert plan.tool_args == {"transcript_id": "abc-123"}
        assert plan.confidence == 0.95
    
    def test_execution_plan_validation_max_steps(self):
        """Test max_steps validation bounds."""
        # Valid: 0 steps
        plan = ExecutionPlan(route_type=RouteType.DIRECT_TOOL, executor_name="test", max_steps=0)
        assert plan.max_steps == 0
        
        # Valid: 20 steps
        plan = ExecutionPlan(route_type=RouteType.FULL_AGENT, executor_name="test", max_steps=20)
        assert plan.max_steps == 20
        
        # Invalid: negative
        with pytest.raises(ValidationError):
            ExecutionPlan(route_type=RouteType.LIGHT_AGENT, executor_name="test", max_steps=-1)
        
        # Invalid: too high
        with pytest.raises(ValidationError):
            ExecutionPlan(route_type=RouteType.FULL_AGENT, executor_name="test", max_steps=21)
    
    def test_execution_plan_validation_confidence(self):
        """Test confidence validation bounds."""
        # Valid: 0.0
        plan = ExecutionPlan(route_type=RouteType.DIRECT_TOOL, executor_name="test", confidence=0.0)
        assert plan.confidence == 0.0
        
        # Valid: 1.0
        plan = ExecutionPlan(route_type=RouteType.DIRECT_TOOL, executor_name="test", confidence=1.0)
        assert plan.confidence == 1.0
        
        # Invalid: negative
        with pytest.raises(ValidationError):
            ExecutionPlan(route_type=RouteType.LIGHT_AGENT, executor_name="test", confidence=-0.1)
        
        # Invalid: > 1.0
        with pytest.raises(ValidationError):
            ExecutionPlan(route_type=RouteType.FULL_AGENT, executor_name="test", confidence=1.1)
    
    def test_execution_plan_invalid_route_type(self):
        """Test validation rejects invalid route types."""
        with pytest.raises(ValidationError):
            ExecutionPlan(route_type="invalid_route", executor_name="test")
    
    def test_execution_plan_serialization(self):
        """Test JSON serialization."""
        plan = ExecutionPlan(
            route_type=RouteType.PROMPT_CHAIN,
            executor_name="chain",
            chain_name="transcript_analysis"
        )
        
        # Serialize
        json_str = plan.model_dump_json()
        data = json.loads(json_str)
        
        # Verify enum serialized as value
        assert data["route_type"] == "prompt_chain"
        assert data["chain_name"] == "transcript_analysis"
    
    def test_execution_plan_deserialization(self):
        """Test JSON deserialization."""
        json_str = '{"route_type": "full_agent", "executor_name": "react", "max_steps": 10}'
        plan = ExecutionPlan.model_validate_json(json_str)
        
        assert plan.route_type == RouteType.FULL_AGENT
        assert plan.max_steps == 10


# =============================================================================
# Execution Base Tests
# =============================================================================

class TestExecutionResult:
    """Tests for ExecutionResult Pydantic model."""
    
    def test_minimal_execution_result(self):
        """Test creating ExecutionResult with only required fields."""
        result = ExecutionResult(content="The answer is 42")
        
        assert result.content == "The answer is 42"
        assert result.steps == []
        assert result.metadata == {}
        assert result.success is True
        assert result.error is None
    
    def test_full_execution_result(self):
        """Test creating ExecutionResult with all fields."""
        result = ExecutionResult(
            content="Analysis complete",
            steps=[{"step_number": 1, "action": "analyze"}],
            metadata={"tokens": 100, "latency_ms": 250},
            success=True,
            error=None
        )
        
        assert len(result.steps) == 1
        assert result.metadata["tokens"] == 100
    
    def test_execution_result_error_state(self):
        """Test ExecutionResult with error."""
        result = ExecutionResult(
            content="",
            success=False,
            error="Tool not found: unknown_tool"
        )
        
        assert result.success is False
        assert "Tool not found" in result.error
    
    def test_add_metadata_method(self):
        """Test add_metadata convenience method."""
        result = ExecutionResult(content="Test")
        
        result.add_metadata("tokens_used", 150)
        result.add_metadata("route_type", "direct_tool")
        
        assert result.metadata["tokens_used"] == 150
        assert result.metadata["route_type"] == "direct_tool"
    
    def test_add_step_method(self):
        """Test add_step convenience method."""
        result = ExecutionResult(content="Test")
        
        result.add_step({"step_number": 1, "action": "lookup"})
        result.add_step({"step_number": 2, "action": "analyze"})
        
        assert len(result.steps) == 2
        assert result.steps[0]["action"] == "lookup"
        assert result.steps[1]["action"] == "analyze"
    
    def test_execution_result_validation_content_required(self):
        """Test that content is required."""
        with pytest.raises(ValidationError):
            ExecutionResult()  # Missing content
    
    def test_execution_result_serialization(self):
        """Test JSON serialization."""
        result = ExecutionResult(
            content="Done",
            steps=[{"step": 1}],
            metadata={"key": "value"}
        )
        
        json_str = result.model_dump_json()
        data = json.loads(json_str)
        
        assert data["content"] == "Done"
        assert data["success"] is True


class TestBaseExecutorProtocol:
    """Tests for BaseExecutor Protocol."""
    
    def test_protocol_can_be_implemented(self):
        """Test that classes can implement BaseExecutor protocol."""
        class TestExecutor:
            @property
            def name(self) -> str:
                return "test"
            
            async def execute(
                self, query: str, plan: Any, context: Dict[str, Any]
            ) -> ExecutionResult:
                return ExecutionResult(content=f"Executed: {query}")
        
        executor = TestExecutor()
        assert executor.name == "test"
    
    @pytest.mark.asyncio
    async def test_protocol_async_execute(self):
        """Test that async execute works."""
        class TestExecutor:
            @property
            def name(self) -> str:
                return "async_test"
            
            async def execute(
                self, query: str, plan: Any, context: Dict[str, Any]
            ) -> ExecutionResult:
                await asyncio.sleep(0.01)  # Simulate async work
                return ExecutionResult(content=f"Async result: {query}")
        
        executor = TestExecutor()
        result = await executor.execute("test query", None, {})
        
        assert result.content == "Async result: test query"
        assert result.success is True


# =============================================================================
# Session Types Tests
# =============================================================================

class TestMessage:
    """Tests for Message Pydantic model."""
    
    def test_create_message(self):
        """Test creating a message."""
        msg = Message(role="user", content="Hello")
        
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}
    
    def test_message_with_metadata(self):
        """Test message with metadata."""
        msg = Message(
            role="assistant",
            content="Response",
            metadata={"tokens": 50, "model": "gpt-4"}
        )
        
        assert msg.metadata["tokens"] == 50
        assert msg.metadata["model"] == "gpt-4"
    
    def test_message_role_validation(self):
        """Test role must be one of allowed values."""
        # Valid roles
        for role in ["system", "user", "assistant", "tool"]:
            msg = Message(role=role, content="Test")
            assert msg.role == role
        
        # Invalid role
        with pytest.raises(ValidationError):
            Message(role="invalid_role", content="Test")
    
    def test_message_content_not_empty(self):
        """Test content cannot be empty."""
        with pytest.raises(ValidationError):
            Message(role="user", content="")
        
        with pytest.raises(ValidationError):
            Message(role="user", content="   ")  # Whitespace only
    
    def test_message_serialization(self):
        """Test JSON serialization with datetime."""
        msg = Message(role="user", content="Test")
        
        json_str = msg.model_dump_json()
        data = json.loads(json_str)
        
        assert data["role"] == "user"
        assert data["content"] == "Test"
        assert "timestamp" in data


class TestSession:
    """Tests for Session Pydantic model."""
    
    def test_create_session(self):
        """Test creating a session."""
        session = Session()
        
        assert len(session.id) == 36  # UUID format
        assert session.messages == []
        assert session.metadata == {}
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_accessed, datetime)
    
    def test_session_with_metadata(self):
        """Test session with metadata."""
        session = Session(metadata={"project_id": "test-project"})
        
        assert session.metadata["project_id"] == "test-project"
    
    def test_add_message(self):
        """Test add_message method."""
        session = Session()
        initial_accessed = session.last_accessed
        
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there!", tokens=50)
        
        assert len(session.messages) == 2
        assert session.messages[0].role == "user"
        assert session.messages[1].metadata["tokens"] == 50
        assert session.last_accessed >= initial_accessed
    
    def test_get_recent_messages(self):
        """Test get_recent_messages method."""
        session = Session()
        
        # Add 15 messages
        for i in range(15):
            session.add_message("user", f"Message {i}")
        
        # Get last 5
        recent = session.get_recent_messages(n=5)
        assert len(recent) == 5
        assert recent[0].content == "Message 10"
        assert recent[4].content == "Message 14"
        
        # Get all if n > total
        all_msgs = session.get_recent_messages(n=100)
        assert len(all_msgs) == 15
    
    def test_clear_history(self):
        """Test clear_history method."""
        session = Session()
        original_id = session.id
        
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi")
        
        session.clear_history()
        
        assert len(session.messages) == 0
        assert session.id == original_id  # ID preserved
    
    def test_session_json_round_trip(self):
        """Test to_json and from_json."""
        session = Session(metadata={"project_id": "test"})
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi")
        
        # Serialize
        json_str = session.to_json()
        
        # Deserialize
        restored = Session.from_json(json_str)
        
        assert restored.id == session.id
        assert len(restored.messages) == 2
        assert restored.messages[0].content == "Hello"
        assert restored.metadata["project_id"] == "test"
    
    def test_session_with_explicit_id(self):
        """Test session with explicit ID."""
        session = Session(id="custom-session-id")
        
        assert session.id == "custom-session-id"


# =============================================================================
# Async Model Tests
# =============================================================================

class TestAsyncModel:
    """Tests for AsyncModel and OpenAIModel async support."""
    
    def test_openai_model_has_async_method(self):
        """Test OpenAIModel has generate_async method."""
        from agents.react_agent.core.models import OpenAIModel, AsyncModel
        
        assert hasattr(OpenAIModel, 'generate_async')
        assert asyncio.iscoroutinefunction(OpenAIModel.generate_async)
    
    def test_openai_model_inherits_async_model(self):
        """Test OpenAIModel inherits from AsyncModel."""
        from agents.react_agent.core.models import OpenAIModel, AsyncModel, Model
        
        assert issubclass(OpenAIModel, Model)
        assert issubclass(OpenAIModel, AsyncModel)
    
    @pytest.mark.asyncio
    async def test_openai_model_async_with_mock(self):
        """Test OpenAIModel generate_async with mocked client."""
        from agents.react_agent.core.models import OpenAIModel, ChatMessage
        
        # Create mock response
        mock_choice = MagicMock()
        mock_choice.message.content = "Mocked response"
        mock_choice.message.tool_calls = None
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        # Patch AsyncOpenAI to avoid API calls
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('openai.AsyncOpenAI') as mock_async_openai:
                # Configure mock
                mock_client = AsyncMock()
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
                mock_async_openai.return_value = mock_client
                
                # Create model (will use mocked client)
                model = OpenAIModel(api_key="test-key")
                model._async_client = mock_client
                
                # Call async method
                messages = [ChatMessage(role="user", content="Test")]
                result = await model.generate_async(messages)
                
                assert result.role == "assistant"
                assert result.content == "Mocked response"
                mock_client.chat.completions.create.assert_called_once()


# =============================================================================
# Integration Tests
# =============================================================================

class TestModuleIntegration:
    """Integration tests between modules."""
    
    def test_execution_result_with_routing_metadata(self):
        """Test ExecutionResult can store routing metadata."""
        plan = ExecutionPlan(
            route_type=RouteType.DIRECT_TOOL,
            executor_name="direct",
            tool_name="test_tool"
        )
        
        result = ExecutionResult(content="Done")
        # Note: use_enum_values=True means route_type is already a string
        result.add_metadata("route_type", plan.route_type)
        result.add_metadata("executor", plan.executor_name)
        
        assert result.metadata["route_type"] == "direct_tool"
        assert result.metadata["executor"] == "direct"
    
    def test_session_message_types_compatible(self):
        """Test Session and Message work with Pydantic validation."""
        session = Session()
        
        # Add messages of different roles
        session.add_message("system", "You are a helpful assistant")
        session.add_message("user", "What is HIPAA?")
        session.add_message("assistant", "HIPAA is...")
        
        # Serialize and deserialize
        json_str = session.to_json()
        restored = Session.from_json(json_str)
        
        # All messages preserved with types
        assert restored.messages[0].role == "system"
        assert restored.messages[1].role == "user"
        assert restored.messages[2].role == "assistant"


# =============================================================================
# Async Tool Tests
# =============================================================================

class TestAsyncTool:
    """Tests for AsyncTool, AsyncToolMixin, and async_tool decorator."""
    
    def test_async_tool_mixin_has_forward_async(self):
        """Test AsyncToolMixin provides forward_async."""
        from agents.react_agent.core.tools import Tool, AsyncToolMixin
        
        class MixedTool(Tool, AsyncToolMixin):
            name = "mixed"
            description = "Test tool with async mixin"
            inputs = {"x": {"type": "integer", "description": "Input"}}
            output_type = "integer"
            
            def forward(self, x: int) -> int:
                return x * 2
        
        tool = MixedTool()
        assert hasattr(tool, 'forward_async')
        assert asyncio.iscoroutinefunction(tool.forward_async)
    
    @pytest.mark.asyncio
    async def test_async_tool_mixin_runs_sync_in_thread(self):
        """Test AsyncToolMixin runs sync method in thread pool."""
        from agents.react_agent.core.tools import Tool, AsyncToolMixin
        
        class SyncTool(Tool, AsyncToolMixin):
            name = "sync_tool"
            description = "Sync tool with async support"
            inputs = {"x": {"type": "integer"}}
            output_type = "integer"
            
            def forward(self, x: int) -> int:
                return x * 2
        
        tool = SyncTool()
        
        # Async execution should work
        result = await tool.forward_async(x=5)
        assert result == 10
    
    def test_async_function_tool_creation(self):
        """Test AsyncFunctionTool can wrap async functions."""
        from agents.react_agent.core.tools import AsyncFunctionTool
        
        async def fetch_data(url: str) -> str:
            """Fetch data from URL."""
            return f"Data from {url}"
        
        tool = AsyncFunctionTool(fetch_data)
        
        assert tool.name == "fetch_data"
        assert "Fetch data" in tool.description
        assert "url" in tool.inputs
        assert tool.output_type == "string"
    
    def test_async_function_tool_rejects_sync_functions(self):
        """Test AsyncFunctionTool rejects non-async functions."""
        from agents.react_agent.core.tools import AsyncFunctionTool
        
        def sync_func() -> str:
            return "sync"
        
        with pytest.raises(TypeError, match="must be async"):
            AsyncFunctionTool(sync_func)
    
    @pytest.mark.asyncio
    async def test_async_function_tool_async_execution(self):
        """Test AsyncFunctionTool async execution."""
        from agents.react_agent.core.tools import AsyncFunctionTool
        
        async def multiply(x: int, y: int) -> int:
            """Multiply two numbers."""
            await asyncio.sleep(0.01)  # Simulate async work
            return x * y
        
        tool = AsyncFunctionTool(multiply)
        
        result = await tool.forward_async(x=3, y=4)
        assert result == 12
    
    def test_async_tool_decorator(self):
        """Test @async_tool decorator."""
        from agents.react_agent.core.tools import async_tool, AsyncFunctionTool
        
        @async_tool
        async def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"
        
        assert isinstance(greet, AsyncFunctionTool)
        assert greet.name == "greet"
        assert hasattr(greet, 'forward_async')
    
    def test_async_tool_decorator_with_args(self):
        """Test @async_tool decorator with custom name/description."""
        from agents.react_agent.core.tools import async_tool
        
        @async_tool(name="custom_fetch", description="Custom fetch tool")
        async def fetch(url: str) -> str:
            return "data"
        
        assert fetch.name == "custom_fetch"
        assert fetch.description == "Custom fetch tool"
    
    def test_async_tool_decorator_rejects_sync(self):
        """Test @async_tool rejects sync functions."""
        from agents.react_agent.core.tools import async_tool
        
        with pytest.raises(TypeError, match="can only be used on async functions"):
            @async_tool
            def sync_func():
                pass
    
    @pytest.mark.asyncio
    async def test_async_tool_decorator_full_workflow(self):
        """Test complete async tool workflow."""
        from agents.react_agent.core.tools import async_tool
        
        @async_tool
        async def process_data(items: list) -> dict:
            """Process a list of items."""
            await asyncio.sleep(0.01)
            return {"count": len(items), "items": items}
        
        # Async execution
        result = await process_data.forward_async(items=[1, 2, 3])
        
        assert result["count"] == 3
        assert result["items"] == [1, 2, 3]
    
    def test_async_tool_to_schema(self):
        """Test async tool generates correct schema."""
        from agents.react_agent.core.tools import async_tool
        
        @async_tool
        async def search(query: str, limit: int = 10) -> list:
            """Search for items."""
            return []
        
        schema = search.to_schema()
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "search"
        assert "query" in schema["function"]["parameters"]["properties"]
        assert "limit" in schema["function"]["parameters"]["properties"]


# =============================================================================
# Async HTTP Client Tests
# =============================================================================

class TestAsyncHTTPClients:
    """Tests for async HTTP clients."""
    
    def test_async_ingestion_client_initialization(self):
        """Test AsyncIngestionClient can be initialized."""
        from agents.react_agent.infrastructure.http_clients import (
            AsyncIngestionClient, DEFAULT_POOL_LIMITS
        )
        
        client = AsyncIngestionClient()
        
        assert client.base_url == "http://localhost:8082/ingest"
        assert client._client is not None
        assert hasattr(client, 'close')
    
    def test_async_rag_client_initialization(self):
        """Test AsyncRAGClient can be initialized."""
        from agents.react_agent.infrastructure.http_clients import AsyncRAGClient
        
        client = AsyncRAGClient()
        
        assert client.base_url == "http://localhost:8082/rag"
        assert client._client is not None
    
    def test_async_health_client_initialization(self):
        """Test AsyncHealthClient can be initialized."""
        from agents.react_agent.infrastructure.http_clients import AsyncHealthClient
        
        client = AsyncHealthClient()
        
        assert client.ingestion_url == "http://localhost:8082/ingest"
        assert client.rag_url == "http://localhost:8082/rag"
    
    def test_pool_limits_configuration(self):
        """Test connection pool limits are configurable."""
        from agents.react_agent.infrastructure.http_clients import (
            AsyncIngestionClient, DEFAULT_POOL_LIMITS
        )
        import httpx
        
        # Default limits
        assert DEFAULT_POOL_LIMITS.max_connections == 100
        assert DEFAULT_POOL_LIMITS.max_keepalive_connections == 20
        
        # Custom limits
        custom_limits = httpx.Limits(max_connections=50)
        client = AsyncIngestionClient(limits=custom_limits)
        
        assert client._client is not None
    
    @pytest.mark.asyncio
    async def test_async_ingestion_client_context_manager(self):
        """Test AsyncIngestionClient works as context manager."""
        from agents.react_agent.infrastructure.http_clients import AsyncIngestionClient
        
        async with AsyncIngestionClient() as client:
            assert client.base_url is not None
        
        # Client should be closed after context
        assert client._client.is_closed
    
    @pytest.mark.asyncio
    async def test_async_rag_client_context_manager(self):
        """Test AsyncRAGClient works as context manager."""
        from agents.react_agent.infrastructure.http_clients import AsyncRAGClient
        
        async with AsyncRAGClient() as client:
            assert client.base_url is not None
        
        assert client._client.is_closed
    
    @pytest.mark.asyncio
    async def test_async_health_client_check_all_structure(self):
        """Test AsyncHealthClient.check_all returns correct structure."""
        from agents.react_agent.infrastructure.http_clients import (
            AsyncHealthClient, ServiceStatus
        )
        
        async with AsyncHealthClient() as client:
            # Mock servers aren't running, so we expect failures
            results = await client.check_all()
            
            assert "ingestion" in results
            assert "rag" in results
            assert isinstance(results["ingestion"], ServiceStatus)
            assert isinstance(results["rag"], ServiceStatus)
            # They'll be unhealthy since no server is running
            assert results["ingestion"].healthy is False
            assert results["rag"].healthy is False
    
    @pytest.mark.asyncio
    async def test_async_regulation_retriever_ownership(self):
        """Test AsyncRegulationRetriever manages client ownership correctly."""
        from agents.react_agent.infrastructure.http_clients import (
            AsyncRegulationRetriever, AsyncRAGClient
        )
        
        # Owns client (creates internally)
        retriever1 = AsyncRegulationRetriever()
        assert retriever1._owns_client is True
        await retriever1.close()
        
        # Doesn't own client (passed in)
        shared_client = AsyncRAGClient()
        retriever2 = AsyncRegulationRetriever(rag_client=shared_client)
        assert retriever2._owns_client is False
        await retriever2.close()  # Should not close shared_client
        assert not shared_client._client.is_closed
        await shared_client.close()
    
    def test_all_async_clients_have_required_methods(self):
        """Test all async clients have the expected interface."""
        from agents.react_agent.infrastructure.http_clients import (
            AsyncIngestionClient, AsyncRAGClient, AsyncHealthClient
        )
        
        # All should have close and async context manager
        for client_class in [AsyncIngestionClient, AsyncRAGClient, AsyncHealthClient]:
            client = client_class()
            assert hasattr(client, 'close')
            assert hasattr(client, '__aenter__')
            assert hasattr(client, '__aexit__')
            assert asyncio.iscoroutinefunction(client.close)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
