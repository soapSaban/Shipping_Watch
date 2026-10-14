# Shipping Watch: Smart Cost Anomaly & RAG Assistant

> **24-Hour AI Challenge Submission**  
> **Role:** Software Engineering Intern (AI) — Case Study Round  
> **Live Cloud Dashboard:** [https://shipping-watch.onrender.com](https://shipping-watch.onrender.com)  
> **Local Web Dashboard:** [http://localhost:5000](http://localhost:5000)  
> **One-Line Command to Run:** `docker compose up --build` *(or `python start.py` locally)*

---

## Quick Start: Run Everything in One Command

To build the environment, execute the batch analytics pipeline, verify 3-run reproducibility, generate the output CSV, and boot the web dashboard:

```bash
docker compose up --build
```

*Then open **[http://localhost:5000](http://localhost:5000)** in your browser.*

> **Alternative (Local Python without Docker):**  
> Run `python start.py` (or double-click [`run.bat`](file:///c:/Users/TANMAY/OneDrive/Desktop/Shipping_Watch/run.bat) on Windows). It runs the pipeline, verifies ground truth, tests reproducibility, and opens your browser automatically.

> **Full Dataset Coverage:**  
> The pipeline ingests all **2,940 shipment records** across 2024–2025 and computes rolling baselines over **728 route-week periods** (7 corridors × 104 weeks). By default, `output/sample_output_format.csv` exports the **20 candidate anomaly spikes** requiring plain-English AI explanations (matching the sample output contract). To export all 728 route-week pairs (including unflagged baseline weeks where `flagged = "No"`), simply run: `python run_pipeline.py --all-rows`.

---

## 1. How It Works

The assistant monitors shipping costs week-by-week, identifies unjustified price creep across transport corridors, and explains why in plain English backed by grounded context notes.

```
+-----------------------------------------------------------------------------------+
| 1. Ingestion & Core Analytics (src/engine.py)                                     |
|    • Groups shipments by route (origin-destination) and route_type (Short/Med/Long)|
|    • Aligns shipment_date to Monday–Sunday weeks (week_of = Monday date)           |
|    • Calculates unit cost: cost_per_tonne_km = sum(freight) / sum(tonnes * km)     |
|    • Computes vs_own_history: strictly prior 8-week trailing rolling average      |
|    • Computes vs_similar_routes: leave-one-out peer average for same route_type   |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 2. Anomaly Detection Gate (src/detector.py)                                       |
|    • Identifies cost spikes: vs_own_history >= 15% OR vs_peers >= 20%             |
|    • Gating mechanism filters 728 route-week pairs down to ~20 candidate anomalies |
|    • Saves >97% of unnecessary LLM calls and avoids rate limits                   |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 3. Hybrid RAG Retrieval (src/retriever.py)                                        |
|    • Corridor Pre-Filter: Matches route or "All Routes"                           |
|    • Temporal Proximity Gate: Limits window to +/- 35 days (avoids future notes)  |
|    • Dense Semantic Search: 384-dim embeddings (all-MiniLM-L6-v2) + FAISS Index   |
|    • Directionality Guardrail: Discards notes with "no cost impact" (N005, N010)   |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 4. Guardrail Reasoner & Model Cascade (src/reasoner.py) (temp = 0.0)              |
|    • Priority 1: gemini-3.5-flash-lite (Free Tier: 15 RPM / 250K TPM / 500 RPD)   |
|    • Fallback Cascade: gemini-2.0-flash-lite -> gemini-1.5-flash -> Heuristic     |
|    • Formulates plain-English explanation citing exact note or stating unexplained|
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 5. Output Contract & Live UI                                                      |
|    • Generates output/sample_output_format.csv (100% schema compliant)            |
|    • Generates output/token_cost_log.json ($0.00 actual billed cost)              |
|    • Boots Flask web dashboard with KPI cards and interactive Q&A assistant       |
+-----------------------------------------------------------------------------------+
```

---

## 2. How I Built It

### Technical Stack Decisions

| Layer | Technology | Engineering Rationale |
| :--- | :--- | :--- |
| **Language** | **Python 3.10+** | Native ecosystem for data processing, vector search, and AI orchestration. |
| **Data Analytics** | **Pure Vectorized Python / Pandas** | Embedded, zero external database setup, sub-second execution across 2,940 shipment records. |
| **Vector DB / RAG** | **`all-MiniLM-L6-v2` + `FAISS`** | 384-dimensional dense semantic vectors with Inner Product (Cosine) search; sub-millisecond retrieval. |
| **LLM Reasoner** | **`gemini-3.5-flash-lite`** (Temp = 0.0) | High speed, deterministic output, and **$0.00 cost** on Google AI Studio's free tier. |
| **Model Cascade** | **Automatic Multi-Model Fallback** | `gemini-3.5-flash-lite` $\rightarrow$ `gemini-2.0-flash-lite` $\rightarrow$ `gemini-1.5-flash` $\rightarrow$ Deterministic Heuristic Engine. |
| **Web UI & API** | **Flask + Gunicorn** | Ultra-lightweight (~45MB RAM footprint), instant boot, and natively deployable to Render. |
| **Containerization** | **Docker & Docker Compose** | Multi-stage image with CPU-optimized PyTorch and volume mounts for 100% host synchronization. |

### Architectural Trade-off: Deterministic DAG vs. Heavy Agent Frameworks
For the batch evaluation pipeline, I deliberately chose a **functional Directed Acyclic Graph (DAG)** over complex multi-agent frameworks like LangGraph. The batch contract demands **100% byte-for-byte reproducibility, minimal token spend, and strict schema compliance**. An unconstrained autonomous agent loop introduces run-to-run variance and token bloat. 

Instead, I reserved the conversational tool-calling pattern specifically for the **interactive Q&A assistant** in the web dashboard.

---

## 3. How I Convinced Myself It Was Right (Evaluation & Validation)

Before submitting, I designed an evaluation harness ([`eval/eval_harness.py`](file:///c:/Users/TANMAY/OneDrive/Desktop/Shipping_Watch/eval/eval_harness.py)) and schema auditor to test against every grading criterion:

### A. Mathematical Verification Against Ground Truth
We cross-referenced calculated numbers against the 3 reference rows provided in `sample_output_format_v2.csv`:

| Corridor | Week Of | Unit Cost (₹/t-km) | vs Own History (8-wk) | vs Similar Routes | Status | Ground Truth Match |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Delhi–Jaipur** | `2024-11-11` | **₹4.17** | **+35.5%** | **+21.0%** | `Yes` (Unexplained) | **100% Match** |
| **Ahmedabad–Mumbai** | `2025-01-20` | **₹3.29** | **+29.5%** | **+22.5%** | `No (justified)` [N002] | **100% Match** |
| **Mumbai–Pune** | `2025-09-15` | **₹3.98** | **+9.2%** | **+23.6%** | `Yes` (Unexplained) | **100% Match** |

### B. Anti-Hallucination & Decoy Note Testing
The prompt notes: *"Failed checks are marked fabricated even if the flag was right."* We tested the system against decoy notes:
1. **Decoy Note N005** (*Mumbai-Delhi maintenance: "costs were not significantly affected"*): Correctly identified as non-justifying; reasoner explicitly states it does not justify a rate increase.
2. **Decoy Note N010** (*vehicle tracking mandate: "absorbed by transporters without rate change"*): Correctly identified as non-justifying.
3. **Decoy Note N004** (*toll plaza: "affected routes are not part of this dataset"*): Correctly excluded.
4. **Corridor Isolation**: Note N001 (*Chennai flood*) is strictly quarantined to `Chennai-Bangalore` and cannot leak to Delhi or Mumbai.
5. **Temporal Proximity Limit**: Limited to $\pm 35$ days so distant future events (such as N003 in May 2025) are not cited for 2024 spikes, correctly outputting: *"No matching note found for this route or date range. Cost rise looks unexplained and worth a human review."*

---

## 4. Reproducibility Check Across 3 Runs

Automated via [`eval/test_reproduce.py`](file:///c:/Users/TANMAY/OneDrive/Desktop/Shipping_Watch/eval/test_reproduce.py), running 3 independent, untouched executions:

```text
======================================================================
 REPRODUCIBILITY VERIFICATION: 3 UNTOUCHED RUNS
======================================================================
 Run #1 MD5 Checksum: 7ff86ae1f97a0a6d4818123332057d8d
 Run #2 MD5 Checksum: 7ff86ae1f97a0a6d4818123332057d8d
 Run #3 MD5 Checksum: 7ff86ae1f97a0a6d4818123332057d8d

======================================================================
 REPRODUCIBILITY COMPLIANCE MATRIX
======================================================================
 Row Count Match:         [PASS] (20 records in all runs)
 Numeric Baselines Match: [PASS] (cost, history, and peer deltas identical)
 Flagged Verdicts Match:  [PASS] ('Yes' / 'No (justified)' identical)
 Cited Note IDs Match:    [PASS] (matched_note_id identical)
 Byte-for-byte MD5 Match: [PASS] (100% Deterministic)
 Overall Brief Result:    [PASS: 100% COMPLIANT]
======================================================================
```
*Full report generated at [`output/reproducibility_report.md`](file:///c:/Users/TANMAY/OneDrive/Desktop/Shipping_Watch/output/reproducibility_report.md).*

---

## 5. Token & Cost Log (One Full Run)

By running the Anomaly Detection Gate before the LLM, only the ~20 candidate spikes across 728 route-week pairs are queried, reducing LLM calls by **>97%**.

*Metrics from [`output/token_cost_log.json`](file:///c:/Users/TANMAY/OneDrive/Desktop/Shipping_Watch/output/token_cost_log.json):*

| Metric | Measured Value |
| :--- | :--- |
| **Model Name** | `gemini-3.5-flash-lite` |
| **Pricing Tier** | Google AI Studio Free Tier (15 RPM / 250K TPM / 500 RPD) |
| **Total Invocations** | **20 calls** |
| **Total Input Tokens** | 6,718 tokens |
| **Total Output Tokens** | 1,485 tokens |
| **Total Tokens** | **8,203 tokens** |
| **Nominal Cost (Published Rates)** | **$0.000949 USD** (< 1/10th of a cent) |
| **Actual Billed Cost** | **$0.00 (Zero-Cost Strategy)** |
| **Full Pipeline Runtime** | **< 1.5 seconds** (cached session) / ~80s (cold API queries) |

---

## Repository Structure

```
Shipping_Watch/
├── data/
│   ├── shipment_records.csv          # 2,940 shipment records (2024-2025)
│   ├── context_notes.csv             # 10 ground truth real-world context notes
│   └── sample_output_format_v2.csv   # Target grading schema contract
├── src/
│   ├── engine.py                     # Monday weekly grouping & baseline mathematics
│   ├── detector.py                   # Anomaly threshold scoring & candidate filter
│   ├── retriever.py                  # Hybrid RAG: metadata filter + all-MiniLM-L6-v2 + FAISS
│   ├── reasoner.py                   # Grounded explanation reasoner with model cascade
│   ├── telemetry.py                  # Token counter, cost logger, and metrics tracker
│   └── logger.py                     # Centralized real-time logging (Host & Container)
├── eval/
│   ├── eval_harness.py               # Unit tests against sample rows & edge cases
│   └── test_reproduce.py             # 3-run identical output diff verification
├── templates/
│   └── index.html                    # Dark-mode dashboard & conversational assistant
├── static/
│   ├── style.css                     # Custom styles & animated framing spinner
│   └── app.js                        # Dynamic table rendering, filters, and chat
├── output/
│   ├── sample_output_format.csv      # Generated submission CSV matching contract
│   ├── token_cost_log.json           # Detailed token and cost telemetry
│   └── reproducibility_report.md     # 3-run MD5 verification report
├── logs/
│   └── system_monitor.log            # Real-time process and error stream
├── app.py                            # Flask server (REST API & UI)
├── run_pipeline.py                   # Headless CLI batch execution script
├── start.py                          # Unified 1-command execution script
├── monitor.py & monitor.bat          # Real-time colored terminal process monitor
├── entrypoint.sh                     # Container startup orchestrator
├── Dockerfile                        # Multi-stage container definition
├── docker-compose.yml                # 1-command Docker service orchestration
├── Procfile & render.yaml            # Render 1-click cloud deployment files
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment template
└── README.md                         # Complete project documentation
```

---

## 10-Minute Walkthrough Talking Points (Round 2)

1. **Problem Framing & Exact Baselines (2 min)**:
   * Walk through the Monday–Sunday weekly grouping, trailing 8-week strictly prior history baseline, and leave-one-out peer average by `route_type`. Show 100% mathematical match on the sample rows.
2. **Deterministic DAG vs. Agentic Overhead (2 min)**:
   * Explain why multi-agent graph frameworks were avoided for batch processing (risk of non-determinism, token bloat) and why a deterministic functional pipeline guarantees identical MD5 runs.
3. **Anti-Hallucination Guardrails (2 min)**:
   * Explain the 3 verification gates: corridor isolation, temporal proximity window ($\pm 35$ days), and directionality/sentiment checks that reject non-affecting decoy notes (N005, N010).
4. **Zero-Cost Strategy & Model Cascade (2 min)**:
   * Present the token log: only 20 calls across 2 full years of data, costing $0.00 on the free tier with `gemini-3.5-flash-lite`.
5. **Live Demo & Interactive Q&A (2 min)**:
   * Open **`https://shipping-watch.onrender.com`** (or `http://localhost:5000`), demonstrate the table filtering, and ask an ad-hoc question in the QA assistant box (e.g. *"Why did Ahmedabad-Mumbai spike in Jan 2025?"*) to showcase the live framing spinner and grounded response.
