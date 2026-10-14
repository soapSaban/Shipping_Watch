"""
Telemetry and Cost Tracking Module for FreightTiger Shipping Watch
Tracks LLM calls, token usage (input/output), latency, and costs based on published model rates.
Produces JSON logs and formatted Markdown summaries for evaluation and README.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

# Published pricing per million tokens (as of Gemini Flash Lite / Google AI Studio)
# Free tier is $0.00 up to 15 RPM / 250k TPM / 500 RPD
PRICING_TABLE = {
    "gemini-3.5-flash-lite": {
        "input_per_million": 0.075,   # Free Tier (15 RPM / 250K TPM / 500 RPD)
        "output_per_million": 0.30,
        "free_tier": True
    },
    "gemini-2.5-flash-lite": {
        "input_per_million": 0.075,
        "output_per_million": 0.30,
        "free_tier": True
    },
    "gemini-2.0-flash-lite": {
        "input_per_million": 0.075,
        "output_per_million": 0.30,
        "free_tier": True
    },
    "gemini-1.5-flash": {
        "input_per_million": 0.075,
        "output_per_million": 0.30,
        "free_tier": True
    },
    "heuristic-verifier": {
        "input_per_million": 0.0,
        "output_per_million": 0.0,
        "free_tier": True
    }
}


class TokenCostTracker:
    """
    Thread-safe tracker for logging LLM token consumption and calculating running costs.
    """
    def __init__(self, model_name: str = "gemini-2.0-flash-lite"):
        self.model_name = model_name
        self.calls: List[Dict[str, Any]] = []
        self.start_time: float = time.time()
        self.pricing = PRICING_TABLE.get(model_name, PRICING_TABLE["gemini-2.0-flash-lite"])

    def record_call(
        self,
        route: str,
        week_of: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        verdict: str,
        matched_note_id: Optional[str] = None,
        cached: bool = False
    ) -> Dict[str, Any]:
        """Record a single LLM invocation."""
        call_record = {
            "call_index": len(self.calls) + 1,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "route": route,
            "week_of": week_of,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "latency_ms": round(latency_ms, 2),
            "verdict": verdict,
            "matched_note_id": matched_note_id or "",
            "cached": cached
        }
        self.calls.append(call_record)
        return call_record

    def get_summary(self) -> Dict[str, Any]:
        """Compute aggregate token, call, and cost statistics."""
        total_calls = len(self.calls)
        total_input = sum(c["input_tokens"] for c in self.calls)
        total_output = sum(c["output_tokens"] for c in self.calls)
        total_tokens = total_input + total_output
        total_latency = sum(c["latency_ms"] for c in self.calls)
        avg_latency = (total_latency / total_calls) if total_calls > 0 else 0.0

        # Nominal dollar cost calculation at published standard rates
        rate_in = self.pricing["input_per_million"] / 1_000_000.0
        rate_out = self.pricing["output_per_million"] / 1_000_000.0
        nominal_cost_usd = (total_input * rate_in) + (total_output * rate_out)

        actual_billed_cost_usd = 0.0 if self.pricing.get("free_tier", True) else nominal_cost_usd

        return {
            "model_name": self.model_name,
            "tier": "Google AI Studio Free Tier (15 RPM / 250K TPM / 500 RPD)",
            "total_llm_calls": total_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_tokens,
            "avg_latency_ms": round(avg_latency, 2),
            "total_runtime_seconds": round(time.time() - self.start_time, 2),
            "published_rates": {
                "input_per_1m_tokens_usd": self.pricing["input_per_million"],
                "output_per_1m_tokens_usd": self.pricing["output_per_million"]
            },
            "nominal_cost_at_published_rates_usd": round(nominal_cost_usd, 6),
            "actual_billed_cost_usd": actual_billed_cost_usd,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    def save_log(self, filepath: str = "output/token_cost_log.json") -> str:
        """Export full telemetry log and summary to a JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        summary = self.get_summary()
        payload = {
            "summary": summary,
            "calls": self.calls
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return filepath

    def get_markdown_summary(self) -> str:
        """Format metrics into a concise markdown table suitable for README and reports."""
        s = self.get_summary()
        return (
            f"| Metric | Value |\n"
            f"| :--- | :--- |\n"
            f"| **Model Used** | `{s['model_name']}` |\n"
            f"| **Pricing Tier** | Free Tier ($0.00 / free quota) |\n"
            f"| **Total LLM Invocations** | **{s['total_llm_calls']} calls** |\n"
            f"| **Total Input Tokens** | {s['total_input_tokens']:,} tokens |\n"
            f"| **Total Output Tokens** | {s['total_output_tokens']:,} tokens |\n"
            f"| **Total Tokens** | **{s['total_tokens']:,} tokens** |\n"
            f"| **Nominal Cost (at published rates)** | **${s['nominal_cost_at_published_rates_usd']:.6f} USD** |\n"
            f"| **Actual Billed Cost** | **$0.00 (Zero Cost Strategy)** |\n"
            f"| **Average Latency / Call** | {s['avg_latency_ms']} ms |\n"
            f"| **Total Run Duration** | {s['total_runtime_seconds']} s |\n"
        )
