# Argo — MCP Auditor Agent

Argo is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io)
server that exposes three audit-specific tools for AI governance and security
compliance work. It runs locally and connects to Claude Code, Claude Desktop,
or any MCP-compatible client.

Each tool wraps `claude-sonnet-4-6` with an auditor-grade prompt and returns
**structured JSON** — designed to mirror how a Big 4 auditor reads a SOC 2
report, drafts an ISO 42001 Statement of Applicability, and evaluates control
evidence.

> **Note:** Argo is a portfolio artifact demonstrating GRC engineering at the
> intersection of Big 4 audit experience and AI governance frameworks. Its
> outputs are AI-generated drafts intended to accelerate a qualified
> professional's work — not a substitute for professional judgment. See
> [Limitations](#limitations).

---

## The three tools

| Tool | Input | Output |
| --- | --- | --- |
| `summarize_soc2_report` | SOC 2 report text | Structured summary of the report |
| `draft_iso42001_soa_section` | AI system description + list of ISO 42001 controls | Drafted Statement of Applicability entries |
| `evaluate_control_evidence` | A control statement + an evidence description | Evidence sufficiency assessment with cross-framework mapping |

### 1. `summarize_soc2_report`

Reads the text of a SOC 2 report the way an auditor does during vendor due
diligence, and extracts the facts that actually affect a reliance decision.

**Input:** `report_text` (string) — the full text of the report.

**Output (JSON):**

- `service_organization_name`
- `audit_period`
- `opinion_type` — `Unqualified` / `Qualified` / `Adverse` / `Disclaimer`
- `trust_services_criteria` — the TSC categories in scope
- `key_exceptions` — testing exceptions and findings, with management responses
- `cuecs` — Complementary User Entity Controls
- `subservice_organizations` — name, service, and inclusive/carve-out treatment
- `risk_flags` — auditor-style flags that bear on reliance

### 2. `draft_iso42001_soa_section`

Drafts Statement of Applicability (SoA) entries for a set of ISO/IEC
42001:2023 Annex A controls, tailored to a specific AI system.

**Input:** `ai_system_description` (string) and `controls` (list of strings —
Annex A control references or names).

**Output (JSON):** a `soa_sections` array with one entry per control, each
containing:

- `control_reference` and `control_title`
- `applicability_decision` — `Applicable` / `Not Applicable`
- `justification` — a narrative tied to the specific system
- `implementation_status` — `Implemented` / `Partially Implemented` / `Planned` / `Not Implemented` / `Not Applicable`
- `evidence_pointer` — the type of artifact that would demonstrate the control

### 3. `evaluate_control_evidence`

Evaluates whether a piece of evidence sufficiently supports a control, applying
standard audit evidence methodology (sufficiency vs. appropriateness, the
reliability hierarchy, design vs. operating effectiveness, and period
coverage).

**Input:** `control_statement` (string) and `evidence_description` (string).

**Output (JSON):**

- `sufficiency_rating` — `Sufficient` / `Partially Sufficient` / `Insufficient`
- `coverage_assessment` — what the evidence does and does not demonstrate
- `gaps_identified`
- `recommended_additional_evidence`
- `framework_mapping` — the most relevant references in SOC 2, ISO 42001, and
  NIST AI RMF (or `No direct mapping`)

---

## Frameworks covered

Argo is built around three frameworks that together span security assurance and
AI governance:

- **SOC 2 (AICPA Trust Services Criteria).** The de facto standard for service
  organization security assurance. `summarize_soc2_report` reads Type I and
  Type II reports; `evaluate_control_evidence` maps controls to the relevant
  Trust Services Criteria (e.g. `CC6.x` logical access).

- **ISO/IEC 42001:2023.** The first international management-system standard for
  artificial intelligence. `draft_iso42001_soa_section` follows the Annex A
  control structure (objectives A.2–A.10) to draft Statement of Applicability
  entries.

- **NIST AI RMF.** The NIST AI Risk Management Framework
  (Govern / Map / Measure / Manage). `evaluate_control_evidence` maps controls
  to the relevant RMF function and category, giving a cross-framework view of
  where a control lives.

---

## How it works

Argo is a **stateless, local MCP server** — no database, no vector store, no
web framework. The architecture is intentionally small:

```
MCP client (Claude Code / Desktop)
        │  JSON-RPC over stdio
        ▼
   server.py            ← registers the 3 tools, routes calls
        │
        ▼
   tools/*.py           ← validate input, call claude-sonnet-4-6, parse JSON
        │
        ▼
   prompts/*.txt        ← the auditor logic lives here, not in code
```

- **`server.py`** advertises the three tools (name, description, input schema)
  and routes each call to its handler in `tools/`.
- Each **tool module** validates its inputs, loads its prompt, calls Claude,
  and parses the response into a Python dict.
- Each tool's **prompt** lives in `prompts/` as plain text, so the audit logic
  can be reviewed and refined without touching code.

---

## Project structure

```
argo-mcp/
├── server.py                 # MCP server entry point
├── requirements.txt
├── tools/
│   ├── soc2_summarizer.py     # Tool 1
│   ├── iso42001_soa.py        # Tool 2
│   └── evidence_evaluator.py  # Tool 3
├── prompts/                   # one prompt per tool (plain text)
├── schemas/                   # JSON output schemas (per tool)
└── tests/                     # per-tool tests
```

---

## Requirements

- Python 3.11 or newer
- An [Anthropic API key](https://console.anthropic.com/)

Runtime dependencies (see `requirements.txt`):

- `mcp` — the Model Context Protocol SDK
- `anthropic` — the Anthropic SDK (calls `claude-sonnet-4-6`)
- `python-dotenv` — convenience for loading the API key during development

---

## Installation

```bash
# Clone, then create and activate a virtual environment
python -m venv venv

# Windows (PowerShell)
venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Configuration

Argo reads your Anthropic API key from the `ANTHROPIC_API_KEY` environment
variable.

Set it in your shell:

```powershell
# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."
```

For local development you can keep the key in a git-ignored `.env` file at the
project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

The recommended way to supply the key to a desktop MCP client is the `env`
block of the client config (shown below), which sets the variable for the
server process directly.

---

## Running it

Argo speaks MCP over **stdio**, so it is launched by an MCP client rather than
run on its own. Register it with your client by pointing the command at the
virtual environment's Python and `server.py`.

Example client configuration (Claude Desktop / Claude Code
`mcpServers` block):

```json
{
  "mcpServers": {
    "argo": {
      "command": "C:\\path\\to\\argo-mcp\\venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\argo-mcp\\server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

On macOS / Linux, use the matching paths
(`venv/bin/python` and `/path/to/argo-mcp/server.py`).

Once the client restarts, the three Argo tools become available to the
assistant, which can call them as part of a conversation.

---

## Example

Calling `summarize_soc2_report` on a Type II report that contains a testing
exception returns (abridged):

```json
{
  "service_organization_name": "Northwind Cloud Services, Inc.",
  "audit_period": "January 1, 2024 to December 31, 2024",
  "opinion_type": "Qualified",
  "trust_services_criteria": ["Security", "Availability"],
  "key_exceptions": [
    {
      "control_area": "CC6.2 – Access deprovisioning",
      "description": "For 2 of 25 terminated employees sampled, production access was not revoked within the required 24 hours.",
      "management_response": "Management has since implemented an automated deprovisioning workflow."
    }
  ],
  "subservice_organizations": [
    {
      "name": "Amazon Web Services (AWS)",
      "service_provided": "Data center hosting",
      "treatment": "carve-out"
    }
  ],
  "risk_flags": [
    "Opinion is Qualified, not Unqualified — the CC6.2 exception modified the auditor's opinion.",
    "AWS is treated as a carve-out; obtain a separate AWS SOC 2 report to cover the infrastructure layer."
  ]
}
```

---

## Design principles

- **Clarity over cleverness.** Every function has a docstring; every file has a
  module comment. The goal is that any line can be explained in plain English.
- **Prompts live in `prompts/`.** Audit logic is text, reviewable independently
  of the code that runs it.
- **Explicit error handling.** Empty inputs, API failures, and malformed model
  output each raise a distinct, descriptive error — no silent failures.

---

## Limitations

- Outputs are **AI-generated drafts**, not assurance opinions or legal advice.
  Every result should be reviewed by a qualified professional before it informs
  a decision.
- Each tool makes a live call to the Anthropic API and is subject to model
  variability; results are not deterministic.
- Argo summarizes and evaluates only the text it is given. It does not fetch,
  validate, or independently verify the underlying evidence.

---

## Status & roadmap

Implemented and verified end-to-end against the live API:

- ✅ MCP server with all three tools registered and routed
- ✅ All three tool handlers and prompts

Planned:

- JSON output schemas in `schemas/` wired into the tools (structured outputs)
  to guarantee schema-valid responses
- Per-tool tests in `tests/`
- Optional file-path input for `summarize_soc2_report`
