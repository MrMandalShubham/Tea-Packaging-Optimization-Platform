# Assumptions

The brief leaves several things unspecified. This document records every
assumption made, why it was made, and what would change if the client corrected
it. Anything marked **⚠ needs client confirmation** is a genuine open question
rather than a settled fact.

---

## 1. Interpreting the inputs

### 1.1 Shipment Type — ⚠ needs client confirmation

The brief lists `Shipment Type: Total Weight / Per Container` but does not say how
it changes the meaning of `Shipment Quantity`. Implemented reading:

| Value | Meaning | Effect |
|---|---|---|
| `total_weight` | Quantity is the whole order, in pouches | Optimiser uses as many containers as needed |
| `per_container` | Quantity must fit in **one** container | Solutions needing a 2nd container are rejected |

`per_container` answers "can I get 5,000 pouches into a single box, and how?" If
the client instead means "quantity is a weight in kg", the change is confined to
`resolve_shipment_type()` in `services/simulation_service.py`.

### 1.2 Package Weight is net tea, not gross

`package_weight` is the tea inside the pouch, excluding packaging. Gross weight is
derived (`carton_weight_kg` = pouches + board tare).

### 1.3 Tea Density range

Accepted: 0.05–5.0 g/cm³. Realistic tea is 0.18–0.48 (see `tea_density_refs`).
The wide bound is deliberate — rejecting an unusual-but-real density is worse than
letting an analyst model one.

### 1.4 Package Weight range

Package Weight is a dropdown of retail SKUs (25 g – 2 kg, `package_weight_refs`),
with the API accepting 1 g – 5 kg. An earlier 500 g cap silently rejected 1 kg
packs — one of the most common tea SKUs — even though the engine costs them
correctly; the limit now lives in one constant (`MAX_PACKAGE_WEIGHT_G`).

---

## 2. The optimisation model

### 2.1 Stages are solved jointly, not sequentially

The brief's flowchart reads Package → Carton → Pallet → Container. Implemented as
a **joint search** rather than a chain, because a chain is greedy: each stage
commits to a local optimum that constrains the next.

Concretely, a sequential pipeline maximises units-per-carton, hits the 25 kg cap,
and produces a ~570 mm-tall carton. That allows only 2 layers under the 1.8 m
pallet limit, giving a 1.29 m pallet in a 2.39 m container — so `int(2.39/1.29) = 1`
and roughly 1.1 m of container height is bought and shipped empty. Measured
result: **36.9% utilisation**.

The joint search enumerates complete configurations and scores each on total
landed cost. Same inputs, measured result: **68.8% packing density, 2 containers
instead of 4** (with the §3.5 real-world loading constraints applied). The stage order in the brief is preserved as the *reporting*
structure and as the standalone `POST /optimize/{stage}` endpoints.

### 2.2 Objective is total landed cost

```
total_cost = packaging_cost + carton_board_cost + freight_cost
```

Carton board cost was previously omitted entirely, which biased the optimiser
toward large heavy cartons — their board cost was invisible.

**Not modelled:** labour, warehousing, duties, insurance, demurrage, carbon cost.
Adding any of them means adding a term to the objective in `optimizers/joint.py`.

### 2.3 Exhaustive search, not a metaheuristic

~15,000 feasible configurations for a typical input; the search completes in well
under a second. So the result is the **true optimum of the model**, not an
approximation. No genetic algorithm or simulated annealing is warranted at this
scale, and either would make the result harder to explain and non-reproducible.

### 2.4 Machine learning is not used

The brief marks ML optional. The problem is combinatorial, not predictive: there
is no training data, and the physics is exactly known. A learned model would be
strictly worse than enumeration *and* unexplainable. The brief asks for logic that
is "transparent and explainable"; arithmetic is both.

AI is used where it adds something arithmetic cannot — validating results against
industry norms, explaining them in prose, and powering a what-if assistant that
calls the real optimiser rather than guessing (see §6).

---

## 3. Physical constants and constraints

| Constraint | Value | Source / rationale |
|---|---|---|
| Container interiors | ISO 668 | 20GP 5.898×2.352×2.385 m, 40GP 12.032×2.352×2.385 m, 40HC 12.032×2.352×2.698 m |
| Pallet | EUR / ISO 6780 | 1200×1000×150 mm, 25 kg tare |
| Max pallet load | 1000 kg | Common export limit |
| Max pallet height | 1.8 m incl. pallet | Warehouse racking convention — ⚠ see §3.1 |
| Max carton weight | 25 kg | Manual handling limit |
| Max carton outer | 800×600×600 mm | Practical corrugator/handling limit |
| Headspace | 15% of net volume | Settling and seal clearance |
| Pouch gap in carton | 2 mm | Packing clearance |
| Operational roof clearance | 50 mm | Forklift working room — see §3.5 |
| Board stack capacity | 35/80/140/220 kg by ply | Safe bottom-carton load — see §3.5 |
| Board area factor | 1.2 × surface area | Flaps, glue tabs, trim waste |

### 3.1 Pallet height vs. container height — ⚠ needs client confirmation

The 1.8 m pallet limit is a *racking* convention. Inside a container, pallets are
not racked, so builds up to the container's 2.39 m are physically possible.
Measured impact on the reference shipment:

| Rule | Utilisation | Containers | Freight |
|---|---|---|---|
| 1.8 m, no stacking | 46.6% | 3 | ₹61,875 |
| 1.8 m + double-stacking *(default)* | 69.8% | 2 | ₹41,250 |
| Relax to container height | ~77% | 2 | ₹41,250 |

Default keeps the 1.8 m rule **and** allows double-stacking. All three are
selectable via `Constraints` without touching the search. (Figures in this table
were measured before the §3.5 operational constraints; the relative picture is
unchanged.)

### 3.2 Pallet double-stacking is allowed by default

Two pallets high where height and payload permit. This assumes the goods can bear
the load — reasonable for cartoned dry tea, and the board grade is selected from
carton weight. Box compression is modelled conservatively — see §3.5. A fragile SKU should
still set `allow_pallet_stacking=False`.

### 3.3 Pallet layer patterns

Cartons are placed in a uniform block, in either orientation, plus a
"mixed" pattern that fills the leftover margin with rotated cartons. **Not
modelled:** full interlocking/pinwheel patterns, which could add a few percent.
Real column stacking (aligned, not interlocked) is assumed for stack strength.

### 3.5 Operational clearance and stack strength — real-world parameters

Added after a production audit, because the pure geometry produced two plans
that pass every fit check and fail in a real warehouse:

- a double-stacked 40GP with **17 mm** of roof clearance — no forklift can place
  a 1.18 m pallet with 17 mm to spare;
- **48 kg** resting on the bottom 3-ply carton of a double-stack — roughly its
  long-term crush limit, meaning the load slowly fails in transit.

Two constraints now apply, on **both** sides of the comparison:

1. **`operational_clearance_mm` (default 50)** — the pallet build must fit under
   the container roof minus forklift working room. Configurable; 0 reproduces
   the pure-geometry answer.
2. **Stack-aware board grade** — each grade carries a `max_stack_load_kg`
   (35/80/140/220 kg for 3/5/7/9-ply): the safe long-term load on the bottom
   carton, ≈ typical fresh BCT ÷ 4 for transit duration and humidity. These are
   **conservative defaults — replace with the client's board supplier data or
   lab BCT results.** The optimiser upgrades board (or finds a flatter carton)
   when a stack would crush; the baseline responds the way a real exporter does
   — it stacks one layer fewer, which is free, rather than buying heavier board.

Measured effect on the reference shipment: the recommendation moved from an
unloadable 40GP ×2 (17 mm clearance) to a loadable **40HC ×2 with 110 mm
clearance and a crush-safe 32 kg bottom-carton load**, and the claimed saving
fell from 26.1% to **27.4% against the equally-constrained baseline** (both
sides got more expensive; the gap held). Realism is applied to both sides or it
is just a new way of cheating.

### 3.4 Round packages are packed as their bounding box

A cylinder occupies its bounding square in the carton. This is honest but
pessimistic — it means ~21% (1 − π/4) of the carton cavity is air, which is
exactly why `square` almost always wins on cost. Hex-nesting of cylinders is not
modelled.

---

## 4. Cost model — ⚠ all rates need client confirmation

Every rate below is a placeholder. They are structurally correct but not sourced
from the client's actual contracts, so **absolute cost figures are indicative;
the relative comparison is the meaningful output.**

| Item | Rate | Where |
|---|---|---|
| Paper / kraft | ₹12 / m² | `MATERIALS` |
| Plastic / LDPE | ₹18 / m² | `MATERIALS` |
| Metal / foil laminate | ₹45 / m² | `MATERIALS` |
| Board 3-ply | ₹22 / m² | `BOARD_COST_PER_SQM` |
| Board 5-ply | ₹35 / m² | `BOARD_COST_PER_SQM` |
| Board 7-ply | ₹48 / m² | `BOARD_COST_PER_SQM` |
| Board 9-ply | ₹62 / m² | `BOARD_COST_PER_SQM` |
| Freight | ₹2.5 / nautical mile × factor | `FREIGHT_RATE_PER_NM` |
| Default voyage | 5,000 NM | `DEFAULT_DISTANCE_NM` |
| Container factor | 20GP 1.0, 40GP 1.65, 40HC 1.80 | `CONTAINERS` |

### 4.1 Freight is per-container, not per-kg

Ocean freight is charged per container regardless of fill. This is why utilisation
drives the saving — and why sub-container orders show little or no saving, since
the fixed freight is paid either way.

### 4.2 Costs are charged on the shipment, not container capacity

Packaging is billed for the pouches actually shipped. A previous version billed
`total_units` (container *capacity*), so a 1-pouch order was charged for 28,800
pouches and the dashboard showed **negative savings**.

### 4.3 Currency

INR throughout. No FX, no inflation, no volume discounts.

---

## 5. The baseline — how "Current vs AI" is computed

This is the most important assumption in the project, because the comparison *is*
the product.

### 5.1 The baseline is modelled independently

The saving is computed as `baseline_total_cost − optimised_total_cost`, where both
sides are produced by the **same physics and the same cost model** but by
**independent** code paths (`optimizers/baseline.py` vs `optimizers/joint.py`).

An earlier version derived "current practice" from the optimised answer by
multiplying it by fixed degradation factors — `units × 0.75`, `utilisation × 0.80`,
`dimensions × 1.12`. That guarantees a positive saving by construction and
measures nothing: the "30% saving" was the constant `0.80` in disguise. A
regression test (`test_baseline_is_not_a_fixed_ratio_of_optimised`) now fails if
the ratio ever becomes suspiciously constant across different inputs.

### 5.2 What "conventional practice" means — ⚠ needs client confirmation

A **competent** human constrained by catalogues and habit, **not** a strawman:

1. **Pouch** — smallest off-the-shelf stock format that holds the tea (catalogue
   rounding). No custom tooling.
2. **Carton** — the stock RSC box giving the most tea **per pallet**, within the
   weight cap. Not the box with the most pouches in it: real stock sizes
   (600×400, 400×300) are standard *because* they are pallet-modular, and any
   exporter shipping regularly knows which of their boxes stacks well.
3. **Pallet** — uniform layers, rotated to whichever way fits more. Mixing
   orientations *within* a layer (pinwheel/interlock) takes planning and is not
   modelled. Stacked to 1.8 m.
4. **Container** — 20GP by habit, floor-loaded, pallets not double-stacked.
   Pallets **are** rotated to fit the floor, using the same geometry the optimiser
   uses — that is how a 20GP takes 9 EUR pallets rather than 8, and every loader
   does it.

The AI wins by custom-sizing the pouch and carton, mixing orientations within a
pallet layer, double-stacking pallets, and choosing the container on cost rather
than habit. Every saving traces to one of those four levers, and each is reported
in the `driver` field of its comparison row.

**Calibration.** Three modelling errors were found and fixed by sanity-checking
the output rather than the code, and they are recorded here because they show what
a strawman looks like from the inside:

| Error | Effect | Fix |
|---|---|---|
| Carton chosen by pouches-per-carton | picked a box covering 58% of the pallet | choose for tea-per-pallet |
| Pallet layers never rotated | 4/layer instead of 6 | rotate the layer (not mix) |
| Container floor loading not rotated | 8 pallets instead of 9 in a 20GP | share the optimiser's geometry |

Savings across the SKU range fell from **39–61%** to **26–50%** as a result.
`test_savings_stay_in_a_defensible_band` fails if they ever exceed 55% again.

**Sanity check.** Tea at 0.35 g/cm³ is volume-limited, not weight-limited: a 20GP
holds ~11.6 t of *loose* tea however strong the floor. Against that ceiling the
baseline runs at ~31% container efficiency and the optimiser at ~53% — a gap that
is large but credible for an unoptimised operation. If the client's real figures
say otherwise, §5.1's override path makes the comparison exact.

**If the client supplies their real current figures**, those override the model
entirely (`current_*` parameters), and the comparison becomes exact rather than
modelled. `baseline_is_user_supplied` reports which happened.

### 5.3 Savings may legitimately be small or negative

For sub-container orders, fixed freight dominates and no packaging change can pay
for it. The model reports this honestly rather than manufacturing a saving.

---

## 6. AI usage

| Use | Model role | Guard |
|---|---|---|
| Result validation | Audits each stage against stated norms | Unparseable response reports `unknown`, not four green ticks |
| Explanation | Writes results up for an export manager | Numbers come from the pipeline, not the model |
| What-if chat | Answers "what if I switch to plastic?" | **Calls the real optimiser via function-calling.** Never estimates a number. The UI badges replies whose figures came from a tool call. |

The API key is server-side only. The browser calls `POST /api/chat`; the backend
calls OpenAI. Previously the key shipped in the client bundle via
`NEXT_PUBLIC_OPENAI_API_KEY`, readable by any visitor.

### 6.1 Target Market is recorded but not yet a constraint — ⚠

`target_market` is stored and shown to the assistant, but does not yet drive
regulatory logic (EU vs US labelling, pallet standards, phytosanitary rules).
Doing so needs a specification from the client on which markets impose what.

---

## 7. The 3D load plan

`GET /api/simulation/{id}/layout` returns the arrangement the optimiser actually
computed, not a plausible-looking one.

- **Recomputed, not stored.** Packing is a pure function of the stored dimensions,
  so recomputing cannot drift from the saved result and costs no schema. The
  recomputed counts are checked against the stored ones; a mismatch is a 500, not
  something to paper over.
- **A recipe, not a dump.** One pallet layer + one container floor + repeat
  counts: **1,940 bytes describes 1,440 cartons.** The browser composes the load
  by translation only and never re-derives a packing — for a `mixed` layer it
  could not, since "12 per layer" does not say where the twelfth carton sits.
- **Verified against physics, not a screenshot** (`frontend/tests/load-plan.spec.ts`):
  nothing overlaps, nothing escapes the container, cartons sit on their deck, and
  the composed count equals the results page. A misplaced carton looks exactly
  like a correct one.
- **Not modelled:** load securing, dunnage, weight distribution across the
  container floor, or door-side access. The view shows where cartons go, not how
  to strap them.

## 8. Scope not implemented

Called out explicitly rather than left as a silent gap:

- **Authentication** — a single default system user owns all simulations. The
  `users` table and FK exist, so adding auth is additive.
- **Mixed SKUs** — one product per simulation. Real containers often mix.
- **Multi-leg logistics** — a single ocean voyage; no inland haulage or transhipment.
- **Carton compression (BCT)** — board grade is chosen by weight, not by verified
  stack strength.
- **Export to PDF** — the browser's print dialog, not generated PDF.
- **Real freight quotes** — a linear rate model, not carrier APIs.

---

## 8. Where these live in code

| Assumption | File |
|---|---|
| Physical constants, rates | `backend/app/optimizers/constants.py` |
| Search constraints (the levers) | `Constraints` in `backend/app/optimizers/joint.py` |
| Baseline definition | `backend/app/optimizers/baseline.py` |
| Shipment type semantics | `resolve_shipment_type()` in `backend/app/services/simulation_service.py` |
| Input validation bounds | `backend/app/schemas.py` |
| Reference data (DB mirror) | `backend/app/services/seed_service.py` |
