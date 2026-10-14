"""
Core Analytics Engine for Shipping Watch
Computes:
1. Monday-to-Sunday weekly aggregations of shipment records
2. cost_per_tonne_km = sum(freight_cost) / sum(quantity * distance)
3. Trailing 8-week history rolling average (strictly prior weeks, no look-ahead)
4. Leave-one-out peer average across same route_type in the same week
"""

import csv
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional


def parse_monday_of_week(date_str: str) -> str:
    """
    Given 'YYYY-MM-DD', returns the Monday date string ('YYYY-MM-DD')
    for that week (Monday to Sunday).
    """
    dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


class ShippingAnalyticsEngine:
    """
    Computes exact freight metrics and baselines across routes and weeks.
    """

    def __init__(self, records_filepath: str):
        self.records_filepath = records_filepath
        self.records: List[Dict[str, Any]] = []
        self.routes: List[str] = []
        self.route_types: Dict[str, str] = {}
        self.sorted_weeks: List[str] = []
        
        # Aggregated table: (route, week_of) -> dict of aggregates
        self.weekly_metrics: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def load_and_aggregate(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """
        Reads CSV and groups shipments by (route, week_of, route_type).
        Computes total freight cost and total tonne-km.
        """
        with open(self.records_filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.records = list(reader)

        # Accumulator: (route, week_of) -> stats
        raw_agg = defaultdict(lambda: {
            "freight_cost": 0.0,
            "tonne_km": 0.0,
            "total_quantity": 0.0,
            "total_distance": 0.0,
            "shipment_count": 0,
            "route_type": ""
        })

        all_weeks = set()
        routes_set = set()

        for r in self.records:
            route = f"{r['origin'].strip()}-{r['destination'].strip()}"
            week_of = parse_monday_of_week(r["shipment_date"])
            route_type = r["route_type"].strip()
            cost = float(r["freight_cost_inr"])
            qty = float(r["quantity_tonnes"])
            dist = float(r["distance_km"])
            tonnes_km = qty * dist

            key = (route, week_of)
            raw_agg[key]["freight_cost"] += cost
            raw_agg[key]["tonne_km"] += tonnes_km
            raw_agg[key]["total_quantity"] += qty
            raw_agg[key]["total_distance"] += dist
            raw_agg[key]["shipment_count"] += 1
            raw_agg[key]["route_type"] = route_type

            all_weeks.add(week_of)
            routes_set.add(route)
            self.route_types[route] = route_type

        self.sorted_weeks = sorted(list(all_weeks))
        self.routes = sorted(list(routes_set))

        # Calculate unit cost per tonne-km
        for (route, week_of), data in raw_agg.items():
            unit_cost = (data["freight_cost"] / data["tonne_km"]) if data["tonne_km"] > 0 else 0.0
            self.weekly_metrics[(route, week_of)] = {
                "route": route,
                "week_of": week_of,
                "route_type": data["route_type"],
                "cost_per_tonne_km": round(unit_cost, 4),
                "cost_per_tonne_km_display": round(unit_cost, 2),
                "freight_cost": round(data["freight_cost"], 2),
                "tonne_km": round(data["tonne_km"], 2),
                "shipment_count": data["shipment_count"]
            }

        return self.weekly_metrics

    def compute_all_baselines(self) -> List[Dict[str, Any]]:
        """
        Computes both comparison baselines for every (route, week_of) entry:
        1. vs_own_history: Trailing 8-week rolling average strictly prior to current week.
        2. vs_similar_routes: Same-week average across all peer routes of the same route_type (excluding self).
        """
        if not self.weekly_metrics:
            self.load_and_aggregate()

        results = []

        for week_idx, week_of in enumerate(self.sorted_weeks):
            for route in self.routes:
                key = (route, week_of)
                if key not in self.weekly_metrics:
                    continue

                item = dict(self.weekly_metrics[key])
                cur_cost = item["cost_per_tonne_km"]
                rtype = item["route_type"]

                # 1. Trailing 8-week history (strictly prior, no look-ahead)
                prior_weeks = self.sorted_weeks[max(0, week_idx - 8):week_idx]
                prior_costs = [
                    self.weekly_metrics[(route, pw)]["cost_per_tonne_km"]
                    for pw in prior_weeks
                    if (route, pw) in self.weekly_metrics
                ]

                if prior_costs:
                    hist_avg = sum(prior_costs) / len(prior_costs)
                    hist_pct = ((cur_cost - hist_avg) / hist_avg) * 100.0
                    hist_str = f"{hist_pct:+.1f}% vs this route's past average"
                    has_prior = True
                else:
                    hist_avg = cur_cost
                    hist_pct = 0.0
                    hist_str = "N/A (first week)"
                    has_prior = False

                # 2. Similar routes average in that same week (exclude route itself)
                peer_routes = [
                    r for r in self.routes
                    if self.route_types.get(r) == rtype and r != route
                ]
                peer_costs = [
                    self.weekly_metrics[(pr, week_of)]["cost_per_tonne_km"]
                    for pr in peer_routes
                    if (pr, week_of) in self.weekly_metrics
                ]

                if peer_costs:
                    peer_avg = sum(peer_costs) / len(peer_costs)
                    peer_pct = ((cur_cost - peer_avg) / peer_avg) * 100.0
                    peer_str = f"{peer_pct:+.1f}% vs similar-length routes this week"
                    has_peers = True
                else:
                    peer_avg = cur_cost
                    peer_pct = 0.0
                    peer_str = "N/A (no peers)"
                    has_peers = False

                item.update({
                    "hist_avg": round(hist_avg, 4),
                    "hist_pct": round(hist_pct, 2),
                    "vs_own_history": hist_str,
                    "prior_weeks_count": len(prior_costs),
                    "has_prior": has_prior,
                    "peer_avg": round(peer_avg, 4),
                    "peer_pct": round(peer_pct, 2),
                    "vs_similar_routes": peer_str,
                    "peer_routes_count": len(peer_costs),
                    "has_peers": has_peers
                })

                results.append(item)

        # Deterministic sort order by (week_of, route)
        results.sort(key=lambda x: (x["week_of"], x["route"]))
        return results
