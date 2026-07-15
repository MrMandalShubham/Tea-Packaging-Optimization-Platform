"""
Tests for the AI service.

Two things are being defended here:

  1. The security boundary. The API key must live server-side and must never
     appear in a response, an error message, or a log line.
  2. The honesty boundary. When the assistant states a number, that number must
     have come from the optimiser via a tool call — not from the model's
     imagination.

No network calls: the OpenAI transport is stubbed throughout.
"""

import json

import pytest

from app.services import ai_service
from app.services.ai_service import (
    AIServiceError,
    _parse_validations,
    _run_what_if,
    answer_question,
    WHAT_IF_TOOL,
)

SIM_INPUTS = {
    "tea_density": 0.35,
    "package_weight": 250.0,
    "shipment_quantity": 100_000,
    "packaging_material": "paper",
    "package_shape": "square",
}


class TestWhatIfTool:
    """The tool must run the real optimiser, not approximate it."""

    def test_returns_real_optimiser_output(self):
        out = _run_what_if({}, SIM_INPUTS)
        assert "result" in out
        r = out["result"]
        assert r["containers_needed"] >= 1
        assert r["total_cost_inr"] > 0
        assert r["container_type"] in ("20GP", "40GP", "40HC")

    def test_override_actually_changes_the_answer(self):
        paper = _run_what_if({"packaging_material": "paper"}, SIM_INPUTS)
        metal = _run_what_if({"packaging_material": "metal"}, SIM_INPUTS)
        assert (
            metal["result"]["packaging_cost_inr"] > paper["result"]["packaging_cost_inr"]
        )

    def test_unspecified_fields_inherit_the_simulation(self):
        out = _run_what_if({"packaging_material": "plastic"}, SIM_INPUTS)
        assert out["inputs_used"]["tea_density"] == 0.35
        assert out["inputs_used"]["shipment_quantity"] == 100_000
        assert out["inputs_used"]["packaging_material"] == "plastic"

    def test_reports_what_changed(self):
        out = _run_what_if({"packaging_material": "metal"}, SIM_INPUTS)
        assert out["changed_inputs"] == {"packaging_material": "metal"}

    def test_no_change_is_stated_explicitly(self):
        out = _run_what_if({}, SIM_INPUTS)
        assert "none" in str(out["changed_inputs"])

    def test_constraint_override_is_applied(self):
        stacked = _run_what_if({"allow_pallet_stacking": True}, SIM_INPUTS)
        flat = _run_what_if({"allow_pallet_stacking": False}, SIM_INPUTS)
        assert flat["result"]["total_cost_inr"] >= stacked["result"]["total_cost_inr"]
        assert flat["result"]["pallets_double_stacked"] is False

    def test_infeasible_request_returns_error_as_data(self):
        """
        An impossible ask must come back as data the model can explain, not as an
        exception that surfaces to the user as a generic 500.
        """
        out = _run_what_if({"max_carton_weight_kg": 0.0001}, SIM_INPUTS)
        assert "error" in out
        assert "result" not in out
        assert "No packaging configuration" in out["error"]
        assert out["inputs"]["tea_density"] == 0.35

    def test_tool_output_is_json_serialisable(self):
        json.dumps(_run_what_if({}, SIM_INPUTS))


class TestToolSchema:
    def test_tool_instructs_model_not_to_guess(self):
        desc = WHAT_IF_TOOL["function"]["description"].lower()
        assert "never estimate" in desc or "do not" in desc

    def test_tool_schema_is_valid(self):
        fn = WHAT_IF_TOOL["function"]
        assert fn["name"] == "run_what_if"
        assert fn["parameters"]["type"] == "object"
        assert fn["parameters"]["required"] == []


class TestValidationParsing:
    def test_parses_plain_json(self):
        raw = '[{"stage":"package","status":"valid","message":"Fine."}]'
        out = _parse_validations(raw)
        assert out[0].stage == "package"
        assert out[0].status == "valid"

    def test_strips_markdown_fence(self):
        raw = '```json\n[{"stage":"carton","status":"warning","message":"Heavy."}]\n```'
        out = _parse_validations(raw)
        assert len(out) == 1
        assert out[0].status == "warning"

    def test_unparseable_reports_unknown_not_green_ticks(self):
        """
        The old fallback returned four 'valid' rows when parsing failed, so a
        broken AI response looked like a clean bill of health.
        """
        out = _parse_validations("the model rambled instead of returning JSON")
        assert len(out) == 4
        assert all(v.status == "unknown" for v in out)
        assert all("unavailable" in v.message.lower() for v in out)

    def test_empty_response_is_safe(self):
        assert all(v.status == "unknown" for v in _parse_validations(""))


class TestSecurityBoundary:
    @pytest.mark.asyncio
    async def test_missing_key_raises_service_error(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setattr(
            ai_service, "get_settings", lambda: Settings(openai_api_key="")
        )
        with pytest.raises(AIServiceError, match="not configured"):
            await answer_question("hi", None, [], db=None)

    @pytest.mark.asyncio
    async def test_upstream_error_does_not_leak_the_key(self, monkeypatch):
        """An OpenAI failure must not echo headers or body back to the user."""
        import httpx

        from app.config import Settings

        secret = "sk-super-secret-key-value"
        monkeypatch.setattr(
            ai_service, "get_settings", lambda: Settings(openai_api_key=secret)
        )

        async def boom(*a, **kw):
            request = httpx.Request("POST", ai_service.OPENAI_CHAT_URL)
            response = httpx.Response(401, request=request, text=f"bad key {secret}")
            raise httpx.HTTPStatusError("401", request=request, response=response)

        monkeypatch.setattr(ai_service.httpx.AsyncClient, "post", boom)

        with pytest.raises(AIServiceError) as exc:
            await ai_service._call_openai_raw(
                messages=[{"role": "user", "content": "x"}],
                api_key=secret,
                model="gpt-4o-mini",
            )
        assert secret not in str(exc.value)
        assert "401" in str(exc.value)

    @pytest.mark.asyncio
    async def test_empty_question_rejected(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setattr(
            ai_service, "get_settings", lambda: Settings(openai_api_key="sk-test")
        )
        with pytest.raises(ValueError, match="empty"):
            await answer_question("   ", None, [], db=None)


class TestAnswerQuestionFlow:
    @pytest.mark.asyncio
    async def test_plain_answer_needs_no_tool(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setattr(
            ai_service, "get_settings", lambda: Settings(openai_api_key="sk-test")
        )

        async def fake(**kwargs):
            return {"choices": [{"message": {"content": "Because it is cheaper."}}]}

        monkeypatch.setattr(ai_service, "_call_openai_raw", fake)

        reply, tools = await answer_question("why 40GP?", None, [], db=None)
        assert reply == "Because it is cheaper."
        assert tools == []

    @pytest.mark.asyncio
    async def test_tool_call_is_executed_and_reported(self, monkeypatch):
        """A what-if must actually invoke the optimiser and say that it did."""
        from app.config import Settings

        monkeypatch.setattr(
            ai_service, "get_settings", lambda: Settings(openai_api_key="sk-test")
        )
        monkeypatch.setattr(
            ai_service,
            "_load_simulation_context",
            lambda sid, db: _async(("context", SIM_INPUTS)),
        )

        calls = {"n": 0}

        async def fake(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "run_what_if",
                                            "arguments": '{"packaging_material":"plastic"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            # Second round: the tool result is now in the message list.
            tool_msgs = [m for m in kwargs["messages"] if m.get("role") == "tool"]
            assert tool_msgs, "tool result was not fed back to the model"
            payload = json.loads(tool_msgs[0]["content"])
            assert payload["result"]["total_cost_inr"] > 0
            return {"choices": [{"message": {"content": "Plastic costs more."}}]}

        monkeypatch.setattr(ai_service, "_call_openai_raw", fake)

        reply, tools = await answer_question("what if plastic?", "sim-1", [], db=None)
        assert reply == "Plastic costs more."
        assert tools == ["run_what_if"]

    @pytest.mark.asyncio
    async def test_runaway_tool_loop_is_bounded(self, monkeypatch):
        from app.config import Settings

        monkeypatch.setattr(
            ai_service, "get_settings", lambda: Settings(openai_api_key="sk-test")
        )
        monkeypatch.setattr(
            ai_service,
            "_load_simulation_context",
            lambda sid, db: _async(("context", SIM_INPUTS)),
        )

        async def always_tool(**kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c",
                                    "type": "function",
                                    "function": {
                                        "name": "run_what_if",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

        monkeypatch.setattr(ai_service, "_call_openai_raw", always_tool)

        reply, tools = await answer_question("loop", "sim-1", [], db=None)
        assert len(tools) <= ai_service.MAX_TOOL_ROUNDS
        assert "could not settle" in reply


async def _async(value):
    """Wrap a value in an awaitable, for monkeypatching async functions."""
    return value
