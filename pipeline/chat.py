"""One chat turn: the model asks for data through query_mart, and the executor answers.

The model never reads the marts, and it never supplies numbers it has not been given:

1. The model sees the catalog as text, and one tool, query_mart.
2. Each query_mart call goes through pipeline/executor.py. A refusal is returned to the
   model as a tool error, and it may try again, up to MAX_TOOL_CALLS calls in all.
3. The final answer may use only numbers that appear in the question or in the rows the
   model was shown. If it uses any other number, the answer is replaced by a statement
   that the chat cannot answer the question, and the status is "unverified".

The model is any object with respond(system, messages, tools), which returns
{"text": str or None, "tool_calls": [{"id", "name", "input"}]}. Messages use a neutral
shape: {"role": "user", "content"}, {"role": "assistant", "content", "tool_calls"}, and
{"role": "tool", "tool_call_id", "content"}. A provider adapter translates them. Adapters
are not in this file, so the rules here do not depend on a provider.

The number check does not verify names, categories, or claims in words. It checks numbers
only. Words are constrained by the prompt and by the rows shown.
"""

import json
import os
import re
import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

from catalog import load_catalog  # noqa: E402
from executor import Executor, QueryRefused  # noqa: E402
from model_gemini import gemini_from_env  # noqa: E402

CANNOT_VERIFY = "I can't answer that question from the numbers I can verify, so I'm not giving an answer."
MAX_TOOL_CALLS = 3
MAX_QUESTION_CHARS = 500
ROW_PREVIEW = 25
FALLBACK_ROWS = 10

NUMBER = re.compile(r"(?<!\w)-?\d[\d,]*(?:\.\d+)?")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
LIST_MARKER = re.compile(r"^\s*\d+[.)](?=\s)", re.MULTILINE)


class ChatError(Exception):
    """The request cannot be answered. code is a short reason for the caller."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def tool_definition(catalog):
    return {
        "name": "query_mart",
        "description": (
            "Run one query against a published mart. Returns the rows, or an error code and "
            "message. Use only the marts and columns listed in the system prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mart": {"type": "string", "enum": sorted(catalog["marts"])},
                "group_by": {"type": "array", "items": {"type": "string"}},
                "measures": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "op": {"type": "string", "enum": ["eq", "in", "gte", "lte"]},
                            "value": {},
                        },
                        "required": ["column", "op", "value"],
                    },
                },
                "sort": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "direction": {"type": "string", "enum": ["asc", "desc"]},
                        },
                        "required": ["column", "direction"],
                    },
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["mart", "measures"],
        },
    }


def render_catalog(catalog):
    """The catalog as plain text for the system prompt."""
    lines = []
    for name in sorted(catalog["marts"]):
        mart = catalog["marts"][name]
        lines.append(f"## {name}: {mart['label']}")
        if mart["description"]:
            lines.append(mart["description"])
        if mart["grain"]:
            lines.append(f"One row per: {mart['grain']}.")
        for note in mart["notes"]:
            lines.append(f"Note: {note}")
        for column, spec in mart["columns"].items():
            synonyms = f" Also called: {', '.join(spec['synonyms'])}." if spec["synonyms"] else ""
            if spec["role"] == "dimension":
                lines.append(f"- {column} (group_by or filter, {spec['type']}): {spec['label']}.{synonyms}")
            else:
                how = "adds up across rows" if spec["aggregation"] == "sum" else "one row per group only"
                people = ", distinct people" if spec["people"] else ""
                caveat = f" Caveat: {spec['caveat']}" if spec["caveat"] else ""
                lines.append(f"- {column} (measure, {how}{people}): {spec['label']}.{synonyms}{caveat}")
        lines.append("")
    if catalog["not_answerable"]:
        lines.append("Not answerable from these marts:")
        lines.extend(f"- {item}" for item in catalog["not_answerable"])
    return "\n".join(lines)


def build_system_prompt(catalog):
    return "\n".join(
        [
            "You answer questions about a subscription product. You have one tool, query_mart,",
            "and you answer only from its results.",
            "",
            "Rules:",
            "- Call query_mart for every number. Do not estimate, recall, or calculate a number yourself.",
            "- Use only the marts, columns, and operators listed below.",
            "- If a call returns an error, read the message. Fix the query, or say the data is not available.",
            "- If the question asks for a total, a sum, or how many in all, call query_mart with no group_by. The mart then returns one total row. Answer with that total, not with a breakdown.",
            "- If the question asks for one value of a column, such as one device or one country, filter to that value. Do not group by a column the question does not name.",
            "- A measure marked \"one row per group only\", such as a rate or a running total, cannot be added up. Ask for it with group_by on the column that gives one row per group, such as quarter, or filter to a single row. If the question names no period, group by the time column, sort it newest first, limit to 4 rows, and say which periods you are showing. A measure that does add up needs no group_by when the question asks for a total or a single figure, so answer with that total.",
            "- Sort only by a column that is in group_by or measures.",
            "- Name a quarter by its label, such as Q4 2025. Do not add calendar dates or day numbers that are not in the rows.",
            "- Never give a person's name or email address, or list individual users.",
            "- Quote numbers exactly as returned. Name the mart you used.",
            "- Include the notes that apply to a measure, such as a caveat that a figure is not revenue.",
            "- If the question cannot be answered from these marts, say so in one sentence.",
            "",
            "Catalog:",
            render_catalog(catalog),
        ]
    )


def clean_question(question):
    if not isinstance(question, str):
        raise ChatError("bad_request", "The question must be text.")
    text = question.strip()
    if not text:
        raise ChatError("bad_request", "The question is empty.")
    if len(text) > MAX_QUESTION_CHARS:
        raise ChatError("too_long", f"The question is longer than {MAX_QUESTION_CHARS} characters.")
    return text


def answer(question, model, catalog=None, executor=None):
    """Run one turn. Returns a payload dict. See _finish for the statuses."""
    text_question = clean_question(question)
    catalog = catalog or load_catalog()
    executor = executor or Executor(catalog)
    system = build_system_prompt(catalog)
    tools = [tool_definition(catalog)]
    messages = [{"role": "user", "content": text_question}]
    successes, refusals, calls = [], [], 0

    for _ in range(MAX_TOOL_CALLS + 1):
        reply = model.respond(system, messages, tools)
        requested = reply.get("tool_calls") or []
        if not requested:
            return _finish(text_question, reply.get("text") or "", successes, refusals, calls)
        messages.append({"role": "assistant", "content": reply.get("text") or "", "tool_calls": requested})
        for call in requested:
            calls += 1
            if calls > MAX_TOOL_CALLS:
                return _finish(text_question, "", successes, refusals, calls, gave_up=True)
            try:
                result = executor.run(call.get("input"))
            except QueryRefused as refusal:
                refusals.append(refusal.code)
                content = {"error": refusal.code, "message": refusal.message}
            else:
                successes.append(result)
                content = _tool_payload(result)
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(content)})

    return _finish(text_question, "", successes, refusals, calls, gave_up=True)


def _tool_payload(result):
    return {
        "mart": result["label"],
        "rows": result["rows"][:ROW_PREVIEW],
        "row_count": result["row_count"],
        "notes": result["notes"],
    }


def _finish(question, text, successes, refusals, calls, gave_up=False):
    """Decide the status and the text the user sees.

    answered    the model answered, and every number is in the question or the rows shown
    declined    no query succeeded, and the model answered without a number it had no source for
    unverified  the model used a number that was not in the question or the rows shown
    gave_up     the model used all its tool calls without a final answer
    """
    last = successes[-1] if successes else None
    shown = [_tool_payload(result) for result in successes]
    base = {
        "mart": last["mart"] if last else None,
        "label": last["label"] if last else None,
        "query": last["query"] if last else None,
        "rows": last["rows"][:ROW_PREVIEW] if last else [],
        "notes": last["notes"] if last else [],
        "row_count": last["row_count"] if last else 0,
        "tool_calls": calls,
        "refusals": refusals,
    }

    if gave_up:
        status = "gave_up"
        answer_text = _fallback(last) if last else "I could not answer that from the available data."
        return {**base, "status": status, "answer": answer_text}

    unknown = _unverified_numbers(text, question, shown)
    if unknown:
        return {**base, "status": "unverified", "answer": CANNOT_VERIFY}

    if successes:
        return {**base, "status": "answered", "answer": text.strip()}
    fallback_text = text.strip() or "I can't answer that from the available data."
    return {**base, "status": "declined", "answer": fallback_text}


def _unverified_numbers(text, question, shown):
    """Numbers in the answer that are not in the question or in the rows the model saw."""
    allowed = _candidates(_numbers_in(question) + _source_numbers(shown))
    # "2." at the start of a list item is a position, not a figure from the data.
    body = LIST_MARKER.sub(" ", text)
    return [n for n in _numbers_in(body) if round(n, 4) not in allowed]


def _numbers_in(text):
    text = ISO_DATE.sub(" ", text)
    found = []
    for token in NUMBER.findall(text):
        try:
            found.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return found


def _source_numbers(shown):
    numbers = []
    for payload in shown:
        numbers.append(float(payload["row_count"]))
        numbers.append(float(len(payload["rows"])))
        # Notes are catalog text the model is shown with the rows, so a figure quoted from them is sourced.
        for note in payload.get("notes") or []:
            numbers.extend(_numbers_in(note))
        for row in payload["rows"]:
            for value in row.values():
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    numbers.append(float(value))
                elif isinstance(value, str):
                    # Numbers inside text, such as a title's "#205", are source numbers too.
                    numbers.extend(_numbers_in(value))
                    for match in ISO_DATE.finditer(value):
                        numbers.extend(float(part) for part in match.groups())
    return numbers


def _candidates(values):
    """Each source value as the answer may write it: as is, or as a percentage, rounded."""
    allowed = set()
    for value in values:
        for digits in range(5):
            allowed.add(round(value, digits))
        for digits in range(3):
            allowed.add(round(value * 100, digits))
    return allowed


def _fallback(result):
    lines = [f"{result['label']}:"]
    for row in result["rows"][:FALLBACK_ROWS]:
        lines.append("- " + ", ".join(f"{key}: {value}" for key, value in row.items()))
    if result["row_count"] > FALLBACK_ROWS:
        lines.append(f"Showing {FALLBACK_ROWS} of {result['row_count']} rows.")
    lines.append("The wording of the answer could not be checked against these rows, so the rows are shown instead.")
    return "\n".join(lines)


def handle_request(body, origin, allowed_origins, model):
    """The HTTP contract, without HTTP. Returns (status code, payload dict).

    allowed_origins is the ALLOWED_ORIGINS setting, a comma-separated list. If it is empty
    every request is refused, so the endpoint is never open by accident.
    """
    allowed = [item.strip() for item in (allowed_origins or "").split(",") if item.strip()]
    if not allowed:
        return 403, {"error": "origins_not_configured", "message": "ALLOWED_ORIGINS is not set."}
    if origin not in allowed:
        return 403, {"error": "forbidden", "message": "This origin may not use the chat."}
    if model is None:
        return 503, {"error": "model_not_configured", "message": "No model provider is configured."}
    if not isinstance(body, dict):
        return 400, {"error": "bad_request", "message": "Send a JSON object with a question."}
    try:
        return 200, answer(body.get("question"), model)
    except ChatError as error:
        return 400, {"error": error.code, "message": error.message}
    except Exception as error:  # noqa: BLE001 - never return internals to the browser
        print(f"chat failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 502, {"error": "model_error", "message": "The chat could not finish this question."}


# Provider adapters register here. A factory returns a model, or None when its key is missing.
# An unregistered or unset CHAT_PROVIDER means no model, and the endpoint answers 503.
PROVIDERS = {"gemini": gemini_from_env}


def model_from_env():
    name = os.environ.get("CHAT_PROVIDER", "")
    factory = PROVIDERS.get(name)
    return factory() if factory else None
