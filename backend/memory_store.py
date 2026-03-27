"""
memory_store.py — Persistent cross-run memory using Aerospike.
Tracks bug history, fix status, and regression risk across test sessions.
Falls back to in-memory dict if Aerospike is unavailable.
"""

import json
import os
import time
from typing import Optional

try:
    import aerospike
    AEROSPIKE_AVAILABLE = True
except ImportError:
    AEROSPIKE_AVAILABLE = False
    print("[memory] Aerospike not installed — using in-memory fallback")

# In-memory fallback for local dev
_memory_fallback: dict = {}


class TestMemoryStore:
    def __init__(self):
        self.client = None
        self.namespace = "vibe_testing"
        self.set_name = "test_runs"

        if AEROSPIKE_AVAILABLE:
            try:
                config = {
                    "hosts": [(
                        os.environ.get("AEROSPIKE_HOST", "localhost"),
                        int(os.environ.get("AEROSPIKE_PORT", 3000)),
                    )]
                }
                self.client = aerospike.client(config).connect()
                print("[memory] Connected to Aerospike")
            except Exception as e:
                print(f"[memory] Aerospike connection failed: {e}. Using fallback.")

    def _repo_key(self, repo_url: str) -> str:
        parts = repo_url.rstrip("/").split("/")
        return "_".join(parts[-2:]) if len(parts) >= 2 else parts[-1]

    def save_run(self, repo_url: str, findings: list[dict]) -> None:
        """Save a test run's findings to persistent storage."""
        key_str = self._repo_key(repo_url)
        run_data = {
            "repo_url": repo_url,
            "timestamp": int(time.time()),
            "findings": json.dumps(findings),
            "bug_count": len([f for f in findings if f.get("severity") == "critical"]),
        }

        if self.client:
            try:
                key = (self.namespace, self.set_name, key_str)
                existing = self._get_raw(key_str)
                history = json.loads(existing.get("history", "[]")) if existing else []
                history.append(run_data)
                history = history[-10:]  # keep last 10 runs
                self.client.put(key, {
                    "history": json.dumps(history),
                    "latest": json.dumps(run_data),
                })
            except Exception as e:
                print(f"[memory] Aerospike write error: {e}")
                _memory_fallback[key_str] = run_data
        else:
            existing = _memory_fallback.get(key_str, {})
            history = existing.get("history", [])
            history.append(run_data)
            _memory_fallback[key_str] = {"history": history[-10:], "latest": run_data}

    def get_history(self, repo_url: str) -> list[dict]:
        """Get prior test runs for a repo."""
        key_str = self._repo_key(repo_url)
        raw = self._get_raw(key_str)
        if not raw:
            return []
        history_val = raw.get("history", "[]")
        try:
            if isinstance(history_val, list):
                return history_val
            return json.loads(history_val)
        except Exception:
            return []

    def get_regression_risk(self, repo_url: str, current_findings: list[dict]) -> list[dict]:
        """
        Compare current findings against history.
        Flag bugs that appeared in previous runs but weren't fixed.
        """
        history = self.get_history(repo_url)
        if not history:
            return []

        regressions = []
        current_locations = {f.get("root_cause_location") for f in current_findings}

        for past_run in history[-3:]:
            findings_raw = past_run.get("findings", "[]")
            past_findings = json.loads(findings_raw) if isinstance(findings_raw, str) else findings_raw
            for past_bug in past_findings:
                if past_bug.get("severity") == "critical":
                    loc = past_bug.get("root_cause_location")
                    if loc and loc in current_locations:
                        times_seen = sum(
                            1 for r in history
                            if loc in (r.get("findings", "") if isinstance(r.get("findings"), str) else json.dumps(r.get("findings", [])))
                        )
                        regressions.append({
                            "location": loc,
                            "first_seen": past_run.get("timestamp"),
                            "times_seen": times_seen,
                            "message": f"This bug was seen {times_seen} run(s) ago and was never fixed. Escalating to CRITICAL.",
                        })

        return regressions

    def _get_raw(self, key_str: str) -> Optional[dict]:
        if self.client:
            try:
                key = (self.namespace, self.set_name, key_str)
                _, _, record = self.client.get(key)
                return record
            except Exception:
                return None
        return _memory_fallback.get(key_str)


# Singleton
memory_store = TestMemoryStore()
