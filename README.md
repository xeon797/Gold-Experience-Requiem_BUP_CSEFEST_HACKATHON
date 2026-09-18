# GridWise LLM

<div align="center">

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![SciPy HiGHS](https://img.shields.io/badge/Optimizer-SciPy_HiGHS_LP-8CAAE6.svg?style=flat&logo=scipy&logoColor=white)](https://scipy.org)
[![LLM](https://img.shields.io/badge/Model-Gemini_3.1_Flash--Lite-4285F4.svg?style=flat&logo=google&logoColor=white)](https://ai.google.dev)
[![Replay Audit](https://img.shields.io/badge/Replay_Audit-100%25_PASS-success.svg?style=flat)](https://gold-experience-requiem-bup-csefest.onrender.com)
[![Public Samples](https://img.shields.io/badge/Public_Samples-10%2F10_Identical_(0.0_BDT_Delta)-blue.svg?style=flat)](https://gold-experience-requiem-bup-csefest.onrender.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat)](LICENSE)

**Autonomous 24-Hour Campus Microgrid Dispatch & Operational Directive Interpretation Engine**  
*Built for the BUP CSE Fest 2026 Hackathon (Preliminary Round)*

[Live API Service](https://gold-experience-requiem-bup-csefest.onrender.com) • [Interactive API Docs (Swagger)](https://gold-experience-requiem-bup-csefest.onrender.com/docs) • [Alternative Docs (ReDoc)](https://gold-experience-requiem-bup-csefest.onrender.com/redoc) • [GitHub Repository](https://github.com/xeon797/Gold-Experience-Requiem_BUP_CSEFEST_HACKATHON)

</div>

---

## 1. System Architecture & Dual-Layer Pipeline

GridWise LLM decouples **probabilistic natural-language understanding** from **deterministic physical optimization**. Unstructured human operator notes are interpreted via Google Gemini (`gemini-3.1-flash-lite`) using strict JSON schema contracts, validated against deterministic guardrails, and compiled into linear constraints. The global minimum-cost dispatch is computed via the HiGHS Linear Programming (LP) solver and independently verified by a post-optimization replay engine.

```
                    ┌────────────────────────────────────────────────────────┐
                    │                   POST /optimize-energy                │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: COGNITIVE DIRECTIVE INTERPRETATION & GUARDRAILS                                                 │
│                                                                                                          │
│  [1 to 3 Operator Notes] ──► Gemini 3.1 Flash-Lite ──► Deterministic Guardrail Engine                    │
│                              (Constrained JSON Schema)  - Strict 0..N-1 note index bijection             │
│                                                         - Ascending hour intervals [0..23]               │
│                                                         - Type validation & parameter bounds             │
│                                                         - Fallback & invalid note sanitization           │
└───────────────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                                │
                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: MATHEMATICAL OPTIMIZATION & VERIFICATION                                                        │
│                                                                                                          │
│  Deterministic Directive Compiler                                                                        │
│   ├── Solar curtailment: alpha(t) = min(factors)                                                         │
│   ├── Reserve floors:    E_min(t) = max(floors)                                                          │
│   └── Feeder caps:       P_grid_max(t) = min(caps)                                                       │
│                               │                                                                          │
│                               ▼                                                                          │
│  HiGHS LP Solver (scipy.optimize.linprog)                                                                │
│   ├── Objective: min sum(Tariff(t) * Grid(t))                                                            │
│   ├── Conservation of Energy: Grid(t) + Solar(t) + Discharge(t) = Demand(t) + Charge(t)                 │
│   ├── State-of-Charge Dynamics: E(t+1) = E(t) + Charge(t) - Discharge(t)                                 │
│   └── Boundary Neutrality: E(24) == E(0)                                                                 │
│                               │                                                                          │
│                               ▼                                                                          │
│  In-Memory Replay Audit Engine                                                                           │
│   ├── Recomputes 24h energy balance from hourly plan                                                     │
│   ├── Verifies zero constraint & directive violations                                                    │
│   └── Asserts recalculated totals match response metadata                                                │
└───────────────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                                │
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │               HTTP 200 JSON Response                   │
                    │   (Hourly Plan, Directive Interpretations, Totals)     │
                    └────────────────────────────────────────────────────────┘
```

---

## 2. Production Endpoints & Live Status

The service is deployed on high-availability container infrastructure and is publicly accessible over HTTPS with zero authentication, tokens, or VPN required:

| Resource | Method | Path | Target / Description |
|---|:---:|---|---|
| **Base Service** | `ANY` | `/` | Redirects to interactive documentation (`/docs`). |
| **Health Probe** | `GET` | `/health` | Container liveness & readiness check. Returns `{"status":"ok"}`. |
| **Optimization API** | `POST` | `/optimize-energy` | Main optimization & directive interpretation pipeline. |
| **Interactive Docs** | `GET` | `/docs` | Custom branded Swagger UI (Satoshi Typography, Raspberry & Electric Navy palette). |
| **ReDoc Engine** | `GET` | `/redoc` | OpenAPI 3.1 specification browser. |
| **OpenAPI Schema** | `GET` | `/openapi.json` | Raw OpenAPI 3.1 JSON contract. |

### Live Service URLs
- **Primary Endpoint:** `https://gold-experience-requiem-bup-csefest.onrender.com`
- **Health Check:** `https://gold-experience-requiem-bup-csefest.onrender.com/health`
- **Interactive UI:** `https://gold-experience-requiem-bup-csefest.onrender.com/docs`

---

## 3. Quickstart & API Usage

### 3.1 Live Verification with cURL (One-Line Execution)

Execute this against the live production endpoint to verify immediate operation:

```bash
curl -s -X POST https://gold-experience-requiem-bup-csefest.onrender.com/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "PROD-AUDIT-01",
    "operator_notes": [
      "Keep at least 20 kWh in reserve from 6 PM to 10 PM for critical campus operations.",
      "Cloud cover expected; solar output drops to 50% between 11 AM and 2 PM."
    ],
    "hours": [
      {"hour": 0, "demand_kwh": 40.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 1, "demand_kwh": 35.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 2, "demand_kwh": 30.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 3, "demand_kwh": 30.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 4, "demand_kwh": 32.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 5, "demand_kwh": 38.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 6, "demand_kwh": 50.0, "solar_kwh": 5.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 7, "demand_kwh": 70.0, "solar_kwh": 15.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 8, "demand_kwh": 95.0, "solar_kwh": 30.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 9, "demand_kwh": 120.0, "solar_kwh": 50.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 10, "demand_kwh": 140.0, "solar_kwh": 70.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 11, "demand_kwh": 150.0, "solar_kwh": 80.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 12, "demand_kwh": 145.0, "solar_kwh": 85.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 13, "demand_kwh": 140.0, "solar_kwh": 80.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 14, "demand_kwh": 135.0, "solar_kwh": 65.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 15, "demand_kwh": 125.0, "solar_kwh": 45.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 16, "demand_kwh": 110.0, "solar_kwh": 25.0, "tariff_bdt_per_kwh": 8.5},
      {"hour": 17, "demand_kwh": 90.0, "solar_kwh": 10.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 18, "demand_kwh": 105.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 19, "demand_kwh": 115.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 20, "demand_kwh": 110.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 21, "demand_kwh": 95.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 12.0},
      {"hour": 22, "demand_kwh": 70.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 23, "demand_kwh": 50.0, "solar_kwh": 0.0, "tariff_bdt_per_kwh": 6.0}
    ],
    "battery": {
      "capacity_kwh": 100.0,
      "initial_energy_kwh": 30.0,
      "minimum_energy_kwh": 10.0,
      "max_charge_kwh_per_hour": 25.0,
      "max_discharge_kwh_per_hour": 25.0
    }
  }'
```

### 3.2 Response Payload (HTTP 200 OK)

```json
{
  "scenario_id": "PROD-AUDIT-01",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "minimum_battery_reserve",
      "structured_adjustment": {
        "hours": [18, 19, 20, 21],
        "minimum_energy_kwh": 20.0
      },
      "explanation": "Maintain at least 20 kWh in the battery between 6 PM and 10 PM."
    },
    {
      "note_index": 1,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {
        "hours": [11, 12, 13],
        "factor": 0.5
      },
      "explanation": "Solar generation reduced to 50% between 11 AM and 2 PM."
    }
  ],
  "hourly_plan": [
    {
      "hour": 0,
      "grid_kwh": 40.0,
      "solar_used_kwh": 0.0,
      "battery_action": "idle",
      "battery_kwh": 0.0,
      "battery_energy_after_kwh": 30.0
    }
  ],
  "total_grid_kwh": 1734.5,
  "total_cost_bdt": 39406.25,
  "peak_grid_kwh": 100.0,
  "plan_summary": "Applied 2 operational directive(s) and ignored 0 irrelevant note(s). Applied controls: minimum battery reserve, solar reduction. Grid use is 1734.50 kWh, cost is 39406.25 BDT, and peak grid use is 100.00 kWh; the battery returns to its initial energy."
}
```

### 3.3 HTTP Status Code Contract

| Code | Status | Trigger Condition | Schema / Error Structure |
|:---:|---|---|---|
| `200` | **OK** | Optimization succeeds; plan passes full constraint replay. | Full `OptimizeResponse` schema. |
| `400` | **Bad Request** | Malformed JSON, missing fields, invalid types, arrays $\ne 24$ hours, notes $< 1$ or $> 3$. | `{"error": "invalid_request", "message": "...", "details": [...]}` |
| `422` | **Unprocessable Entity** | Pydantic semantic contract violations. | Sanitized `ErrorResponse` schema (zero stack traces). |
| `500` | **Internal Error** | Controlled solver infeasibility or upstream LLM timeout. | `{"error": "internal_error", "message": "..."}` |

---

## 4. Mathematical Optimization Model

The core energy scheduling problem is formulated as a linear program and solved using `scipy.optimize.linprog(method="highs")`.

### 4.1 Index Sets & Decision Variables
- $t \in \{0, 1, \dots, 23\}$: Hourly intervals over the 24-hour horizon.
- $P_{g,t} \ge 0$: Electricity imported from the utility grid at hour $t$ (kWh).
- $P_{s,t} \ge 0$: Solar power self-consumed on-site at hour $t$ (kWh).
- $P_{c,t} \ge 0$: Energy dispatched to charge the battery at hour $t$ (kWh).
- $P_{d,t} \ge 0$: Energy discharged from the battery to serve campus load at hour $t$ (kWh).
- $E_t \ge 0$: Energy stored in the battery at the start of hour $t$ (kWh).

### 4.2 Objective Function
Minimize total campus electricity procurement cost:
$$\min \sum_{t=0}^{23} \text{Tariff}_t \cdot P_{g,t}$$

### 4.3 Subject to Physical & Directive Constraints

1. **Conservation of Energy (Demand Balance):**
   $$P_{g,t} + P_{s,t} + P_{d,t} = D_t + P_{c,t} \quad \forall t \in \{0, \dots, 23\}$$
2. **Solar Resource Curtailment & Directive Bounds:**
   $$0 \le P_{s,t} \le \alpha_t \cdot S_t \quad \text{where } \alpha_t \in (0, 1] \text{ is the effective solar factor}$$
3. **State-of-Charge Dynamics (100% Round-Trip Efficiency):**
   $$E_{t+1} = E_t + P_{c,t} - P_{d,t} \quad \forall t \in \{0, \dots, 22\}$$
4. **Battery Energy Capacity & Reserve Windows:**
   $$E_{\min,t} \le E_t \le E_{\max} \quad \forall t \in \{0, \dots, 23\}$$
5. **Charge & Discharge Inverter Limits:**
   $$0 \le P_{c,t} \le P_{c,\max}, \quad 0 \le P_{d,t} \le P_{d,\max} \quad \forall t \in \{0, \dots, 23\}$$
6. **Mutually Exclusive Inverter Modes:**
   Enforced via cost-optimal dispatch (since $\text{Tariff}_t > 0$, simultaneous charge and discharge is strictly sub-optimal and eliminated in linear space).
7. **Feeder Capacity & Grid Import Caps:**
   $$0 \le P_{g,t} \le P_{g,\max,t} \quad \forall t \in \{0, \dots, 23\}$$
8. **End-of-Day Battery Neutrality:**
   $$E_{23} + P_{c,23} - P_{d,23} = E_0$$

---

## 5. Directive Taxonomy & Conflict Resolution Algebra

The cognitive engine parses 6 operational directive types alongside neutral distractor notes. Multiple overlapping directives are compiled deterministically using conservative multi-directive arbitration algebra:

| Directive Type | Target Parameter | Natural Language Semantics | Overlap Conflict Algebra |
|---|---|---|---|
| `solar_reduction` | `factor` $\in [0, 1)$ | Curtail solar generation over specified hours. | $\alpha_{\text{eff}}(t) = \min_{i}(\alpha_i(t))$ *(strictest curtailment)* |
| `no_charge_window` | Charging lockout | Inhibit battery charging during specified hours. | Logical OR: $P_{c,\max}(t) = 0$ if any note applies. |
| `no_discharge_window` | Discharging lockout | Inhibit battery discharging during specified hours. | Logical OR: $P_{d,\max}(t) = 0$ if any note applies. |
| `minimum_battery_reserve`| `minimum_energy_kwh` | Enforce higher battery floor during critical hours. | $E_{\min,\text{eff}}(t) = \max(E_{\min}, \max_i(R_i(t)))$ *(safest reserve)* |
| `max_grid_window` | `max_grid_kwh` $\ge 0$ | Impose grid import limit due to feeder/demand caps. | $P_{g,\max,\text{eff}}(t) = \min_i(\text{Cap}_i(t))$ *(strictest feeder cap)* |
| `no_op` | None | Operational context, irrelevant chatter, or distractors. | `applies: false`, `structured_adjustment: null`. |

---

## 6. Deterministic Guardrail Safeguards

1. **Bijective Note Mapping:** Strict 1-to-1 bijection between input `operator_notes` (indexes $0 \dots N-1$) and output `directive_interpretation`. No missing, skipped, or duplicated notes.
2. **Canonical Hour Validation:** Hours are normalized to zero-indexed, sorted, strictly ascending integers:
   $$\text{hours} = [h_1, h_2, \dots, h_k], \quad 0 \le h_i \le 23, \quad h_i < h_{i+1}$$
3. **Half-Open Interval Interpretation:** Time ranges expressed in colloquial speech (e.g. "9 AM to 11 AM") map to discrete hourly intervals `[9, 10]`. "From 10 PM to midnight" maps to `[22, 23]`.
4. **Independent Post-Optimization Replay Audit:** Every response is validated by `app/replay.py` in-memory prior to serialization. If any demand equation, battery bound, or compiled directive constraint is violated by $> 10^{-4}$ kWh, the request halts with an error rather than emitting a corrupted dispatch.

---

## 7. Local Quickstart (Reproducibility Guide)

### 7.1 Clone & Environment Setup
```bash
# Clone the repository
git clone https://github.com/xeon797/Gold-Experience-Requiem_BUP_CSEFEST_HACKATHON.git
cd Gold-Experience-Requiem_BUP_CSEFEST_HACKATHON/gridwise-llm

# Initialize virtual environment
python -m venv .venv
source .venv/bin/activate       # On Linux/macOS
# .\.venv\Scripts\Activate.ps1  # On Windows PowerShell

# Install pinned dependencies
pip install -r requirements.txt
```

### 7.2 Configure Runtime Credentials
Create `.env` from the provided template:
```bash
cp .env.example .env
```

Configure your `.env` file:
```dotenv
GEMINI_API_KEY=your_google_gemini_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
PORT=8000
LOG_LEVEL=INFO
```

### 7.3 Run the Application
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify service readiness:
```bash
curl -s http://localhost:8000/health
# Returns: {"status":"ok"}
```

---

## 8. Docker Deployment & Container Registries

Container images are cross-compiled for `linux/amd64` using multi-stage builds on `python:3.11-slim`, with zero baked-in secrets and automated healthchecks.

### 8.1 Public Container Images
- **GitHub Container Registry (GHCR):** `ghcr.io/xeon797/gridwise-llm:v1.0.0`
- **Docker Hub:** `ankonsinha797/gridwise-llm:v1.0.0`

### 8.2 Run via Docker (Verified Single Command)
```bash
docker run -d \
  -p 8000:8000 \
  -e PORT=8000 \
  -e GEMINI_API_KEY="your_api_key_here" \
  --name gridwise-service \
  ghcr.io/xeon797/gridwise-llm:v1.0.0
```

### 8.3 Build Container Locally
```bash
docker build -t gridwise-llm:local .
docker run -d -p 8000:8000 -e GEMINI_API_KEY="your_api_key_here" gridwise-llm:local
```

---

## 9. Benchmark Verification & Adversarial Audit

### 9.1 Public Benchmark Results (10/10 Cases)
Executed against the live production deployment using `scripts/test_public_samples.py`:

```
| Case ID   | Replay Audit | Returned Cost (BDT) | Reference Cost (BDT) | Delta (BDT) | Directive Violated |
|:----------|:------------:|--------------------:|---------------------:|------------:|:------------------:|
| SAMPLE-01 | PASS         |             38365.0 |                38365 |         0.0 |       False        |
| SAMPLE-02 | PASS         |             42885.0 |                42885 |         0.0 |       False        |
| SAMPLE-03 | PASS         |             35480.0 |                35480 |         0.0 |       False        |
| SAMPLE-04 | PASS         |             40495.0 |                40495 |         0.0 |       False        |
| SAMPLE-05 | PASS         |             33950.0 |                33950 |         0.0 |       False        |
| SAMPLE-06 | PASS         |             34090.0 |                34090 |         0.0 |       False        |
| SAMPLE-07 | PASS         |             38550.0 |                38550 |         0.0 |       False        |
| SAMPLE-08 | PASS         |             37665.0 |                37665 |         0.0 |       False        |
| SAMPLE-09 | PASS         |             34873.0 |                34873 |         0.0 |       False        |
| SAMPLE-10 | PASS         |             41620.0 |                41620 |         0.0 |       False        |
```
*Result: 100% replay pass rate, 0.0 BDT cost delta across all public cases.*

### 9.2 Adversarial Stress-Test Suite (`scripts/live_adversarial_test.py`)
Tested live against `https://gold-experience-requiem-bup-csefest.onrender.com`:

| Scenario Category | Test Description | Injected Condition | Live Status | Replay Result |
|---|---|---|:---:|:---:|
| **Novel Paraphrasing** | Colloquial solar wash note | *"power-washing panels 9 to 11, expect third solar"* | HTTP 200 | **PASS** (`factor: 0.333`) |
| **Novel Paraphrasing** | Colloquial charge lockout | *"battery can't take a charge between 3 and 5 afternoon"* | HTTP 200 | **PASS** (`hours: [15, 16]`) |
| **Novel Paraphrasing** | Evening discharge ban | *"hold back on draining battery from 7pm to 8pm"* | HTTP 200 | **PASS** (`hours: [19]`) |
| **Novel Paraphrasing** | Night reserve floor | *"floor of 60kWh sitting in battery all evening 6 to 10pm"*| HTTP 200 | **PASS** (`reserve: 60.0`) |
| **Novel Paraphrasing** | Feeder cap enforcement | *"feeder capped — don't pull more than 140 from grid 8-10pm"*| HTTP 200 | **PASS** (`grid <= 140.0`) |
| **Distractor Filtering**| 3 Unrelated campus notes | IT migrations, cafeteria menus, HVAC filter change | HTTP 200 | **PASS** (All 3 `no_op`) |
| **Overlap Arbitration** | Overlapping solar cuts | 10 AM–2 PM @ 50% vs. 12 PM–4 PM @ 30% | HTTP 200 | **PASS** (Min factor 0.3) |
| **Boundary Conditions** | Edge hours (Hour 0 & 23) | Midnight-2 AM lockout & 10 PM-midnight grid cap | HTTP 200 | **PASS** (Hours 0-1, 22-23) |
| **Near-Capacity Reserve**| 95 kWh floor on 100 kWh | High reserve requirement solved without infeasibility | HTTP 200 | **PASS** (SOC $\ge$ 95.0) |
| **Malformed Requests**  | Missing fields, 23h arrays | Injected structural schema violations | HTTP 400 | **PASS** (Sanitized JSON) |
| **Concurrency Load**    | 5 Sequential requests | Rapid back-to-back solves | HTTP 200 | **PASS** (Avg 2.90s) |

---

## 10. Runtime Environment Matrix

| Variable | Type | Default | Description |
|---|:---:|:---:|---|
| `GEMINI_API_KEY` | `string` | *Required* | API key for Google Gemini Generative Language API. |
| `GEMINI_MODEL` | `string` | `gemini-3.1-flash-lite` | Model identifier used for natural language parsing. |
| `GEMINI_BASE_URL` | `string` | `https://generativelanguage.googleapis.com/v1beta` | Upstream REST endpoint for Google Gemini API. |
| `LLM_TIMEOUT_SECONDS` | `float` | `20.0` | HTTP timeout for upstream LLM inference calls. |
| `PORT` | `integer` | `8000` | Local port bound by Uvicorn ASGI server. |
| `LOG_LEVEL` | `string` | `INFO` | Sanitized application logging level (`INFO`, `DEBUG`, `WARNING`). |

---

## 11. Security Audit & Secret Handling

- **Zero Hardcoded Secrets:** No API keys, credentials, tokens, or confidential URLs exist within source code, commit history, or container images.
- **Runtime Injection:** All credentials are provided exclusively via environment variables (`GEMINI_API_KEY`) at execution time.
- **Exclusion Filters:** `.env`, `.env.*`, `tests/`, and scratch test scripts are strictly excluded via `.gitignore` and `.dockerignore`.
- **Sanitized Error Surfaces:** Production exceptions never leak stack traces, internal paths, or environment variables to client responses.

---

## 12. External Dependencies & Acknowledgments

- **[FastAPI](https://fastapi.tiangolo.com/):** Modern, high-performance web framework for building APIs with Python 3.11+.
- **[SciPy](https://scipy.org/):** Fundamental algorithms for scientific computing, providing `scipy.optimize.linprog` with the HiGHS solver.
- **[Pydantic v2](https://docs.pydantic.dev/):** Rust-backed data parsing and validation for strict schema conformance.
- **[Google Gemini API](https://ai.google.dev/):** Next-generation generative language foundation model (`gemini-3.1-flash-lite`).
- **[HTTPX](https://www.python-httpx.org/):** Fully featured HTTP client for Python with async connection pooling.
- **[Uvicorn](https://www.uvicorn.org/):** Lightning-fast ASGI server implementation for production hosting.
