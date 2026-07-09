"""
iso42001_soa.py — Tool 2: draft an ISO 42001 Statement of Applicability section.

This module implements the logic behind the draft_iso42001_soa_section MCP
tool. It takes a description of an AI system plus a list of ISO/IEC 42001
Annex A controls, sends them to Claude with a Statement of Applicability (SoA)
prompt, and returns a structured Python dictionary containing one drafted SoA
entry per control.

The prompt that drives the drafting logic lives in
prompts/iso42001_soa_prompt.txt, not in this file, so it can be edited and
reviewed without touching code.

The small helpers at the bottom (_load_prompt, _extract_text, _parse_json)
mirror those in soc2_summarizer.py on purpose: each tool module is kept
self-contained so it can be read and explained on its own.
"""

import json
from pathlib import Path

import anthropic
from anthropic.types import Message


# Claude model used for the drafting logic, per the project's tech stack.
MODEL = "claude-sonnet-4-6"

# Input size limits, in characters (and count for the controls list). These caps
# keep the assembled prompt well inside the model's context window and reject
# oversized input at the boundary before any API call is made.
MAX_DESCRIPTION_CHARS = 50_000
MAX_CONTROLS = 100
MAX_CONTROL_CHARS = 500

# Where the SoA prompt lives. Resolved relative to this file so the tool works
# no matter which directory the server is launched from.
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "iso42001_soa_prompt.txt"
)


def draft_iso42001_soa_section(ai_system_description: str, controls: list) -> dict:
    """
    Draft a Statement of Applicability section for a set of ISO 42001 controls.

    Takes a description of the AI system as a string, and a list of ISO 42001
    Annex A controls (strings) to address. Returns a dictionary with one
    "soa_sections" entry per control, each carrying a control reference,
    control title, applicability decision, justification narrative,
    implementation status, and evidence pointer.

    Raises ValueError if the description is empty or the controls list is
    missing, empty, or contains anything other than strings. Raises
    RuntimeError if the Claude API call fails or returns something that is not
    valid JSON.
    """
    if not ai_system_description or not ai_system_description.strip():
        raise ValueError(
            "ai_system_description is empty — describe the AI system in scope."
        )

    _validate_length(
        "ai_system_description", ai_system_description, MAX_DESCRIPTION_CHARS
    )
    _validate_controls(controls)

    system_prompt = _load_prompt()
    user_message = _build_user_message(ai_system_description, controls)
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
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


def _validate_controls(controls: list) -> None:
    """
    Check that the controls argument is a non-empty list of strings.

    Takes the controls value passed by the caller. Returns nothing on success.
    Raises ValueError with a clear message if the value is not a list, is
    empty, holds more than MAX_CONTROLS items, contains any item that is not a
    string, or contains a control longer than MAX_CONTROL_CHARS — so bad or
    oversized input fails loudly at the boundary instead of producing a
    confusing or overlong prompt.
    """
    if not isinstance(controls, list) or not controls:
        raise ValueError(
            "controls must be a non-empty list of ISO 42001 control references."
        )

    if len(controls) > MAX_CONTROLS:
        raise ValueError(
            f"controls has too many items — {len(controls):,} exceeds the "
            f"limit of {MAX_CONTROLS}. Reduce the number of controls and try again."
        )

    if not all(isinstance(control, str) for control in controls):
        raise ValueError("Every item in controls must be a string.")

    for index, control in enumerate(controls):
        _validate_length(f"controls[{index}]", control, MAX_CONTROL_CHARS)


def _build_user_message(ai_system_description: str, controls: list) -> str:
    """
    Assemble the user message sent to Claude.

    Takes the AI system description and the list of controls. Returns a single
    string that labels the system description and lists each control on its own
    line, so the prompt the model sees is clear and ordered.
    """
    control_lines = "\n".join(f"- {control}" for control in controls)
    return (
        "AI system description:\n"
        f"{ai_system_description}\n\n"
        "ISO 42001 Annex A controls to address:\n"
        f"{control_lines}"
    )


def _load_prompt() -> str:
    """
    Read the SoA system prompt from the prompts/ folder.

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
