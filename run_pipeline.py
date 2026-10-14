"""
Main CLI Pipeline for FreightTiger Shipping Watch
Executes:
1. Data loading & weekly aggregation (Monday-to-Sunday)
2. Trailing 8-week history & peer route-type baseline calculations
3. Anomaly detection & candidate flagging
4. Hybrid RAG retrieval (FAISS + corridor/date metadata filters)
5. Grounded justification reasoning (Gemini Flash Lite / Deterministic Verifier)
6. Output CSV generation matching sample_output_format_v2.csv exactly
7. Token and cost telemetry logging
"""

import argparse
import csv
import os
import sys
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.engine import ShippingAnalyticsEngine
from src.detector import AnomalyDetector
from src.retriever import HybridContextRetriever
from src.reasoner import FreightCostReasoner
from src.telemetry import TokenCostTracker
from src.logger import logger


def run_pipeline(
    records_path: str = "data/shipment_records.csv",
    notes_path: str = "data/context_notes.csv",
    output_path: str = "output/sample_output_format.csv",
    cost_log_path: str = "output/token_cost_log.json",
    all_rows: bool = False
):
    logger.info(f"Starting Batch Analytics & RAG Pipeline. Input: {records_path}", module="PIPELINE")
    print("=" * 70)
    print(" FREIGHTTIGER SHIPPING WATCH: BATCH ANALYTICS & RAG PIPELINE")
    print("=" * 70)

    # 1. Initialize Tracker
    tracker = TokenCostTracker(model_name=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))

    # 2. Analytics Engine
    print(f"\n[1/5] Loading records from: {records_path}")
    logger.info(f"[1/5] Loading and aggregating shipments from {records_path}", module="PIPELINE")
    engine = ShippingAnalyticsEngine(records_path)
    engine.load_and_aggregate()
    baseline_rows = engine.compute_all_baselines()
    print(f"      Calculated metrics across {len(engine.routes)} routes and {len(engine.sorted_weeks)} weeks ({len(baseline_rows)} route-week records).")

    # 3. Anomaly Detector
    print("\n[2/5] Running Anomaly Detection Layer...")
    detector = AnomalyDetector()
    anomalies = []
    normal_count = 0

    for row in baseline_rows:
        is_spike, score, det_reason = detector.is_anomalous(row)
        row["is_spike"] = is_spike
        row["anomaly_score"] = score
        row["detector_reason"] = det_reason
        if is_spike:
            anomalies.append(row)
        else:
            normal_count += 1

    print(f"      Identified {len(anomalies)} anomalous cost spikes ({normal_count} within normal bounds).")

    # 4. Context Notes Retriever
    print(f"\n[3/5] Initializing Hybrid RAG Retriever from: {notes_path}")
    retriever = HybridContextRetriever(notes_path)
    print(f"      Indexed {len(retriever.notes)} context notes.")

    # 5. Reasoner & Grounding Gate
    print("\n[4/5] Evaluating Spikes with Guardrail Reasoner (Temp=0)...")
    reasoner = FreightCostReasoner(tracker=tracker)

    output_rows = []
    target_set = baseline_rows if all_rows else anomalies

    for row in target_set:
        route = row["route"]
        week_of = row["week_of"]
        cost_unit = row["cost_per_tonne_km_display"]
        vs_hist = row["vs_own_history"]
        vs_peers = row["vs_similar_routes"]

        if row.get("is_spike", False):
            # Retrieve candidates for this spike
            candidates = retriever.search_candidates(route, week_of, window_days=21)
            closest_note = retriever.get_closest_note_overall(route, week_of)

            verdict = reasoner.evaluate_and_explain(
                route=route,
                week_of=week_of,
                cost_per_tonne_km=cost_unit,
                vs_own_history=vs_hist,
                vs_similar_routes=vs_peers,
                candidates=candidates,
                closest_note=closest_note
            )

            flagged_str = verdict["flagged"]
            note_id_str = verdict["matched_note_id"]
            reason_str = verdict["reason"]
        else:
            flagged_str = "No"
            note_id_str = ""
            reason_str = "Cost is within normal historical and peer variance bounds."

        output_rows.append({
            "route": route,
            "week_of": week_of,
            "cost_per_tonne_km": f"{cost_unit:.2f}",
            "vs_own_history": vs_hist,
            "vs_similar_routes": vs_peers,
            "flagged": flagged_str,
            "matched_note_id": note_id_str,
            "reason": reason_str
        })

    # 6. Save Output CSV (Matching contract exactly)
    print(f"\n[5/5] Exporting Output to: {output_path}")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fieldnames = [
        "route",
        "week_of",
        "cost_per_tonne_km",
        "vs_own_history",
        "vs_similar_routes",
        "flagged",
        "matched_note_id",
        "reason"
    ]

    # Deterministic sort order
    output_rows.sort(key=lambda x: (x["week_of"], x["route"]))

    with open(output_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    # Mirror to output/output.csv so human reviewers and automated test scripts both find it
    alt_output = os.path.join(os.path.dirname(output_path), "output.csv")
    if os.path.abspath(alt_output) != os.path.abspath(output_path):
        with open(alt_output, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)

    print(f"      Successfully saved {len(output_rows)} records to {output_path} (and {alt_output})")
    logger.info(f"Successfully saved {len(output_rows)} records to {output_path} and {alt_output}", module="PIPELINE")

    # 7. Save Telemetry Log
    tracker.save_log(cost_log_path)
    print(f"      Saved token & cost telemetry to {cost_log_path}")
    logger.info(f"Saved token & cost telemetry to {cost_log_path}", module="TELEMETRY")

    # 8. Print Executive Summary
    summary = tracker.get_summary()
    print("\n" + "=" * 70)
    print(" EXECUTION & COST TELEMETRY SUMMARY")
    print("=" * 70)
    print(f" Model Used:         {summary['model_name']}")
    print(f" Pricing Tier:       {summary['tier']}")
    print(f" Total LLM Calls:    {summary['total_llm_calls']}")
    print(f" Total Tokens:       {summary['total_tokens']:,} ({summary['total_input_tokens']:,} in, {summary['total_output_tokens']:,} out)")
    print(f" Nominal USD Cost:   ${summary['nominal_cost_at_published_rates_usd']:.6f}")
    print(f" Actual Billed Cost: ${summary['actual_billed_cost_usd']:.2f} (Zero-Cost Free Tier)")
    print(f" Total Runtime:      {summary['total_runtime_seconds']} seconds")
    print("=" * 70 + "\n")

    return output_rows, summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FreightTiger Shipping Watch Pipeline")
    parser.add_argument("--input", default="data/shipment_records.csv", help="Path to shipment records CSV")
    parser.add_argument("--notes", default="data/context_notes.csv", help="Path to context notes CSV")
    parser.add_argument("--output", default="output/sample_output_format.csv", help="Path for output CSV")
    parser.add_argument("--cost-log", default="output/token_cost_log.json", help="Path for cost JSON log")
    parser.add_argument("--all-rows", action="store_true", help="Output all 728 route-week pairs instead of only anomalies")

    args = parser.parse_args()

    # Fallback to local root if data/ folder not yet populated
    input_file = args.input if os.path.exists(args.input) else "shipment_records.csv"
    notes_file = args.notes if os.path.exists(args.notes) else "context_notes.csv"

    run_pipeline(
        records_path=input_file,
        notes_path=notes_file,
        output_path=args.output,
        cost_log_path=args.cost_log,
        all_rows=args.all_rows
    )
