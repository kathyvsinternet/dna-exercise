"""Gemini adapter for pipeline/chat.py. Standard library only.

chat.py speaks a neutral message shape. This file turns it into a Gemini generateContent
request and turns the reply back into {"text", "tool_calls"}.

The key comes from GEMINI_API_KEY and is sent in the x-goog-api-key header. It is never put
in the URL, so it does not appear in logs that record URLs. Errors raised here do not
include the key or the request body.
"""

import json
import os
import urllib.error
import urllib.request

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
TIMEOUT_SECONDS = 30
MAX_OUTPUT_TOKENS = 1024

FILTER_VALUE_NOTE = (
    "The filter value, as a string. Dates as YYYY-MM-DD. Integers as digits, such as 2. "
    "For op in, a JSON list written as a string, such as [\"email_campaign\",\"paid_social\"]."
)

SCHEMA_TYPES = {
    "object": "OBJECT",
    "array": "ARRAY",
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
}


class GeminiError(Exception):
    """The Gemini call failed. The message never contains the key or the request body."""


class GeminiModel:
    def __init__(self, api_key, model=DEFAULT_MODEL, transport=None):
        self.api_key = api_key
        self.model = model
        self.transport = transport or _post

    def respond(self, system, messages, tools):
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": _contents(messages),
            "tools": [{"functionDeclarations": [_declaration(tool) for tool in tools]}],
            "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS, "temperature": 0},
        }
        raw = self.transport(ENDPOINT.format(model=self.model), self.api_key, body)
        return _reply(raw)


def gemini_from_env():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    return GeminiModel(key, model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL)


def _contents(messages):
    """Neutral messages to Gemini contents. Consecutive tool results share one turn."""
    names = {}
    contents = []
    for message in messages:
        role = message["role"]
        if role == "user":
            contents.append({"role": "user", "parts": [{"text": message["content"]}]})
        elif role == "assistant":
            parts = []
            if message.get("content"):
                parts.append({"text": message["content"]})
            for call in message.get("tool_calls") or []:
                names[call.get("id")] = call["name"]
                parts.append({"functionCall": {"name": call["name"], "args": call.get("input") or {}}})
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif role == "tool":
            part = {
                "functionResponse": {
                    "name": names.get(message.get("tool_call_id"), "query_mart"),
                    "response": {"result": _as_object(message["content"])},
                }
            }
            if contents and contents[-1]["role"] == "user" and _is_tool_turn(contents[-1]):
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
    return contents


def _is_tool_turn(content):
    return all("functionResponse" in part for part in content["parts"])


def _as_object(content):
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        return {"text": str(content)}
    return value if isinstance(value, dict) else {"value": value}


def _declaration(tool):
    return {
        "name": tool["name"],
        "description": tool["description"],
        "parameters": _schema(tool["input_schema"], top=True),
    }


def _schema(node, top=False):
    """Convert a JSON Schema fragment to the subset Gemini accepts.

    Untyped values become a string with an explanation. Bounds such as minimum and minItems
    are dropped here, and the executor still enforces them.
    """
    if not node.get("type") and "enum" not in node and not top:
        return {"type": "STRING", "description": FILTER_VALUE_NOTE}
    out = {"type": SCHEMA_TYPES[node["type"]]} if "type" in node else {}
    if "description" in node:
        out["description"] = node["description"]
    if "enum" in node:
        out["enum"] = node["enum"]
        out.setdefault("type", "STRING")
    if "properties" in node:
        out["properties"] = {name: _schema(child) for name, child in node["properties"].items()}
    if "required" in node:
        out["required"] = list(node["required"])
    if "items" in node:
        out["items"] = _schema(node["items"])
    return out


def _reply(raw):
    candidates = raw.get("candidates") or []
    if not candidates:
        reason = (raw.get("promptFeedback") or {}).get("blockReason", "no candidates")
        raise GeminiError(f"Gemini returned no answer ({reason}).")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = []
    calls = []
    for part in parts:
        if "text" in part:
            texts.append(part["text"])
        if "functionCall" in part:
            call = part["functionCall"]
            calls.append(
                {
                    "id": f"call-{len(calls) + 1}",
                    "name": call.get("name", ""),
                    "input": call.get("args") or {},
                }
            )
    text = "".join(texts).strip() or None
    return {"text": text, "tool_calls": calls}


def _post(url, api_key, body):
    data = json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        raise GeminiError(f"Gemini request failed with HTTP {status}.") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise GeminiError("Gemini request failed before a reply arrived.") from None
