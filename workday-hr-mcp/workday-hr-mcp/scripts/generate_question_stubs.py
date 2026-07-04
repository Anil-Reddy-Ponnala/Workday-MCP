"""
Turns a plain-text requirements doc (section header, blank line, then one
question per line, blank line, next section...) into a starter
config/questions.yaml with best-guess report/filter/metric/group_by
mappings, plus TODO markers wherever a guess is uncertain.

Usage:
    python scripts/generate_question_stubs.py path/to/requirements.txt > config/questions.yaml

This is meant to be run ONCE to bootstrap the config from the HR
requirements doc, then hand-edited/reviewed. Re-run it later if HR hands
you a new batch of questions to fold in (diff the output rather than
blindly overwriting your edited file).
"""

import re
import sys
import yaml

SECTION_TO_REPORT = {
    "Workforce & Headcount": "workers_report",
    "Hiring & Recruiting": "requisitions_report",
    "Turnover & Retention": "workers_report",
    "Internal Mobility": "mobility_report",
    "Performance Management": "workers_report",
    "Nine Box & Talent Reviews": "nine_box_report",
    "Succession Planning": "nine_box_report",
    "Learning & Development": "learning_report",
    "Skills & Workforce Planning": "skills_report",
    "Compensation": "workers_report",
    "Employee Engagement": "engagement_report",
    "Manager Analytics": "workers_report",
    "Executive Dashboards": "workers_report",
}

# metric_field guesses when a question implies "average X"
AVG_FIELD_GUESS = {
    "performance rating": "Performance_Rating",
    "compensation": "Base_Pay",
    "salary": "Base_Pay",
    "learning hours": "Learning_Hours",
    "tenure": "Time_in_Position_Days",
}

GROUP_BY_TRIGGERS = {
    "by department": ["Department"],
    "by region": ["Region"],
    "by manager": ["Manager"],
    "by job family": ["Job_Family"],
    "by grade": ["Compensation_Grade"],
    "by level": ["Management_Level"],
    "by location": ["Location_Country"],
    "by tenure": ["Tenure_Band"],
    "by performance rating": ["Performance_Rating"],
}


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s


def guess_filters(question: str) -> dict:
    q = question.lower()
    filters = {}
    if "voluntary" in q and "involuntary" not in q:
        filters["Termination_Category"] = "Voluntary"
        filters["Active_Status"] = "Terminated"
    elif "involuntary" in q:
        filters["Termination_Category"] = "Involuntary"
        filters["Active_Status"] = "Terminated"
    elif "regrettable" in q:
        filters["Regrettable_Termination"] = "Yes"
        filters["Active_Status"] = "Terminated"
    elif "turnover" in q:
        filters["Active_Status"] = "Terminated"
    elif "current" in q or ("headcount" in q and "trend" not in q):
        filters["Active_Status"] = "Active"

    if "contractor" in q:
        filters["Employee_Type"] = "Contractor"
    if "full-time" in q or "full time" in q:
        filters["Full_Time_Part_Time"] = "Full_Time"
    if "part-time" in q or "part time" in q:
        filters["Full_Time_Part_Time"] = "Part_Time"
    if "high performer" in q:
        filters["Performance_Rating"] = "TODO_high_band_value"
    if "high potential" in q:
        filters["Potential_Rating"] = "TODO_high_band_value"
    if "critical role" in q or "critical skill" in q:
        filters["Critical_Role"] = "Yes"
    return filters


def guess_metric(question: str) -> tuple[str, str | None]:
    q = question.lower()
    if q.startswith("average") or " average " in q:
        for phrase, field in AVG_FIELD_GUESS.items():
            if phrase in q:
                return "avg", field
        return "avg", "TODO_metric_field"
    if "distribution" in q or "population" in q and "high" in q:
        return "list", None
    if "rate" in q or "%" in q:
        # rates are usually (numerator count / denominator count) — best
        # expressed as two chained questions/tools rather than one metric.
        return "count", None
    return "count", None


def guess_group_by(question: str) -> list[str]:
    q = question.lower()
    for phrase, fields in GROUP_BY_TRIGGERS.items():
        if phrase in q:
            return list(fields)
    return []


def parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in SECTION_TO_REPORT:
            current = line
            sections[current] = []
            continue
        if current:
            sections[current].append(line)
    return sections


def build_question_entry(section: str, question: str, seen_ids: set) -> dict:
    report = SECTION_TO_REPORT.get(section, "workers_report")
    base_id = slugify(question)
    qid = base_id
    n = 2
    while qid in seen_ids:
        qid = f"{base_id}_{n}"
        n += 1
    seen_ids.add(qid)

    metric, metric_field = guess_metric(question)
    entry = {
        "id": qid,
        "name": question,
        "category": section,
        "keywords": [question.lower()],
        "report": report,
        "metric": metric,
        "filters": guess_filters(question) or {},
        "group_by": guess_group_by(question),
        "description": (
            f"Answers: '{question}'. Review the auto-generated filters/"
            f"group_by/metric below — marked TODO where a human judgment "
            f"call is needed (e.g. what counts as a 'high performer')."
        ),
    }
    if metric_field:
        entry["metric_field"] = metric_field
    return entry


def main():
    if len(sys.argv) != 2:
        print("Usage: python generate_question_stubs.py <requirements.txt>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        text = f.read()

    sections = parse_sections(text)
    seen_ids: set = set()
    questions = []
    for section, lines in sections.items():
        for q in lines:
            questions.append(build_question_entry(section, q, seen_ids))

    print("# AUTO-GENERATED by scripts/generate_question_stubs.py — review every")
    print("# TODO_ marker before relying on these in production.\n")
    print(yaml.dump({"questions": questions}, sort_keys=False, allow_unicode=True, width=100))


if __name__ == "__main__":
    main()
