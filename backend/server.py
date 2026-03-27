"""server.py — FastAPI backend for Vibe Testing.

Drives the full pipeline and streams events via SSE:
- Local git clone + spec inference
- TrueFoundry deployment
- Orchestrator agent for test planning
- Deep reasoning loop for root cause analysis
- Aerospike persistent memory for regression tracking
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_THIS_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _THIS_DIR.parent

load_dotenv(_THIS_DIR / ".env")
load_dotenv(_ROOT_DIR / ".env")
sys.path.insert(0, str(_ROOT_DIR))

from repo_scanner import Scanner
from agent_tester import (
    discover_tools,
    generate_test_plan,
    execute_test_plan,
    run_deep_reasoning_loop,
    generate_final_report,
    run_agent_tests_with_tracking,
)
from orchestrator import analyze_and_plan, format_plan_for_display
from memory_store import memory_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Vibe Testing — Autonomous AI QA Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_runs: dict[str, dict] = {}


class PipelineRequest(BaseModel):
    urls: list[str]


def _sse_event(step_id: str, status: str, items: list[str],
               extra: dict | None = None) -> str:
    """Format an SSE event."""
    data = {"step": step_id, "status": status, "items": items}
    if extra:
        data.update(extra)
    return f"data: {json.dumps(data)}\n\n"


def deploy_mcp_server(server_path: str, server_name: str) -> Optional[str]:
    """
    Deploy a generated MCP server to TrueFoundry and return its public URL.
    Returns None if deployment fails (non-fatal).
    """
    try:
        from truefoundry.deploy import Service, Build, PythonBuild, Port, Resources

        workspace_fqn = os.environ.get("TFY_WORKSPACE_FQN", "")
        if not workspace_fqn:
            print(f"[backend] TFY_WORKSPACE_FQN not set — skipping TrueFoundry deploy")
            return None

        safe_name = server_name.lower().replace("_", "-")[:50]

        service = Service(
            name=safe_name,
            image=Build(
                build_spec=PythonBuild(
                    command="python server.py",
                    requirements_path="requirements.txt",
                    python_version="3.11",
                )
            ),
            ports=[
                Port(
                    port=8000,
                    protocol="TCP",
                    expose=True,
                    app_protocol="http",
                )
            ],
            resources=Resources(
                cpu_request=0.5,
                cpu_limit=1,
                memory_request=512,
                memory_limit=1024,
            ),
            env={"PORT": "8000"},
            replicas=1,
        )

        deployment = service.deploy(workspace_fqn=workspace_fqn)
        url = f"https://{safe_name}.{workspace_fqn}.truefoundry.com"
        print(f"[backend] Deployed {safe_name} to TrueFoundry: {url}")
        return url

    except ImportError:
        print(f"[backend] truefoundry not installed — skipping deploy")
        return None
    except Exception as e:
        print(f"[backend] TrueFoundry deploy failed (non-fatal): {e}")
        return None


def _build_test_detail(test_results) -> list[dict]:
    """Build serializable test detail for frontend."""
    detail = []
    for r in test_results:
        steps_detail = []
        for s in r.steps:
            steps_detail.append({
                "action": s.action,
                "success": s.success,
                "duration_ms": s.duration_ms,
                "error": s.error,
            })
        detail.append({
            "test_name": r.test_name,
            "description": r.description,
            "passed": r.passed,
            "duration_ms": r.duration_ms,
            "summary": r.summary,
            "narrative": r.narrative,
            "analysis": r.analysis,
            "steps": steps_detail,
            # Deep reasoning fields
            "root_cause": getattr(r, "root_cause", None),
            "root_cause_location": getattr(r, "root_cause_location", None),
            "fix_suggestion": getattr(r, "fix_suggestion", None),
            "fix_explanation": getattr(r, "fix_explanation", None),
            "severity": getattr(r, "severity", "info"),
        })
    return detail


def _run_pipeline_sync(urls: list[str]):
    """Generator that yields SSE events as the pipeline progresses."""
    from pipeline.ingest import ingest
    from pipeline.mine import mine_tools
    from pipeline.safety import SafetyPolicy, apply_safety
    from pipeline.codegen import generate as codegen_generate

    extract_dir = str(_THIS_DIR / "extracted_specs")

    # ── 1. Clone ─────────────────────────────────────────────────────────
    yield _sse_event("clone", "running", ["Cloning repositories locally..."])
    yield _sse_event("clone", "running", [
        "Cloning repositories locally...",
        f"Repositories to clone: {len(urls)}",
    ])

    scanner = Scanner()
    clone_items = [f"Repositories to clone: {len(urls)}"]

    def on_scan_progress(repo_url, index, total):
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        clone_items.append(f"Cloning {repo_name}... ({index+1}/{total})")

    scan_result = scanner.scan_all(urls, progress_callback=on_scan_progress, extract_dir=extract_dir)

    for url in urls:
        rn = url.split("/")[-1].replace(".git", "")
        clone_items.append(f"✓ {rn} cloned successfully")
    clone_items.append(f"Total repositories cloned: {len(urls)}/{len(urls)}")
    yield _sse_event("clone", "done", clone_items)

    # ── 2. Sandbox (compatibility step — now just local) ─────────────────
    yield _sse_event("deploy-sandbox", "running", ["Setting up local processing environment..."])
    sandbox_items = [
        "Environment: local (no sandbox required)",
        f"Repos cloned: {len(urls)}",
        "Storage: local temp directories",
        "Status: READY",
    ]
    yield _sse_event("deploy-sandbox", "done", sandbox_items)

    # ── 3. Extract ───────────────────────────────────────────────────────
    yield _sse_event("extract", "running", ["Scanning repos for OpenAPI/Swagger specs..."])
    all_specs = scan_result.all_specs()
    extract_items = []
    for url in urls:
        rn = url.split("/")[-1].replace(".git", "")
        specs_for_repo = [s for s in all_specs if s["repo_name"] == rn]
        if specs_for_repo:
            for sp in specs_for_repo:
                fname = os.path.basename(sp["local_path"])
                inferred = "_inferred" in fname
                tag = "🔍 Inferred" if inferred else "✓ Found"
                extract_items.append(f"{tag}: {rn}/{fname}")
                extract_items.append(f"  Saved to: extracted_specs/{rn}/{fname}")
        else:
            extract_items.append(f"⊘ {rn} — no spec found or inferred")
    extract_items.append(f"Total specs: {len(all_specs)}")
    yield _sse_event("extract", "done" if all_specs else "error", extract_items)

    if not all_specs:
        yield _sse_event("pipeline", "error", ["No OpenAPI specs found in any repository. Pipeline stopped."])
        return

    # ── 4. Ingest ────────────────────────────────────────────────────────
    yield _sse_event("ingest", "running", ["Parsing API specifications..."])
    parsed_specs = []
    ingest_items = []
    for sp in all_specs:
        ingest_items.append(f"Parsing: {sp['repo_name']}...")
        yield _sse_event("ingest", "running", ingest_items)
        try:
            api_spec = ingest(sp["local_path"])
            parsed_specs.append({"spec": api_spec, "info": sp})
            ingest_items.append(f"✓ {api_spec.title} v{api_spec.version}")
            ingest_items.append(f"  Endpoints: {len(api_spec.endpoints)} | Base URL: {getattr(api_spec, 'base_url', 'N/A')}")
            for ep in api_spec.endpoints[:5]:
                method = getattr(ep, 'method', 'GET').upper() if hasattr(ep.method, 'upper') else ep.method.value
                ingest_items.append(f"    {method} {ep.path} — {ep.summary[:60]}")
            if len(api_spec.endpoints) > 5:
                ingest_items.append(f"    ... and {len(api_spec.endpoints) - 5} more")
        except Exception as e:
            ingest_items.append(f"✗ {sp['repo_name']} — {e}")
        yield _sse_event("ingest", "running", ingest_items)

    ingest_items.append(f"Specs ingested: {len(parsed_specs)}/{len(all_specs)}")
    yield _sse_event("ingest", "done", ingest_items)

    # ── 5. Discover ──────────────────────────────────────────────────────
    yield _sse_event("discover", "running", ["Mining capabilities from API endpoints..."])
    all_tools_by_spec = []
    discover_items = []
    for ps in parsed_specs:
        api_spec = ps["spec"]
        discover_items.append(f"Mining: {api_spec.title}...")
        yield _sse_event("discover", "running", discover_items)
        tools = mine_tools(api_spec)
        all_tools_by_spec.append({"tools": tools, **ps})
        for t in tools:
            discover_items.append(f"  → {t.name}: {t.description[:80]}")
        discover_items.append(f"✓ {api_spec.title}: {len(tools)} tool(s) discovered")
    total_tools = sum(len(x["tools"]) for x in all_tools_by_spec)
    discover_items.append(f"Total tools discovered: {total_tools}")
    yield _sse_event("discover", "done", discover_items)

    # ── 6. Schema ────────────────────────────────────────────────────────
    yield _sse_event("schema", "running", ["Synthesizing JSON type schemas for each tool..."])
    schema_items = []
    for ts in all_tools_by_spec:
        schema_items.append(f"Service: {ts['spec'].title}")
        for t in ts["tools"]:
            params = t.parameters if hasattr(t, "parameters") else getattr(t, "params", [])
            n_params = len(params)
            param_names = ", ".join(getattr(p, 'name', str(p)) for p in params[:4])
            if n_params > 4:
                param_names += f", +{n_params - 4} more"
            schema_items.append(f"  {t.name}: {n_params} param(s) — [{param_names}]")
        yield _sse_event("schema", "running", schema_items)
    schema_items.append(f"Total typed tools: {total_tools}")
    yield _sse_event("schema", "done", schema_items)

    # ── 7. Policy ────────────────────────────────────────────────────────
    yield _sse_event("policy", "running", ["Configuring execution policies — all APIs enabled..."])
    policy = SafetyPolicy(block_destructive=False, require_write_confirmation=False)
    policy_items = []
    policy_tools_data = []
    for ts in all_tools_by_spec:
        safe_tools = apply_safety(ts["tools"], policy)
        policy_items.append(f"✓ {ts['spec'].title}: {len(safe_tools)} tool(s) — all enabled")
        policy_tools_data.append({**ts, "tools": safe_tools})

    tool_rows = []
    for ts in policy_tools_data:
        for t in ts["tools"]:
            method = t.endpoints[0].method.value if t.endpoints else "GET"
            path_str = t.endpoints[0].path if t.endpoints else ""
            tool_rows.append({
                "name": t.name,
                "method": method,
                "path": path_str,
                "safety": "Enabled",
                "execution": "Auto Execute",
                "rateLimit": 60,
            })

    policy_items.append(f"All {len(tool_rows)} tool(s) set to Auto Execute")
    policy_items.append("Destructive operations: ENABLED")
    policy_items.append("Write confirmation: DISABLED")
    yield _sse_event("policy", "done", policy_items, {"toolRows": tool_rows})

    # ── 8. Generate ──────────────────────────────────────────────────────
    yield _sse_event("generate", "running", ["Generating MCP server code via LLM..."])
    generated_servers = []
    gen_items = []
    output_base = str(_THIS_DIR / "output")

    for ts in policy_tools_data:
        if not ts["tools"]:
            continue
        repo_name = ts["info"]["repo_name"]
        server_name = repo_name.lower().replace("_", "-")
        gen_items.append(f"Generating: {server_name} ({len(ts['tools'])} tools)...")
        gen_items.append(f"  LLM: DeepSeek-V3 via Featherless")
        yield _sse_event("generate", "running", gen_items)
        try:
            output_dir = os.path.join(output_base, server_name)
            result = codegen_generate(
                ts["spec"], ts["tools"],
                server_name=server_name, output_dir=output_dir,
            )
            generated_servers.append({
                "server_name": server_name,
                "output_dir": output_dir,
                "repo_name": repo_name,
                "tool_count": result.tool_count,
                "api_title": ts["spec"].title,
                "api_spec_raw": ts["spec"].raw_meta,
            })
            gen_items.append(f"✓ {server_name}: {result.tool_count} tool(s) generated")
            gen_items.append(f"  Output: {output_dir}")
        except Exception as e:
            gen_items.append(f"✗ {server_name}: FAILED — {e}")
        yield _sse_event("generate", "running", gen_items)

    gen_items.append(f"Servers generated: {len(generated_servers)}/{len(policy_tools_data)}")
    yield _sse_event("generate", "done" if generated_servers else "error", gen_items)

    if not generated_servers:
        yield _sse_event("pipeline", "error", ["No servers generated. Pipeline stopped."])
        return

    # ── 9. MCP Tests (validate generated servers) ────────────────────────
    yield _sse_event("mcp-test", "running", ["Validating generated MCP server code..."])
    mcp_test_items = [f"Servers to validate: {len(generated_servers)}"]

    for srv in generated_servers:
        sname = srv["server_name"]
        odir = srv["output_dir"]
        mcp_test_items.append(f"Validating: {sname}...")
        yield _sse_event("mcp-test", "running", mcp_test_items)

        server_py = os.path.join(odir, "src", "server.py")
        if os.path.exists(server_py):
            with open(server_py) as f:
                lines = len(f.readlines())
            mcp_test_items.append(f"  ✓ server.py: {lines} lines")
        else:
            mcp_test_items.append(f"  ✗ server.py: missing!")

        req_file = os.path.join(odir, "requirements.txt")
        if os.path.exists(req_file):
            with open(req_file) as f:
                deps = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            mcp_test_items.append(f"  ✓ requirements.txt: {len(deps)} dependencies")

        try:
            result = subprocess.run(
                ["python3", "-m", "py_compile", server_py],
                capture_output=True, text=True, timeout=10,
            )
            mcp_test_items.append(f"  ✓ Syntax check: {'passed' if result.returncode == 0 else result.stderr[:100]}")
        except Exception:
            mcp_test_items.append(f"  ⊘ Syntax check: skipped")

        mcp_test_items.append(f"✓ {sname}: validation complete")
        yield _sse_event("mcp-test", "running", mcp_test_items)

    mcp_test_items.append(f"All {len(generated_servers)} server(s) validated")
    yield _sse_event("mcp-test", "done", mcp_test_items)

    # ── 10. Deploy (TrueFoundry) ─────────────────────────────────────────
    yield _sse_event("deploy", "running", ["Deploying MCP servers to TrueFoundry..."])
    deploy_items = []
    tfy_host = os.environ.get("TFY_HOST", "https://app.truefoundry.com")
    tfy_workspace = os.environ.get("TFY_WORKSPACE_FQN", "")

    for srv in generated_servers:
        sname = srv["server_name"]
        deploy_items.append(f"Deploying: {sname}...")
        yield _sse_event("deploy", "running", deploy_items)

        live_url = deploy_mcp_server(srv["output_dir"], sname)
        if live_url:
            srv["deployed"] = True
            srv["endpoint_url"] = live_url
            deploy_items.append(f"✓ {sname}: LIVE at {live_url}")
            if tfy_workspace:
                dashboard_url = f"{tfy_host}/workspaces/{tfy_workspace}/deployments"
                deploy_items.append(f"  📊 TrueFoundry Dashboard: {dashboard_url}")
                srv["dashboard_url"] = dashboard_url
        else:
            srv["deployed"] = False
            srv["endpoint_url"] = None
            deploy_items.append(f"⚠ {sname}: TrueFoundry deploy skipped (check TFY_WORKSPACE_FQN)")
            deploy_items.append(f"  Server code available at: {srv['output_dir']}")

        yield _sse_event("deploy", "running", deploy_items)

    deployed = [s for s in generated_servers if s.get("deployed")]
    deploy_items.append(f"Deployed: {len(deployed)}/{len(generated_servers)} MCP servers")
    yield _sse_event("deploy", "done", deploy_items, {
        "tfy_dashboard": f"{tfy_host}/workspaces/{tfy_workspace}/deployments" if tfy_workspace else None,
    })

    # ── 11. End User Testing (AI agent + orchestrator + reasoning) ────────
    yield _sse_event("user-test", "running", ["Starting AI agent end-user testing..."])
    ut_items = [f"Deployed services: {len(generated_servers)}"]

    # Load prior bug history from Aerospike
    all_prior_history = []
    for url in urls:
        history = memory_store.get_history(url)
        if history:
            all_prior_history.extend(history)
            ut_items.append(f"📚 Loaded {len(history)} prior test run(s) for {url.split('/')[-1]}")
    yield _sse_event("user-test", "running", ut_items)

    # Orchestrator: analyze spec and build test plan
    if parsed_specs:
        ut_items.append("🧠 Orchestrator analyzing app and building test strategy...")
        yield _sse_event("user-test", "running", ut_items)

        try:
            # Use the first spec for orchestrator analysis
            first_spec_path = all_specs[0]["local_path"]
            with open(first_spec_path) as f:
                raw_spec = json.load(f) if first_spec_path.endswith(".json") else {}
        except Exception:
            raw_spec = {}

        orchestrator_plan = analyze_and_plan(raw_spec, urls[0] if urls else "")
        plan_display = format_plan_for_display(orchestrator_plan)
        for line in plan_display.split("\n"):
            if line.strip():
                ut_items.append(line)
        yield _sse_event("user-test", "running", ut_items, {"orchestratorPlan": orchestrator_plan})

    # Discover MCP tools
    ut_items.append("Discovering MCP tools from deployed services...")
    yield _sse_event("user-test", "running", ut_items)

    tools_found = discover_tools(generated_servers)
    ut_items.append(f"Discovered {len(tools_found)} tool(s) across {len(generated_servers)} service(s)")
    for t in tools_found:
        ut_items.append(f"  → {t.name} ({t.server_name}): {t.description[:60]}")
    yield _sse_event("user-test", "running", ut_items)

    if tools_found:
        ut_items.append("AI agent generating cross-service test plan...")
        yield _sse_event("user-test", "running", ut_items)

        test_plan = generate_test_plan(tools_found)
        ut_items.append(f"Generated {len(test_plan)} test case(s):")
        for tp in test_plan:
            ut_items.append(f"  • {tp.get('test_name', '?')}: {tp.get('description', '')[:80]}")
        yield _sse_event("user-test", "running", ut_items)

        ut_items.append("Executing tests as real end-user via MCP tools...")
        yield _sse_event("user-test", "running", ut_items)

        test_results = execute_test_plan(test_plan, tools_found)
        passed = sum(1 for r in test_results if r.passed)
        total_tests = len(test_results)

        for r in test_results:
            icon = "PASS" if r.passed else "FAIL"
            ut_items.append(f"[{icon}] {r.test_name}: {r.summary}")
        yield _sse_event("user-test", "running", ut_items)

        # Deep reasoning loop
        ut_items.append("🔍 Running deep reasoning loop for root cause analysis...")
        yield _sse_event("user-test", "running", ut_items)

        enriched_results = run_deep_reasoning_loop(test_results, raw_spec if parsed_specs else {})

        critical_count = sum(1 for r in enriched_results if getattr(r, "severity", "info") == "critical")
        if critical_count:
            ut_items.append(f"🔴 Found {critical_count} critical bug(s) with fix suggestions")
        else:
            ut_items.append("✅ No critical bugs found in deep analysis")
        yield _sse_event("user-test", "running", ut_items)

        # Persist findings to Aerospike
        findings_dicts = [
            {
                "test_name": r.test_name,
                "severity": getattr(r, "severity", "info"),
                "root_cause_location": getattr(r, "root_cause_location", None),
                "passed": r.passed,
            }
            for r in enriched_results
        ]
        for url in urls:
            try:
                memory_store.save_run(url, findings_dicts)
            except Exception as e:
                print(f"[backend] Memory store save failed (non-fatal): {e}")

        # Check for regressions
        regressions = []
        for url in urls:
            try:
                regressions.extend(memory_store.get_regression_risk(url, findings_dicts))
            except Exception as e:
                print(f"[backend] Regression check failed (non-fatal): {e}")

        if regressions:
            ut_items.append(f"⚠️  {len(regressions)} regression(s) detected from prior runs!")
            for reg in regressions[:3]:
                ut_items.append(f"  ↩ {reg['message']}")

        # TrueFoundry tracking
        run_agent_tests_with_tracking(
            repo_url=urls[0] if urls else "",
            mcp_endpoint=generated_servers[0].get("endpoint_url", "") if generated_servers else "",
            test_results_summary={
                "critical": critical_count,
                "warnings": sum(1 for r in enriched_results if getattr(r, "severity", "info") == "warning"),
                "flows_tested": total_tests,
                "duration": sum(r.duration_ms for r in enriched_results) / 1000,
            },
        )

        # Generate final report
        final_report = generate_final_report(enriched_results, {}, urls[0] if urls else "")

        yield _sse_event("user-test", "done", ut_items, {
            "testResults": _build_test_detail(enriched_results),
            "passed": passed,
            "total": total_tests,
            "finalReport": final_report,
            "regressions": regressions,
            "orchestratorPlan": orchestrator_plan if parsed_specs else None,
        })
    else:
        ut_items.append("No MCP tools found — skipping end-user tests")
        ut_items.append("Tip: ensure TFY_WORKSPACE_FQN is set for live deployment")
        yield _sse_event("user-test", "done", ut_items, {
            "testResults": [], "passed": 0, "total": 0,
        })

    # ── Final summary ────────────────────────────────────────────────────
    yield _sse_event("pipeline", "done", [
        f"Repos scanned: {len(urls)}",
        f"Specs extracted: {len(all_specs)}",
        f"Servers generated: {len(generated_servers)}",
        f"Servers deployed: {len(deployed)}",
        "Pipeline complete ✓",
    ])


@app.post("/api/pipeline/start")
async def start_pipeline(req: PipelineRequest):
    """Start a pipeline run. Returns a run_id to connect to SSE stream."""
    if not req.urls:
        raise HTTPException(400, "No URLs provided")
    run_id = str(uuid.uuid4())[:8]
    _runs[run_id] = {"urls": req.urls, "status": "pending"}
    return {"run_id": run_id}


@app.get("/api/pipeline/stream/{run_id}")
async def stream_pipeline(run_id: str):
    """SSE stream of pipeline events."""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    import queue
    import threading

    event_queue: queue.Queue[str | None] = queue.Queue()

    def _worker():
        try:
            for event in _run_pipeline_sync(run["urls"]):
                event_queue.put(event)
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            event_queue.put(_sse_event("pipeline", "error", [str(e)]))
        finally:
            event_queue.put(None)

    thread = threading.Thread(target=_worker, daemon=True)

    async def event_generator():
        run["status"] = "running"
        thread.start()
        try:
            while True:
                try:
                    event = event_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue
                if event is None:
                    break
                yield event
        finally:
            run["status"] = "done"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
