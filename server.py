"""
server.py — Argo MCP server entry point.

This file is the front door of the Argo MCP server. It does four things:

1. Creates an MCP server instance using the MCP SDK.
2. Tells any connected client (for example, Claude Code) which tools Argo
   exposes, by listing each tool's name, description, and input schema.
3. Routes an incoming tool call to the matching handler function in tools/.
4. Runs the server over stdio so a local MCP client can talk to it.

Argo exposes three audit tools. Only summarize_soc2_report is implemented so
far; the other two are registered here but their handler functions are still
being built, so calling them returns a clear error message rather than
crashing the server.
"""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types


# Load environment variables (notably ANTHROPIC_API_KEY) from a .env file next
# to this script, if one exists. The path is resolved relative to this file so
# it works no matter which directory the MCP client launches the server from.
# If there is no .env, this does nothing and the key is read from the real
# environment instead (for example, an MCP client's "env" config block).
load_dotenv(Path(__file__).resolve().parent / ".env")


# The single MCP server instance. The name "argo" is how clients identify us.
server = Server("argo")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """
    Tell the connected MCP client which tools Argo exposes.

    Takes no arguments. Returns a list of tool definitions, where each
    definition carries the tool's name, a human-readable description, and a
    JSON Schema describing the arguments the tool expects.
    """
    return [
        types.Tool(
            name="summarize_soc2_report",
            description=(
                "Summarize a SOC 2 report into structured JSON: service "
                "organization, audit period, opinion type, Trust Services "
                "Criteria, key exceptions, CUECs, subservice organizations, "
                "and risk flags. Mirrors how a Big 4 auditor reads a Type II "
                "report during vendor due diligence."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "report_text": {
                        "type": "string",
                        "description": "The full text of the SOC 2 report to summarize.",
                        "maxLength": 500000,
                    }
                },
                "required": ["report_text"],
            },
        ),
        types.Tool(
            name="draft_iso42001_soa_section",
            description=(
                "Draft a Statement of Applicability section for ISO/IEC "
                "42001:2023, given an AI system description and a list of "
                "Annex A controls to address."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ai_system_description": {
                        "type": "string",
                        "description": "Description of the AI system in scope.",
                        "maxLength": 50000,
                    },
                    "controls": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 500},
                        "maxItems": 100,
                        "description": "List of ISO 42001 controls to address.",
                    },
                },
                "required": ["ai_system_description", "controls"],
            },
        ),
        types.Tool(
            name="evaluate_control_evidence",
            description=(
                "Evaluate whether a piece of evidence sufficiently supports a "
                "control. Returns a sufficiency rating, coverage assessment, "
                "gaps, recommended additional evidence, and a mapping across "
                "SOC 2 / ISO 42001 / NIST AI RMF."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "control_statement": {
                        "type": "string",
                        "description": "The control being tested.",
                        "maxLength": 20000,
                    },
                    "evidence_description": {
                        "type": "string",
                        "description": "Description of the evidence provided.",
                        "maxLength": 50000,
                    },
                },
                "required": ["control_statement", "evidence_description"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """
    Route an incoming tool call to the correct handler in the tools/ folder.

    Takes the tool name and a dictionary of arguments sent by the client.
    Returns the handler's structured result serialized as pretty-printed JSON
    inside a single text block. If the tool name is unknown, the handler is
    not implemented yet, or the handler raises, it returns a clear error
    message instead of letting the server crash.
    """
    try:
        result = _dispatch(name, arguments)
    except Exception as error:
        # Explicit, visible failure — never swallow the error silently.
        return [types.TextContent(type="text", text=f"Error running '{name}': {error}")]

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _dispatch(name: str, arguments: dict) -> dict:
    """
    Call the handler function that matches the requested tool name.

    Takes the tool name and its arguments. Returns the handler's result as a
    dictionary. Imports are done lazily (inside each branch) so the server can
    start even while the handlers for tools 2 and 3 are still empty files.
    Raises ValueError for an unknown tool name.
    """
    if name == "summarize_soc2_report":
        from tools.soc2_summarizer import summarize_soc2_report

        return summarize_soc2_report(arguments["report_text"])

    if name == "draft_iso42001_soa_section":
        from tools.iso42001_soa import draft_iso42001_soa_section

        return draft_iso42001_soa_section(
            arguments["ai_system_description"], arguments["controls"]
        )

    if name == "evaluate_control_evidence":
        from tools.evidence_evaluator import evaluate_control_evidence

        return evaluate_control_evidence(
            arguments["control_statement"], arguments["evidence_description"]
        )

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """
    Run the Argo MCP server over stdio.

    Takes no arguments and returns nothing. Opens a stdio connection (the
    transport a local MCP client such as Claude Code uses) and hands control
    to the server's run loop until the client disconnects.
    """
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
