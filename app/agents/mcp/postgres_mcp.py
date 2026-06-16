"""Postgres MCP client for LangGraph agents."""
import os
import shutil
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.core import get_custom_logger
from app.core.settings import config

logger = get_custom_logger(__name__)

_client: MultiServerMCPClient | None = None
_tools: list[BaseTool] | None = None


def _postgres_server_command() -> str:
    return shutil.which("mcp-postgres-server") or "mcp-postgres-server"


def _postgres_mcp_env() -> dict[str, str]:
    """Minimal env for the MCP subprocess (avoids loading the app .env)."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "POSTGRES_HOST": config.postgres_host,
        "POSTGRES_PORT": str(config.postgres_port),
        "POSTGRES_USER": config.postgres_user,
        "POSTGRES_PASSWORD": config.postgres_password_str,
        "POSTGRES_DB": config.postgres_db,
    }


def postgres_mcp_connection() -> dict[str, Any]:
    return {
        "postgres": {
            "command": _postgres_server_command(),
            "args": [],
            "transport": "stdio",
            "env": _postgres_mcp_env(),
            "cwd": "/tmp",
        }
    }


async def init_postgres_mcp() -> list[BaseTool]:
    """Start MCP client and load Postgres tools once at app startup."""
    global _client, _tools

    _client = MultiServerMCPClient(postgres_mcp_connection())
    _tools = await _client.get_tools()
    tool_names = [tool.name for tool in _tools]
    logger.info(f"Postgres tool names: {tool_names}")
    return _tools


async def get_postgres_mcp_tools() -> list[BaseTool]:
    if _tools is None:
        await init_postgres_mcp()
    assert _tools is not None
    return _tools


def reset_postgres_mcp() -> None:
    global _client, _tools
    _client = None
    _tools = None
