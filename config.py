import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from mcp import StdioServerParameters

load_dotenv()

BASE_DIR = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "reports"

# Ensure directories exist
REPORTS_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/medicaid")

# Resolve the actual path to globally-installed MCP server binaries.
# This avoids npx, which pollutes stdout with install messages that
# corrupt the MCP JSON-RPC stream.
_pg_bin = shutil.which("mcp-server-postgres")
_fs_bin = shutil.which("mcp-server-filesystem")

SERVER_CONFIGS = {
    "postgres": StdioServerParameters(
        command=_pg_bin or "npx",
        args=[DATABASE_URL] if _pg_bin else ["-y", "@modelcontextprotocol/server-postgres", DATABASE_URL],
    ),
    "fetch": StdioServerParameters(
        command="python",
        args=["-m", "mcp_server_fetch"],
    ),
    "filesystem": StdioServerParameters(
        command=_fs_bin or "npx",
        args=[str(REPORTS_DIR)] if _fs_bin else ["-y", "@modelcontextprotocol/server-filesystem", str(REPORTS_DIR)],
    ),
    "memory": StdioServerParameters(
        command="uvx",
        args=["mem0-mcp-server"],
        env={
            "MEM0_API_KEY": os.environ.get("MEM0_API_KEY", ""),
            "MEM0_DEFAULT_USER_ID": "medicaid-copilot",
        },
    ),
}
