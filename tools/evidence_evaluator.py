"""
evidence_evaluator.py — Tool 3: evaluate control evidence.

This module implements the logic behind the evaluate_control_evidence MCP tool.
It takes a control statement and a description of the evidence offered for that
control, sends them to Claude with an evidence-evaluation prompt, and returns a
structured Python dictionary: a sufficiency rating, a coverage assessment, the
gaps identified, recommended additional evidence, and a mapping of the control
across SOC 2, ISO 42001, and NIST AI RMF.

The prompt that drives the evaluation logic lives in
prompts/evidence_evaluator_prompt.txt, not in this file, so it can be edited
and reviewed without touching code.

The small helpers at the bottom (_load_prompt, _extract_text, _parse_json)
mirror those in the other two tool modules on purpose: each tool module is kept
self-contained so it can be read and explained on its own.
"""

import json
from pathlib import Path

import anthropic
from anthropic.types import Message


# Claude model used for the evaluation logic, per the project's tech stack.
MODEL = "claude-sonnet-4-6"

# Input size limits, in characters. A control statement is normally a sentence
# or two, while an evidence description can be a longer narrative, so they are
# capped separately. These limits keep the assembled prompt well inside the
# model's context window and reject oversized input at the boundary before any
# API call is made.
MAX_CONTROL_STATEMENT_CHARS = 20_000
MAX_EVIDENCE_CHARS = 50_000

# Where the evaluation prompt lives. Resolved relative to this file so the tool
# works no matter which directory the server is launched from.
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "evidence_evaluator_prompt.txt"
)


def evaluate_control_evidence(control_statement: str, evidence_description: str) -> dict:
    """
    Evaluate whether a piece of evidence sufficiently supports a control.

    Takes the control statement and a description of the evidence, both as
    strings. Returns a dictionary with a sufficiency rating, a coverage
    assessment, the gaps identified, recommended additional evidence, and a
    framework mapping across SOC 2, ISO 42001, and NIST AI RMF.

    Raises ValueError if either input is empty. Raises RuntimeError if the
    Claude API call fails or returns something that is not valid JSON.
    """
    if not control_statement or not control_statement.strip():
        raise ValueError(
            "control_statement is empty — provide the control being tested."
        )

    if not evidence_description or not evidence_description.strip():
        raise ValueError(
            "evidence_description is empty — describe the evidence being evaluated."
        )

    _validate_length(
        "control_statement", control_statement, MAX_CONTROL_STATEMENT_CHARS
    )
    _validate_length(
        "evidence_description", evidence_description, MAX_EVIDENCE_CHARS
    )

    system_prompt = _load_prompt()
    user_message = _build_user_message(control_statement, evidence_description)
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as error:
        raise RuntimeError(f"Claude API call failed: {error}") from error

    raw_output = _extract_text(response)
    return _parse_json(raw_output)


def _validate_length(field_name: str, text: str, limit: int) -> None:
    """
    Check that a text input does not exceed its character limit.

    Takes the field's name (used only to build a clear error message), the text
    to measure, and the maximum number of characters allowed. Returns nothing on
    success. Raises ValueError stating the actual size and the limit if the text
    is too long, so oversized input is rejected loudly at the boundary before any
    API call is made.
    """
    if len(text) > limit:
        raise ValueError(
            f"{field_name} is too large — {len(text):,} characters exceeds the "
            f"{limit:,}-character limit. Trim the input and try again."
        )


def _build_user_message(control_statement: str, evidence_description: str) -> str:
    """
    Assemble the user message sent to Claude.

    Takes the control statement and the evidence description. Returns a single
    string that labels each input clearly, so the model sees the control and
    the evidence as two separate, well-marked sections.
    """
    return (
        "Control statement:\n"
        f"{control_statement}\n\n"
        "Evidence description:\n"
        f"{evidence_description}"
    )


def _load_prompt() -> str:
    """
    Read the evaluation system prompt from the prompts/ folder.

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
