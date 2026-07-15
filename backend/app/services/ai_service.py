"""
AI Service — calls OpenAI for result validation and natural-language explanation.

Read-only: AI comments on pipeline results but never modifies them.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


@dataclass
class StageValidation:
    stage: str = ""      # "package", "carton", "pallet", "container"
    status: str = ""     # "valid", "warning", "invalid"
    message: str = ""    # one-sentence explanation


@dataclass
class AIAnalysis:
    validations: list[StageValidation] = field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None


# ── Public API ────────────────────────────────────────────────────────────────

async def analyze_results(pipeline_data: dict) -> AIAnalysis:
    """
    Run AI validation + explanation on pipeline results.

    Args:
        pipeline_data: Dict with keys: tea_density, package_weight, shipment_quantity,
                       best_package (dict), carton (dict), pallet (dict),
                       best_container (dict), comparison (list[dict]),
                       packaging_cost, freight_cost, total_cost, total_savings.

    Returns:
        AIAnalysis with per-stage validations and a human-readable summary.
    """
    settings = get_settings()
    api_key = settings.openai_api_key

    if not api_key:
        return AIAnalysis(error="OpenAI API key not configured. Add OPENAI_API_KEY to .env.")

    try:
        validations = await _run_validation(pipeline_data, api_key, settings.openai_model)
        summary = await _run_explanation(pipeline_data, api_key, settings.openai_model)
        return AIAnalysis(validations=validations, summary=summary)
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return AIAnalysis(error=str(e))


# ── Validation ────────────────────────────────────────────────────────────────

async def _run_validation(data: dict, api_key: str, model: str) -> list[StageValidation]:
    """Ask AI to validate each optimization stage against industry norms."""

    pkg = data.get("best_package", {})
    carton = data.get("carton", {})
    pallet = data.get("pallet", {})
    container = data.get("best_container", {})

    prompt = f"""You are a tea packaging quality auditor. Validate these optimization results against real-world tea industry standards.

CONTEXT:
- Tea density: {data.get('tea_density')} g/cm³
- Package weight: {data.get('package_weight')}g
- Shipment: {data.get('shipment_quantity')} units

STAGE 1 — PACKAGE:
Dimensions: {pkg.get('length_mm')}×{pkg.get('width_mm')}×{pkg.get('height_mm')}mm
Volume: {pkg.get('volume_cm3')} cm³, Fill ratio: {pkg.get('fill_ratio')}
Material: {pkg.get('material')}, Shape: {pkg.get('shape')}

STAGE 2 — CARTON:
Inner: {carton.get('inner_length_mm')}×{carton.get('inner_width_mm')}×{carton.get('inner_height_mm')}mm
Units per carton: {carton.get('units_per_carton')}, Weight: {carton.get('carton_weight_kg')}kg
Board grade: {carton.get('board_grade')}

STAGE 3 — PALLET:
Cartons/layer: {pallet.get('cartons_per_layer')}, Layers: {pallet.get('layers')}
Cartons/pallet: {pallet.get('cartons_per_pallet')}, Height: {pallet.get('pallet_height_m')}m
Total weight: {pallet.get('total_weight_kg')}kg

STAGE 4 — CONTAINER:
Type: {container.get('container_type')}, Utilization: {container.get('utilization_pct')}%
Containers needed: {container.get('containers_needed')}
Freight cost: ₹{container.get('total_freight_cost', 0):,.0f}

For each stage, respond with ONLY a JSON array — no markdown, no extra text:
[
  {{"stage":"package","status":"valid|warning|invalid","message":"one sentence"}},
  {{"stage":"carton","status":"valid|warning|invalid","message":"one sentence"}},
  {{"stage":"pallet","status":"valid|warning|invalid","message":"one sentence"}},
  {{"stage":"container","status":"valid|warning|invalid","message":"one sentence"}}
]

Rules:
- "valid" = within industry norms
- "warning" = slightly outside typical range but acceptable
- "invalid" = clearly wrong or impossible
- Messages must reference specific numbers and industry context
- For packages: typical 250g tea pouches are 100-140mm long, 80-110mm wide, 50-75mm high
- For cartons: typical tea cartons weigh 15-22kg, use 3-5 ply board
- For pallets: EUR pallets hold 20-50 cartons typically
- For containers: 75-85% utilization is good, below 60% is poor"""

    response = await _call_openai(prompt, api_key, model, max_tokens=300)
    return _parse_validations(response)


async def _run_explanation(data: dict, api_key: str, model: str) -> str:
    """Ask AI to write a natural-language summary of the optimization results."""

    pkg = data.get("best_package", {})
    carton = data.get("carton", {})
    pallet = data.get("pallet", {})
    container = data.get("best_container", {})
    comparison = data.get("comparison", [])

    comp_text = "\n".join(
        f"- {r.get('parameter_name')}: {r.get('current_value')} → {r.get('ai_value')} ({r.get('improvement_pct', 0):+.1f}%)"
        for r in comparison
    )

    prompt = f"""You are an expert tea packaging consultant explaining optimization results to an export manager.

Write a concise 4-paragraph summary:

Paragraph 1: Package choice — explain the recommended pouch dimensions, why this shape/size was chosen, and how it balances material cost with fill efficiency.
Paragraph 2: Carton & pallet — explain the arrangement (how many pouches per carton, cartons per pallet), board grade choice, and weight handling.
Paragraph 3: Container & costs — which container was selected and why, utilization achieved, containers needed, freight cost.
Paragraph 4: Savings — total savings vs current practice, key improvement areas, recommendation.

DATA:
- Tea: {data.get('tea_density')} g/cm³, {data.get('package_weight')}g packs, {data.get('shipment_quantity')} units
- Best package: {pkg.get('length_mm')}×{pkg.get('width_mm')}×{pkg.get('height_mm')}mm, {pkg.get('volume_cm3')} cm³, {pkg.get('fill_ratio')} fill, {pkg.get('material')}
- Carton: {carton.get('units_per_carton')} units, {carton.get('carton_weight_kg')}kg, {carton.get('board_grade')}
- Pallet: {pallet.get('cartons_per_pallet')} cartons, {pallet.get('pallet_height_m')}m tall, {pallet.get('total_weight_kg')}kg
- Container: {container.get('container_type')}, {container.get('utilization_pct')}% utilization, {container.get('containers_needed')} needed
- Freight: ₹{container.get('total_freight_cost', 0):,.0f}
- Total AI cost: ₹{data.get('total_cost', 0):,.0f}
- Total savings: ₹{data.get('total_savings', 0):,.0f}
- Improvements:
{comp_text}

Write naturally in 4 paragraphs. No markdown headings, no bullet points. Use ₹ for INR. Keep it professional but accessible."""

    response = await _call_openai(prompt, api_key, model, max_tokens=500)
    return response.strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _call_openai(prompt: str, api_key: str, model: str, max_tokens: int = 500) -> str:
    """Make a single-turn OpenAI chat completion call."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENAI_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an expert tea packaging optimization consultant. Respond concisely with no fluff."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _parse_validations(raw: str) -> list[StageValidation]:
    """Parse OpenAI's JSON response into StageValidation objects."""
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])
        items = json.loads(raw)
        return [
            StageValidation(
                stage=item.get("stage", ""),
                status=item.get("status", "valid"),
                message=item.get("message", ""),
            )
            for item in items
        ]
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse AI validation response: {e}")
        return [
            StageValidation(stage="package", status="valid", message="Validation skipped — could not parse AI response."),
            StageValidation(stage="carton", status="valid", message=""),
            StageValidation(stage="pallet", status="valid", message=""),
            StageValidation(stage="container", status="valid", message=""),
        ]
