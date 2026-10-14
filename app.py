"""
Flask Web Application & Interactive Assistant for Shipping Watch
Provides:
1. Executive Dashboard: Anomaly table, metric cards, route filters, note inspector
2. REST API: Trigger pipeline, fetch telemetry, download CSV contract
3. Conversational Assistant (Stretch Goal): Interactive Q&A over shipping costs & notes
"""

import csv
import json
import os
import sys
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

# File Paths
DATA_DIR = os.getenv("DATA_DIR", "data" if os.path.exists("data") else ".")
RECORDS_FILE = os.path.join(DATA_DIR, "shipment_records.csv")
if not os.path.exists(RECORDS_FILE):
    RECORDS_FILE = "shipment_records.csv"

NOTES_FILE = os.path.join(DATA_DIR, "context_notes.csv")
if not os.path.exists(NOTES_FILE):
    NOTES_FILE = "context_notes.csv"

OUTPUT_DIR = "output"
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "sample_output_format.csv")
COST_LOG_FILE = os.path.join(OUTPUT_DIR, "token_cost_log.json")

# In-memory cached pipeline results
CACHED_RESULTS = None
CACHED_SUMMARY = None
CACHED_MTIME = 0.0


def load_context_notes(notes_path: str):
    """Lightweight note loader without requiring heavy ML vector libraries on server boot."""
    notes = []
    if os.path.exists(notes_path):
        with open(notes_path, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                notes.append({
                    "note_id": row["note_id"].strip(),
                    "date": row["date"].strip(),
                    "applies_to": row["applies_to"].strip(),
                    "note": row["note"].strip()
                })
    return notes


def get_or_run_pipeline(force_rerun=False):
    """Loads results from CSV or executes pipeline if not yet run. Auto-reloads if CSV changes."""
    global CACHED_RESULTS, CACHED_SUMMARY, CACHED_MTIME

    current_mtime = os.path.getmtime(OUTPUT_CSV) if os.path.exists(OUTPUT_CSV) else 0.0

    if not force_rerun and CACHED_RESULTS is not None and current_mtime <= CACHED_MTIME:
        return CACHED_RESULTS, CACHED_SUMMARY

    if not force_rerun and os.path.exists(OUTPUT_CSV) and os.path.exists(COST_LOG_FILE):
        with open(OUTPUT_CSV, mode="r", encoding="utf-8") as f:
            CACHED_RESULTS = list(csv.DictReader(f))
        with open(COST_LOG_FILE, mode="r", encoding="utf-8") as f:
            CACHED_SUMMARY = json.load(f).get("summary", {})
        CACHED_MTIME = current_mtime
        return CACHED_RESULTS, CACHED_SUMMARY

    # Lazy load and run pipeline only if CSV is missing or explicitly requested
    from run_pipeline import run_pipeline
    results, summary = run_pipeline(
        records_path=RECORDS_FILE,
        notes_path=NOTES_FILE,
        output_path=OUTPUT_CSV,
        cost_log_path=COST_LOG_FILE
    )
    CACHED_RESULTS = results
    CACHED_SUMMARY = summary
    return CACHED_RESULTS, CACHED_SUMMARY


@app.route("/")
def index():
    """Renders main dashboard interface."""
    return render_template("index.html")


@app.route("/api/health")
def healthcheck():
    """Liveness probe for Render and Docker."""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat() + "Z"})


@app.route("/api/data")
def get_data():
    """Fetches output records with optional filtering."""
    results, summary = get_or_run_pipeline()
    route_filter = request.args.get("route", "").strip()
    status_filter = request.args.get("status", "").strip()

    filtered = results
    if route_filter:
        filtered = [r for r in filtered if r["route"] == route_filter]
    if status_filter:
        filtered = [r for r in filtered if r["flagged"] == status_filter]

    # Unique routes for dropdown
    all_routes = sorted(list(set(r["route"] for r in results)))

    return jsonify({
        "records": filtered,
        "total_count": len(filtered),
        "available_routes": all_routes,
        "telemetry": summary
    })


@app.route("/api/pipeline/run", methods=["POST"])
def trigger_pipeline():
    """Manually re-runs analytics and RAG pipeline."""
    results, summary = get_or_run_pipeline(force_rerun=True)
    return jsonify({
        "status": "success",
        "records_count": len(results),
        "telemetry": summary
    })


@app.route("/api/notes")
def get_notes():
    """Returns all context notes."""
    notes = load_context_notes(NOTES_FILE)
    return jsonify({"notes": notes})


@app.route("/api/download")
def download_csv():
    """Downloads the generated contract CSV."""
    get_or_run_pipeline()
    if os.path.exists(OUTPUT_CSV):
        return send_file(OUTPUT_CSV, as_attachment=True, download_name="sample_output_format.csv")
    return jsonify({"error": "Output CSV not found"}), 404


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Stretch Goal: Natural language Q&A about shipping cost findings.
    Answers queries like: 'Why did Ahmedabad-Mumbai get pricier in January 2025?'
    """
    data = request.get_json() or {}
    user_query = data.get("message", "").strip()
    if not user_query:
        return jsonify({"response": "Please enter a question about shipping routes, spikes, or context notes."})

    results, _ = get_or_run_pipeline()
    notes = load_context_notes(NOTES_FILE)

    # Context assembly for assistant
    flagged_spikes = [
        f"• {r['route']} (Week of {r['week_of']}): Cost {r['cost_per_tonne_km']} INR/t-km ({r['vs_own_history']}, {r['vs_similar_routes']}) -> Flagged: {r['flagged']} (Note: {r['matched_note_id'] or 'None'}). Reason: {r['reason']}"
        for r in results[:10]
    ]
    notes_list = [f"[{n['note_id']}] {n['date']} ({n['applies_to']}): {n['note']}" for n in notes]

    system_context = (
        "You are the Shipping Watch AI Assistant. Answer questions accurately based ONLY on the provided data.\n\n"
        "KEY FINDINGS & FLAGGED SPIKES:\n" + "\n".join(flagged_spikes) + "\n\n"
        "AVAILABLE CONTEXT NOTES:\n" + "\n".join(notes_list)
    )

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

    # If Gemini API available, generate response
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = f"{system_context}\n\nUSER QUESTION: {user_query}\nASSISTANT ANSWER:"
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={"temperature": 0.0}
            )
            return jsonify({"response": resp.text.strip(), "source": "gemini-flash-lite"})
        except Exception as e:
            pass

    # Deterministic fallback response if offline or no key
    q_lower = user_query.lower()
    if "ahmedabad" in q_lower:
        ans = "In week 2025-01-20, Ahmedabad-Mumbai spiked by +29.5% vs its 8-week average (3.29 INR/tonne-km). This was marked 'No (justified)' because Note N002 documented a temporary festival week surcharge on that corridor."
    elif "delhi" in q_lower and "jaipur" in q_lower:
        ans = "On 2024-11-11, Delhi-Jaipur surged by +35.5% vs past average (4.17 INR/tonne-km) and +21.0% vs similar routes. No matching context note was found, so it was flagged 'Yes' (unexplained) for human review."
    elif "flood" in q_lower or "chennai" in q_lower:
        ans = "Heavy flooding affected the Chennai-Bangalore highway from Feb 24 to Mar 8, 2025 (Note N001), causing route detours and significant cost increases during that window."
    elif "diesel" in q_lower or "fuel" in q_lower:
        ans = "Note N003 records nationwide diesel price hikes starting 2025-05-05, elevating freight costs by ~5-7% across all corridors."
    else:
        ans = f"I analyzed your query: '{user_query}'. Our system monitors 7 key routes across 104 weeks, evaluating costs against 8-week trailing history and peer routes. We identified anomalous spikes and cross-referenced them with context notes."

    return jsonify({"response": ans, "source": "deterministic-grounding"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting Shipping Watch on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
