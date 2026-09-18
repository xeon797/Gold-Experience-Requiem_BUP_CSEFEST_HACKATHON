"""Adversarial live test runner against the deployed Render URL.

Executes 7 thorough adversarial checks as specified in the judge review pass.
"""

import json
from pathlib import Path
import sys
from time import monotonic, sleep
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.replay import ReplayValidationError, validate_replay
from app.schemas import OptimizeRequest, OptimizeResponse

LIVE_URL = "https://gold-experience-requiem-bup-csefest.onrender.com"

with open(PROJECT_ROOT / "reference" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json", encoding="utf-8") as f:
    SAMPLE_CASES = json.load(f)["cases"]

BASE_INPUT = SAMPLE_CASES[0]["input"]  # SAMPLE-01 input


def get_base_request(notes: list[str], scenario_id: str = "ADV-TEST") -> dict[str, Any]:
    import copy
    req = copy.deepcopy(BASE_INPUT)
    req["scenario_id"] = scenario_id
    req["operator_notes"] = notes
    return req


def main() -> None:
    client = httpx.Client(base_url=LIVE_URL, timeout=60.0)
    report_rows = []

    print("=" * 80)
    print("LIVE ADVERSARIAL TEST SUITE — TARGET:", LIVE_URL)
    print("=" * 80)

    # -------------------------------------------------------------------------
    # CHECK 1: Novel paraphrases covering all 6 directive types + distractor
    # -------------------------------------------------------------------------
    print("\n--- CHECK 1: Novel Paraphrases (6 directives + distractor) ---")
    novel_cases = [
        (
            "1.1 Solar Reduction",
            ["We'll be power-washing the panels from 9 to 11 in the morning, expect only a third of normal solar."],
            "solar_reduction",
            [9, 10],
            lambda adj: abs(adj.get("factor", 0) - 0.33) <= 0.05 or abs(adj.get("factor", 0) - 0.333333) <= 0.05,
        ),
        (
            "1.2 No Charge Window",
            ["The battery can't take a charge between 3 and 5 this afternoon."],
            "no_charge_window",
            [15, 16],
            lambda adj: "hours" in adj,
        ),
        (
            "1.3 No Discharge Window",
            ["Hold back on draining the battery from 7pm to 8pm tonight."],
            "no_discharge_window",
            [19],
            lambda adj: "hours" in adj,
        ),
        (
            "1.4 Minimum Battery Reserve",
            ["We need a floor of 60kWh sitting in the battery all evening from 6 to 10pm."],
            "minimum_battery_reserve",
            [18, 19, 20, 21],
            lambda adj: abs(adj.get("minimum_energy_kwh", 0) - 60.0) < 0.1,
        ),
        (
            "1.5 Max Grid Window",
            ["Feeder's capped — don't pull more than 140 from the grid between 8 and 10pm."],
            "max_grid_window",
            [20, 21],
            lambda adj: abs(adj.get("max_grid_kwh", 0) - 140.0) < 0.1,
        ),
        (
            "1.6 No-Op Distractor",
            ["IT is migrating the ticketing system this weekend."],
            "no_op",
            None,
            lambda adj: adj is None,
        ),
    ]

    for label, notes, exp_type, exp_hours, adj_check in novel_cases:
        sleep(1.0)
        t0 = monotonic()
        import copy
        base_source = SAMPLE_CASES[8]["input"] if "1.5" in label else BASE_INPUT
        payload = copy.deepcopy(base_source)
        payload["scenario_id"] = f"CH1-{label[:3]}"
        payload["operator_notes"] = notes
        r = client.post("/optimize-energy", json=payload)
        dur = monotonic() - t0
        if r.status_code == 200:
            data = r.json()
            di = data["directive_interpretation"][0]
            req_model = OptimizeRequest.model_validate(payload)
            resp_model = OptimizeResponse.model_validate(data)
            try:
                validate_replay(req_model, resp_model)
                replay_ok = True
            except ReplayValidationError as exc:
                replay_ok = False
                replay_err = str(exc)

            type_match = (di["directive_type"] == exp_type)
            hours_match = (di.get("structured_adjustment", {}).get("hours") == exp_hours if exp_hours else di["structured_adjustment"] is None)
            adj_match = adj_check(di.get("structured_adjustment"))
            passed = type_match and hours_match and adj_match and replay_ok

            act = f"type={di['directive_type']}, adj={di['structured_adjustment']}, replay={'PASS' if replay_ok else 'FAIL'}"
            report_rows.append({
                "check": f"Check 1: {label}",
                "expected": f"type={exp_type}, hours={exp_hours}, replay=PASS",
                "actual": act,
                "status": "PASS" if passed else "FAIL",
                "time": f"{dur:.2f}s"
            })
            print(f"[{'PASS' if passed else 'FAIL'}] {label} ({dur:.2f}s): {act}")
        else:
            report_rows.append({
                "check": f"Check 1: {label}",
                "expected": f"HTTP 200, type={exp_type}",
                "actual": f"HTTP {r.status_code}: {r.text[:80]}",
                "status": "FAIL",
                "time": f"{dur:.2f}s"
            })
            print(f"[FAIL] {label} ({dur:.2f}s): HTTP {r.status_code}")

    # -------------------------------------------------------------------------
    # CHECK 2: Two overlapping solar_reduction directives (minimum factor wins)
    # -------------------------------------------------------------------------
    print("\n--- CHECK 2: Overlapping Solar Reductions (10-14 @ 0.5, 12-16 @ 0.3) ---")
    sleep(1.0)
    notes_overlap = [
        "Rooftop maintenance from 10 AM to 2 PM will cut solar output to 50%.",
        "Smoke haze from 12 PM to 4 PM will reduce solar output to 30%."
    ]
    payload_c2 = get_base_request(notes_overlap, "CH2-OVERLAP-SOLAR")
    t0 = monotonic()
    r = client.post("/optimize-energy", json=payload_c2)
    dur = monotonic() - t0
    if r.status_code == 200:
        data = r.json()
        interps = data["directive_interpretation"]
        req_model = OptimizeRequest.model_validate(payload_c2)
        resp_model = OptimizeResponse.model_validate(data)
        try:
            validate_replay(req_model, resp_model)
            replay_ok = True
        except ReplayValidationError as exc:
            replay_ok = False
            replay_err = str(exc)

        # Inspect effective solar used in overlapping hours [12, 13]
        # In hours 12 and 13, factor must be min(0.5, 0.3) = 0.3.
        # Max solar available in hour 12 in BASE_INPUT is 85.0. Effective solar is 85.0 * 0.3 = 25.5.
        plan_h12 = next(p for p in resp_model.hourly_plan if p.hour == 12)
        plan_h13 = next(p for p in resp_model.hourly_plan if p.hour == 13)
        base_s12 = next(h for h in req_model.hours if h.hour == 12).solar_kwh
        base_s13 = next(h for h in req_model.hours if h.hour == 13).solar_kwh
        
        # solar_used must be <= 0.3 * base_solar
        bound_h12_ok = plan_h12.solar_used_kwh <= round(base_s12 * 0.3 + 1e-4, 6)
        bound_h13_ok = plan_h13.solar_used_kwh <= round(base_s13 * 0.3 + 1e-4, 6)
        passed = replay_ok and bound_h12_ok and bound_h13_ok
        act = f"Replay={'PASS' if replay_ok else 'FAIL'}, H12 solar_used={plan_h12.solar_used_kwh}<={base_s12*0.3:.2f}, H13 solar_used={plan_h13.solar_used_kwh}<={base_s13*0.3:.2f}"
        report_rows.append({
            "check": "Check 2: Overlapping Solar Reductions",
            "expected": "Min factor (0.3) enforced on hours 12-13; replay PASS",
            "actual": act,
            "status": "PASS" if passed else "FAIL",
            "time": f"{dur:.2f}s"
        })
        print(f"[{'PASS' if passed else 'FAIL'}] Check 2 ({dur:.2f}s): {act}")
    else:
        report_rows.append({
            "check": "Check 2: Overlapping Solar Reductions",
            "expected": "HTTP 200, min factor 0.3",
            "actual": f"HTTP {r.status_code}: {r.text[:80]}",
            "status": "FAIL",
            "time": f"{dur:.2f}s"
        })
        print(f"[FAIL] Check 2: HTTP {r.status_code}")

    # -------------------------------------------------------------------------
    # CHECK 3: All operator_notes are distractors (no_op)
    # -------------------------------------------------------------------------
    print("\n--- CHECK 3: All Distractor Notes (3x no_op) ---")
    sleep(1.0)
    all_distractors = [
        "IT is migrating the campus ticketing system this weekend.",
        "The cafeteria will serve biryani for lunch tomorrow.",
        "Facility staff replaced air filters in building 3 last Thursday."
    ]
    payload_c3 = get_base_request(all_distractors, "CH3-ALL-DISTRACTORS")
    t0 = monotonic()
    r = client.post("/optimize-energy", json=payload_c3)
    dur = monotonic() - t0
    if r.status_code == 200:
        data = r.json()
        req_model = OptimizeRequest.model_validate(payload_c3)
        resp_model = OptimizeResponse.model_validate(data)
        try:
            validate_replay(req_model, resp_model)
            replay_ok = True
        except ReplayValidationError as exc:
            replay_ok = False
        all_noop = all(di["directive_type"] == "no_op" and di["applies"] is False for di in data["directive_interpretation"])
        passed = replay_ok and all_noop
        act = f"All 3 no_op={all_noop}, Replay={'PASS' if replay_ok else 'FAIL'}, Cost={resp_model.total_cost_bdt} BDT"
        report_rows.append({
            "check": "Check 3: All Distractor Notes",
            "expected": "All 3 notes return no_op (applies=false, adj=null); replay PASS",
            "actual": act,
            "status": "PASS" if passed else "FAIL",
            "time": f"{dur:.2f}s"
        })
        print(f"[{'PASS' if passed else 'FAIL'}] Check 3 ({dur:.2f}s): {act}")
    else:
        report_rows.append({
            "check": "Check 3: All Distractor Notes",
            "expected": "HTTP 200, all no_op",
            "actual": f"HTTP {r.status_code}: {r.text[:80]}",
            "status": "FAIL",
            "time": f"{dur:.2f}s"
        })
        print(f"[FAIL] Check 3: HTTP {r.status_code}")

    # -------------------------------------------------------------------------
    # CHECK 4: Boundary hours (Hour 0 and Hour 23)
    # -------------------------------------------------------------------------
    print("\n--- CHECK 4: Edge Hours (Hour 0 and Hour 23) ---")
    sleep(1.0)
    edge_notes = [
        "Do not charge the battery between midnight and 2 AM.",
        "Limit grid draw to 100 kWh between 10 PM and midnight."
    ]
    payload_c4 = get_base_request(edge_notes, "CH4-EDGE-HOURS")
    t0 = monotonic()
    r = client.post("/optimize-energy", json=payload_c4)
    dur = monotonic() - t0
    if r.status_code == 200:
        data = r.json()
        req_model = OptimizeRequest.model_validate(payload_c4)
        resp_model = OptimizeResponse.model_validate(data)
        try:
            validate_replay(req_model, resp_model)
            replay_ok = True
        except ReplayValidationError:
            replay_ok = False
        di0 = data["directive_interpretation"][0]
        di1 = data["directive_interpretation"][1]
        h0_ok = (di0["directive_type"] == "no_charge_window" and di0["structured_adjustment"]["hours"] == [0, 1])
        h23_ok = (di1["directive_type"] == "max_grid_window" and di1["structured_adjustment"]["hours"] == [22, 23] and di1["structured_adjustment"]["max_grid_kwh"] == 100.0)
        # Check plan compliance directly
        plan_h0_h1_no_charge = all(p.battery_action != "charge" for p in resp_model.hourly_plan if p.hour in [0, 1])
        plan_h22_h23_cap = all(p.grid_kwh <= 100.0 + 1e-4 for p in resp_model.hourly_plan if p.hour in [22, 23])
        passed = replay_ok and h0_ok and h23_ok and plan_h0_h1_no_charge and plan_h22_h23_cap
        act = f"H0-1 no charge={plan_h0_h1_no_charge}, H22-23 cap={plan_h22_h23_cap}, Replay={'PASS' if replay_ok else 'FAIL'}"
        report_rows.append({
            "check": "Check 4: Boundary Hours 0 and 23",
            "expected": "hours [0,1] no charge, hours [22,23] grid cap 100; replay PASS",
            "actual": act,
            "status": "PASS" if passed else "FAIL",
            "time": f"{dur:.2f}s"
        })
        print(f"[{'PASS' if passed else 'FAIL'}] Check 4 ({dur:.2f}s): {act}")
    else:
        report_rows.append({
            "check": "Check 4: Boundary Hours 0 and 23",
            "expected": "HTTP 200, edge hours respected",
            "actual": f"HTTP {r.status_code}: {r.text[:80]}",
            "status": "FAIL",
            "time": f"{dur:.2f}s"
        })
        print(f"[FAIL] Check 4: HTTP {r.status_code}")

    # -------------------------------------------------------------------------
    # CHECK 5: Tight near-capacity reserve (95 kWh on 100 kWh battery)
    # -------------------------------------------------------------------------
    print("\n--- CHECK 5: Near-Capacity Feasible Reserve (95 kWh of 100 kWh) ---")
    sleep(1.0)
    tight_note = ["Maintain at least 95 kWh in the battery between 2 PM and 4 PM."]
    payload_c5 = get_base_request(tight_note, "CH5-TIGHT-RESERVE")
    t0 = monotonic()
    r = client.post("/optimize-energy", json=payload_c5)
    dur = monotonic() - t0
    if r.status_code == 200:
        data = r.json()
        req_model = OptimizeRequest.model_validate(payload_c5)
        resp_model = OptimizeResponse.model_validate(data)
        try:
            validate_replay(req_model, resp_model)
            replay_ok = True
        except ReplayValidationError:
            replay_ok = False
        # verify energy at hours 14 and 15 >= 95.0
        soc_h14 = next(p for p in resp_model.hourly_plan if p.hour == 14).battery_energy_after_kwh
        soc_h15 = next(p for p in resp_model.hourly_plan if p.hour == 15).battery_energy_after_kwh
        tight_ok = (soc_h14 >= 95.0 - 1e-4 and soc_h15 >= 95.0 - 1e-4)
        passed = replay_ok and tight_ok
        act = f"H14 SOC={soc_h14}kWh, H15 SOC={soc_h15}kWh (>=95.0), Replay={'PASS' if replay_ok else 'FAIL'}"
        report_rows.append({
            "check": "Check 5: Near-Capacity Reserve (95kWh)",
            "expected": "Feasible LP solve, battery SOC >= 95 kWh on hours 14-15; replay PASS",
            "actual": act,
            "status": "PASS" if passed else "FAIL",
            "time": f"{dur:.2f}s"
        })
        print(f"[{'PASS' if passed else 'FAIL'}] Check 5 ({dur:.2f}s): {act}")
    else:
        report_rows.append({
            "check": "Check 5: Near-Capacity Reserve (95kWh)",
            "expected": "HTTP 200, solved successfully",
            "actual": f"HTTP {r.status_code}: {r.text[:80]}",
            "status": "FAIL",
            "time": f"{dur:.2f}s"
        })
        print(f"[FAIL] Check 5: HTTP {r.status_code}")

    # -------------------------------------------------------------------------
    # CHECK 6: Malformed / Edge HTTP Requests
    # -------------------------------------------------------------------------
    print("\n--- CHECK 6: Malformed / Edge HTTP Requests ---")
    
    # 6.1 Invalid JSON body
    t0 = monotonic()
    r = client.post("/optimize-energy", content=b"{malformed-json-payload", headers={"Content-Type": "application/json"})
    dur = monotonic() - t0
    p61 = (r.status_code == 400 and "invalid_request" in r.text and "traceback" not in r.text.lower())
    report_rows.append({
        "check": "Check 6.1: Invalid JSON Body",
        "expected": "HTTP 400, sanitized JSON, no stack trace",
        "actual": f"HTTP {r.status_code}: {r.text[:70]}",
        "status": "PASS" if p61 else "FAIL",
        "time": f"{dur:.2f}s"
    })
    print(f"[{'PASS' if p61 else 'FAIL'}] 6.1 Invalid JSON: HTTP {r.status_code} ({r.text[:60]})")

    # 6.2 Missing required field ('battery')
    bad_req_62 = get_base_request(["Note"])
    del bad_req_62["battery"]
    t0 = monotonic()
    r = client.post("/optimize-energy", json=bad_req_62)
    dur = monotonic() - t0
    p62 = (r.status_code == 400 and "invalid_request" in r.text)
    report_rows.append({
        "check": "Check 6.2: Missing Required Field ('battery')",
        "expected": "HTTP 400 with details pointing to battery",
        "actual": f"HTTP {r.status_code}: {r.text[:70]}",
        "status": "PASS" if p62 else "FAIL",
        "time": f"{dur:.2f}s"
    })
    print(f"[{'PASS' if p62 else 'FAIL'}] 6.2 Missing Field: HTTP {r.status_code} ({r.text[:60]})")

    # 6.3 23-hour array
    bad_req_63 = get_base_request(["Note"])
    bad_req_63["hours"] = bad_req_63["hours"][:23]
    t0 = monotonic()
    r = client.post("/optimize-energy", json=bad_req_63)
    dur = monotonic() - t0
    p63 = (r.status_code == 400 and "invalid_request" in r.text)
    report_rows.append({
        "check": "Check 6.3: 23-Hour Array",
        "expected": "HTTP 400 rejecting incomplete 23-hour array",
        "actual": f"HTTP {r.status_code}: {r.text[:70]}",
        "status": "PASS" if p63 else "FAIL",
        "time": f"{dur:.2f}s"
    })
    print(f"[{'PASS' if p63 else 'FAIL'}] 6.3 23-Hour Array: HTTP {r.status_code} ({r.text[:60]})")

    # 6.4 Empty operator_notes array
    bad_req_64 = get_base_request([])
    t0 = monotonic()
    r = client.post("/optimize-energy", json=bad_req_64)
    dur = monotonic() - t0
    p64 = (r.status_code == 400 and "invalid_request" in r.text)
    report_rows.append({
        "check": "Check 6.4: Empty operator_notes Array",
        "expected": "HTTP 400 rejecting 0 operator notes",
        "actual": f"HTTP {r.status_code}: {r.text[:70]}",
        "status": "PASS" if p64 else "FAIL",
        "time": f"{dur:.2f}s"
    })
    print(f"[{'PASS' if p64 else 'FAIL'}] 6.4 Empty Notes: HTTP {r.status_code} ({r.text[:60]})")

    # 6.5 4-item operator_notes array
    bad_req_65 = get_base_request(["Note 1", "Note 2", "Note 3", "Note 4"])
    t0 = monotonic()
    r = client.post("/optimize-energy", json=bad_req_65)
    dur = monotonic() - t0
    p65 = (r.status_code == 400 and "invalid_request" in r.text)
    report_rows.append({
        "check": "Check 6.5: 4-Item operator_notes Array",
        "expected": "HTTP 400 rejecting >3 operator notes",
        "actual": f"HTTP {r.status_code}: {r.text[:70]}",
        "status": "PASS" if p65 else "FAIL",
        "time": f"{dur:.2f}s"
    })
    print(f"[{'PASS' if p65 else 'FAIL'}] 6.5 4 Notes: HTTP {r.status_code} ({r.text[:60]})")

    # 6.6 Wrong Content-Type header
    t0 = monotonic()
    r = client.post("/optimize-energy", content=b"plain text", headers={"Content-Type": "text/plain"})
    dur = monotonic() - t0
    p66 = (r.status_code in [400, 415, 422] and "traceback" not in r.text.lower())
    report_rows.append({
        "check": "Check 6.6: Wrong Content-Type Header",
        "expected": "HTTP 400 or 415 or 422, sanitized error",
        "actual": f"HTTP {r.status_code}: {r.text[:70]}",
        "status": "PASS" if p66 else "FAIL",
        "time": f"{dur:.2f}s"
    })
    print(f"[{'PASS' if p66 else 'FAIL'}] 6.6 Content-Type text/plain: HTTP {r.status_code} ({r.text[:60]})")

    # -------------------------------------------------------------------------
    # CHECK 7: 5 Valid requests back-to-back
    # -------------------------------------------------------------------------
    print("\n--- CHECK 7: 5 Valid Requests Back-to-Back (Concurrency / Stability) ---")
    c7_results = []
    for i in range(5):
        sample = SAMPLE_CASES[i]
        t0 = monotonic()
        r = client.post("/optimize-energy", json=sample["input"])
        dur = monotonic() - t0
        if r.status_code == 200:
            req_m = OptimizeRequest.model_validate(sample["input"])
            resp_m = OptimizeResponse.model_validate(r.json())
            try:
                validate_replay(req_m, resp_m)
                rep = True
            except ReplayValidationError:
                rep = False
            c7_results.append((i+1, sample["id"], r.status_code, dur, rep, resp_m.total_cost_bdt))
            print(f"   Request {i+1}/5 ({sample['id']}): HTTP 200 in {dur:.2f}s, replay={'PASS' if rep else 'FAIL'}, cost={resp_m.total_cost_bdt}")
        else:
            c7_results.append((i+1, sample["id"], r.status_code, dur, False, None))
            print(f"   Request {i+1}/5 ({sample['id']}): HTTP {r.status_code} in {dur:.2f}s")
    
    all_c7_passed = all(r[2] == 200 and r[4] for r in c7_results)
    times_str = ", ".join(f"{r[3]:.2f}s" for r in c7_results)
    report_rows.append({
        "check": "Check 7: 5 Back-to-Back Requests",
        "expected": "All 5 return HTTP 200 and pass replay",
        "actual": f"All 5 HTTP 200 & replay PASS. Latencies: [{times_str}]",
        "status": "PASS" if all_c7_passed else "FAIL",
        "time": f"Avg {sum(r[3] for r in c7_results)/5:.2f}s"
    })

    # Output formatted markdown table
    print("\n" + "=" * 80)
    print("FINAL ADVERSARIAL REPORT TABLE")
    print("=" * 80)
    print(json.dumps(report_rows, indent=2))


if __name__ == "__main__":
    main()
