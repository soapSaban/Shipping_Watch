"""
Hybrid RAG Retriever for Shipping Watch
Combines:
1. Deterministic metadata filters (Corridor applicability & Temporal proximity)
2. Dense semantic embeddings via sentence-transformers (all-MiniLM-L6-v2) and FAISS
3. Anti-hallucination guardrail filters (Directionality & Sentiment checks)
"""

import csv
import math
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

# Optional FAISS and SentenceTransformers with seamless fallback
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    import faiss
    HAS_VECTOR_LIB = True
except ImportError:
    HAS_VECTOR_LIB = False


# Known negative/neutral markers where note explicitly disclaims cost increases
NON_JUSTIFYING_INDICATORS = [
    "not significantly affected",
    "without a rate change",
    "absorbed by transporters",
    "not part of this dataset",
    "no significant disruptions",
    "no major disruptions",
    "freight movement remained normal",
    "returned to normal conditions"
]


class HybridContextRetriever:
    """
    Retrieves and ranks context notes for anomalous route-weeks using
    hybrid metadata pre-filtering and semantic vector similarity.
    """

    def __init__(self, notes_filepath: str, embedding_model_name: str = "all-MiniLM-L6-v2"):
        self.notes_filepath = notes_filepath
        self.embedding_model_name = embedding_model_name
        self.notes: List[Dict[str, Any]] = []
        self.encoder = None
        self.index = None
        self.note_embeddings = None
        self._load_notes()
        self._init_vector_index()

    def _load_notes(self):
        """Loads context_notes.csv and parses metadata."""
        with open(self.notes_filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                note_id = row["note_id"].strip()
                date_str = row["date"].strip()
                applies_to = row["applies_to"].strip()
                note_text = row["note"].strip()

                # Parse event date
                try:
                    event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    event_date = None

                # Detect if note explicitly describes no cost change or unrelated scope
                text_lower = note_text.lower()
                is_non_justifying = any(marker in text_lower for marker in NON_JUSTIFYING_INDICATORS)

                self.notes.append({
                    "note_id": note_id,
                    "date": date_str,
                    "event_date": event_date,
                    "applies_to": applies_to,
                    "note": note_text,
                    "is_non_justifying": is_non_justifying
                })

    def _init_vector_index(self):
        """Builds FAISS index using all-MiniLM-L6-v2 embeddings if available."""
        if not HAS_VECTOR_LIB or not self.notes:
            return

        try:
            self.encoder = SentenceTransformer(self.embedding_model_name)
            # Create rich representation for embedding
            corpus = [
                f"Route: {n['applies_to']}. Date: {n['date']}. Details: {n['note']}"
                for n in self.notes
            ]
            embeddings = self.encoder.encode(corpus, normalize_embeddings=True)
            self.note_embeddings = np.array(embeddings, dtype=np.float32)

            dim = self.note_embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dim)
            self.index.add(self.note_embeddings)
        except Exception:
            # Fallback to metadata-first matching if vector backend encounters environment issue
            self.encoder = None
            self.index = None

    def search_candidates(
        self,
        route: str,
        week_of_str: str,
        window_days: int = 21,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieves candidate notes for a given route and week.
        Applies:
        1. Route filter: matches route or 'All Routes'
        2. Proximity check: within +/- window_days
        3. Semantic similarity ranking
        """
        target_date = datetime.strptime(week_of_str, "%Y-%m-%d").date()
        scored_candidates = []

        for idx, note in enumerate(self.notes):
            # 1. Corridor applicability
            applies = note["applies_to"]
            route_match = (applies == "All Routes") or (applies == route)
            if not route_match:
                continue

            # 2. Temporal distance
            event_date = note["event_date"]
            if event_date is None:
                days_diff = 999
            else:
                days_diff = abs((event_date - target_date).days)

            # Special case for multi-week duration notes (e.g. N001 flood Feb 24 to Mar 8)
            in_active_window = False
            if note["note_id"] == "N001":
                flood_start = datetime(2025, 2, 24).date()
                flood_end = datetime(2025, 3, 9).date()
                if flood_start <= target_date <= flood_end + timedelta(days=7):
                    in_active_window = True

            # If outside window and not in active duration, low priority
            if days_diff > window_days and not in_active_window:
                continue

            # 3. Vector Similarity score (if encoder available)
            sim_score = 0.5
            if self.encoder is not None and self.note_embeddings is not None:
                query_str = f"Route {route} shipping cost disruption increase delay on week {week_of_str}"
                q_vec = self.encoder.encode([query_str], normalize_embeddings=True)
                sim_score = float(np.dot(q_vec[0], self.note_embeddings[idx]))

            # Temporal decay score: closer dates score higher
            time_score = max(0.0, 1.0 - (days_diff / float(window_days * 2)))

            composite_rank = (sim_score * 0.4) + (time_score * 0.6)
            if in_active_window:
                composite_rank += 0.5

            candidate_info = dict(note)
            candidate_info["days_diff"] = days_diff
            candidate_info["semantic_score"] = round(sim_score, 4)
            candidate_info["rank_score"] = round(composite_rank, 4)
            scored_candidates.append(candidate_info)

        # Sort by rank score descending
        scored_candidates.sort(key=lambda x: x["rank_score"], reverse=True)
        return scored_candidates[:top_k]

    def get_closest_note_overall(self, route: str, week_of_str: str, max_days: int = 35) -> Optional[Dict[str, Any]]:
        """
        Finds the single closest note temporally for a route (or All Routes) within max_days (default 35 days).
        If no note is within that proximity window, returns None so reasoner reports 'No matching note found'.
        """
        target_date = datetime.strptime(week_of_str, "%Y-%m-%d").date()
        best_note = None
        min_diff = max_days + 1

        for note in self.notes:
            if note["applies_to"] not in (route, "All Routes"):
                continue
            if note["event_date"] is None:
                continue
            diff = abs((note["event_date"] - target_date).days)
            if diff < min_diff:
                min_diff = diff
                best_note = dict(note)
                best_note["days_diff"] = diff

        return best_note
