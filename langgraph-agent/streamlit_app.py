"""
Streamlit UI for the Tool-Calling RAG Agent

Interactive chat interface to test the MCP-based LangGraph agent with Beanis.
"""

import os
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv

# Must be imported before asyncio to patch it
import nest_asyncio
nest_asyncio.apply()

import asyncio
import redis.asyncio as redis

from beanis import init_beanis
from models import KnowledgeDocument, ConversationHistory, AgentState
from mcp_server import BeanisRAGTools
from agent_with_tools import ToolCallingRAGAgent


# Page config
st.set_page_config(
    page_title="Beanis RAG Agent",
    page_icon="🤖",
    layout="wide",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        color: #666;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .tool-badge {
        background-color: #e3f2fd;
        color: #1976d2;
        padding: 0.2rem 0.5rem;
        border-radius: 0.3rem;
        font-size: 0.8rem;
        font-weight: 600;
        margin: 0.2rem;
        display: inline-block;
    }
    .message-tools {
        font-size: 0.8rem;
        color: #666;
        margin-top: 0.5rem;
        font-style: italic;
    }
    .sidebar-info {
        background-color: #f5f5f5;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_initialized" not in st.session_state:
        st.session_state.agent_initialized = False
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "mcp_tools" not in st.session_state:
        st.session_state.mcp_tools = None


async def setup_agent():
    """Setup agent - called once"""
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("⚠️ OPENAI_API_KEY not found in environment variables!")
        st.stop()

    # Create new Redis client for this session
    redis_client = redis.Redis(
        host="localhost",
        port=6379,
        decode_responses=False
    )

    # Initialize Beanis
    await init_beanis(
        database=redis_client,
        document_models=[KnowledgeDocument, ConversationHistory, AgentState],
    )

    # Initialize MCP tools and agent
    mcp_tools = BeanisRAGTools(redis_client=redis_client, openai_api_key=api_key)
    agent = ToolCallingRAGAgent(mcp_tools=mcp_tools, openai_api_key=api_key)

    return agent, mcp_tools


def display_message(role, content, tools_used=None, timestamp=None):
    """Display a chat message with optional tool usage info"""
    with st.chat_message(role):
        st.markdown(content)
        if tools_used:
            tools_html = "".join([f'<span class="tool-badge">🔧 {tool}</span>' for tool in tools_used])
            st.markdown(f'<div class="message-tools">Tools used: {tools_html}</div>', unsafe_allow_html=True)


async def query_agent(agent, query, session_id):
    """Query the agent and return response with metadata"""
    result = await agent.query(query, session_id=session_id)
    return result


def main():
    # Header
    st.markdown('<div class="main-header">🤖 Beanis RAG Agent</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Interactive chat with LangGraph + MCP tools + Redis memory</div>',
        unsafe_allow_html=True
    )

    # Initialize session state
    init_session_state()

    # Initialize agent once
    if not st.session_state.agent_initialized:
        with st.spinner("🔄 Initializing agent and connecting to Redis..."):
            agent, mcp_tools = asyncio.run(setup_agent())
            st.session_state.agent = agent
            st.session_state.mcp_tools = mcp_tools
            st.session_state.agent_initialized = True

    agent = st.session_state.agent
    mcp_tools = st.session_state.mcp_tools

    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Settings")

        session_id = st.text_input(
            "Session ID",
            value="streamlit_session",
            help="All messages in this session will share conversation history and memory"
        )

        st.markdown("---")
        st.markdown("### 📊 Agent Info")
        st.markdown("""
        <div class="sidebar-info">
        <b>Available Tools:</b><br/>
        🔍 search_knowledge_base<br/>
        💬 get_conversation_history<br/>
        💾 store_memory<br/>
        🧠 retrieve_memory
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 💡 Try these queries")

        example_queries = [
            "Hello! How are you?",
            "What do you know about Notre Dame?",
            "My name is Stefan and I prefer brief answers",
            "What did I just tell you?",
            "Search for information about Super Bowl winners",
        ]

        for query in example_queries:
            if st.button(query, key=f"example_{query[:20]}", use_container_width=True):
                st.session_state.example_query = query

        st.markdown("---")

        # Clear conversation button
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        # Clear memory button
        if st.button("🧹 Clear Memory", use_container_width=True):
            async def clear_mem():
                await mcp_tools.clear_session_memory(session_id)
            asyncio.run(clear_mem())
            st.success("Memory cleared!")

    # Display chat history
    for message in st.session_state.messages:
        display_message(
            message["role"],
            message["content"],
            message.get("tools_used"),
            message.get("timestamp")
        )

    # Handle example query from sidebar
    if hasattr(st.session_state, 'example_query'):
        query = st.session_state.example_query
        del st.session_state.example_query
    else:
        # Chat input
        query = st.chat_input("Ask me anything...")

    if query:
        # Add user message to chat
        st.session_state.messages.append({
            "role": "user",
            "content": query,
            "timestamp": datetime.now().isoformat()
        })
        display_message("user", query)

        # Get agent response
        with st.spinner("🤔 Thinking..."):
            result = asyncio.run(query_agent(agent, query, session_id))

        # Extract tools used (simplified)
        tools_used = []
        response = result["response"]

        # Add assistant message to chat
        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "tools_used": tools_used if tools_used else None,
            "timestamp": datetime.now().isoformat()
        })
        display_message("assistant", response, tools_used)

        # Show response metadata
        with st.expander("📊 Response Metadata"):
            st.json({
                "session_id": result["session_id"],
                "message_count": result["message_count"],
            })

        st.rerun()


if __name__ == "__main__":
    main()
