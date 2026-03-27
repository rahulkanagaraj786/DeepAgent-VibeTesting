"""scanner.py — Compatibility shim + public API for repo cloning and spec extraction.

Wraps repo_scanner.py (clone_repo, find_or_infer_spec) and exposes:
  - clone_repo(url) -> str
  - extract_spec(repo_path) -> dict | None
"""

import json
import logging
from pathlib import Path
from typing import Optional

from repo_scanner import clone_repo, find_or_infer_spec  # noqa: F401 — re-export

logger = logging.getLogger(__name__)


def extract_spec(repo_path: str, repo_url: str = "") -> Optional[dict]:
    """
    Given a cloned repo path, find an OpenAPI/Swagger spec and return it as a dict.
    Falls back to spec inference if no spec file is found.

    Args:
        repo_path: Local path to the cloned repository.
        repo_url:  Original GitHub URL (used for spec inference context).

    Returns:
        Parsed OpenAPI spec dict, or None if not found/inferred.
    """
    spec_path = find_or_infer_spec(repo_path, repo_url or repo_path)
    if not spec_path:
        return None

    try:
        path = Path(spec_path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        if spec_path.endswith(".json"):
            return json.loads(text)
        # YAML
        try:
            import yaml  # type: ignore
            return yaml.safe_load(text)
        except ImportError:
            # yaml not available — try basic JSON parse (may fail for YAML)
            try:
                return json.loads(text)
            except Exception:
                logger.warning(f"[scanner] Could not parse spec at {spec_path} (yaml not installed)")
                return None
    except Exception as e:
        logger.error(f"[scanner] Error reading spec {spec_path}: {e}")
        return None
