"""repo_scanner.py — Repo cloning and OpenAPI spec extraction.

Uses plain git clone into local temp directories.
Falls back to spec inference if no OpenAPI spec is found.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def clone_repo(repo_url: str) -> str:
    """Clone a GitHub repo into a temp directory and return the path."""
    tmp_dir = tempfile.mkdtemp(prefix="vibe_test_")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, tmp_dir],
            check=True,
            capture_output=True,
            timeout=60,
        )
        logger.info(f"[scanner] Cloned {repo_url} → {tmp_dir}")
        return tmp_dir
    except subprocess.CalledProcessError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone repo: {e.stderr.decode()}")


def _is_openapi_file(path: Path) -> bool:
    """Quick check if a file looks like an OpenAPI/Swagger spec."""
    try:
        snippet = path.read_text(encoding="utf-8", errors="ignore")[:500]
        return any(kw in snippet for kw in ["openapi", "swagger"])
    except Exception:
        return False


def find_or_infer_spec(repo_path: str, repo_url: str) -> Optional[str]:
    """
    Find an existing OpenAPI spec in the repo, or infer one from code.
    Returns the local path to the spec file, or None if inference fails.
    """
    repo = Path(repo_path)

    # Search for existing spec files
    candidates = list(repo.rglob("*.yaml")) + list(repo.rglob("*.yml")) + list(repo.rglob("*.json"))
    swagger_files = [f for f in candidates if _is_openapi_file(f)]

    if swagger_files:
        logger.info(f"[scanner] Found existing spec: {swagger_files[0]}")
        return str(swagger_files[0])

    # No spec found — infer from codebase
    logger.info(f"[scanner] No OpenAPI spec found in {repo_url}. Inferring from codebase...")
    try:
        from pipeline.spec_inference import infer_spec_from_repo
        inferred_spec = infer_spec_from_repo(repo_path, repo_url)
        if inferred_spec:
            spec_path = repo / "_inferred_openapi.json"
            spec_path.write_text(json.dumps(inferred_spec, indent=2))
            logger.info(f"[scanner] Inferred spec written to {spec_path}")
            return str(spec_path)
    except Exception as e:
        logger.error(f"[scanner] Spec inference failed: {e}")

    return None


class ScanResult:
    """Holds scan results — cloned repo paths and extracted spec paths."""

    def __init__(self, results: dict, repo_dirs: dict):
        self.results = results          # repo_url -> list of spec dicts
        self.repo_dirs = repo_dirs      # repo_url -> local clone path
        self.sandbox_name = "local"     # compatibility shim

    def all_specs(self) -> list:
        """Return flat list of all extracted spec dicts."""
        specs = []
        for files in self.results.values():
            for f in files:
                if isinstance(f, dict):
                    specs.append(f)
        return specs

    def delete_sandbox(self):
        """Clean up cloned repos."""
        for path in self.repo_dirs.values():
            shutil.rmtree(path, ignore_errors=True)
            logger.info(f"[scanner] Cleaned up {path}")


class Scanner:
    def __init__(self):
        pass

    def scan_all(self, repo_urls: list, progress_callback=None, extract_dir=None):
        """
        Clone repos locally and find/infer OpenAPI specs.
        Returns a ScanResult with spec paths and repo dirs.
        """
        all_results = {}
        repo_dirs = {}

        for i, repo_url in enumerate(repo_urls):
            repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
            logger.info(f"[scanner] Processing {repo_url} ({i+1}/{len(repo_urls)})...")

            try:
                repo_path = clone_repo(repo_url)
                repo_dirs[repo_url] = repo_path

                spec_path = find_or_infer_spec(repo_path, repo_url)

                if spec_path and extract_dir:
                    repo_out_dir = os.path.join(extract_dir, repo_name)
                    os.makedirs(repo_out_dir, exist_ok=True)
                    local_name = os.path.basename(spec_path)
                    local_path = os.path.join(repo_out_dir, local_name)
                    shutil.copy2(spec_path, local_path)
                    all_results[repo_url] = [{
                        "sandbox_path": spec_path,
                        "local_path": local_path,
                        "repo_name": repo_name,
                    }]
                    logger.info(f"[scanner] Spec saved to {local_path}")
                elif spec_path:
                    all_results[repo_url] = [{
                        "sandbox_path": spec_path,
                        "local_path": spec_path,
                        "repo_name": repo_name,
                    }]
                else:
                    logger.warning(f"[scanner] No spec found or inferred for {repo_url}")
                    all_results[repo_url] = []

            except Exception as e:
                logger.error(f"[scanner] Failed to process {repo_url}: {e}")
                all_results[repo_url] = []

            if progress_callback:
                progress_callback(repo_url, i, len(repo_urls))

        return ScanResult(all_results, repo_dirs)
