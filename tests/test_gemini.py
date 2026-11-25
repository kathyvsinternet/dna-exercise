"""The Gemini adapter, tested without network. A fake transport stands in for the API.

These tests check the request and reply shapes against the documented REST format, and that
the key is sent only in the header. They do not prove the live API accepts every field. The
live golden run (tests/test_live.py) does that when a key is set.
"""

import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "pipeline"))

import chat  # noqa: E402
import model_gemini  # noqa: E402
from catalog import load_catalog  # noqa: E402
from model_gemini import ENDPOINT, GeminiError, GeminiModel, gemini_from_env  # noqa: E402

KEY = "test-key-123456"


class FakeTransport:
    """Records each call and returns the scripted replies in order."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, api_key, body):
        self.calls.append({"url": url, "api_key": api_key, "body": body})
        return self.replies.pop(0)


def function_call(name, args):
    return {"candidates": [{"content": {"parts": [{"functionCall": {"name": name, "args": args}}]}}]}


def text_reply(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class RequestShapeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.tools = [chat.tool_definition(self.catalog)]

    def test_request_carries_system_prompt_tools_and_no_key(self):
        transport = FakeTransport(text_reply("hi"))
        model = GeminiModel(KEY, transport=transport)
        model.respond("SYSTEM TEXT", [{"role": "user", "content": "How many?"}], self.tools)
        call = transport.calls[0]
        self.assertEqual(call["url"], ENDPOINT.format(model=model_gemini.DEFAULT_MODEL))
        self.assertNotIn(KEY, call["url"])
        self.assertEqual(call["body"]["systemInstruction"]["parts"][0]["text"], "SYSTEM TEXT")
        declaration = call["body"]["tools"][0]["functionDeclarations"][0]
        self.assertEqual(declaration["name"], "query_mart")
        self.assertEqual(declaration["parameters"]["type"], "OBJECT")
        self.assertEqual(declaration["parameters"]["properties"]["mart"]["enum"], sorted(self.catalog["marts"]))

    def test_schema_has_no_untyped_or_unsupported_fields(self):
        transport = FakeTransport(text_reply("hi"))
        GeminiModel(KEY, transport=transport).respond("s", [{"role": "user", "content": "q"}], self.tools)
        text = json.dumps(transport.calls[0]["body"]["tools"])
        self.assertNotIn("minItems", text)
        self.assertNotIn('"minimum"', text)
        self.assertNotIn('"maximum"', text)
        value = transport.calls[0]["body"]["tools"][0]["functionDeclarations"][0]["parameters"]["properties"]["filters"]["items"]["properties"]["value"]
        self.assertEqual(value["type"], "STRING")
        self.assertIn("JSON list", value["description"])

    def test_tool_results_map_to_function_responses_with_the_same_name(self):
        messages = [
            {"role": "user", "content": "How many?"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "name": "query_mart", "input": {"mart": "mart_user_info_counts", "measures": ["n_users_active"]}}],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": json.dumps({"rows": [{"n_users_active": 389}]})},
        ]
        transport = FakeTransport(text_reply("389"))
        GeminiModel(KEY, transport=transport).respond("s", messages, self.tools)
        contents = transport.calls[0]["body"]["contents"]
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user"])
        self.assertEqual(contents[1]["parts"][0]["functionCall"]["name"], "query_mart")
        response = contents[2]["parts"][0]["functionResponse"]
        self.assertEqual(response["name"], "query_mart")
        self.assertEqual(response["response"]["result"], {"rows": [{"n_users_active": 389}]})

    def test_consecutive_tool_results_share_one_turn(self):
        messages = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "a", "name": "query_mart", "input": {}},
                    {"id": "b", "name": "query_mart", "input": {}},
                ],
            },
            {"role": "tool", "tool_call_id": "a", "content": "{}"},
            {"role": "tool", "tool_call_id": "b", "content": "{}"},
        ]
        transport = FakeTransport(text_reply("x"))
        GeminiModel(KEY, transport=transport).respond("s", messages, self.tools)
        contents = transport.calls[0]["body"]["contents"]
        self.assertEqual(len(contents), 3)
        self.assertEqual(len(contents[2]["parts"]), 2)


class ReplyTests(unittest.TestCase):
    def test_text_reply(self):
        reply = model_gemini._reply(text_reply("  There are 389 active users. "))
        self.assertEqual(reply, {"text": "There are 389 active users.", "tool_calls": []})

    def test_function_call_reply(self):
        reply = model_gemini._reply(function_call("query_mart", {"mart": "mart_user_info_counts"}))
        self.assertIsNone(reply["text"])
        self.assertEqual(reply["tool_calls"], [{"id": "call-1", "name": "query_mart", "input": {"mart": "mart_user_info_counts"}}])

    def test_thought_signature_is_kept_and_sent_back(self):
        raw = {"candidates": [{"content": {"parts": [
            {"functionCall": {"name": "query_mart", "args": {"mart": "mart_user_info_counts"}},
             "thoughtSignature": "SIG-ABC"}]}}]}
        reply = model_gemini._reply(raw)
        self.assertEqual(reply["tool_calls"][0]["signature"], "SIG-ABC")

        transport = FakeTransport(text_reply("389"))
        GeminiModel(KEY, transport=transport).respond(
            "s",
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "", "tool_calls": reply["tool_calls"]},
                {"role": "tool", "tool_call_id": "call-1", "content": '{"status": "answered"}'},
            ],
            [],
        )
        model_turn = transport.calls[0]["body"]["contents"][1]
        self.assertEqual(model_turn["parts"][0]["thoughtSignature"], "SIG-ABC")

    def test_http_error_shows_google_message_but_not_the_key(self):
        body = json.dumps({"error": {"message": f"API key not valid: {KEY}"}}).encode()

        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

        with mock.patch("model_gemini.urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(GeminiError) as raised:
                model_gemini._post(ENDPOINT.format(model="m"), KEY, {"contents": []})
        self.assertIn("HTTP 400", str(raised.exception))
        self.assertIn("API key not valid", str(raised.exception))
        self.assertNotIn(KEY, str(raised.exception))

    def test_blocked_reply_raises_without_detail(self):
        with self.assertRaises(GeminiError) as raised:
            model_gemini._reply({"promptFeedback": {"blockReason": "SAFETY"}})
        self.assertIn("SAFETY", str(raised.exception))


class TransportTests(unittest.TestCase):
    def test_key_goes_in_the_header_not_the_url(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps(text_reply("ok")).encode()

        def fake_urlopen(request, timeout):
            captured["request"] = request
            return FakeResponse()

        with mock.patch("model_gemini.urllib.request.urlopen", side_effect=fake_urlopen):
            model_gemini._post(ENDPOINT.format(model="m"), KEY, {"contents": []})
        request = captured["request"]
        self.assertEqual(request.get_header("X-goog-api-key"), KEY)
        self.assertNotIn(KEY, request.full_url)
        self.assertNotIn("key=", request.full_url)

    def test_http_error_message_does_not_contain_the_key(self):
        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

        with mock.patch("model_gemini.urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(GeminiError) as raised:
                model_gemini._post(ENDPOINT.format(model="m"), KEY, {"contents": []})
        self.assertIn("403", str(raised.exception))
        self.assertNotIn(KEY, str(raised.exception))


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def test_no_key_means_no_model(self):
        os.environ.pop("GEMINI_API_KEY", None)
        self.assertIsNone(gemini_from_env())

    def test_key_gives_a_model_and_gemini_is_registered(self):
        os.environ["GEMINI_API_KEY"] = KEY
        os.environ.pop("GEMINI_MODEL", None)
        model = gemini_from_env()
        self.assertEqual(model.model, model_gemini.DEFAULT_MODEL)
        self.assertIn("gemini", chat.PROVIDERS)

    def test_model_name_can_be_changed_without_code(self):
        os.environ["GEMINI_API_KEY"] = KEY
        os.environ["GEMINI_MODEL"] = "gemini-test-model"
        self.assertEqual(gemini_from_env().model, "gemini-test-model")


class EndToEndTests(unittest.TestCase):
    def test_a_turn_through_the_gemini_adapter(self):
        transport = FakeTransport(
            function_call("query_mart", {"mart": "mart_user_info_counts", "measures": ["n_users_active"]}),
            text_reply("There are 389 active users."),
        )
        payload = chat.answer("How many active users are there?", GeminiModel(KEY, transport=transport))
        self.assertEqual(payload["status"], "answered")
        self.assertEqual(payload["rows"], [{"n_users_active": 389}])

    def test_string_values_from_the_model_are_accepted(self):
        transport = FakeTransport(
            function_call(
                "query_mart",
                {
                    "mart": "mart_user_share_subs_active",
                    "measures": ["n_users"],
                    "filters": [{"column": "n_subs_active", "op": "eq", "value": "2"}],
                },
            ),
            text_reply("43 users hold two active subscriptions."),
        )
        payload = chat.answer("How many users hold two active subscriptions?", GeminiModel(KEY, transport=transport))
        self.assertEqual(payload["status"], "answered")
        self.assertEqual(payload["rows"], [{"n_users": 43}])

    def test_refusal_reaches_the_model_as_a_function_response(self):
        transport = FakeTransport(
            function_call("query_mart", {"mart": "mart_user_share_country", "group_by": ["email"], "measures": ["n_users"]}),
            text_reply("I can't provide email addresses."),
        )
        payload = chat.answer("What is the email for USR_00001?", GeminiModel(KEY, transport=transport))
        self.assertEqual(payload["status"], "declined")
        response = transport.calls[1]["body"]["contents"][2]["parts"][0]["functionResponse"]["response"]["result"]
        self.assertEqual(response["error"], "unknown_column")


if __name__ == "__main__":
    unittest.main()
