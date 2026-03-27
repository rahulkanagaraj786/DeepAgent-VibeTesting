"""AI Agent that tests cross-service integration via deployed MCP tools.

Uses DeepSeek-V3 via Featherless to simulate real user flows across
multiple microservices, calling MCP tools and validating responses.
Includes deep reasoning loop and TrueFoundry observability tracking.
"""

import json
import os
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
FEATHERLESS_MODEL = "deepseek-ai/DeepSeek-V3-0324"

# Anthropic client for reasoning loop
try:
    import anthropic
    _anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
except Exception:
    _anthropic_client = None


@dataclass
class ToolInfo:
    name: str
    description: str
    input_schema: dict
    server_name: str
    endpoint_url: str


@dataclass
class TestStep:
    action: str
    tool_name: str
    tool_args: dict
    expected: str = ""
    raw_response: str = ""
    parsed_result: dict = field(default_factory=dict)
    success: bool = False
    error: str = ""
    duration_ms: int = 0


@dataclass
class TestResult:
    test_name: str
    description: str
    steps: list = field(default_factory=list)
    passed: bool = False
    summary: str = ""
    narrative: str = ""
    analysis: str = ""
    duration_ms: int = 0
    # Deep reasoning fields
    root_cause: Optional[str] = None
    root_cause_location: Optional[str] = None
    fix_suggestion: Optional[str] = None
    fix_explanation: Optional[str] = None
    severity: str = "info"
    status: str = "passed"


def _call_mcp_tool(endpoint_url: str, tool_name: str, tool_args: dict) -> dict:
    """Call an MCP tool via the deployed endpoint (no auth needed for local)."""
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": tool_args},
        "id": int(time.time() * 1000),
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(endpoint_url, json=payload, headers=headers)
        text = resp.text
        for line in text.split("\n"):
            if line.startswith("data: "):
                return json.loads(line[6:])
        return {"raw": text}


def _list_mcp_tools(endpoint_url: str) -> list[dict]:
    """List tools from an MCP endpoint."""
    payload = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(endpoint_url, json=payload, headers=headers)
        text = resp.text
        for line in text.split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                return data.get("result", {}).get("tools", [])
    return []


def _call_llm(prompt: str, system: str = "") -> str:
    """Call DeepSeek-V3 via Featherless."""
    api_key = os.getenv("FEATHERLESS_API_KEY", "")
    if not api_key:
        raise RuntimeError("FEATHERLESS_API_KEY not set")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    with httpx.Client(timeout=120.0) as c:
        resp = c.post(
            f"{FEATHERLESS_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": FEATHERLESS_MODEL,
                "messages": messages,
                "max_tokens": 4096,
                "temperature": 0.1,
            },
        )
        resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def discover_tools(servers: list[dict], workspace: str = "") -> list[ToolInfo]:
    """Discover all available MCP tools from deployed servers."""
    all_tools = []

    for srv in servers:
        server_name = srv["server_name"]
        # Support both local and remote endpoints
        endpoint = srv.get("endpoint_url") or f"http://localhost:8000/mcp"
        logger.info(f"[agent_tester] Discovering tools from {server_name}...")

        try:
            tools = _list_mcp_tools(endpoint)
            for t in tools:
                all_tools.append(ToolInfo(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    server_name=server_name,
                    endpoint_url=endpoint,
                ))
                logger.info(f"[agent_tester]   Found tool: {t['name']}")
        except Exception as e:
            logger.error(f"[agent_tester]   Failed to discover tools from {server_name}: {e}")

    return all_tools


def generate_test_plan(tools: list[ToolInfo]) -> list[dict]:
    """Use LLM to generate a cross-service integration test plan."""
    tool_descriptions = []
    for t in tools:
        props = t.input_schema.get("properties", {})
        params = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in props.items())
        tool_descriptions.append(
            f"- {t.name} (service: {t.server_name}): {t.description}"
            + (f" | params: {params}" if params else " | no params")
        )

    prompt = f"""You are a QA engineer testing a microservices system. The following MCP tools are available:

{chr(10).join(tool_descriptions)}

Generate a JSON array of integration test cases that test the CROSS-SERVICE customer flow.
Each test simulates a real user interacting with these services.

For each test, provide:
- "test_name": short snake_case name
- "description": what this test validates from a user perspective
- "steps": array of objects with "tool_name", "args" (dict), "expected_behavior" (string)

Focus on:
1. Calling each service and verifying it responds (health check)
2. Cross-service flow: e.g. get inventory items, then check pricing for them
3. Edge cases: empty results, invalid params

Return ONLY valid JSON array. No prose."""

    try:
        raw = _call_llm(prompt, system="You are a QA test engineer. Return only valid JSON.")
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:])
            if raw.endswith("```"):
                raw = raw[:-3]
        tests = json.loads(raw)
        if isinstance(tests, list):
            return tests
    except Exception as e:
        logger.error(f"[agent_tester] LLM test plan failed: {e}")

    return _default_test_plan(tools)


def _default_test_plan(tools: list[ToolInfo]) -> list[dict]:
    """Generate a sensible default test plan without LLM."""
    tests = []
    steps = [{"tool_name": t.name, "args": {}, "expected_behavior": f"{t.name} should return a valid response"} for t in tools]
    tests.append({
        "test_name": "service_health_check",
        "description": "Verify all services respond to basic requests",
        "steps": steps,
    })
    if len(tools) >= 2:
        tests.append({
            "test_name": "cross_service_integration",
            "description": "Test cross-service data flow as a real user would",
            "steps": [{"tool_name": t.name, "args": {}, "expected_behavior": f"Call {t.name} and use result in next service call"} for t in tools],
        })
    return tests


def execute_test_plan(
    test_plan: list[dict],
    tools: list[ToolInfo],
    workspace: str = "",
    progress_callback=None,
) -> list[TestResult]:
    """Execute the test plan by calling MCP tools and evaluating results."""
    tool_map = {t.name: t for t in tools}
    results = []

    for ti, test in enumerate(test_plan):
        test_result = TestResult(
            test_name=test.get("test_name", f"test_{ti}"),
            description=test.get("description", ""),
        )
        test_start = time.time()
        all_steps_ok = True
        step_outputs = {}

        for si, step_def in enumerate(test.get("steps", [])):
            tool_name = step_def.get("tool_name", "")
            tool_args = step_def.get("args", {})
            expected = step_def.get("expected_behavior", "")

            action_desc = expected if expected else f"Call {tool_name}"
            if tool_args:
                args_str = ", ".join(f"{k}={v!r}" for k, v in tool_args.items())
                action_desc += f" with ({args_str})"

            step = TestStep(
                action=action_desc,
                tool_name=tool_name,
                tool_args=tool_args,
                expected=expected,
            )

            if tool_name not in tool_map:
                step.error = f"Unknown tool: {tool_name}"
                step.success = False
                all_steps_ok = False
                test_result.steps.append(step)
                continue

            tool_info = tool_map[tool_name]
            step_start = time.time()

            try:
                response = _call_mcp_tool(tool_info.endpoint_url, tool_name, tool_args)
                step.duration_ms = int((time.time() - step_start) * 1000)
                step.raw_response = json.dumps(response, indent=2)

                if "result" in response:
                    content = response["result"].get("content", [])
                    if content:
                        text_content = content[0].get("text", "")
                        step.parsed_result = {"text": text_content}
                        step_outputs[tool_name] = text_content
                        try:
                            parsed = json.loads(text_content)
                            if isinstance(parsed, dict) and ("error" in parsed or "detail" in parsed):
                                step.error = str(parsed.get("error") or parsed.get("detail"))
                                step.success = False
                                all_steps_ok = False
                            else:
                                step.success = True
                        except (json.JSONDecodeError, TypeError):
                            lower = text_content.lower()
                            if any(kw in lower for kw in ["error", "failed", "connection", "refused", "timeout", "unreachable"]):
                                step.error = text_content[:300]
                                step.success = False
                                all_steps_ok = False
                            else:
                                step.success = True
                    else:
                        step.error = "MCP tool returned empty response"
                        step.success = False
                        all_steps_ok = False
                elif "error" in response:
                    step.error = response["error"].get("message", str(response["error"]))
                    step.success = False
                    all_steps_ok = False
                else:
                    step.error = f"Unexpected response: {json.dumps(response)[:200]}"
                    step.success = False
                    all_steps_ok = False

            except Exception as e:
                step.duration_ms = int((time.time() - step_start) * 1000)
                step.error = str(e)
                step.success = False
                all_steps_ok = False

            test_result.steps.append(step)
            logger.info(
                f"[agent_tester]   [{test_result.test_name}] {step.action}: "
                f"{'PASS' if step.success else 'FAIL'} ({step.duration_ms}ms)"
                + (f" — {step.error}" if step.error else "")
            )

        test_result.duration_ms = int((time.time() - test_start) * 1000)
        test_result.passed = all_steps_ok
        test_result.status = "passed" if all_steps_ok else "failed"
        _analyze_test(test_result)
        results.append(test_result)

        if progress_callback:
            progress_callback(ti, len(test_plan), test_result)

    return results


def _analyze_test(test_result: TestResult) -> None:
    """Use LLM to generate a human-like narrative and analytical summary."""
    passed_count = sum(1 for s in test_result.steps if s.success)
    total = len(test_result.steps)

    step_details = []
    for s in test_result.steps:
        detail = f"- Action: {s.action}\n  Tool: {s.tool_name}\n  Result: {'SUCCESS' if s.success else 'FAILED'}\n  Duration: {s.duration_ms}ms"
        if s.error:
            detail += f"\n  Error: {s.error}"
        step_details.append(detail)

    prompt = f"""You are an experienced QA engineer writing up test results.
Test: "{test_result.test_name}" — {test_result.description}

Steps:
{chr(10).join(step_details)}

Overall: {passed_count}/{total} steps passed. Test {'PASSED' if test_result.passed else 'FAILED'}.

Return JSON:
{{
  "summary": "One-line result summary",
  "narrative": "2-3 sentence first-person narrative as a human QA tester",
  "analysis": "2-3 sentence analytical assessment with root cause and recommendation"
}}

Return ONLY valid JSON."""

    try:
        raw = _call_llm(prompt, system="You are a senior QA engineer. Return only valid JSON.")
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:])
            if raw.endswith("```"):
                raw = raw[:-3]
        parsed = json.loads(raw)
        test_result.summary = parsed.get("summary", "")
        test_result.narrative = parsed.get("narrative", "")
        test_result.analysis = parsed.get("analysis", "")
        return
    except Exception as e:
        logger.warning(f"[agent_tester] LLM analysis failed: {e}")

    # Fallback
    errors = [s.error for s in test_result.steps if s.error]
    if test_result.passed:
        test_result.summary = f"All {total} steps passed."
        test_result.narrative = f"I tested the {test_result.test_name} flow. All {total} tools responded with valid data."
        test_result.analysis = "All MCP tools are correctly deployed and upstream APIs returned valid responses."
    else:
        err_summary = "; ".join(errors[:2])
        test_result.summary = f"{passed_count}/{total} steps passed. Errors: {err_summary}"
        test_result.narrative = f"I attempted to test {test_result.test_name}. {total - passed_count}/{total} steps failed."
        test_result.analysis = "The MCP server infrastructure is deployed but upstream APIs are failing. Verify endpoint URLs and connectivity."


def run_deep_reasoning_loop(
    test_results: list[TestResult],
    openapi_spec: dict,
    max_iterations: int = 3,
) -> list[TestResult]:
    """
    Re-reasoning loop: analyze initial results, perform root cause analysis
    and fix suggestion on each bug found.
    """
    if not _anthropic_client:
        logger.warning("[reasoning_loop] Anthropic client not available, skipping deep reasoning")
        return test_results

    all_findings = list(test_results)

    for iteration in range(max_iterations):
        anomalies = [f for f in all_findings if f.status in ["error", "unexpected", "failed"] or not f.passed]

        if not anomalies:
            print(f"[reasoning_loop] Iteration {iteration+1}: No anomalies. Done.")
            break

        print(f"[reasoning_loop] Iteration {iteration+1}: Found {len(anomalies)} anomalies. Re-reasoning...")

        anomaly_context = json.dumps([
            {
                "test_name": f.test_name,
                "description": f.description,
                "summary": f.summary,
                "analysis": f.analysis,
                "errors": [s.error for s in f.steps if s.error],
            }
            for f in anomalies[:5]
        ], indent=2)

        spec_context = json.dumps(openapi_spec.get("paths", {}), indent=2)[:3000]

        try:
            response = _anthropic_client.messages.create(
                model="claude-opus-4-5",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": f"""You are debugging a failing application. Here are anomalies found during testing:

{anomaly_context}

API Spec context:
{spec_context}

For each anomaly:
1. What is the ROOT CAUSE likely to be?
2. What is the EXACT FIX (with code snippet if possible)?
3. What is the SEVERITY? (critical/warning/info)

Return JSON array:
[
  {{
    "anomaly_id": "reference the test name",
    "root_cause": "specific explanation",
    "root_cause_location": "file.py:line_number or component name",
    "fix_suggestion": "exact code or configuration change",
    "severity": "critical|warning|info",
    "fix_explanation": "why this fix works"
  }}
]

Return ONLY JSON.""",
                }],
            )

            raw = response.content[0].text.strip().replace("```json", "").replace("```", "")
            deep_analysis = json.loads(raw)

            for analysis in deep_analysis:
                for finding in all_findings:
                    if finding.test_name == analysis.get("anomaly_id"):
                        finding.root_cause = analysis.get("root_cause")
                        finding.root_cause_location = analysis.get("root_cause_location")
                        finding.fix_suggestion = analysis.get("fix_suggestion")
                        finding.fix_explanation = analysis.get("fix_explanation")
                        finding.severity = analysis.get("severity", "warning")

        except Exception as e:
            print(f"[reasoning_loop] Parse error: {e}")

        new_critical = [f for f in all_findings if f.severity == "critical" and f.root_cause]
        if not new_critical:
            break

    return all_findings


def generate_final_report(findings: list[TestResult], test_plan: dict, repo_url: str) -> dict:
    """Generate the final structured bug report."""
    critical = [f for f in findings if f.severity == "critical"]
    warnings = [f for f in findings if f.severity == "warning"]
    info = [f for f in findings if f.severity == "info"]
    passed = [f for f in findings if f.passed]

    return {
        "repo_url": repo_url,
        "summary": {
            "total_flows_tested": len(findings),
            "critical_bugs": len(critical),
            "warnings": len(warnings),
            "passed": len(passed),
        },
        "critical_bugs": [
            {
                "test_name": f.test_name,
                "description": f.description,
                "root_cause": f.root_cause,
                "root_cause_location": f.root_cause_location,
                "fix_suggestion": f.fix_suggestion,
                "severity": f.severity,
            }
            for f in critical
        ],
        "warnings": [
            {
                "test_name": f.test_name,
                "summary": f.summary,
                "severity": f.severity,
            }
            for f in warnings
        ],
        "passed_tests": [{"test_name": f.test_name, "duration_ms": f.duration_ms} for f in passed],
        "fix_suggestions": [
            {
                "location": f.root_cause_location,
                "fix": f.fix_suggestion,
                "explanation": f.fix_explanation,
            }
            for f in findings if f.fix_suggestion
        ],
    }


def run_agent_tests_with_tracking(repo_url: str, mcp_endpoint: str, test_results_summary: dict) -> None:
    """Log test run metrics to TrueFoundry ML tracking."""
    try:
        import truefoundry.ml as tfy
        tfy.init(ml_repo="vibe-testing", auto_end_run=True)
        run = tfy.create_run(
            ml_repo="vibe-testing",
            run_name=f"test-{repo_url.split('/')[-1]}-{int(time.time())}",
        )
        run.log_params({"repo_url": repo_url, "mcp_endpoint": mcp_endpoint})
        run.log_metrics({
            "bugs_found_critical": test_results_summary.get("critical", 0),
            "bugs_found_warning": test_results_summary.get("warnings", 0),
            "flows_tested": test_results_summary.get("flows_tested", 0),
            "test_duration_seconds": test_results_summary.get("duration", 0),
        })
    except Exception as e:
        print(f"[agent_tester] TrueFoundry tracking error (non-fatal): {e}")


def run_agent_tests(
    servers: list[dict],
    workspace: str = "",
    progress_callback=None,
) -> list[TestResult]:
    """Full agent testing flow: discover → plan → execute → report."""
    logger.info("[agent_tester] Starting AI agent integration tests...")

    tools = discover_tools(servers, workspace)
    if not tools:
        logger.error("[agent_tester] No tools discovered from deployed servers.")
        return []

    logger.info(f"[agent_tester] Discovered {len(tools)} tools across {len(servers)} services")

    test_plan = generate_test_plan(tools)
    logger.info(f"[agent_tester] Generated {len(test_plan)} test cases")

    results = execute_test_plan(test_plan, tools, workspace, progress_callback)

    passed = sum(1 for r in results if r.passed)
    logger.info(f"[agent_tester] Tests complete: {passed}/{len(results)} passed")

    return results
