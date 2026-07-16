"""
AI service — OpenAI-backed validation, explanation and what-if assistant.

Where AI belongs in this system
-------------------------------
The optimisation itself is deterministic arithmetic and stays that way: it must be
reproducible, auditable and explainable in an interview. An LLM that guessed at
carton dimensions would be strictly worse than the search in `optimizers/joint.py`.

So the model is used where it genuinely adds something a formula cannot:

  1. `analyze_results`  — sanity-checks the numbers against industry norms and
                          writes the result up for an export manager.
  2. `answer_question`  — a what-if assistant. Crucially it does not *guess* the
                          answer to "what if I switch to plastic?"; it calls the
                          real optimiser through a tool and reports what came back.
                          A number in the chat window is a computed number.

The API key never leaves this process — see routers/chat.py.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
REQUEST_TIMEOUT_S = 45.0
MAX_TOOL_ROUNDS = 4


class AIServiceError(RuntimeError):
    """Raised when the AI provider is unusable — missing key, upstream failure."""


@dataclass
class StageValidation:
    stage: str = ""
    status: str = ""
    message: str = ""


@dataclass
class AIAnalysis:
    validations: list[StageValidation] = field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None


# ── Tool definitions ──────────────────────────────────────────────────────────

WHAT_IF_TOOL = {
    "type": "function",
    "function": {
        "name": "run_what_if",
        "description": (
            "Re-run the packaging optimiser with one or more inputs changed, and "
            "return the resulting costs, container utilisation and configuration. "
            "ALWAYS call this before answering any question of the form 'what if…', "
            "'would it be cheaper if…', or any question whose answer is a number "
            "that differs from the current simulation. Never estimate such a number "
            "yourself — call this tool and report what it returns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tea_density": {
                    "type": "number",
                    "description": "Tea density in g/cm³. Omit to keep the current value.",
                },
                "package_weight": {
                    "type": "number",
                    "description": "Net tea per pouch in grams. Omit to keep current.",
                },
                "shipment_quantity": {
                    "type": "integer",
                    "description": "Total pouches to ship. Omit to keep current.",
                },
                "packaging_material": {
                    "type": "string",
                    "enum": ["paper", "plastic", "metal"],
                    "description": "Pouch material. Omit to keep current.",
                },
                "package_shape": {
                    "type": "string",
                    "enum": ["square", "round"],
                    "description": "Pouch geometry. Omit to keep current.",
                },
                "allow_pallet_stacking": {
                    "type": "boolean",
                    "description": (
                        "Whether pallets may be double-stacked in the container. "
                        "Set false to quantify the cost of a no-stacking rule."
                    ),
                },
                "max_carton_weight_kg": {
                    "type": "number",
                    "description": (
                        "Manual-handling weight limit per carton. Use to answer "
                        "questions about lighter cartons for warehouse ergonomics."
                    ),
                },
            },
            "required": [],
        },
    },
}


# ── Public API ────────────────────────────────────────────────────────────────

async def analyze_results(pipeline_data: dict) -> AIAnalysis:
    """Validate pipeline results against industry norms and explain them."""
    settings = get_settings()
    if not settings.openai_api_key:
        return AIAnalysis(
            error="OpenAI API key not configured. Add OPENAI_API_KEY to your .env."
        )

    try:
        validations = await _run_validation(
            pipeline_data, settings.openai_api_key, settings.openai_model
        )
        summary = await _run_explanation(
            pipeline_data, settings.openai_api_key, settings.openai_model
        )
        return AIAnalysis(validations=validations, summary=summary)
    except Exception as e:
        logger.exception("AI analysis failed")
        return AIAnalysis(error=f"AI analysis unavailable: {e}")


async def answer_question(
    question: str,
    simulation_id: Optional[str],
    history: list[dict],
    db: AsyncSession,
) -> tuple[str, list[str]]:
    """
    Answer a question about a simulation, calling the optimiser when needed.

    Returns:
        (reply_text, names_of_tools_invoked) — the tool list is surfaced in the UI
        so the user can tell a computed answer from a conversational one.

    Raises:
        AIServiceError: if the provider is unconfigured or unreachable.
        ValueError: if the question is empty.
    """
    if not question or not question.strip():
        raise ValueError("Message cannot be empty")

    settings = get_settings()
    if not settings.openai_api_key:
        raise AIServiceError(
            "AI assistant is not configured. Set OPENAI_API_KEY on the server."
        )

    context, sim_inputs = await _load_simulation_context(simulation_id, db)

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a tea packaging optimisation assistant helping an export "
                "manager understand their results.\n\n"
                f"{context}\n\n"
                "RULES:\n"
                "- For any question whose answer is a number not already in the "
                "context above, call run_what_if and report its output. Do not "
                "estimate, interpolate or guess numbers.\n"
                "- Use Rs. for currency. Be concrete and cite the numbers.\n"
                "- Keep answers under 4 sentences unless asked for detail.\n"
                "- If a question is outside packaging optimisation, say so briefly."
            ),
        }
    ]
    for m in history[-8:]:  # bound the context window
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})

    tools_used: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        payload = await _call_openai_raw(
            messages=messages,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            tools=[WHAT_IF_TOOL],
            max_tokens=700,
        )
        choice = payload["choices"][0]["message"]
        calls = choice.get("tool_calls") or []

        if not calls:
            return (choice.get("content") or "").strip(), tools_used

        messages.append(choice)
        for call in calls:
            name = call["function"]["name"]
            tools_used.append(name)
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _dispatch_tool(name, args, sim_inputs)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result),
                }
            )

    # The model kept asking for tools past the cap; answer from what we have.
    logger.warning("Chat hit MAX_TOOL_ROUNDS without settling")
    return (
        "I ran several scenarios but could not settle on an answer. "
        "Try asking about one change at a time.",
        tools_used,
    )


# ── Tool dispatch ─────────────────────────────────────────────────────────────

def _dispatch_tool(name: str, args: dict, sim_inputs: dict) -> dict:
    """Execute a tool call. Returns a JSON-serialisable result for the model."""
    if name != "run_what_if":
        return {"error": f"Unknown tool {name!r}"}
    return _run_what_if(args, sim_inputs)


def _run_what_if(args: dict, sim_inputs: dict) -> dict:
    """
    Re-run the real optimiser with overrides applied to the simulation's inputs.

    Imported locally to keep the import graph acyclic: the router imports this
    service, and the service reaches back into the pipeline.
    """
    from app.optimizers.joint import Constraints
    from app.services.simulation_service import run_full_pipeline

    merged = {
        "tea_density": args.get("tea_density", sim_inputs.get("tea_density", 0.35)),
        "package_weight": args.get(
            "package_weight", sim_inputs.get("package_weight", 250.0)
        ),
        "shipment_quantity": args.get(
            "shipment_quantity", sim_inputs.get("shipment_quantity", 100_000)
        ),
        "packaging_material": args.get(
            "packaging_material", sim_inputs.get("packaging_material", "paper")
        ),
        "package_shape": args.get(
            "package_shape", sim_inputs.get("package_shape", "square")
        ),
    }

    constraints = None
    if "allow_pallet_stacking" in args or "max_carton_weight_kg" in args:
        defaults = Constraints()
        constraints = Constraints(
            allow_pallet_stacking=args.get(
                "allow_pallet_stacking", defaults.allow_pallet_stacking
            ),
            max_carton_weight_kg=args.get(
                "max_carton_weight_kg", defaults.max_carton_weight_kg
            ),
        )

    try:
        r = run_full_pipeline(**merged, constraints=constraints)
    except ValueError as e:
        # Hand the failure to the model as data so it can explain it, rather than
        # letting a 500 surface as "sorry, something went wrong".
        return {"error": str(e), "inputs": merged}

    changed = {
        k: v
        for k, v in merged.items()
        if sim_inputs.get(k) is not None and sim_inputs.get(k) != v
    }
    if constraints is not None:
        changed["constraints"] = {
            "allow_pallet_stacking": constraints.allow_pallet_stacking,
            "max_carton_weight_kg": constraints.max_carton_weight_kg,
        }

    return {
        "changed_inputs": changed or "none — this is the current configuration",
        "inputs_used": merged,
        "result": {
            "package_mm": [
                round(r.best_package.length_mm, 1),
                round(r.best_package.width_mm, 1),
                round(r.best_package.height_mm, 1),
            ],
            "units_per_carton": r.carton.units_per_carton,
            "carton_outer_mm": [
                r.carton.outer_length_mm,
                r.carton.outer_width_mm,
                r.carton.outer_height_mm,
            ],
            "carton_weight_kg": r.carton.carton_weight_kg,
            "board_grade": r.carton.board_grade,
            "cartons_per_pallet": r.pallet.cartons_per_pallet,
            "pallet_height_m": r.pallet.pallet_height_m,
            "pallets_double_stacked": r.best_container.pallet_stack > 1,
            "container_type": r.best_container.container_type,
            "containers_needed": r.best_container.containers_needed,
            "container_utilization_pct": r.best_container.utilization_pct,
            "packaging_cost_inr": r.packaging_cost,
            "carton_cost_inr": r.carton_cost,
            "freight_cost_inr": r.freight_cost,
            "total_cost_inr": r.total_cost,
            "savings_vs_current_practice_inr": r.total_savings,
        },
    }


# ── Simulation context ────────────────────────────────────────────────────────

async def _load_simulation_context(
    simulation_id: Optional[str], db: AsyncSession
) -> tuple[str, dict]:
    """
    Build the assistant's factual context from the database.

    Loaded server-side rather than accepted from the client, so the browser cannot
    feed the assistant invented figures.
    """
    if not simulation_id:
        return (
            "No simulation is loaded. If the user asks about specific numbers, "
            "call run_what_if with explicit inputs.",
            {},
        )

    from app.models import Simulation

    result = await db.execute(
        select(Simulation)
        .options(
            selectinload(Simulation.inputs),
            selectinload(Simulation.package_options),
            selectinload(Simulation.carton_config),
            selectinload(Simulation.pallet_config),
            selectinload(Simulation.container_configs),
            selectinload(Simulation.cost_summary),
        )
        .where(Simulation.id == simulation_id)
    )
    sim = result.scalar_one_or_none()
    if not sim or not sim.inputs:
        return ("The referenced simulation could not be found.", {})

    i = sim.inputs
    sim_inputs = {
        "tea_density": i.tea_density,
        "package_weight": i.package_weight,
        "shipment_quantity": i.shipment_quantity,
        "packaging_material": i.packaging_material,
        "package_shape": i.package_shape,
    }

    best_pkg = next((p for p in sim.package_options if p.is_best), None)
    best_ct = next((c for c in sim.container_configs if c.is_best), None)
    cs = sim.cost_summary
    carton = sim.carton_config
    pallet = sim.pallet_config

    lines = [
        "CURRENT SIMULATION",
        f"Inputs: density {i.tea_density} g/cm3, {i.package_weight} g per pouch, "
        f"{i.shipment_quantity:,} pouches, {i.packaging_material}, {i.package_shape}"
        + (f", market {i.target_market}" if i.target_market else ""),
    ]
    if best_pkg:
        lines.append(
            f"Pouch: {best_pkg.length}x{best_pkg.width}x{best_pkg.height} mm, "
            f"fill ratio {best_pkg.fill_ratio}"
        )
    if carton:
        lines.append(
            f"Carton: {carton.length}x{carton.width}x{carton.height} mm outer, "
            f"{carton.units_per_carton} pouches, {carton.carton_weight} kg, "
            f"{carton.board_grade}"
        )
    if pallet:
        lines.append(
            f"Pallet: {pallet.cartons_per_layer}/layer x {pallet.layers} layers = "
            f"{pallet.cartons_per_pallet} cartons, {pallet.pallet_height} m tall"
        )
    if best_ct:
        lines.append(
            f"Container: {best_ct.container_type}, {best_ct.containers_needed} needed, "
            f"{best_ct.utilization_pct}% of booked volume holds tea "
            f"(packing density {best_ct.capacity_utilization_pct}%), "
            f"pallets stacked {best_ct.pallet_stack} high"
        )
    if cs:
        lines.append(
            f"Cost: packaging Rs.{cs.packaging_cost:,.0f} + board Rs.{cs.carton_cost:,.0f} "
            f"+ freight Rs.{cs.freight_cost:,.0f} = Rs.{cs.total_cost:,.0f}. "
            f"Current practice would cost Rs.{cs.baseline_total_cost:,.0f}, "
            f"so the saving is Rs.{cs.total_savings:,.0f}."
        )

    return "\n".join(lines), sim_inputs


# ── Validation & explanation ──────────────────────────────────────────────────

async def _run_validation(data: dict, api_key: str, model: str) -> list[StageValidation]:
    """Ask the model to audit each stage against real-world norms."""
    pkg = data.get("best_package", {})
    carton = data.get("carton", {})
    pallet = data.get("pallet", {})
    container = data.get("best_container", {})

    prompt = (
        "You are a tea packaging quality auditor. Validate these results against "
        "real-world tea export practice.\n\n"
        f"CONTEXT: density {data.get('tea_density')} g/cm3, "
        f"{data.get('package_weight')} g per pouch, "
        f"{data.get('shipment_quantity')} pouches\n\n"
        f"PACKAGE: {pkg.get('length_mm')}x{pkg.get('width_mm')}x{pkg.get('height_mm')} mm, "
        f"{pkg.get('volume_cm3')} cm3, fill ratio {pkg.get('fill_ratio')}, "
        f"{pkg.get('material')}, {pkg.get('shape')}\n"
        f"CARTON: {carton.get('outer_length_mm')}x{carton.get('outer_width_mm')}"
        f"x{carton.get('outer_height_mm')} mm outer, "
        f"{carton.get('units_per_carton')} pouches, {carton.get('carton_weight_kg')} kg, "
        f"{carton.get('board_grade')}\n"
        f"PALLET: {pallet.get('cartons_per_layer')}/layer x {pallet.get('layers')} layers "
        f"= {pallet.get('cartons_per_pallet')} cartons, {pallet.get('pallet_height_m')} m, "
        f"{pallet.get('total_weight_kg')} kg, footprint "
        f"{pallet.get('footprint_utilization_pct')}% used\n"
        f"CONTAINER: {container.get('container_type')}, packing density "
        f"{container.get('capacity_utilization_pct')}%, "
        f"{container.get('containers_needed')} needed, pallets stacked "
        f"{container.get('pallet_stack')} high\n\n"
        "Judge against these norms:\n"
        "- Pouch: must physically hold the tea with some headspace; proportions "
        "should be handleable and shelf-presentable (no needle-thin or pancake shapes).\n"
        "- Carton: at or under 25 kg for manual handling; board grade should suit "
        "the weight (3-ply under 10 kg, 5-ply under 20 kg, 7-ply above).\n"
        "- Pallet: at or under 1.8 m and 1000 kg; footprint above 85% is good.\n"
        "- Container: packing density above 65% is good, below 50% is poor.\n\n"
        "Respond with ONLY a JSON array, no markdown fence:\n"
        '[{"stage":"package","status":"valid|warning|invalid","message":"one sentence"},\n'
        ' {"stage":"carton","status":"...","message":"..."},\n'
        ' {"stage":"pallet","status":"...","message":"..."},\n'
        ' {"stage":"container","status":"...","message":"..."}]'
    )

    raw = await _call_openai(prompt, api_key, model, max_tokens=350)
    return _parse_validations(raw)


async def _run_explanation(data: dict, api_key: str, model: str) -> str:
    """
    Ask the model for a short, plain-language brief a non-expert can act on.

    The earlier prompt asked for "four paragraphs written to an export manager",
    which produced a formal letter — "Dear [Export Manager's Name]", filler like
    "enhances our brand image", and a sign-off with [Your Name] placeholders.
    Useless. This asks for a scannable brief in everyday words, in a fixed shape
    the UI can render cleanly, and forbids the letter furniture explicitly.
    """
    pkg = data.get("best_package", {})
    carton = data.get("carton", {})
    pallet = data.get("pallet", {})
    container = data.get("best_container", {})
    comparison = data.get("comparison", [])

    # Give the model the plain cause→effect for each line so it explains rather
    # than invents. It should paraphrase these, not restate the raw numbers.
    drivers = "\n".join(
        f"- {r.get('parameter_name')}: {r.get('current_value')} -> {r.get('ai_value')} "
        f"({r.get('improvement_pct', 0):+.1f}%) — {r.get('driver', '')}"
        for r in comparison
    )

    total = data.get("total_cost", 0)
    base = data.get("baseline_total_cost", 0)
    saving = data.get("total_savings", 0)
    saving_pct = (saving / base * 100) if base else 0
    weight_kg = carton.get("carton_weight_kg", 0)
    lift_note = "one person can lift it" if weight_kg and weight_kg <= 20 else (
        "needs two people or a trolley" if weight_kg else ""
    )

    prompt = (
        "You are explaining a tea packaging plan to a busy operations team — "
        "warehouse, packing, dispatch. Many are not native English speakers and "
        "none are packaging engineers. Write so a shop-floor supervisor gets it on "
        "the first read.\n\n"
        "STRICT STYLE:\n"
        "- NO letter. No 'Dear', no greeting, no sign-off, no [placeholders], no "
        "  company/brand talk. Start straight at the first heading.\n"
        "- Short sentences. Everyday words. If you must use a term like 'pallet "
        "  footprint', add three words of plain meaning.\n"
        "- Every claim gets a number from the data below. Invent nothing.\n"
        "- Use Rs for money. Keep the whole thing under 180 words.\n\n"
        "OUTPUT EXACTLY THESE FOUR SECTIONS, each heading on its own line wrapped "
        "in double asterisks, each point a line starting with '- ':\n\n"
        "**The plan**\n"
        "One or two lines: the pouch, how many per box, which container, and the "
        "saving as both Rs and %.\n\n"
        "**Why it's cheaper**\n"
        "3 bullets. Plain cause and effect. A smaller box that holds fewer pouches "
        "can still win because it stacks tighter and fills fewer containers — say "
        "it simply.\n\n"
        "**What the team should know**\n"
        "Exactly 3 bullets a packer or loader needs, in this order and kept "
        "separate so nothing is confused:\n"
        "  (a) box weight, and whether one person can lift it;\n"
        "  (b) how many boxes go on ONE pallet, and how tall that loaded pallet "
        "is in metres;\n"
        "  (c) how many containers, and whether whole PALLETS are stacked "
        "two-high inside the container (this is about pallets, not boxes).\n\n"
        "**Good to know**\n"
        "1 bullet: the Rs figures use standard market rates, so the % saving is the "
        "reliable part; exact rupees depend on the client's real prices.\n\n"
        "── DATA ──\n"
        f"Pouch: {pkg.get('length_mm')}x{pkg.get('width_mm')}x{pkg.get('height_mm')} mm, "
        f"{pkg.get('material')}, {pkg.get('shape')}.\n"
        f"Box: holds {carton.get('units_per_carton')} pouches, weighs "
        f"{weight_kg} kg ({lift_note}), {carton.get('board_grade')} board.\n"
        f"Pallet: {pallet.get('cartons_per_pallet')} boxes, "
        f"{pallet.get('pallet_height_m')} m tall.\n"
        f"Container: {container.get('containers_needed')} x "
        f"{container.get('container_type')}, pallets stacked "
        f"{container.get('pallet_stack')} high, "
        f"{container.get('capacity_utilization_pct')}% full by volume "
        f"(tea is light, so a part-full-by-volume container is normal and expected).\n"
        f"Money: new plan Rs {total:,.0f} vs current practice Rs {base:,.0f}. "
        f"Saving Rs {saving:,.0f} ({saving_pct:.0f}%).\n"
        f"What changed and why:\n{drivers}\n"
    )

    return (await _call_openai(prompt, api_key, model, max_tokens=500)).strip()


# ── Transport ─────────────────────────────────────────────────────────────────

async def _call_openai_raw(
    messages: list[dict],
    api_key: str,
    model: str,
    tools: Optional[list[dict]] = None,
    max_tokens: int = 500,
) -> dict:
    """POST to OpenAI and return the parsed body. Raises AIServiceError on failure."""
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
            resp = await client.post(
                OPENAI_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        # Never echo the response body: it can repeat request content, and the
        # Authorization header must not end up in a log or a user-facing string.
        raise AIServiceError(
            f"OpenAI returned HTTP {e.response.status_code}"
        ) from None
    except httpx.TimeoutException:
        raise AIServiceError("OpenAI request timed out") from None
    except httpx.HTTPError as e:
        raise AIServiceError(f"Could not reach OpenAI: {type(e).__name__}") from None


async def _call_openai(prompt: str, api_key: str, model: str, max_tokens: int = 500) -> str:
    """Single-turn completion returning message text."""
    payload = await _call_openai_raw(
        messages=[
            {
                "role": "system",
                "content": "You are an expert tea packaging optimisation consultant.",
            },
            {"role": "user", "content": prompt},
        ],
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
    )
    return payload["choices"][0]["message"]["content"] or ""


def _parse_validations(raw: str) -> list[StageValidation]:
    """Parse the model's JSON array, tolerating a markdown fence."""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        items = json.loads(text)
        if not isinstance(items, list):
            raise ValueError("expected a JSON array")
        return [
            StageValidation(
                stage=str(item.get("stage", "")),
                status=str(item.get("status", "valid")),
                message=str(item.get("message", "")),
            )
            for item in items
            if isinstance(item, dict)
        ]
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        logger.warning("Could not parse AI validation response: %s", e)
        # Report the failure rather than fabricating four green ticks, which is
        # what the previous fallback did.
        return [
            StageValidation(
                stage=stage,
                status="unknown",
                message="Validation unavailable — the AI response could not be parsed.",
            )
            for stage in ("package", "carton", "pallet", "container")
        ]
