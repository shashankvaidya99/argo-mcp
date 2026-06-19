"""
soc2_summarizer.py — Tool 1: summarize a SOC 2 report.

This module implements the logic behind the summarize_soc2_report MCP tool.
It takes the raw text of a SOC 2 report, sends it to Claude together with an
auditor prompt, and returns a structured Python dictionary that mirrors what a
Big 4 auditor extracts from a Type II report during vendor due diligence.

The prompt that drives the audit logic lives in
prompts/soc2_summarizer_prompt.txt, not in this file, so it can be edited and
reviewed without touching code.
"""

import json
from pathlib import Path

import anthropic
from anthropic.types import Message


# Claude model used for the audit logic, per the project's tech stack.
MODEL = "claude-sonnet-4-6"

# Where the auditor prompt lives. Resolved relative to this file so the tool
# works no matter which directory the server is launched from.
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "soc2_summarizer_prompt.txt"
)


def summarize_soc2_report(report_text: str) -> dict:
    """
    Summarize a SOC 2 report into structured audit findings.

    Takes the full text of a SOC 2 report as a string. Returns a dictionary
    with the service organization name, audit period, opinion type, Trust
    Services Criteria covered, key exceptions, CUECs, subservice
    organizations, and risk flags.

    Raises ValueError if the report text is empty, and RuntimeError if the
    Claude API call fails or returns something that is not valid JSON.
    """
    if not report_text or not report_text.strip():
        raise ValueError(
            "report_text is empty — provide the SOC 2 report text to summarize."
        )

    system_prompt = _load_prompt()
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": report_text}],
        )
    except anthropic.APIError as error:
        raise RuntimeError(f"Claude API call failed: {error}") from error

    raw_output = _extract_text(response)
    return _parse_json(raw_output)


def _load_prompt() -> str:
    """
    Read the auditor system prompt from the prompts/ folder.

    Takes no arguments. Returns the prompt text as a string. Raises
    FileNotFoundError with a clear message if the prompt file is missing, so a
    misconfigured install fails loudly instead of silently.
    """
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt file not found at {PROMPT_PATH}")

    return PROMPT_PATH.read_text(encoding="utf-8")


def _extract_text(response: Message) -> str:
    """
    Pull the text out of Claude's response.

    Takes the Message object returned by the Anthropic SDK. Returns the
    concatenated text of every text block in the response. Raises RuntimeError
    if the response contains no text at all.
    """
    text_parts = [block.text for block in response.content if block.type == "text"]
    if not text_parts:
        raise RuntimeError("Claude returned no text content to parse.")

    return "".join(text_parts)


def _parse_json(raw_output: str) -> dict:
    """
    Turn Claude's JSON text into a Python dictionary.

    Takes the raw text returned by Claude, tolerating a Markdown code fence
    around the JSON if the model adds one. Returns the parsed dictionary.
    Raises RuntimeError, including the raw text, if the output is not valid
    JSON — so the failure is explicit and debuggable.
    """
    cleaned = _strip_code_fences(raw_output)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Claude did not return valid JSON. "
            f"Error: {error}. Raw output:\n{raw_output}"
        ) from error


def _strip_code_fences(text: str) -> str:
    """
    Remove a Markdown code fence around JSON, if the model added one.

    Takes the raw model text. If it begins with a ``` fence (optionally tagged,
    such as ```json), this drops the opening fence line and the closing fence
    line and returns what is between them. Text with no fence is returned
    unchanged apart from surrounding whitespace.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    lines = lines[1:]  # drop the opening fence (``` or ```json)
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]  # drop the closing fence

    return "\n".join(lines)
