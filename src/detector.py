"""
Anomaly Detection Layer for FreightTiger Shipping Watch
Identifies route-week entries where cost is rising and out of the ordinary
compared to its own history (trailing 8 weeks) or peer routes in the same week.
"""

from typing import Dict, Any, Tuple


class AnomalyDetector:
    """
    Evaluates whether a route-week metric indicates an abnormal cost spike.
    """
    def __init__(
        self,
        hist_threshold_pct: float = 15.0,
        peer_threshold_pct: float = 20.0,
        dual_hist_threshold_pct: float = 8.0,
        dual_peer_threshold_pct: float = 10.0
    ):
        self.hist_threshold_pct = hist_threshold_pct
        self.peer_threshold_pct = peer_threshold_pct
        self.dual_hist_threshold_pct = dual_hist_threshold_pct
        self.dual_peer_threshold_pct = dual_peer_threshold_pct

    def is_anomalous(self, row: Dict[str, Any]) -> Tuple[bool, float, str]:
        """
        Determines if a row represents a cost spike worth flagging.
        Returns:
            (is_anomaly: bool, anomaly_score: float, reason_summary: str)
        """
        hist_pct = row.get("hist_pct", 0.0)
        peer_pct = row.get("peer_pct", 0.0)
        has_prior = row.get("has_prior", False)
        has_peers = row.get("has_peers", False)

        # Composite score weighting cost rise above baselines
        # Only positive deltas count toward cost spikes
        score_hist = max(0.0, hist_pct) if has_prior else 0.0
        score_peer = max(0.0, peer_pct) if has_peers else 0.0
        composite_score = round(max(score_hist, score_peer), 2)

        # Condition 1: Major historical spike (>= 15%)
        if has_prior and hist_pct >= self.hist_threshold_pct:
            return True, composite_score, f"Historical spike: {hist_pct:+.1f}% vs 8-wk average"

        # Condition 2: Major peer premium (>= 20%)
        if has_peers and peer_pct >= self.peer_threshold_pct:
            return True, composite_score, f"Peer spike: {peer_pct:+.1f}% vs peers"

        # Condition 3: Dual elevation (both history >= 8% and peer >= 10%)
        if has_prior and has_peers and hist_pct >= self.dual_hist_threshold_pct and peer_pct >= self.dual_peer_threshold_pct:
            return True, composite_score, f"Dual elevation: {hist_pct:+.1f}% hist, {peer_pct:+.1f}% peer"

        return False, composite_score, "Normal cost variation"
