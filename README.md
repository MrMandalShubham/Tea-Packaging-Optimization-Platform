# Tea Packaging Optimization Platform

AI-assisted packaging optimisation for tea exporters. Given tea density, pouch
weight and shipment size, it recommends the pouch, master carton, pallet layout
and container that minimise **total landed cost** — and shows its working.

On the reference shipment (0.35 g/cm³, 250 g pouches, 100,000 units) it packs
**2 containers at 69% utilisation instead of 8**, cutting modelled cost from
₹2,15,560 to ₹1,56,600 — a **27% saving**, with every rupee traced to a named
decision. Across the SKU range the saving runs **27–53%**. Plans respect
real-world loading: 50 mm forklift clearance and crush-safe carton stacks
(see docs/assumptions.md §3.5).

---

## The core idea

The obvious way to build this is a pipeline:

```
Package → Carton → Pallet → Container
```

That is what the brief's flowchart describes, and it does not work. Each stage
optimises itself and silently constrains the next:

> The carton stage maximises units per carton, hits the 25 kg limit, and produces
> a **570 mm-tall carton**. Only 2 layers then fit under the 1.8 m pallet rule, so
> the pallet is **1.29 m**. In a **2.39 m** container that stacks 1 high — and
> **1.1 m of container height is bought and shipped empty.**
>
> Every step is locally optimal. The result is **36.9% utilisation** — the exact
> problem the brief asks us to solve.

So the stages are solved **together**. `optimizers/joint.py` enumerates complete
configurations — pouch × carton arrangement × pallet pattern × container × pallet
stacking — and scores each on total landed cost. A carton that holds *fewer*
pouches wins, because it tiles the pallet at 94.9% and stacks two-high.

| | Greedy pipeline | Joint search |
|---|---|---|
| Container utilisation | 36.9% | **67.3%** |
| Containers needed | 4 | **2** |
| Freight | ₹82,500 | **₹41,250** |

(That table compares the two *optimisers* on identical inputs, before the
operational constraints below existed. The 27% headline saving is against
modelled current practice — a different and harder yardstick.)

~15,000 configurations, evaluated exhaustively in **under a second**. So the
result is the true optimum of the model, not an approximation — and it is
reproducible and explainable, which a metaheuristic or an LLM guess would not be.

## The comparison is the product

"AI saves you 27%" is only meaningful if the number it is measured against is
real. So the baseline is **modelled independently** (`optimizers/baseline.py`) and
costed with the *same* physics and rates:

1. **Pouch** — smallest off-the-shelf stock format that holds the tea
2. **Carton** — stock RSC box giving the most tea **per pallet**, within the
   weight cap. Not the box with the most pouches in it: 600×400 and 400×300 are
   standard sizes *because* they are pallet-modular
3. **Pallet** — uniform layers, rotated whichever way fits more; orientations not
   *mixed* within a layer; stacked to 1.8 m
4. **Container** — 20GP by habit, floor-loaded, no double-stacking. Pallets *are*
   rotated to fit the floor, using the same geometry the optimiser uses

That is a *competent human constrained by catalogues* — not a strawman, because a
strawman inflates savings just as dishonestly as a fudge factor would. The
optimiser wins on four explainable levers: custom pouch, custom carton, **mixed**
layer patterns, and double-stacking. Each comparison row carries the lever
responsible in its `driver` field, and the UI prints the baseline's assumptions
next to the savings.

If you supply your real current figures, they override the model entirely and the
comparison becomes exact.

> Two regression tests guard this. `test_baseline_is_not_a_fixed_ratio_of_optimised`
> fails if the savings ratio becomes suspiciously constant across inputs — the
> signature of a multiplier in disguise. `test_savings_stay_in_a_defensible_band`
> fails above 55%: three modelling errors once put it at 39–61%, and a 60% claim
> would not survive the first question from a packaging engineer. See
> [docs/assumptions.md §5](docs/assumptions.md) for what those errors were.

## Where AI is used

The optimisation is deterministic arithmetic and stays that way. The LLM is used
where a formula cannot help:

- **Validation** — audits each stage against industry norms
- **Explanation** — writes the result up for an export manager
- **What-if assistant** — "what if I switch to plastic?" **calls the real
  optimiser** via function-calling and reports what came back. It never estimates
  a number, and replies whose figures came from a tool call are badged in the UI.

The API key is server-side only. The browser calls `POST /api/chat`; the backend
calls OpenAI.

---

## Quick start

### Docker (recommended)

```bash
git clone https://github.com/MrMandalShubham/Tea-Packaging-Optimization-Platform.git
cd Tea-Packaging-Optimization-Platform
cp .env.example .env
docker compose up -d
```

That's the whole thing. `.env.example` ships working local defaults — nothing to
fill in — the backend runs `alembic upgrade head` before serving, and reference
data seeds on startup. (Verified from a clean clone, and it also starts with no
`.env` at all.)

- Frontend → http://localhost:3000
- Swagger → http://localhost:8000/docs
- Health → http://localhost:8000/health

`OPENAI_API_KEY` is optional: everything except the AI assistant and the
explanation panel works without it, since the optimisation is arithmetic.

### Local

```bash
# Database
docker compose up -d db

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp ../.env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### Environment

All of these have working defaults; you only need to touch `OPENAI_API_KEY`.

| Variable | Where | Notes |
|---|---|---|
| `POSTGRES_USER/PASSWORD/DB` | db | Local container credentials — not secrets |
| `DATABASE_URL` | backend | `postgresql+asyncpg://…` — async driver. **Used only when running uvicorn on the host**; compose derives its own (host `db`, not `localhost`) |
| `DATABASE_URL_SYNC` | backend | `postgresql://…` — Alembic offline mode |
| `OPENAI_API_KEY` | backend | **Optional.** The optimisation is arithmetic and runs without it; only the assistant and written explanation need it. **Server-side only** — never `NEXT_PUBLIC_*` |
| `OPENAI_MODEL` | backend | default `gpt-4o-mini` |
| `CORS_ORIGINS` | backend | comma-separated |
| `AUTO_CREATE_TABLES` | backend | dev only; compose forces it off so Alembic owns the schema |
| `NEXT_PUBLIC_API_URL` | frontend | public — ships in the browser bundle |

> Anything `NEXT_PUBLIC_*` is inlined into the JS bundle and readable by every
> visitor. Never put a secret there.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Next.js 14 · TS · Tailwind · Shadcn · Recharts · three.js │
│  /  /simulation  /results/[id]  /compare  /history       │
└───────────────────────┬──────────────────────────────────┘
                        │ REST (JSON)
┌───────────────────────▼──────────────────────────────────┐
│                    FastAPI                                │
│                                                           │
│  routers/          services/           optimizers/        │
│  ─────────         ─────────           ───────────        │
│  simulation        simulation_service  joint    ← engine  │
│  optimization      ai_service          baseline ← honesty │
│  dashboard         seed_service        package            │
│  chat  ← proxy                         carton             │
│                                        pallet             │
│                                        container          │
│                                        constants          │
│                                                           │
│         SQLAlchemy 2.0 async  ·  Alembic                  │
└───────────────────────┬──────────────────────────────────┘
                        │
                  PostgreSQL 16
```

`optimizers/` are **pure functions with no database access** — which is why 150+
tests run in ~30s without a Postgres, and why the logic is easy to reason about.

### Layout

```
backend/
  app/
    main.py                  FastAPI entry, lifespan, CORS
    config.py                Pydantic settings
    database.py              async engine + session
    models.py                ORM: 7 reference + 9 transactional tables
    schemas.py               Pydantic v2 DTOs
    routers/
      simulation.py          POST/GET /api/simulation
      optimization.py        POST /api/optimize/{stage}
      dashboard.py           GET /api/dashboard
      chat.py                POST /api/chat — server-side OpenAI proxy
      reference.py           GET /api/reference — dropdown master data
    services/
      simulation_service.py  orchestration + comparison
      ai_service.py          validation, explanation, function-calling
      seed_service.py        reference data from constants.py
    optimizers/
      joint.py               THE ENGINE — global cost search
      baseline.py            conventional practice, modelled independently
      package.py             pouch geometry candidates
      carton.py              standalone carton stage
      pallet.py              standalone pallet stage
      container.py           standalone container stage
      constants.py           ISO specs, rates, materials
  alembic/versions/          migrations
  tests/                     152 tests
frontend/
  app/(main)/                dashboard, simulation, results, compare, history
  components/layout/         sidebar, chat widget
  components/viz/            3D container load (lazy-loaded three.js)
  lib/api.ts                 typed client
  lib/export.ts              Excel export
  lib/load-plan.ts           load-plan geometry — pure, testable, no three.js
  tests/                     Playwright E2E
docs/assumptions.md          every assumption, and what would change it
```

---

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/simulation` | Create & run an optimisation |
| `GET` | `/api/simulation` | List (paginated) |
| `GET` | `/api/simulation/{id}` | Full result |
| `GET` | `/api/simulation/{id}/ai` | AI validation + explanation |
| `POST` | `/api/compare` | Current vs AI |
| `POST` | `/api/optimize/package` | Package stage only |
| `POST` | `/api/optimize/carton` | Carton stage only |
| `POST` | `/api/optimize/pallet` | Pallet stage only |
| `POST` | `/api/optimize/container` | Container stage only |
| `GET` | `/api/simulation/{id}/layout` | Load plan for the 3D view |
| `POST` | `/api/chat` | What-if assistant (OpenAI proxy) |
| `GET` | `/api/reference` | Master data for form dropdowns |
| `GET` | `/api/dashboard` | Aggregate stats |
| `GET` | `/health` | Health check |

Interactive docs at `/docs`. The `/optimize/{stage}` endpoints run a stage in
isolation — useful for inspection, but chaining them is exactly the greedy
behaviour `joint.py` exists to replace.

### Two of everything, on purpose

Container metrics come in pairs because they answer different questions.
Conflating them is how an earlier version reported 64% utilisation on a
**one-pouch order**, and made a 20GP look like it out-shipped a 40GP (it doesn't;
it just needs five boxes instead of two).

| Capacity view — one full container | Shipment view — this order |
|---|---|
| `cartons_per_container` | `containers_needed` |
| `units_per_container` *(Module 6's "Total Units")* | `total_units_shipped` |
| `capacity_utilization_pct` — packing density | `utilization_pct` — what the freight bill reflects |
| `empty_space_per_container_m3` *(Module 6's "Empty Space")* | `empty_space_total_m3` |

Package volumes likewise: `product_volume_cm3` is the tea itself (mass ÷ density,
Module 3's "Product Volume"); `volume_cm3` is the pouch, which is larger because
tea needs headspace.

### 3D container load

`/layout` returns the load plan the optimiser actually computed — **not** a
plausible-looking arrangement. `fit_rectangles` used to return only `(count,
pattern)`, which meant a viewer had to guess where cartons went, and for a `mixed`
pattern it could not: *"12 per layer"* does not say where the twelfth one sits.
It now returns real placements.

The payload is a **recipe**, not a dump: one pallet layer + one container floor +
repeat counts. **1,940 bytes describes 1,440 cartons.** The browser composes the
load by pure translation and never re-derives a packing.

The geometry is checked against physics rather than a screenshot
(`frontend/tests/load-plan.spec.ts`): nothing overlaps, nothing leaves the
container, cartons sit on their deck, and the composed count equals the number on
the results page. A misplaced carton looks exactly like a correct one, so it has
to be tested rather than eyeballed.

three.js is lazy-loaded on click (~600 KB) and cartons render as a single
instanced mesh — 1,440 individual meshes would not be viable.

---

## Database

```
Reference (seeded from constants.py at startup, served via GET /api/reference)
  tea_density_refs · packaging_material_refs · package_type_refs
  package_weight_refs · board_grade_refs · container_specs · pallet_specs

Transactional
  users ──< simulations ──< simulation_inputs   (1:1)
                        ──< package_options     (1:N)
                        ──< carton_configs      (1:1)
                        ──< pallet_configs      (1:1)
                        ──< container_configs   (1:N, one per container type)
                        ──< comparison_results  (1:N)
                        ──< cost_summary        (1:1)
```

Cartons store **both inner and outer** dimensions. Outer is what you buy and
palletise; keeping only inner means the pallet and container stages stack cartons
as though the board had no thickness.

Schema is owned by Alembic. CI fails if the models drift from the migrations.

---

## Screenshots

In [docs/screenshots](docs/screenshots) — generated from a real run by
`frontend/tests/screenshots.spec.ts`, so they cannot drift from what the app
actually renders.

## Testing

```bash
cd backend && pytest tests/ -v          # 205 tests, no DB needed
cd frontend && npm run typecheck
cd frontend && npm run test:e2e         # 30 tests; needs the app running
```

The tests assert **business outcomes**, not implementation. The previous suite
passed 66/66 while the optimiser shipped 37%-full containers, because every test
checked that the code did what the code did. Representative assertions now:

- `test_container_utilization_is_good` — fails below 60% packing density
- `test_baseline_is_not_a_fixed_ratio_of_optimised` — catches a fake baseline
- `test_baseline_carton_tiles_the_pallet` — catches a strawman baseline
- `test_savings_stay_in_a_defensible_band` — fails if savings exceed 55%
- `test_best_package_is_the_one_inside_the_carton` — the recommendation must be coherent
- `test_upstream_error_does_not_leak_the_key` — no secret in any error path
- `test_tiny_order_reports_near_zero_real_utilization` — honest metrics
- `load-plan.spec.ts` — the 3D view's cartons must not overlap or escape the container

CI (`.github/workflows/ci.yml`) runs backend tests, a migration-drift check,
frontend typecheck/lint/build, and Playwright E2E against a live stack.

---

## Assumptions

Every assumption — and what would change if the client corrected it — is in
[docs/assumptions.md](docs/assumptions.md). The load-bearing ones:

- **Cost rates are indicative placeholders.** Absolute figures are illustrative;
  the *relative* comparison is the meaningful output.
- **Shipment Type semantics** are inferred: `total_weight` = whole order,
  `per_container` = must fit one container.
- **Pallet double-stacking is on by default** (worth ~18 utilisation points).
  Turn it off via `Constraints` for fragile goods.
- **Round pouches pack as their bounding box** — honest but pessimistic; ~21% of
  the carton is unavoidably air, which is why `square` usually wins.
- **Single user, no auth.** The `users` table and FK exist; adding auth is additive.

---

## Known gaps

Stated rather than hidden: no authentication, no mixed-SKU containers, no real
carrier freight quotes, and `target_market` is recorded but not yet a regulatory
constraint. Carton compression is modelled with conservative default stack
ratings — replace them with the client's board data before trusting a specific
board choice. "Export to PDF" is the browser's
print dialog, not generated PDF.
