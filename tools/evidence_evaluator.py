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

    Takes the raw text returned by Claude. Returns the parsed dictionary.
    Raises RuntimeError, including the raw text, if the output is not valid
    JSON — so the failure is explicit and debuggable.
    """
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Claude did not return valid JSON. "
            f"Error: {error}. Raw output:\n{raw_output}"
        ) from error
