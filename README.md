# Tea Packaging Optimization Platform

AI-powered packaging optimization for tea exporters — automatically recommends optimal pouch dimensions, master cartons, pallet layouts, and container selection.

## Overview

Tea manufacturers export thousands of cartons worldwide. Today, packaging dimensions, carton sizes, pallet layouts, and container loading are manually decided, resulting in low container utilization, high freight costs, and packaging waste.

This platform uses a **5-stage optimization pipeline** to compute the most cost-efficient packaging configuration:

```
Tea Density → Volume → Package → Carton → Pallet → Container → Cost Comparison
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind CSS |
| UI Components | Shadcn UI + Radix Primitives |
| Charts | Recharts |
| Backend | Python 3.12 + FastAPI |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy 2.0 (async) + Alembic |
| Optimization | Custom heuristics + mathematical formulas |
| Testing | Pytest + Playwright |
| Infrastructure | Docker + docker-compose |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 22+ (for local frontend dev)
- Python 3.12+ (for local backend dev)

### Option 1: Docker (recommended)

```bash
git clone <repo-url>
cd tea-packaging-optimization-platform

# Start all services
docker compose up -d

# Wait for backend to be ready, then:
# Backend: http://localhost:8000
# Swagger: http://localhost:8000/docs
# Frontend: http://localhost:3000
```

### Option 2: Local Development

**Backend:**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp ../.env.example .env

# Start PostgreSQL (via Docker or local)
docker compose up -d db

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Next.js Frontend                   │
│  /  /simulation  /compare  /history  /results/[id]  │
│         (Shadcn UI + Tailwind + Recharts)           │
└──────────────────────┬──────────────────────────────┘
                       │ REST API (JSON) / Swagger
┌──────────────────────▼──────────────────────────────┐
│                 FastAPI Backend                      │
│                                                      │
│  Routers          Services          Optimizers       │
│  ─────────        ─────────         ────────────     │
│  /simulation      run_full_pipeline  PackageOpt      │
│  /optimize/*      run_package_only   CartonOpt       │
│  /compare         run_carton_only    PalletOpt       │
│  /dashboard       run_pallet_only    ContainerOpt    │
│                   run_container_only                 │
│                                                      │
│              SQLAlchemy Async (PostgreSQL)           │
└─────────────────────────────────────────────────────┘
```

### Optimization Pipeline

**Stage 1 — Package:** Given tea density and target weight, generates 80+ dimension candidates for rectangular/cylindrical pouches. Scores by material surface area cost, fill ratio, and aspect ratio practicality.

**Stage 2 — Carton:** Finds optimal arrangement (nx×ny×nz) of packages inside master cartons. Constraints: max 25 kg carton weight, max 800×600×600mm outer dimensions. Board grade auto-selected (3/5/7/9-ply).

**Stage 3 — Pallet:** Fits cartons on EUR pallets (1200×1000mm). Tries both carton orientations. Constraints: max 1.8m height, max 1000 kg load.

**Stage 4 — Container:** Evaluates 20GP, 40GP, and 40HC containers. Calculates pallets per container floor, utilization %, empty space, and freight cost (₹2.5/NM × 5000 NM × type factor).

**Stage 5 — Compare:** Generates naive "current practice" estimate (non-optimized) and compares against AI-optimized configuration across 8 parameters.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/simulation` | Create & run full optimization |
| `GET` | `/api/simulation` | List simulations (paginated) |
| `GET` | `/api/simulation/{id}` | Get simulation with all results |
| `POST` | `/api/optimize/package` | Run package optimization only |
| `POST` | `/api/optimize/carton` | Run carton optimization only |
| `POST` | `/api/optimize/pallet` | Run pallet optimization only |
| `POST` | `/api/optimize/container` | Run container optimization only |
| `POST` | `/api/compare` | Compare current vs AI |
| `GET` | `/api/dashboard` | Dashboard aggregate stats |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc |

Full API documentation is available at `http://localhost:8000/docs` when the backend is running.

## Folder Structure

```
tea-packaging-optimization-platform/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings (Pydantic)
│   │   ├── database.py          # Async engine + session
│   │   ├── models.py            # 9 SQLAlchemy ORM models
│   │   ├── schemas.py           # 25+ Pydantic v2 DTOs
│   │   ├── routers/
│   │   │   ├── simulation.py    # CRUD endpoints
│   │   │   ├── optimization.py  # Standalone stage endpoints
│   │   │   └── dashboard.py     # Aggregate stats
│   │   ├── services/
│   │   │   └── simulation_service.py  # 5-stage orchestrator
│   │   └── optimizers/
│   │       ├── constants.py     # ISO standards, costs, material props
│   │       ├── package.py       # Stage 1: pouch dimensions
│   │       ├── carton.py        # Stage 2: master carton
│   │       ├── pallet.py        # Stage 3: pallet layout
│   │       └── container.py     # Stage 4: container selection
│   └── tests/
│       ├── conftest.py
│       ├── test_package_optimizer.py
│       ├── test_carton_optimizer.py
│       ├── test_pallet_optimizer.py
│       ├── test_container_optimizer.py
│       ├── test_pipeline.py
│       └── test_api.py
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   ├── playwright.config.ts
│   ├── app/
│   │   ├── layout.tsx           # Root HTML shell
│   │   ├── globals.css          # CSS variables + print styles
│   │   └── (main)/
│   │       ├── layout.tsx       # Sidebar + content area
│   │       ├── page.tsx         # Dashboard
│   │       ├── simulation/page.tsx
│   │       ├── compare/page.tsx
│   │       ├── history/page.tsx
│   │       └── results/[id]/page.tsx
│   ├── components/
│   │   ├── layout/sidebar.tsx   # Responsive nav sidebar
│   │   └── ui/                  # Shadcn UI primitives
│   ├── lib/
│   │   ├── api.ts               # Typed API client
│   │   └── utils.ts             # cn() utility
│   └── tests/
│       └── smoke.spec.ts        # Playwright E2E
│
└── docs/
    └── assumptions.md           # Business assumptions
```

## Database Schema

```
users ──< simulations ──< simulation_inputs (1:1)
                      ──< package_options (1:N)
                      ──< carton_configs (1:1)
                      ──< pallet_configs (1:1)
                      ──< container_configs (1:N)
                      ──< comparison_results (1:N)
                      ──< cost_summary (1:1)
```

## Assumptions

1. **Tea density range**: 0.2–0.5 g/cm³ typical; supports 0.05–5.0
2. **Headspace**: 15% added to net volume for pouch fill
3. **Standard pallet**: EUR/ISO 1200mm × 1000mm × 150mm, max load 1000 kg
4. **Container interior dims**: ISO 668 standard (20GP: 5.90×2.35×2.39m, 40GP: 12.04×2.35×2.39m, 40HC: 12.04×2.35×2.70m)
5. **Board grades**: 3-ply (≤10kg), 5-ply (≤20kg), 7-ply (≤30kg), 9-ply (>30kg)
6. **Freight cost model**: Freight Rate (₹2.5/NM) × Default Distance (5000 NM) × Container Type Factor (20GP: 1.0, 40GP: 1.65, 40HC: 1.80)
7. **Material costs**: Paper ₹12/m², Plastic ₹18/m², Metal ₹45/m² (INR)
8. **"Current" estimate**: Derived as AI result degraded by 12–25% across all stages
9. **Single user**: No authentication; default system user for all simulations
10. **Carton weight**: Package weight × units × 1.05 (5% tare for board)

## Testing

### Backend (Pytest)

```bash
cd backend
pip install -r tests/requirements-test.txt
pytest tests/ -v

# Coverage
pip install pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```

**Test suite**: 6 files, 55+ tests covering:
- Package optimizer (12 tests): dimensions, volume scaling, material cost, fill ratio
- Carton optimizer (12 tests): unit count, weight limits, board grades, arrangements
- Pallet optimizer (10 tests): layout, height/weight constraints, orientations
- Container optimizer (12 tests): all 3 types, utilization, freight, edge cases
- Pipeline integration (14 tests): end-to-end, savings, materials, comparison
- API endpoints (12 tests): all stateless endpoints, validation, OpenAPI docs

### Frontend (Playwright)

```bash
cd frontend
npx playwright install chromium
npx playwright test
```

**E2E suite**: 7 smoke tests covering:
- All 5 pages load
- Sidebar navigation
- Form field visibility
- HTML5 form validation
- Responsive mobile viewport

## Run Tests

```bash
# All backend tests (no DB required for optimizer + API tests)
cd backend && pytest tests/ -v

# Frontend E2E (requires running app)
cd frontend && npx playwright test
```

## Key Design Decisions

1. **Pure computation layer**: Optimizers are stateless functions — they don't depend on DB. This makes them testable and reusable.
2. **Heuristics over ML**: The optimization problem is more combinatorial than pattern-based. Explicit heuristics with explainable scoring is more transparent and auditable.
3. **Type-safe API**: Frontend `lib/api.ts` mirrors backend Pydantic schemas, ensuring end-to-end type safety.
4. **PostgreSQL over SQLite**: UUID primary keys, proper enum types, and rich querying via SQLAlchemy relationships.
5. **Staged pipeline**: Each stage can run independently or as part of the full pipeline — enabling both standalone optimization and full-simulation workflows.

## Demo

1. Start all services: `docker compose up -d`
2. Open `http://localhost:3000`
3. Click "New Simulation"
4. Enter: Tea Density = 0.35, Package Weight = 250g, Quantity = 100,000
5. Click "Run Optimization"
6. View results: best package dimensions, carton config, pallet layout, container comparison chart, cost breakdown, and savings vs current practice
7. Try "Export PDF" to save the report
8. Visit "Compare" to run standalone comparisons with custom current values
