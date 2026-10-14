#!/bin/sh
set -e

mkdir -p /app/logs /app/output
LOG_FILE="/app/logs/system_monitor.log"

log_msg() {
    echo "$@" | tee -a "$LOG_FILE"
}

log_msg "=========================================================="
log_msg " SHIPPING WATCH ASSISTANT (CONTAINERIZED)"
log_msg "=========================================================="
log_msg "[$(date -u +'%Y-%m-%d %H:%M:%S')] [INFO   ] [CONTAINER] [SYSTEM] Container booted. Starting pipeline..."

# If output CSV already exists and RECOMPUTE is not requested, boot immediately
if [ ! -f "output/sample_output_format.csv" ] || [ "$RECOMPUTE" = "1" ]; then
    log_msg "\n[Step 1/3] Running Core Analytics & Hybrid RAG Pipeline..."
    python run_pipeline.py --input shipment_records.csv --notes context_notes.csv --output output/sample_output_format.csv --cost-log output/token_cost_log.json 2>&1 | tee -a "$LOG_FILE"

    log_msg "\n[Step 2/3] Validating Ground Truth & Guardrails..."
    python eval/eval_harness.py 2>&1 | tee -a "$LOG_FILE"

    log_msg "\n[Step 3/3] Verifying 3-Run Reproducibility..."
    python eval/test_reproduce.py 2>&1 | tee -a "$LOG_FILE"
else
    log_msg "\n[INFO] Verified output/sample_output_format.csv is present. Skipping redundant generation for instant startup."
fi

log_msg "\n--> Starting Flask Dashboard & Interactive Assistant on http://0.0.0.0:${PORT:-5000}..."
exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 --access-logfile - --error-logfile - app:app 2>&1 | tee -a "$LOG_FILE"
