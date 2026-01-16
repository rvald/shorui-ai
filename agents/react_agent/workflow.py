"""
LangGraph ReAct agent workflow with Redis checkpointing.
"""

from typing import Optional
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage

from .state import AgentState
from .agent import ReActAgent
from shorui_core.config import settings

from loguru import logger


class AgentWorkflow:
    """
    LangGraph workflow for the ReAct agent with Redis checkpointing.
    
    The workflow follows a simple pattern:
    1. START → Agent (reasoning and tool selection)
    2. Agent → [tools_condition decides] → Tools OR END
    3. Tools → Agent (observation and next action)
    
    This creates the ReAct loop: Thought → Action → Observation
    
    Multi-turn sessions are persisted via Redis checkpointer using thread_id.
    """

    def __init__(self, redis_url: str | None = None):
        self.agent = ReActAgent()
        self.redis_url = redis_url or getattr(settings, "CELERY_BROKER_URL", "redis://redis:6379/0")
        self._checkpointer: AsyncRedisSaver | None = None
        self._checkpointer_cm = None  # Keep context manager reference alive
        logger.info(f"Workflow initializing with Redis: {self.redis_url}")
        self._graph = self._build_graph()

    def _build_graph(self):
        """
        Build the LangGraph workflow with nodes and edges.
        
        Graph structure:
        START → agent → [tools_condition] → tools → agent
                           ↓                          ↑
                          END ←───────────────────────┘
        """

        graph = StateGraph(AgentState)

        # Add nodes
        # 1. Agent node: Reasons and decides on actions (ReAct: Thought + Action)
        graph.add_node("agent", self.agent.call_model)
        
        # 2. Tools node: Executes tool calls (ReAct: Observation)
        #    ToolNode automatically handles tool execution and formats results
        graph.add_node("tools", ToolNode(self.agent.tools))
        
        # Add edges
        # Start with the agent node
        graph.add_edge(START, "agent")

        # Use built-in tools_condition for routing
        # If agent returned tool_calls, go to tools node
        # Otherwise, end the workflow
        graph.add_conditional_edges(
            "agent",
            tools_condition,  # Built-in function that checks for tool_calls
            {
                "tools": "tools",  # If tool calls exist, go to tools
                END: END           # If no tool calls, end
            }
        )
        
        # After tools execute, always return to agent for observation
        graph.add_edge("tools", "agent")
        
        logger.info(f"Workflow built with nodes=['agent', 'tools']")
        return graph  # Return uncommitted graph - we compile with checkpointer at invoke time

    async def get_checkpointer(self) -> AsyncRedisSaver:
        """Get or create async Redis checkpointer."""
        if self._checkpointer is None:
            # Create and enter the async context manager
            self._checkpointer_cm = AsyncRedisSaver.from_conn_string(self.redis_url)
            self._checkpointer = await self._checkpointer_cm.__aenter__()
            # Setup indices after entering context
            await self._checkpointer.asetup()
            logger.info("Redis checkpointer initialized")
        return self._checkpointer

    async def invoke_async(
        self, 
        user_input: str, 
        thread_id: str,
        **kwargs
    ) -> dict:
        """
        Execute ReAct agent workflow with Redis checkpointing.
        
        Args:
            user_input: User query/task
            thread_id: Session ID for conversation persistence
            
        Returns:
            Final state with result
        """
        logger.info(f"ReAct workflow invoke - thread: {thread_id}, input: {user_input[:100]}...")
        
        # Get checkpointer and compile graph
        checkpointer = await self.get_checkpointer()
        compiled = self._graph.compile(checkpointer=checkpointer)
        
        # Config with thread_id for checkpointing
        config = {"configurable": {"thread_id": thread_id}}
        
        # Add new user message (checkpointer handles previous messages)
        input_state = {
            "messages": [HumanMessage(content=user_input)],
        }
        
        try:
            result = await compiled.ainvoke(input_state, config=config)
            
            logger.info(f"ReAct workflow complete - iterations: {result.get('iterations', 0)}, messages: {len(result.get('messages', []))}")
            
            return result
            
        except Exception as e:
            logger.error(f"ReAct workflow error: {str(e)}")
            raise

    async def stream_async(
        self, 
        user_input: str,
        thread_id: str,
        **kwargs
    ):
        """
        Stream ReAct agent workflow with Redis checkpointing.
        
        Args:
            user_input: User query/task
            thread_id: Session ID for conversation persistence
            
        Yields:
            State updates as they occur
        """
        logger.info(f"ReAct workflow stream - thread: {thread_id}, input: {user_input[:100]}...")
        
        # Get checkpointer and compile graph
        checkpointer = await self.get_checkpointer()
        compiled = self._graph.compile(checkpointer=checkpointer)
        
        # Config with thread_id for checkpointing
        config = {"configurable": {"thread_id": thread_id}}
        
        # Add new user message (checkpointer handles previous messages)
        input_state = {
            "messages": [HumanMessage(content=user_input)],
        }
        
        try:
            async for chunk in compiled.astream(input_state, config=config):
                yield chunk
        except Exception as e:
            logger.error(f"ReAct workflow stream error: {str(e)}")
            raise