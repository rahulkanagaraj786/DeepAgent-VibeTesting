"""
spec_inference.py — Infer OpenAPI spec from any codebase using AST parsing + LLM.
Supports: Express.js, FastAPI, Flask, Next.js API routes, Django REST.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

FRAMEWORK_PATTERNS = {
    "fastapi": {
        "files": ["main.py", "app.py", "api.py", "routes.py"],
        "markers": ["FastAPI()", "APIRouter()", "@app.get", "@app.post", "@router.get"],
    },
    "flask": {
        "files": ["app.py", "main.py", "views.py"],
        "markers": ["Flask(__name__)", "@app.route", "Blueprint("],
    },
    "express": {
        "files": ["index.js", "app.js", "server.js", "routes.js"],
        "markers": ["express()", "router.get(", "app.get(", "app.post("],
    },
    "nextjs": {
        "dirs": ["pages/api", "app/api"],
        "markers": ["export default", "export async function GET", "export async function POST"],
    },
    "django": {
        "files": ["urls.py", "views.py"],
        "markers": ["urlpatterns", "path(", "include(", "APIView", "ViewSet"],
    },
}


def detect_framework(repo_path: str) -> str:
    """Detect the web framework used in the repo."""
    repo = Path(repo_path)

    for framework, config in FRAMEWORK_PATTERNS.items():
        for file_pattern in config.get("files", []):
            for filepath in repo.rglob(file_pattern):
                try:
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                    if any(marker in content for marker in config.get("markers", [])):
                        return framework
                except Exception:
                    continue

        for dir_pattern in config.get("dirs", []):
            if (repo / dir_pattern).exists():
                return framework

    return "unknown"


def extract_routes_from_code(repo_path: str, framework: str) -> list[dict]:
    """Extract route definitions from source code."""
    repo = Path(repo_path)

    if framework == "fastapi":
        return _extract_fastapi_routes(repo)
    elif framework == "flask":
        return _extract_flask_routes(repo)
    elif framework == "express":
        return _extract_express_routes(repo)
    elif framework == "nextjs":
        return _extract_nextjs_routes(repo)
    elif framework == "django":
        return _extract_django_routes(repo)
    else:
        return _extract_generic_routes(repo)


def _extract_fastapi_routes(repo: Path) -> list[dict]:
    """Extract FastAPI route decorators using regex."""
    routes = []
    pattern = re.compile(
        r'@(?:app|router)\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',
        re.IGNORECASE,
    )

    for pyfile in repo.rglob("*.py"):
        try:
            content = pyfile.read_text(encoding="utf-8", errors="ignore")
            for match in pattern.finditer(content):
                method, path = match.group(1).upper(), match.group(2)
                func_match = re.search(
                    rf'{re.escape(match.group(0))}\s*\nasync def (\w+)\([^)]*\):\s*\n\s*"""([^"]*?)"""',
                    content,
                    re.DOTALL,
                )
                routes.append({
                    "method": method,
                    "path": path,
                    "description": func_match.group(2).strip() if func_match else f"{method} {path}",
                    "operation_id": func_match.group(1) if func_match else None,
                    "source_file": str(pyfile.relative_to(repo)),
                })
        except Exception:
            continue

    return routes


def _extract_express_routes(repo: Path) -> list[dict]:
    """Extract Express.js route definitions using regex."""
    routes = []
    pattern = re.compile(
        r'(?:app|router)\.(get|post|put|delete|patch)\(["\`]([^"\'`]+)["\`]',
        re.IGNORECASE,
    )

    for jsfile in list(repo.rglob("*.js")) + list(repo.rglob("*.ts")):
        if "node_modules" in str(jsfile):
            continue
        try:
            content = jsfile.read_text(encoding="utf-8", errors="ignore")
            for match in pattern.finditer(content):
                method, path = match.group(1).upper(), match.group(2)
                routes.append({
                    "method": method,
                    "path": path,
                    "description": f"{method} {path}",
                    "source_file": str(jsfile.relative_to(repo)),
                })
        except Exception:
            continue

    return routes


def _extract_nextjs_routes(repo: Path) -> list[dict]:
    """Extract Next.js API routes from file structure."""
    routes = []

    for api_dir in ["pages/api", "app/api"]:
        api_path = repo / api_dir
        if not api_path.exists():
            continue

        for route_file in list(api_path.rglob("*.ts")) + list(api_path.rglob("*.js")):
            rel = route_file.relative_to(api_path)
            url_path = "/" + str(rel).replace("\\", "/")
            url_path = re.sub(r'\.(ts|js|tsx|jsx)$', '', url_path)
            url_path = re.sub(r'/index$', '', url_path)
            url_path = re.sub(r'\[(\w+)\]', r'{\1}', url_path)

            content = route_file.read_text(encoding="utf-8", errors="ignore")
            methods = re.findall(r'export (?:async )?function (GET|POST|PUT|DELETE|PATCH)', content)

            for method in methods:
                routes.append({
                    "method": method,
                    "path": f"/api{url_path}",
                    "description": f"{method} {url_path}",
                    "source_file": str(route_file.relative_to(repo)),
                })

    return routes


def _extract_flask_routes(repo: Path) -> list[dict]:
    routes = []
    pattern = re.compile(r'@(?:app|bp)\.route\(["\']([^"\']+)["\'](?:.*?methods=\[([^\]]+)\])?')
    for pyfile in repo.rglob("*.py"):
        try:
            content = pyfile.read_text(encoding="utf-8", errors="ignore")
            for match in pattern.finditer(content):
                path = match.group(1)
                methods_str = match.group(2) or '"GET"'
                methods = [m.strip().strip('"\'') for m in methods_str.split(',')]
                for method in methods:
                    routes.append({
                        "method": method.upper(),
                        "path": path,
                        "description": f"{method} {path}",
                        "source_file": str(pyfile.relative_to(repo)),
                    })
        except Exception:
            continue
    return routes


def _extract_django_routes(repo: Path) -> list[dict]:
    routes = []
    for urlfile in repo.rglob("urls.py"):
        try:
            content = urlfile.read_text(encoding="utf-8", errors="ignore")
            paths = re.findall(r'path\(["\']([^"\']+)["\']', content)
            for p in paths:
                routes.append({
                    "method": "GET",
                    "path": f"/{p}",
                    "description": f"Django route: {p}",
                    "source_file": str(urlfile.relative_to(repo)),
                })
        except Exception:
            continue
    return routes


def _extract_generic_routes(repo: Path) -> list[dict]:
    """Generic fallback: scan all text files for HTTP method patterns."""
    routes = []
    http_pattern = re.compile(r'(GET|POST|PUT|DELETE|PATCH)\s+(/[/\w{}-]+)', re.IGNORECASE)
    for f in list(repo.rglob("*.py")) + list(repo.rglob("*.js")) + list(repo.rglob("*.ts")):
        if "node_modules" in str(f) or ".git" in str(f):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            for m in http_pattern.finditer(content):
                routes.append({
                    "method": m.group(1).upper(),
                    "path": m.group(2),
                    "description": f"{m.group(1)} {m.group(2)}",
                    "source_file": str(f.relative_to(repo)),
                })
        except Exception:
            continue
    # deduplicate
    return list({(r["method"], r["path"]): r for r in routes}.values())


def read_repo_context(repo_path: str, max_chars: int = 8000) -> str:
    """Read key files to give the LLM context about the app."""
    repo = Path(repo_path)
    context_parts = []

    priority_files = [
        "README.md", "readme.md",
        "package.json", "pyproject.toml", "setup.py",
        "main.py", "app.py", "index.js", "server.js",
    ]

    total = 0
    for filename in priority_files:
        for filepath in repo.glob(filename):
            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")[:2000]
                context_parts.append(f"=== {filename} ===\n{content}")
                total += len(content)
                if total > max_chars:
                    break
            except Exception:
                continue
        if total > max_chars:
            break

    return "\n\n".join(context_parts)


def generate_openapi_spec(routes: list[dict], repo_context: str, repo_url: str) -> dict:
    """Use Claude to generate a complete OpenAPI 3.0 spec from extracted routes."""
    if not routes:
        return _minimal_spec(repo_url)

    routes_summary = json.dumps(routes[:30], indent=2)

    prompt = f"""You are an expert API documentation engineer.

I have a GitHub repository at: {repo_url}

Here are the API routes I extracted from the codebase:
{routes_summary}

Here is some context about the app:
{repo_context[:3000]}

Generate a complete, valid OpenAPI 3.0 specification JSON for this API.

Rules:
- Use realistic request/response schemas based on the route names and context
- Add meaningful descriptions for each endpoint
- Include at least basic authentication if you see auth-related routes
- Use proper HTTP status codes in responses
- Make schemas realistic — e.g. if there's a /users route, include id, email, name fields
- Return ONLY valid JSON, no markdown, no explanation

The spec must have: openapi, info, paths, and components.schemas sections."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        spec = json.loads(raw)
        return spec
    except json.JSONDecodeError:
        return _minimal_spec(repo_url)


def _minimal_spec(repo_url: str) -> dict:
    """Fallback minimal spec when generation fails."""
    repo_name = repo_url.rstrip("/").split("/")[-1]
    return {
        "openapi": "3.0.0",
        "info": {"title": repo_name, "version": "1.0.0"},
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health check",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }


def infer_spec_from_repo(repo_path: str, repo_url: str) -> Optional[dict]:
    """
    Main entry point: given a cloned repo path, infer an OpenAPI spec.
    Returns the spec dict or None if inference fails.
    """
    print(f"[spec_inference] Detecting framework...")
    framework = detect_framework(repo_path)
    print(f"[spec_inference] Detected: {framework}")

    print(f"[spec_inference] Extracting routes...")
    routes = extract_routes_from_code(repo_path, framework)
    print(f"[spec_inference] Found {len(routes)} routes")

    print(f"[spec_inference] Reading repo context...")
    context = read_repo_context(repo_path)

    print(f"[spec_inference] Generating OpenAPI spec with LLM...")
    spec = generate_openapi_spec(routes, context, repo_url)

    return spec
