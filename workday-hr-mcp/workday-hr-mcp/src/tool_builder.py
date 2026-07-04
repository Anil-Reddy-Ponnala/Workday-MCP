"""
Turns config/questions.yaml into live MCP tools at server startup.

Each question becomes its own tool (name = question id, description =
question name + category, so Claude's normal tool-selection picks the
right one straight from the user's wording). Every generated tool also
accepts optional `extra_filters` / `extra_group_by` so a predefined
question like "current headcount" can still be narrowed on the fly
("...in Engineering", "...hired after 2020-01-01") without you having
to predefine every combination.

On top of the generated tools, register_generic_tools() adds a small set
of always-available fallback tools that can answer literally anything
the report data supports, for questions nobody predefined yet.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml
from pathlib import Path

from . import query_engine as qe
from .workday_client import WorkdayClient

logger = logging.getLogger("tool_builder")
ROOT = Path(__file__).resolve().parent.parent


def load_questions() -> list[dict]:
    path = ROOT / "config" / "questions.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("questions", [])


def _format_answer(question_name: str, result: Any, metric: str) -> str:
    if isinstance(result, dict):
        lines = [f"{question_name} — by group:"]
        for k, v in result.items():
            lines.append(f"  - {k}: {v}")
        return "\n".join(lines)
    if isinstance(result, list):
        preview = result[:25]
        header = f"{question_name}: {len(result)} matching record(s)."
        if not preview:
            return header
        cols = list(preview[0].keys())[:6]
        lines = [header, " | ".join(cols)]
        for row in preview:
            lines.append(" | ".join(str(row.get(c, "")) for c in cols))
        if len(result) > 25:
            lines.append(f"... and {len(result) - 25} more (showing first 25).")
        return "\n".join(lines)
    return f"{question_name}: {result}"


def register_question_tools(mcp, client: WorkdayClient, questions: list[dict]):
    for q in questions:
        _register_one_question_tool(mcp, client, q)
    logger.info("Registered %d question tools from config/questions.yaml", len(questions))


def _register_one_question_tool(mcp, client: WorkdayClient, q: dict):
    tool_id = q["id"]
    report_id = q["report"]
    base_filters = q.get("filters") or {}
    base_group_by = q.get("group_by") or []
    metric = q.get("metric", "count")
    metric_field = q.get("metric_field")
    name = q.get("name", tool_id)
    category = q.get("category", "")
    keywords = q.get("keywords", [])
    description = (
        f"[{category}] {q.get('description', name)} "
        f"Matches user phrasing like: {', '.join(keywords) if keywords else name}. "
        f"Optionally pass extra_filters to narrow further (e.g. a department, "
        f"a date range) and extra_group_by to break the result down."
    )

    def make_handler():
        def handler(
            extra_filters: dict | None = None,
            extra_group_by: list[str] | None = None,
        ) -> str:
            rows = client.get_report_rows(report_id)
            filters = {**base_filters, **(extra_filters or {})}
            group_by = extra_group_by if extra_group_by else base_group_by
            filtered = qe.apply_filters(rows, filters)
            result = qe.aggregate(filtered, metric=metric, metric_field=metric_field, group_by=group_by)
            return _format_answer(name, result, metric)
        return handler

    fn = make_handler()
    fn.__name__ = tool_id
    fn.__doc__ = description
    mcp.tool(name=tool_id, description=description)(fn)


def register_generic_tools(mcp, client: WorkdayClient):
    """Fallback tools for any question that isn't predefined in
    config/questions.yaml — covers arbitrary field/date/value combos like
    'workers hired after 2020-01-01 in APAC'."""

    @mcp.tool(
        name="list_available_reports",
        description=(
            "Lists every Workday report this server can query, and the fields "
            "available on each one. Call this first if you're not sure which "
            "report/fields to use for query_hr_data or list_predefined_questions."
        ),
    )
    def list_available_reports() -> str:
        lines = []
        for rid, cfg in client.reports.items():
            lines.append(f"- {rid}: {cfg.get('description', '').strip()}")
            lines.append(f"    fields: {', '.join(cfg.get('fields', []))}")
        return "\n".join(lines)

    @mcp.tool(
        name="list_predefined_questions",
        description=(
            "Lists every predefined HR question tool available on this server "
            "(the ones generated from config/questions.yaml), grouped by "
            "category, so you can see what's already covered before falling "
            "back to query_hr_data."
        ),
    )
    def list_predefined_questions() -> str:
        questions = load_questions()
        by_cat: dict[str, list[str]] = {}
        for q in questions:
            by_cat.setdefault(q.get("category", "Other"), []).append(f"{q['id']} — {q['name']}")
        lines = []
        for cat, items in by_cat.items():
            lines.append(f"## {cat}")
            lines.extend(f"  - {i}" for i in items)
        return "\n".join(lines)

    @mcp.tool(
        name="query_hr_data",
        description=(
            "General-purpose fallback for ANY HR data question not already "
            "covered by a predefined tool — arbitrary filters, grouping, and "
            "metrics over a given Workday report. Use list_available_reports "
            "first to see report ids and field names. "
            "filters: list of {field, op, value} where op is one of "
            "eq/neq/gt/gte/lt/lte/contains/in (default eq). Dates can be "
            "compared as 'YYYY-MM-DD' strings, e.g. "
            "{field: Hire_Date, op: gte, value: '2020-01-01'}. "
            "metric: count | sum | avg | min | max | list."
        ),
    )
    def query_hr_data(
        report_id: str,
        filters: list[dict] | None = None,
        metric: str = "count",
        metric_field: str | None = None,
        group_by: list[str] | None = None,
    ) -> str:
        rows = client.get_report_rows(report_id)
        filtered = qe.apply_filters(rows, filters)
        result = qe.aggregate(filtered, metric=metric, metric_field=metric_field, group_by=group_by)
        return _format_answer(f"query_hr_data({report_id})", result, metric)

    @mcp.tool(
        name="refresh_report_cache",
        description=(
            "Forces a fresh pull of a Workday report instead of using the "
            "in-memory cache. Use if the user says the numbers look stale or "
            "explicitly asks for 'live'/'latest' data."
        ),
    )
    def refresh_report_cache(report_id: str) -> str:
        rows = client.get_report_rows(report_id, force_refresh=True)
        return f"Refreshed '{report_id}': {len(rows)} rows pulled from Workday."
