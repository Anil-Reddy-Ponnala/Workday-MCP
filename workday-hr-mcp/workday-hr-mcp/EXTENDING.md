# Extending the server

Everything here is a config edit (`config/reports.yaml` and/or
`config/questions.yaml`) followed by a restart. Nothing in `src/` needs
to change for any of the four scenarios below. Each one is a full worked
example, not just a description, so you can copy-paste and adapt.

Quick mental model before you start: **`reports.yaml` describes what data
exists** (which Workday report, which fields it has). **`questions.yaml`
describes what to do with that data** (which report, which filters, which
aggregation) for one named question. The engine that actually runs a
question (`src/query_engine.py`) doesn't know anything about HR — it just
filters rows and counts/sums/averages them, so it never needs to change
when the *data* changes, only when the *kind of computation* changes
(which is rare: count/sum/avg/min/max/list covers almost everything).

---

## Scenario 1 - Someone added a new field to a Workday report

Say your Workday admin adds a `Visa_Status` column to the Worker Master
Report so you can eventually ask "how many workers need visa sponsorship
renewal."

1. **Confirm it's really on the RAAS output.** Hit the report's JSON URL
   directly (or re-run the smoke test with `MOCK_MODE=false`) and check
   the exact field name Workday gives it - Workday sometimes renders your
   label as `Visa_Status_1` or similar depending on how the report field
   was built. Use the exact key it comes back with.

2. **Add it to `config/reports.yaml`** under that report's `fields:` list
   - this list is documentation only (nothing enforces it), but it's what
   the next person editing `questions.yaml` will read to know what's
   queryable:
   ```yaml
   - id: workers_report
     ...
     fields:
       - Worker
       - Active_Status
       - ...
       - Visa_Status        # added
   ```

3. **That's it for the field itself.** It's now usable anywhere a field
   name goes:
   - as a `filters` key in a predefined question
   - as a `group_by` entry
   - as a `metric_field` (if it's numeric)
   - in an ad-hoc `query_hr_data` call from Claude - e.g. Claude could
     already answer "how many workers have Visa_Status = Pending" the
     moment the field exists on the report, with no config edit at all,
     via the `query_hr_data` fallback tool.

4. **(Optional) also add a predefined question**, if you want a
   dedicated named tool rather than relying on the ad-hoc fallback - see
   Scenario 2, it's the same process.

5. **If you're in mock mode**, also add the field to
   `scripts/generate_mock_data.py`'s row generator so local testing
   reflects it, then re-run `python scripts/generate_mock_data.py`.

6. **Restart the server** (or redeploy your container). Done.

---

## Scenario 2 - A new question over data you already have

Say HR asks: "How many workers are on a Performance Improvement Plan
(PIP)?" - and you already have a `PIP_Status` field on `workers_report`
(add it per Scenario 1 first if you don't).

Open `config/questions.yaml` and append:

```yaml
- id: workers_on_pip
  name: "Workers on a Performance Improvement Plan"
  category: "Performance Management"
  keywords:
    - "workers on pip"
    - "how many people are on a pip"
    - "performance improvement plan count"
  report: workers_report
  metric: count
  filters:
    Active_Status: Active
    PIP_Status: Active
  group_by: []
  description: >
    Count of currently active workers on an active Performance
    Improvement Plan.
```

Field-by-field, what each key does (this is the whole schema - nothing
else is read):

| Key | Required | What it does |
|---|---|---|
| `id` | yes | The MCP tool's name. Must be unique. Use `snake_case`. |
| `name` | yes | Human-readable label, used in the answer text. |
| `category` | no | Cosmetic grouping, shown by `list_predefined_questions`. |
| `keywords` | no | Extra phrasings folded into the tool's description, so Claude's tool-selection has more to match against. Doesn't need to be exhaustive - Claude generalizes from a couple of examples. |
| `report` | yes | Must match an `id` in `config/reports.yaml`. |
| `metric` | yes | One of `count`, `sum`, `avg`, `min`, `max`, `list`. |
| `metric_field` | only for sum/avg/min/max | Which numeric field to aggregate. |
| `filters` | no | `{field: value}` shorthand for equality, or a list of `{field, op, value}` for `gt/gte/lt/lte/neq/contains/in`. Omit for "no filter." |
| `group_by` | no | List of fields to break the result down by. Omit for a single number. |
| `description` | yes | What Claude reads to decide this tool matches the user's question - be specific about what it counts/excludes. |

Restart the server. `workers_on_pip` is now a real tool Claude can call,
and (per the table) it still accepts ad-hoc `extra_filters` /
`extra_group_by` on top of the base definition - e.g. "workers on PIP, by
manager" reuses this same tool with `extra_group_by: ["Manager"]` without
you predefining that combination.

**A subtlety worth internalizing**: you don't need a predefined entry for
every phrasing or every filter combination. `query_hr_data` (the generic
fallback) already answers anything the report's fields support -
Scenario 2 is worth doing when a question comes up *often enough* that a
clean, named, reusable tool is better than Claude reconstructing the same
ad-hoc filter every time. For a one-off question, just let Claude use
`query_hr_data` directly; no config edit needed at all.

---

## Scenario 3 - A new report entirely

Say HR wants to track **exit interview data** - sentiment, would-rehire
flag, feedback themes - which live in a brand-new Workday custom report
that doesn't map cleanly onto any existing one.

1. **Build/confirm the Workday custom report and its RAAS URL** (or, to
   build and test the question logic before Workday is ready, skip
   straight to step 3 with a mock fixture).

2. **Register it in `config/reports.yaml`**:
   ```yaml
   - id: exit_interviews_report
     name: "Exit Interview Report"
     description: >
       One row per completed exit interview. Powers exit-sentiment and
       rehire-eligibility questions.
     url: "/service/customreport2/your_tenant/ISU_User/Exit_Interviews_Report"
     mock_file: "exit_interviews_report.json"
     fields:
       - Worker
       - Department
       - Termination_Date
       - Would_Rehire
       - Exit_Sentiment_Score
       - Primary_Exit_Reason
   ```

3. **Add a mock fixture** so you can build/test before Workday access
   exists - either hand-write a small
   `mock_data/exit_interviews_report.json` matching the shape below, or
   add a generator function to `scripts/generate_mock_data.py` and run
   it:
   ```json
   {
     "Report_Entry": [
       {"Worker": "Jane Doe", "Department": "Sales", "Termination_Date": "2026-03-01",
        "Would_Rehire": "Yes", "Exit_Sentiment_Score": 4, "Primary_Exit_Reason": "Compensation"}
     ]
   }
   ```

4. **Add your questions to `config/questions.yaml`** referencing the new
   report id, exactly like Scenario 2:
   ```yaml
   - id: average_exit_sentiment
     name: "Average Exit Sentiment Score"
     category: "Turnover & Retention"
     keywords: ["average exit sentiment", "exit interview sentiment score"]
     report: exit_interviews_report
     metric: avg
     metric_field: Exit_Sentiment_Score
     filters: {}
     group_by: []
     description: "Average exit interview sentiment score (1-5) across all completed exit interviews."
   ```

5. **Restart.** `list_available_reports` immediately shows the new
   report to Claude, and both the new predefined question and ad-hoc
   `query_hr_data` calls against `exit_interviews_report` work right away.

6. **Wire up the real RAAS URL and OAuth once the Workday side is ready**
   - flip `MOCK_MODE=false`, confirm the `url:` field points at the real
   report, and re-test.

---

## Scenario 4 - HR hands you a whole new batch of questions

If HR sends another requirements doc shaped like your original one (a
section header, then one question per line, blank lines between
sections), don't hand-write 30 YAML entries - bootstrap them:

```bash
python scripts/generate_question_stubs.py new_requirements.txt >> config/questions.yaml
```

This is the exact script that produced the 141 questions already in
`config/questions.yaml`. It guesses `report` / `filters` / `metric` /
`group_by` from the wording - e.g. "involuntary turnover by region" is
correctly guessed as `Termination_Category: Involuntary`,
`group_by: [Region]` - and marks anything it's not confident about with a
`TODO_` placeholder (e.g. `TODO_high_band_value` for "high performer,"
since that threshold is a judgment call only your team can make).

**Always review the output before trusting it in production** - treat it
as a strong first draft, not a finished config. Specifically check:
- every `TODO_` marker got replaced with a real value
- any question implying a *rate* (e.g. "offer acceptance rate") - the
  generator maps these to a plain `count`, since a rate is really two
  numbers (accepted / total offers) divided. The cleanest fix is usually
  not a new metric type - it's two separate predefined `count` questions
  (e.g. `offers_accepted`, `offers_extended`) and letting Claude compute
  the ratio itself by calling both tools and dividing, which it's
  perfectly capable of doing in one turn.
- any question needing a report that doesn't exist yet in
  `reports.yaml` - the generator assigns a best-guess `report:` id, but
  if that report doesn't exist you'll need Scenario 3 first.

If you want to teach the generator new heuristics (e.g. your org has a
specific phrase pattern it keeps guessing wrong), the mappings live in
`scripts/generate_question_stubs.py` - `SECTION_TO_REPORT`,
`GROUP_BY_TRIGGERS`, and the `guess_filters`/`guess_metric` functions are
all plain Python dictionaries/if-chains, safe to extend.

---

## After any of the above: how to verify before you ship it

```bash
python -m tests.smoke_test
```
Add your new tool's `id` to the `names_to_try` list near the top of
`tests/smoke_test.py` temporarily, or just call it directly in a Python
shell:
```python
result = await mcp.call_tool("workers_on_pip", {})
```
This catches YAML typos, wrong field names, and bad report references in
seconds, without needing Claude Desktop or a real Workday connection in
the loop at all.
