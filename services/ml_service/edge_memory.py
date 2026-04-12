# services/ml_service/edge_memory.py
# VIT Sports Intelligence — Edge Memory System
# Stores profitable betting patterns with ROI tracking + time decay
# Uses the existing SQLite `edges` table

import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default DB path — resolved relative to project root
_DEFAULT_DB = None  # resolved at runtime

PATTERN_TYPES = {
    "away_underdog":    {"desc": "Away team is large underdog (>3.0 odds) and wins",  "market": "1x2"},
    "home_steamroller": {"desc": "Elite home team vs lower-tier away",                 "market": "1x2"},
    "high_ou":          {"desc": "High-scoring match (over 2.5 likely)",               "market": "over_under"},
    "low_ou":           {"desc": "Low-scoring match (under 2.5 likely)",               "market": "over_under"},
    "btts_likely":      {"desc": "Both teams likely to score",                         "market": "btts"},
    "no_btts_likely":   {"desc": "Clean sheet likely (one team has weak attack)",      "market": "btts"},
    "draw_underrated":  {"desc": "Market underrates draw probability",                 "market": "1x2"},
    "chaos_match":      {"desc": "Tier-3 chaos match — extreme outcome likely",       "market": "1x2"},
}

MIN_SAMPLE_SIZE = 30       # patterns below this are not surfaced
DECAY_THRESHOLD  = -0.01   # patterns below this ROI are archived
MAX_ACTIVE_PATTERNS = 50   # prune above this limit


def _db_path() -> str:
    global _DEFAULT_DB
    if _DEFAULT_DB is None:
        base = __file__
        for _ in range(5):
            base = os.path.dirname(base)
            candidate = os.path.join(base, "vit.db")
            if os.path.exists(candidate):
                _DEFAULT_DB = candidate
                break
        if _DEFAULT_DB is None:
            _DEFAULT_DB = os.path.join(os.getcwd(), "vit.db")
    return _DEFAULT_DB


class EdgeMemory:
    """
    Persistent edge pattern store backed by SQLite `edges` table.

    Workflow:
    1. Detect patterns from a batch of simulated/real matches
    2. Store them with initial ROI estimate
    3. Update ROI as more results come in
    4. Apply time decay — stale patterns erode
    5. Archive patterns below ROI threshold
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _db_path()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Pattern detection from match batch ───────────────────────────────────
    def detect_and_update(self, matches: List[Dict]) -> Dict[str, int]:
        """
        Scan a batch of match dicts for known patterns and update the edge table.
        Returns count of patterns updated per type.
        """
        pattern_buckets: Dict[str, Dict[str, Any]] = {}  # pattern_type → aggregated stats

        for m in matches:
            result = m.get("result") or m.get("actual_outcome", "")
            ho = m.get("market_odds", {}).get("home", 2.0)
            ao = m.get("market_odds", {}).get("away", 3.0)
            total = m.get("total_goals", 0)
            over25 = m.get("over_25", 0)
            btts = m.get("btts", 0)
            tier = m.get("tier", 1)
            league = m.get("league", "all")

            # away_underdog
            if ao >= 3.0 and result == "A":
                self._bucket_add(pattern_buckets, "away_underdog", league, roi=(ao - 1), hit=True)
            elif ao >= 3.0:
                self._bucket_add(pattern_buckets, "away_underdog", league, roi=-1.0, hit=False)

            # home_steamroller
            if ho <= 1.50 and result == "H":
                self._bucket_add(pattern_buckets, "home_steamroller", league, roi=(ho - 1), hit=True)
            elif ho <= 1.50:
                self._bucket_add(pattern_buckets, "home_steamroller", league, roi=-1.0, hit=False)

            # high_ou / low_ou
            if over25:
                self._bucket_add(pattern_buckets, "high_ou", league, roi=0.88, hit=True)
            else:
                self._bucket_add(pattern_buckets, "high_ou", league, roi=-1.0, hit=False)
                self._bucket_add(pattern_buckets, "low_ou", league, roi=0.85, hit=True)

            # btts
            if btts:
                self._bucket_add(pattern_buckets, "btts_likely", league, roi=0.80, hit=True)
            else:
                self._bucket_add(pattern_buckets, "btts_likely", league, roi=-1.0, hit=False)
                self._bucket_add(pattern_buckets, "no_btts_likely", league, roi=0.75, hit=True)

            # draw_underrated: draw happened but draw odds > 3.5
            draw_o = m.get("market_odds", {}).get("draw", 3.3)
            if result == "D" and draw_o >= 3.5:
                self._bucket_add(pattern_buckets, "draw_underrated", league, roi=(draw_o - 1), hit=True)
            elif draw_o >= 3.5:
                self._bucket_add(pattern_buckets, "draw_underrated", league, roi=-1.0, hit=False)

            # chaos_match
            if tier == 3:
                if result in ("H", "A") and total >= 4:
                    self._bucket_add(pattern_buckets, "chaos_match", league, roi=1.20, hit=True)
                else:
                    self._bucket_add(pattern_buckets, "chaos_match", league, roi=-1.0, hit=False)

        updated = {}
        for ptype, stats in pattern_buckets.items():
            count = self._upsert_pattern(ptype, stats)
            updated[ptype] = count

        return updated

    @staticmethod
    def _bucket_add(buckets: Dict, ptype: str, league: str, roi: float, hit: bool):
        if ptype not in buckets:
            buckets[ptype] = {"league": league, "rois": [], "hits": 0, "total": 0}
        buckets[ptype]["rois"].append(roi)
        buckets[ptype]["total"] += 1
        if hit:
            buckets[ptype]["hits"] += 1

    def _upsert_pattern(self, ptype: str, stats: Dict) -> int:
        rois = stats["rois"]
        if not rois:
            return 0

        avg_roi = sum(rois) / len(rois)
        league = stats["league"]
        meta = PATTERN_TYPES.get(ptype, {})
        desc = meta.get("desc", ptype)
        market = meta.get("market", "1x2")
        now = datetime.now(timezone.utc).isoformat()
        sample_add = len(rois)

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM edges WHERE edge_id = ?",
                (f"{ptype}_{league}",)
            ).fetchone()

            if existing:
                # Blend ROI (exponential moving average)
                old_roi = existing["roi"]
                old_n   = existing["sample_size"]
                new_n   = old_n + sample_add
                blended_roi = (old_roi * old_n + avg_roi * sample_add) / new_n
                conn.execute(
                    "UPDATE edges SET roi=?, sample_size=?, last_updated=?, status=? WHERE edge_id=?",
                    (round(blended_roi, 4), new_n, now, "active", f"{ptype}_{league}")
                )
            else:
                conn.execute(
                    """INSERT INTO edges
                       (edge_id, description, roi, sample_size, confidence, avg_edge,
                        league, market, status, decay_rate, created_at, last_updated)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"{ptype}_{league}", desc, round(avg_roi, 4), sample_add,
                     round(min(0.9, sample_add / 1000), 3), round(avg_roi, 4),
                     league, market, "active", 0.03, now, now)
                )

        return sample_add

    # ── Apply time decay ─────────────────────────────────────────────────────
    def apply_decay(self, days_elapsed: float = 1.0) -> Dict[str, int]:
        """
        Reduce ROI of all active patterns by decay_rate × days_elapsed.
        Archive patterns whose ROI falls below DECAY_THRESHOLD.
        """
        now = datetime.now(timezone.utc).isoformat()
        archived = 0
        decayed = 0

        with self._conn() as conn:
            active = conn.execute(
                "SELECT * FROM edges WHERE status='active'"
            ).fetchall()

            for row in active:
                new_roi = row["roi"] - row["decay_rate"] * days_elapsed
                if new_roi < DECAY_THRESHOLD or (row["sample_size"] >= MIN_SAMPLE_SIZE and new_roi < -0.02):
                    conn.execute(
                        "UPDATE edges SET status='archived', archived_at=?, roi=? WHERE edge_id=?",
                        (now, round(new_roi, 4), row["edge_id"])
                    )
                    archived += 1
                else:
                    conn.execute(
                        "UPDATE edges SET roi=?, last_updated=? WHERE edge_id=?",
                        (round(new_roi, 4), now, row["edge_id"])
                    )
                    decayed += 1

        return {"decayed": decayed, "archived": archived}

    # ── Get active edges ─────────────────────────────────────────────────────
    def get_active(self, min_sample: int = MIN_SAMPLE_SIZE, limit: int = MAX_ACTIVE_PATTERNS) -> List[Dict]:
        """Return active edge patterns sorted by ROI descending."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM edges
                   WHERE status='active' AND sample_size >= ?
                   ORDER BY roi DESC LIMIT ?""",
                (min_sample, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Summary stats ────────────────────────────────────────────────────────
    def summary(self) -> Dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM edges WHERE status='active'").fetchone()[0]
            archived = conn.execute("SELECT COUNT(*) FROM edges WHERE status='archived'").fetchone()[0]
            top = conn.execute(
                "SELECT edge_id, roi, sample_size FROM edges WHERE status='active' ORDER BY roi DESC LIMIT 5"
            ).fetchall()

        return {
            "total_patterns": total,
            "active": active,
            "archived": archived,
            "top_edges": [dict(r) for r in top],
        }

    # ── Prune excess patterns ────────────────────────────────────────────────
    def prune(self, keep: int = MAX_ACTIVE_PATTERNS) -> int:
        """Archive lowest-ROI active patterns if total exceeds keep limit."""
        with self._conn() as conn:
            active_count = conn.execute("SELECT COUNT(*) FROM edges WHERE status='active'").fetchone()[0]
            if active_count <= keep:
                return 0
            excess = active_count - keep
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                f"""UPDATE edges SET status='archived', archived_at=?
                    WHERE edge_id IN (
                        SELECT edge_id FROM edges WHERE status='active'
                        ORDER BY roi ASC LIMIT {excess}
                    )""",
                (now,)
            )
        return excess
