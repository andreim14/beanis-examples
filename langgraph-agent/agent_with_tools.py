"""
LangGraph RAG Agent with MCP Tool Calling

The agent intelligently decides when to:
- Search the knowledge base (only when needed)
- Use conversation history for context
- Store/retrieve memory for multi-turn conversations
"""

import os
from typing import TypedDict, List, Annotated, Literal
from operator import add

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool

from mcp_server import BeanisRAGTools


# Define the agent state
class AgentState(TypedDict):
    """State for the tool-calling RAG agent"""

    messages: Annotated[List, add]  # Message history
    session_id: str
    query: str
    final_response: str


class ToolCallingRAGAgent:
    """
    RAG Agent that uses tool calling to decide when to retrieve context

    Features:
    - LLM decides when to search knowledge base vs use memory
    - Redis-based persistent memory across sessions
    - Conversation history as a tool
    - Intelligent retrieval (only when needed)
    """

    def __init__(self, mcp_tools: BeanisRAGTools, openai_api_key: str, model: str = "gpt-4o-mini"):
        self.mcp_tools = mcp_tools
        self.llm = ChatOpenAI(
            model=model, temperature=0.7, openai_api_key=openai_api_key
        )

        # Session tracking
        self._current_session_id = "default"

        # Wrap MCP tools as LangChain tools
        self.tools = self._create_langchain_tools()
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        # Build the graph
        self.graph = self._build_graph()

    def _create_langchain_tools(self):
        """Convert MCP tools to LangChain format"""

        @tool
        async def search_knowledge_base(query: str, k: int = 3) -> str:
            """Search the knowledge base for relevant information. Use this when you need factual information to answer the user's question."""
            results = await self.mcp_tools.search_knowledge_base(query, k=k)
            if not results:
                return "No relevant information found in the knowledge base."

            # Format results
            formatted = []
            for doc in results:
                formatted.append(
                    f"[{doc['title']}] (score: {doc['score']:.2f})\n{doc['context']}"
                )
            return "\n\n".join(formatted)

        @tool
        async def get_conversation_history(limit: int = 5) -> str:
            """Get recent conversation history for this session. Use this to maintain context across turns."""
            # Get session_id from agent context
            session_id = self._current_session_id
            messages = await self.mcp_tools.get_conversation_history(
                session_id, limit=limit
            )
            if not messages:
                return "No conversation history found."

            formatted = []
            for msg in messages:
                role = "User" if msg["role"] == "user" else "Assistant"
                formatted.append(f"{role}: {msg['content']}")
            return "\n".join(formatted)

        @tool
        async def store_memory(key: str, value: str) -> str:
            """Store information in the agent's memory for later retrieval. Use this to remember important facts about the user or conversation."""
            # Get session_id from agent context (will be injected)
            session_id = self._current_session_id
            success = await self.mcp_tools.store_agent_memory(session_id, key, value)
            return "Memory stored successfully" if success else "Failed to store memory"

        @tool
        async def retrieve_memory(key: str) -> str:
            """Retrieve previously stored information from the agent's memory."""
            # Get session_id from agent context (will be injected)
            session_id = self._current_session_id
            value = await self.mcp_tools.retrieve_agent_memory(session_id, key)
            if value:
                return f"Retrieved: {value}"
            return "No memory found for this key"

        return [
            search_knowledge_base,
            get_conversation_history,
            store_memory,
            retrieve_memory,
        ]

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph with tool calling support"""

        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("agent", self._agent_node)
        workflow.add_node("tools", self._tool_node)

        # Define conditional routing
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "tools",
                "end": END,
            },
        )
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    async def _agent_node(self, state: AgentState) -> AgentState:
        """Agent reasoning node - decides whether to use tools or respond"""

        print(f"🤖 [Agent] Processing with {len(state['messages'])} messages...")

        # Call LLM with tools
        response = await self.llm_with_tools.ainvoke(state["messages"])

        return {"messages": [response]}

    async def _tool_node(self, state: AgentState) -> AgentState:
        """Execute tools and return results"""

        # Get the last message (should be tool call)
        last_message = state["messages"][-1]

        print(f"🔧 [Tools] Executing {len(last_message.tool_calls)} tool(s)...")

        # Execute each tool call
        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            print(f"   → {tool_name}({tool_args})")

            # Find and execute the tool
            tool_func = next(
                (t for t in self.tools if t.name == tool_name), None
            )
            if tool_func:
                result = await tool_func.ainvoke(tool_args)
                tool_messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                    )
                )

        return {"messages": tool_messages}

    def _should_continue(self, state: AgentState) -> Literal["continue", "end"]:
        """Decide whether to continue with tools or end"""

        last_message = state["messages"][-1]

        # If the last message has tool calls, continue
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"

        # Otherwise, we're done
        return "end"

    async def query(self, query: str, session_id: str = "default") -> dict:
        """
        Query the agent

        Args:
            query: User question
            session_id: Session identifier

        Returns:
            Dict with response and metadata
        """

        print(f"\n{'=' * 70}")
        print(f"🚀 New Query: {query}")
        print(f"📋 Session: {session_id}")
        print(f"{'=' * 70}\n")

        # Set current session for tools
        self._current_session_id = session_id

        # Build system message
        system_msg = SystemMessage(
            content="""You are a helpful AI assistant with access to a knowledge base and memory.

When answering questions:
1. First check if you have conversation history to understand context
2. If you need factual information not in your training data, search the knowledge base
3. Store important information about the user in memory for future reference
4. Be concise but informative

Available tools:
- search_knowledge_base: Search for factual information
- get_conversation_history: Retrieve past conversation context
- store_memory: Save information about the user
- retrieve_memory: Recall previously saved information

Only use tools when necessary. For simple questions or greetings, respond directly."""
        )

        # Initialize state
        initial_state: AgentState = {
            "messages": [system_msg, HumanMessage(content=query)],
            "session_id": session_id,
            "query": query,
            "final_response": "",
        }

        # Run the graph
        final_state = await self.graph.ainvoke(initial_state)

        # Extract final response
        final_message = final_state["messages"][-1]
        response_text = (
            final_message.content if hasattr(final_message, "content") else str(final_message)
        )

        # Save conversation
        await self.mcp_tools.save_conversation_turn(
            session_id=session_id,
            user_message=query,
            assistant_message=response_text,
        )

        print(f"\n{'=' * 70}")
        print(f"✅ Response: {response_text[:100]}...")
        print(f"{'=' * 70}\n")

        return {
            "response": response_text,
            "session_id": session_id,
            "message_count": len(final_state["messages"]),
        }
