"""
Quick smoke test you can run locally without any MCP client:
    MOCK_MODE=true python -m tests.smoke_test

It builds the FastMCP server exactly like the real entrypoint does, then
calls a few of the generated tool functions directly to sanity-check the
whole pipeline: config -> tool registration -> mock data -> filter/aggregate.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("MOCK_MODE", "true")

from src.server import build_server  # noqa: E402


async def main():
    mcp = build_server()
    tools = await mcp.list_tools()
    print(f"\n{len(tools)} tools registered.\n")

    names_to_try = [
        "current_headcount",
        "headcount_by_department",
        "voluntary_turnover",
        "new_hires_by_department",
    ]
    for name in names_to_try:
        if not any(t.name == name for t in tools):
            print(f"[skip] tool '{name}' not found (check config/questions.yaml ids)")
            continue
        result = await mcp.call_tool(name, {})
        text = "".join(block.text for block in result[0] if hasattr(block, "text"))
        print(f"── {name} ──\n{text}\n")

    # Ad-hoc example: "workers hired after 2020-01-01 in APAC, by department"
    result = await mcp.call_tool(
        "query_hr_data",
        {
            "report_id": "workers_report",
            "filters": [
                {"field": "Hire_Date", "op": "gte", "value": "2020-01-01"},
                {"field": "Region", "op": "eq", "value": "APAC"},
            ],
            "metric": "count",
            "group_by": ["Department"],
        },
    )
    text = "".join(block.text for block in result[0] if hasattr(block, "text"))
    print(f"── query_hr_data (ad-hoc) ──\n{text}\n")


if __name__ == "__main__":
    asyncio.run(main())
