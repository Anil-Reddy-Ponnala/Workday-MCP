"""
Generic filter + aggregate engine.

This is what makes the server "extendable to any field": it doesn't know
anything about HR concepts. It just takes rows (dicts) coming back from a
Workday RAAS report, a list of filter conditions, an optional group_by,
and a metric, and computes the answer. Every predefined "question" in
config/questions.yaml is just a saved combination of these arguments;
the ad-hoc tool exposes the same engine directly so any question that
isn't predefined can still be answered.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

Row = dict[str, Any]

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%Y-%m-%dT%H:%M:%S")


def _parse_value(value: Any) -> Any:
    """Best-effort coercion so '2020-01-01' compares correctly against
    dates, '3000' compares numerically, etc."""
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return value
    s = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s.lower()


_OPS = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "contains": lambda a, b: str(b).lower() in str(a).lower(),
    "in": lambda a, b: _parse_value(a) in [_parse_value(x) for x in b],
}


class FilterCondition:
    """One condition: {"field": "Active_Status", "op": "eq", "value": "Active"}
    'op' defaults to 'eq' if omitted. Field names must match the keys
    coming back from Workday for that report (case-insensitive match is
    attempted as a fallback)."""

    def __init__(self, field: str, value: Any, op: str = "eq"):
        self.field = field
        self.op = op
        self.value = value

    @classmethod
    def from_dict(cls, d: dict) -> "FilterCondition":
        return cls(field=d["field"], value=d.get("value"), op=d.get("op", "eq"))

    def matches(self, row: Row) -> bool:
        if self.field in row:
            raw = row[self.field]
        else:
            # case-insensitive fallback so config authors don't need to
            # match Workday's exact XML-ish field casing every time
            match_key = next(
                (k for k in row if k.lower() == self.field.lower()), None
            )
            if match_key is None:
                return False
            raw = row[match_key]

        fn = _OPS.get(self.op)
        if fn is None:
            raise ValueError(f"Unsupported filter operator: {self.op}")

        if self.op == "in":
            return fn(raw, self.value)
        return fn(_parse_value(raw), _parse_value(self.value))


def apply_filters(rows: list[Row], filters: list[dict] | dict | None) -> list[Row]:
    if not filters:
        return rows
    if isinstance(filters, dict):
        # shorthand: {"Active_Status": "Active"} == eq filter
        conditions = [FilterCondition(field=k, value=v) for k, v in filters.items()]
    else:
        conditions = [FilterCondition.from_dict(f) for f in filters]
    return [r for r in rows if all(c.matches(r) for c in conditions)]


def _group_key(row: Row, group_by: list[str]) -> tuple:
    key = []
    for field in group_by:
        if field in row:
            key.append(row[field])
        else:
            match_key = next((k for k in row if k.lower() == field.lower()), None)
            key.append(row.get(match_key, "Unknown"))
    return tuple(key)


def aggregate(
    rows: list[Row],
    metric: str = "count",
    metric_field: str | None = None,
    group_by: list[str] | None = None,
) -> Any:
    """metric: count | sum | avg | min | max | list
    - count/sum/avg/min/max operate over `metric_field` (numeric ones
      require it; count doesn't).
    - list returns the matching rows (trimmed) — useful for "show me who".
    """
    group_by = group_by or []

    def compute(subset: list[Row]):
        if metric == "count":
            return len(subset)
        if metric == "list":
            return subset
        if not metric_field:
            raise ValueError(f"metric '{metric}' requires metric_field")
        values = []
        for r in subset:
            key = metric_field if metric_field in r else next(
                (k for k in r if k.lower() == metric_field.lower()), None
            )
            if key is None:
                continue
            v = _parse_value(r[key])
            if isinstance(v, (int, float)):
                values.append(v)
        if not values:
            return None
        if metric == "sum":
            return sum(values)
        if metric == "avg":
            return round(sum(values) / len(values), 2)
        if metric == "min":
            return min(values)
        if metric == "max":
            return max(values)
        raise ValueError(f"Unsupported metric: {metric}")

    if not group_by:
        return compute(rows)

    groups: dict[tuple, list[Row]] = {}
    for r in rows:
        groups.setdefault(_group_key(r, group_by), []).append(r)

    return {
        ", ".join(str(k) for k in key): compute(subset)
        for key, subset in sorted(groups.items(), key=lambda kv: str(kv[0]))
    }
