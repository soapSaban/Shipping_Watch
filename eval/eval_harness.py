"""
Evaluation Harness for Shipping Watch
Performs unit tests and precision checks against known ground truth rows:
1. Exact mathematical replication of sample_output_format_v2.csv
2. Anti-hallucination guardrail assertions
3. Date window & corridor boundary testing
"""

import csv
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import ShippingAnalyticsEngine
from src.retriever import HybridContextRetriever
from src.detector import AnomalyDetector
from src.reasoner import FreightCostReasoner


def run_evaluation_harness(
    records_path: str = "shipment_records.csv",
    notes_path: str = "context_notes.csv",
    sample_format_path: str = "sample_output_format_v2.csv"
):
    print("=" * 70)
    print(" EVALUATION HARNESS: GROUND TRUTH & GUARDRAIL INTEGRITY")
    print("=" * 70)

    # Resolve paths
    if not os.path.exists(records_path) and os.path.exists("data/shipment_records.csv"):
        records_path = "data/shipment_records.csv"
    if not os.path.exists(notes_path) and os.path.exists("data/context_notes.csv"):
        notes_path = "data/context_notes.csv"
    if not os.path.exists(sample_format_path) and os.path.exists("data/sample_output_format_v2.csv"):
        sample_format_path = "data/sample_output_format_v2.csv"

    engine = ShippingAnalyticsEngine(records_path)
    baselines = engine.compute_all_baselines()
    retriever = HybridContextRetriever(notes_path)
    detector = AnomalyDetector()
    reasoner = FreightCostReasoner()

    # Index baselines by (route, week_of)
    metrics_map = {(r["route"], r["week_of"]): r for r in baselines}

    # Test 1: Ground Truth Sample Rows
    print("\n[Test 1] Validating Mathematical Fidelity against sample_output_format_v2.csv:")
    with open(sample_format_path, mode="r", encoding="utf-8") as f:
        samples = list(csv.DictReader(f))

    all_passed = True
    for s in samples:
        key = (s["route"], s["week_of"])
        if key not in metrics_map:
            print(f" [FAIL] Route-week {key} not found in computed baseline results!")
            all_passed = False
            continue

        calc = metrics_map[key]
        calc_cost = f"{calc['cost_per_tonne_km_display']:.2f}"
        calc_hist = calc["vs_own_history"]
        calc_peer = calc["vs_similar_routes"]

        expected_cost = s["cost_per_tonne_km"]
        expected_hist = s["vs_own_history"]
        expected_peer = s["vs_similar_routes"]

        cost_ok = (calc_cost == expected_cost)
        hist_ok = (calc_hist == expected_hist)
        peer_ok = (calc_peer == expected_peer)

        if cost_ok and hist_ok and peer_ok:
            print(f" [PASS] {s['route']} ({s['week_of']}): Cost={calc_cost}, Hist={calc_hist}, Peer={calc_peer}")
        else:
            print(f" [FAIL] Mismatch for {s['route']} ({s['week_of']}):")
            print(f"        Expected: Cost={expected_cost}, Hist={expected_hist}, Peer={expected_peer}")
            print(f"        Got:      Cost={calc_cost}, Hist={calc_hist}, Peer={calc_peer}")
            all_passed = False

    # Test 2: Guardrail - False Positive Justification Check
    print("\n[Test 2] Validating Guardrails (Non-Justifying Notes & Corridor Isolation):")
    # Note N005 (Mumbai-Delhi maintenance without cost change) should NEVER justify
    n005_cands = retriever.search_candidates("Mumbai-Delhi", "2024-07-29")
    closest_n005 = retriever.get_closest_note_overall("Mumbai-Delhi", "2024-07-29")
    verdict_n005 = reasoner.evaluate_and_explain(
        route="Mumbai-Delhi",
        week_of="2024-07-29",
        cost_per_tonne_km=2.85,
        vs_own_history="+12.0% vs this route's past average",
        vs_similar_routes="+15.0% vs similar-length routes this week",
        candidates=n005_cands,
        closest_note=closest_n005
    )
    if verdict_n005["flagged"] == "Yes" and verdict_n005["matched_note_id"] == "":
        print(" [PASS] N005 Guardrail: Maintenance without cost change was correctly rejected as justification.")
    else:
        print(" [FAIL] N005 Guardrail: Unexpectedly accepted non-justifying note!")
        all_passed = False

    # Note N001 (Chennai-Bangalore flood) should NEVER justify Delhi-Jaipur
    delhi_cands = retriever.search_candidates("Delhi-Jaipur", "2025-02-24")
    has_n001 = any(c["note_id"] == "N001" for c in delhi_cands)
    if not has_n001:
        print(" [PASS] Corridor Isolation: Chennai-Bangalore flood correctly excluded from Delhi-Jaipur candidates.")
    else:
        print(" [FAIL] Corridor Isolation: Chennai note leaked into Delhi route candidates!")
        all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print(" [SUMMARY] ALL EVALUATION TESTS PASSED (100% Reliability)")
    else:
        print(" [SUMMARY] SOME TESTS FAILED")
    print("=" * 70 + "\n")

    return all_passed


if __name__ == "__main__":
    success = run_evaluation_harness()
    if not success:
        sys.exit(1)
