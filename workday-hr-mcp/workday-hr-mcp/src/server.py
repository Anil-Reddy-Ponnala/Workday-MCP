"""
Workday HR MCP server.

Run locally (stdio, for Claude Desktop / claude mcp add):
    python -m src.server

Run as a hosted/enterprise server (Streamable HTTP, for Claude Enterprise
custom connectors, or Microsoft Copilot Studio's MCP connector):
    MCP_TRANSPORT=streamable-http python -m src.server
"""

import logging
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .workday_client import WorkdayClient
from .tool_builder import load_questions, register_question_tools, register_generic_tools

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("server")


def build_server() -> FastMCP:
    host = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_HTTP_PORT", "8787"))

    mcp = FastMCP(
        name="workday-hr-reporting",
        instructions=(
            "Answers HR/People-analytics questions (headcount, turnover, hiring, "
            "performance, nine-box, succession, learning, skills, compensation, "
            "engagement) by querying Workday custom reports. Call "
            "list_predefined_questions or list_available_reports if unsure which "
            "tool fits the user's question. Prefer a predefined question tool "
            "over query_hr_data when one matches; use extra_filters/"
            "extra_group_by on predefined tools, or query_hr_data directly, for "
            "anything more specific than the predefined tool covers."
        ),
        host=host,
        port=port,
    )

    client = WorkdayClient()
    questions = load_questions()
    register_question_tools(mcp, client, questions)
    register_generic_tools(mcp, client)

    logger.info(
        "Workday HR MCP server ready. mock_mode=%s reports=%s questions=%d",
        client.mock_mode, list(client.reports), len(questions),
    )
    return mcp


def main():
    mcp = build_server()
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
