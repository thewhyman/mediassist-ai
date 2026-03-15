import os
from pathlib import Path

from dotenv import load_dotenv
from mcp import StdioServerParameters

load_dotenv()

BASE_DIR = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "reports"

# Ensure directories exist
REPORTS_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/medicaid")

_NPX_ENV = {"NPM_CONFIG_LOGLEVEL": "silent", "NPM_CONFIG_FUND": "false", "NPM_CONFIG_AUDIT": "false"}

SERVER_CONFIGS = {
    "postgres": StdioServerParameters(
        command="npx",
        args=["-y", "--loglevel=silent", "@modelcontextprotocol/server-postgres", DATABASE_URL],
        env={**_NPX_ENV},
    ),
    "fetch": StdioServerParameters(
        command="python",
        args=["-m", "mcp_server_fetch"],
    ),
    "filesystem": StdioServerParameters(
        command="npx",
        args=["-y", "--loglevel=silent", "@modelcontextprotocol/server-filesystem", str(REPORTS_DIR)],
        env={**_NPX_ENV},
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
