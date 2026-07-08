# Workday-MCP


# Workday HR MCP Server

## What this is

This is an MCP (Model Context Protocol) server — a small, self-hosted
program that sits between Claude (or Microsoft 365 Copilot) and your
Workday tenant, and turns plain-English HR questions into live Workday
report data. Someone on your team types "what's our current headcount"
or "voluntary turnover by department this year," Claude reads that,
picks the matching tool this server exposes, the server pulls the
relevant Workday Custom Report (via RAAS, authenticated with your
Integration System User over OAuth 2.0), filters/aggregates the rows,
and hands Claude back a plain answer to present.

Nothing in Workday changes to make this work — you're not building a new
integration platform, just exposing report data you already have (or can
build in an afternoon) through a protocol Claude and Copilot both already
speak. The server itself is intentionally small: a few hundred lines of
Python, no database, no message queue, no background jobs. State lives in
two YAML files you edit directly.

## Why it's built this way (config-driven, not hardcoded)

The tempting way to build this is one Python function per HR question —
`get_current_headcount()`, `get_voluntary_turnover()`, and so on — which
works fine for the first ten questions and becomes unmanageable at 141
(your requirements doc) and worse once new ones show up every month.
Instead, every question is a **data entry**, not a function:

```yaml
- id: current_headcount
  name: "Current headcount"
  report: workers_report        # which Workday report to pull
  filters: {Active_Status: Active}
  metric: count
```

A generic engine (`src/query_engine.py`) reads that entry and does the
filtering/counting — it has no idea what "headcount" means, it just
applies filters and aggregates. That's what makes adding the 142nd
question, or a field nobody thought of yet, a YAML edit instead of a
code review. The step-by-step for both is in `EXTENDING.md`.

## Architecture at a glance

```
                     ┌─────────────────────────────────────────┐
                     │   Workday HR MCP Server (this project)   │
  "current           │                                           │      Workday
  headcount?"        │  config/questions.yaml                   │   ┌──────────────┐
Claude ───MCP──────▶ │   one entry per question — id, report,   │──▶│ RAAS reports  │
 or Copilot          │   filters, metric, group_by, no code     │OAuth2  (via ISU)  │
                     │                                           │   └──────────────┘
                     │  config/reports.yaml                     │
                     │   report id → RAAS URL + documented       │
                     │   field list                              │
                     │                                           │
                     │  src/query_engine.py                     │
                     │   generic filter/aggregate — works on     │
                     │   any field on any report                 │
                     │                                           │
                     │  src/tool_builder.py + src/server.py     │
                     │   turns the YAML into live MCP tools at   │
                     │   startup, serves them over stdio         │
                     │   (local) or Streamable HTTP (enterprise) │
                     └─────────────────────────────────────────┘
```

Three ways to run the same code, no changes between them:
- **stdio, local** — Claude Desktop launches it as a subprocess on your
  machine. Good for building/testing.
- **Streamable HTTP, hosted** — a persistent service with a public HTTPS
  URL. Required for Claude Enterprise custom connectors and for
  Microsoft 365 Copilot.
- **Mock mode** — either of the above, but reading synthetic JSON
  fixtures instead of hitting Workday, so you can build and test the
  whole thing before your Workday reports/OAuth client even exist.

## 1. How it decides which "question" to run — the important part

This server does **not** do NLP/keyword matching itself. It registers **one
MCP tool per question** in `config/questions.yaml` — `current_headcount`,
`voluntary_turnover`, `headcount_by_department`, etc. — each with a
description like *"Current headcount. Matches phrasing like: current
headcount, headcount now, total employees, current population."*

Claude's normal tool-selection is what does the matching: when the user
types "what's our current headcount" or "how many employees do we have
right now", Claude reads the ~145 tool descriptions and picks
`current_headcount` itself — exactly the way it picks any other tool. You
don't write a router.

For anything not predefined (there are 141 predefined questions covering
every line in your requirements doc, but HR will always think of new
ones), two fallback tools cover the rest:

- **`query_hr_data`** — pass a report id, arbitrary filters (any field, any
  operator: `eq/neq/gt/gte/lt/lte/contains/in`), a metric
  (`count/sum/avg/min/max/list`), and optional `group_by`. This is what
  answers "hired population after 1/1/2020" even though nobody predefined
  that exact question — Claude just calls it with
  `{"field": "Hire_Date", "op": "gte", "value": "2020-01-01"}`.
- **`list_available_reports`** / **`list_predefined_questions`** — Claude
  calls these itself if it's unsure what's available, so it can construct
  a correct ad-hoc `query_hr_data` call.

Every predefined tool *also* accepts `extra_filters` / `extra_group_by`, so
"current headcount in Engineering" reuses the `current_headcount` tool
with `extra_filters: {"Department": "Engineering"}` instead of needing a
separate predefined question for every department.

## 2. Quickstart — run locally against mock data (no Workday needed yet)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # MOCK_MODE=true by default
python -m tests.smoke_test  # sanity-check: prints headcount, turnover, etc.
```

You should see output like:
```
── current_headcount ──
Current headcount: 452
── headcount_by_department ──
Headcount by department — by group:
  - Engineering: 67
  ...
```
Mock data lives in `mock_data/*.json` (regenerate with
`python scripts/generate_mock_data.py`) — it's shaped exactly like real
Workday RAAS JSON output, so switching to live data later is a
config/env change, not a code change.

### Connect it to Claude Desktop (stdio, local)

Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "workday-hr": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "src.server"],
      "cwd": "/absolute/path/to/workday-hr-mcp",
      "env": { "MOCK_MODE": "true" }
    }
  }
}
```
Restart Claude Desktop, then ask it "what's our current headcount" — it
should call the tool and answer from the mock data.

## 3. Wiring up real Workday

1. **Build the custom report(s) in Workday.** Start with one wide "Worker
   Master Report" (one row per worker) — see `config/reports.yaml` for the
   field list this server expects; add columns to match, or edit the yaml
   to match what you actually put on the report.
2. **Enable it as a web service (RAAS)**, share it with your Integration
   System User (ISU).
3. **Register an OAuth 2.0 API client for integrations** in Workday
   (Tenant Setup → Register API Client), scoped to your ISU. Workday's
   typical pattern is the **refresh-token grant**: you get a Client ID,
   Client Secret, and a long-lived Refresh Token once, and the server
   exchanges the refresh token for short-lived access tokens automatically
   (`src/workday_client.py` handles this — see `_get_access_token`).
4. Fill in `.env`:
   ```
   MOCK_MODE=false
   WORKDAY_BASE_URL=https://your-tenant.workday.com/ccx
   WORKDAY_TOKEN_URL=https://your-tenant.workday.com/ccx/oauth2/your_tenant/token
   WORKDAY_CLIENT_ID=...
   WORKDAY_CLIENT_SECRET=...
   WORKDAY_REFRESH_TOKEN=...
   ```
5. In `config/reports.yaml`, point `url:` at the report's actual RAAS path
   (Workday's "View URLs" button on the report gives you this — use the
   JSON variant).
6. Re-run the smoke test with `MOCK_MODE=false` to confirm a live pull.

Report responses are cached in memory for `REPORT_CACHE_TTL_SECONDS`
(default 5 min) so a burst of related questions in one conversation
doesn't re-hit Workday every time; `refresh_report_cache` (a generic tool)
forces a live re-pull if the user asks for "latest" numbers.

## 4. Deploying it as a remote server (required before Enterprise Claude or Copilot can use it)

Both Claude Enterprise custom connectors and Microsoft 365 Copilot call your
server **from the cloud**, not from a colleague's laptop — so it has to be
running somewhere with a public HTTPS URL, not just on your machine.

```bash
MCP_TRANSPORT=streamable-http MCP_HTTP_PORT=8787 python -m src.server
```

A `Dockerfile` is included — build and run it anywhere that runs
containers (an internal Kubernetes/ECS cluster, a small VM, Fly.io,
Render, Azure Container Apps, etc.):
```bash
docker build -t workday-hr-mcp .
docker run -p 8787:8787 --env-file .env workday-hr-mcp
```
Put it behind your normal TLS/ingress (so the public URL is `https://...`,
not raw `http://`) and give it a stable hostname, e.g.
`https://hr-mcp.yourcompany.com/mcp`.

## 5. Connecting to Claude Enterprise — step by step

### A note on authentication first (read this before you deploy)

Claude's custom connectors currently support **no auth** ("authless") or
**real OAuth 2.1 with PKCE** (Dynamic Client Registration, Client ID
Metadata Documents, or Anthropic-held credentials). Three things people
often try do **not** work, so don't spend time on them:
- a static bearer token pasted into the UI
- an API key/token in the URL's query string
- a plain machine-to-machine `client_credentials` grant with no user in
  the loop

Full OAuth 2.1 (with a discovery-compliant authorization server) is real
infrastructure work — most teams front it with an identity provider they
already run (Okta/Entra/Auth0) rather than hand-rolling one. Given that,
the pragmatic path for a first internal rollout is:

**Start authless.** The connector is still gated twice: (1) only an Owner
can add it to your org's connector list at all, and (2) each colleague
still has to individually find and enable it. Combine that with hosting
the server on a network/hostname that isn't publicly discoverable, and
optionally allowlisting Anthropic's published connector IP range at your
firewall (see "Building custom connectors" in Claude's Help Center for
that list), and you have a reasonable first version. Layer on real OAuth
later once you know whether you need per-person row-level restrictions on
top of what your ISU report already returns.

### Steps

1. **Deploy it as a remote server first** (see section 4) — you need a
   real `https://.../mcp` URL before this step will work.
2. **An Organization Owner or Primary Owner** (this has to be them, not
   just any member) goes to **Organization Settings -> Connectors -> Add
   -> Custom -> Web**.
3. Enter a name (e.g. "Workday HR Reporting") and your server's URL,
   e.g. `https://hr-mcp.yourcompany.com/mcp`. Leave "Advanced settings"
   (OAuth Client ID/Secret) blank if you're starting authless. Click
   **Add**.
4. Optional but recommended for HR data: click into the connector's
   **Tool permissions** and review the list — everything this server
   exposes is read-only (it only queries Workday reports), but it's worth
   confirming that before rolling it out org-wide.
5. **Each colleague** goes to **Customize -> Connectors**, finds "Workday
   HR Reporting" in the list (labeled "Custom"), and clicks **Connect**.
   With no auth configured, this just enables it — no sign-in prompt.
6. In a conversation, they enable it via the **"+"** button -> Connectors
   -> toggle it on (or Claude will offer to enable it automatically the
   first time a question looks like it needs HR data). Then they can just
   ask: "what's our current headcount?"

## 6. Connecting to Microsoft 365 Copilot — step by step

Same server, same URL, no code changes — Copilot just needs to be pointed
at it. Microsoft currently offers two ways in; which one you'll see
depends on your tenant's rollout stage, so check both.

### Option A — Copilot Studio (most direct, works today for most tenants)

1. Requires **generative orchestration turned on** for your agent, and a
   Microsoft 365 Copilot license for whoever uses the agent.
2. In Copilot Studio (copilotstudio.microsoft.com), open an existing
   agent or create a new one.
3. Go to **Tools -> Add a tool -> New tool -> Model Context Protocol**.
4. Fill in:
   - **Server name / description** — what you'd tell a colleague this
     does.
   - **Server URL** — your `https://.../mcp` endpoint (Copilot Studio
     requires **Streamable HTTP**; this server already speaks that when
     run with `MCP_TRANSPORT=streamable-http`).
5. **Authentication**: choose **None** if you're running authless (same
   reasoning as the Claude section above), or **OAuth 2.0 -> Manual** if
   you've wired up a real authorization server, entering its Authorization
   URL / Token URL / Client ID / Client Secret. If your server supports
   OAuth 2.0 Dynamic Client Registration with a discovery document,
   **Dynamic discovery** is simpler than Manual.
6. Click **Create** — Copilot Studio auto-discovers every tool this
   server exposes (all ~145) and lists them; it re-syncs automatically
   if you add more questions to `config/questions.yaml` later.
7. Test it in Copilot Studio's built-in test chat pane: ask "current
   headcount" and confirm it calls the tool and answers correctly.
8. **Publish** the agent, then **Share** it and assign specific users or
   groups (Viewer role) so only the right people can use it — or add the
   **Teams / Microsoft 365 Copilot** channel so it's reachable straight
   from Copilot chat rather than as a separate agent.

### Option B — Admin Center custom MCP connector (newer, tenant-wide)

Some tenants (particularly those in Microsoft's Frontier program) can
instead register the MCP server once, tenant-wide, without building a
Copilot Studio agent around it:

1. **Microsoft 365 Admin Center -> Copilot -> Settings** — confirm your
   tenant has custom MCP connectors available (this is rolling out
   gradually; if you don't see it, use Option A instead).
2. Add a **custom MCP connector**, pointing at the same `https://.../mcp`
   URL, with the same authentication choice as above (None, or OAuth).
3. Assign it to the users/groups who should have it, per your tenant's
   normal Copilot governance flow.
4. Copilot queries it **in real time** (not indexed like a Graph
   connector) — every question hits your live Workday data through the
   cache described in section 3, same as with Claude.

Either path, this is genuinely the same integration work you already did
for Claude — one server, two connector registrations. If Microsoft's UI
has moved by the time you get here (this space changes monthly), search
"Microsoft 365 Copilot MCP connector" on learn.microsoft.com for the
current screens.

## 7. Extending — add a field, a question, or a whole new report

This comes up constantly (someone adds a column to the Workday report,
or HR wants a question nobody predefined) so it has its own dedicated
walkthrough: **see `EXTENDING.md`** for the full step-by-step, with
worked examples for:
- adding a new field to a report someone already added a column for in
  Workday
- adding a new question over data you already have
- adding a whole new report + its questions
- bulk-generating a batch of new questions from a plain-text requirements
  list, the same way `config/questions.yaml`'s 141 questions were
  bootstrapped from yours

None of it requires touching `src/` — every case below is a YAML edit
plus a restart.

## 8. Project layout

```
workday-hr-mcp/
  config/
    reports.yaml     # report id → RAAS URL/mock fixture/documented fields
    questions.yaml    # 141 predefined questions, generated from your reqs doc
  src/
    workday_client.py # OAuth2 + RAAS fetch + in-memory cache + mock mode
    query_engine.py    # generic filter/aggregate over any rows/fields
    tool_builder.py     # turns questions.yaml into live MCP tools
    server.py            # entrypoint (stdio or streamable-http)
  scripts/
    generate_mock_data.py       # regenerate mock_data/*.json fixtures
    generate_question_stubs.py  # bulk-generate questions.yaml from a reqs doc
  mock_data/          # synthetic RAAS-shaped JSON for local testing
  tests/smoke_test.py # calls a handful of tools directly, no MCP client needed
```

## 9. Which Workday fields power which questions

`config/reports.yaml` documents this inline: each report has a
`description` explaining what it's for and a `fields:` list showing
what's on it. Short version: almost everything in Workforce, Turnover,
Performance, and Compensation comes off one wide `workers_report` (one
row per worker), plus five smaller, purpose-built reports for Recruiting,
Nine-Box/Succession, Internal Mobility, Learning, Skills, and Engagement,
since Workday typically tracks those as separate business processes
rather than worker attributes. See `EXTENDING.md` for exactly how to add
a field once you've decided you need one.
