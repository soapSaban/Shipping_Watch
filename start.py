"""
Unified Single-Command Launcher for Shipping Watch
Executes:
1. Core Analytics & Hybrid RAG Pipeline -> generates output/sample_output_format.csv & token_cost_log.json
2. Evaluation Harness -> validates ground truth sample rows and anti-hallucination guardrails
3. 3-Run Reproducibility Suite -> asserts 100% deterministic output across 3 untouched runs
4. Flask Web Application & Interactive Q&A Assistant -> boots local server and opens browser
"""

import os
import sys
import time
import webbrowser
import threading

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_pipeline import run_pipeline
from eval.eval_harness import run_evaluation_harness
from eval.test_reproduce import verify_reproducibility
from app import app


def open_browser(url: str, delay_seconds: float = 1.2):
    """Opens browser after server starts."""
    time.sleep(delay_seconds)
    print(f"\n--> Opening web dashboard at {url} in your default browser...\n")
    webbrowser.open(url)


def main():
    print("=" * 75)
    print(" 🚀 SHIPPING WATCH: UNIFIED 1-COMMAND EXECUTION")
    print("=" * 75)

    # Step 1: Run Full Analytics & RAG Pipeline
    print("\n[PHASE 1/4] Running Core Analytics & RAG Pipeline...")
    records_file = "data/shipment_records.csv" if os.path.exists("data/shipment_records.csv") else "shipment_records.csv"
    notes_file = "data/context_notes.csv" if os.path.exists("data/context_notes.csv") else "context_notes.csv"
    output_file = "output/sample_output_format.csv"
    cost_log_file = "output/token_cost_log.json"

    run_pipeline(
        records_path=records_file,
        notes_path=notes_file,
        output_path=output_file,
        cost_log_path=cost_log_file
    )

    # Step 2: Evaluation Harness (Ground Truth & Guardrails)
    print("\n[PHASE 2/4] Validating Ground Truth & Anti-Hallucination Guardrails...")
    harness_passed = run_evaluation_harness(
        records_path=records_file,
        notes_path=notes_file
    )
    if not harness_passed:
        print("⚠️ Warning: Some evaluation tests did not pass.")

    # Step 3: 3-Run Reproducibility Verification
    print("\n[PHASE 3/4] Verifying 3-Run Deterministic Reproducibility...")
    reproduce_passed = verify_reproducibility(
        input_path=records_file,
        notes_path=notes_file
    )
    if not reproduce_passed:
        print("⚠️ Warning: Reproducibility verification differed.")

    # Step 4: Boot Flask Dashboard & Open Browser
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "127.0.0.1")
    url = f"http://{host}:{port}"

    print("\n" + "=" * 75)
    print(f" [PHASE 4/4] Starting Web Dashboard & Interactive Assistant on {url}")
    print("=" * 75)

    # Spawn thread to open browser automatically
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()

    # Start Flask server
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
