"""
orchestrator.py — The "thinking" layer.
Analyzes the app and dispatches specialized sub-agents for different test strategies.
"""

import json
import os

import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

ORCHESTRATOR_SYSTEM_PROMPT = """You are a senior QA architect and security engineer.
Your job is to analyze an application's API spec and create a comprehensive,
prioritized test strategy.

You think like a curious, adversarial power user who wants to find every way
the app can fail. You are systematic, thorough, and you never just test the
happy path.

When given an OpenAPI spec, you must:
1. Identify what type of application this is
2. Identify the highest-risk user flows (payment, auth, data mutation)
3. Create specific test scenarios for 3 categories:
   - HAPPY_PATH: Core user journeys that must work
   - EDGE_CASES: Boundary conditions, invalid inputs, race conditions
   - SECURITY: Auth, authorization, injection, access control

Always output valid JSON matching the schema provided."""


def analyze_and_plan(openapi_spec: dict, repo_url: str) -> dict:
    """
    Orchestrator agent: analyze spec, return structured test plan.
    Returns dict with app_type, risk_ranking, and test_scenarios.
    """
    spec_summary = json.dumps(openapi_spec, indent=2)[:6000]

    prompt = f"""Analyze this OpenAPI spec for repo: {repo_url}

SPEC:
{spec_summary}

Return a JSON object with this exact structure:
{{
  "app_type": "e-commerce|social|fintech|saas|api|unknown",
  "app_description": "one sentence describing what this app does",
  "risk_ranking": ["highest risk flow", "second highest", "third"],
  "test_plan": {{
    "happy_path": [
      {{
        "name": "test name",
        "steps": ["step 1", "step 2", "step 3"],
        "endpoints": ["/endpoint1", "/endpoint2"],
        "expected": "what should happen"
      }}
    ],
    "edge_cases": [
      {{
        "name": "test name",
        "input": "what malformed/edge input to send",
        "endpoint": "/endpoint",
        "method": "POST",
        "expected_behavior": "what a well-built app should do",
        "likely_failure": "what might actually happen"
      }}
    ],
    "security": [
      {{
        "name": "test name",
        "attack_type": "auth_bypass|injection|idor|rate_limit|privilege_escalation",
        "endpoint": "/endpoint",
        "method": "GET",
        "description": "what we're testing"
      }}
    ]
  }},
  "reasoning": "2-3 sentences explaining your test strategy"
}}

Return ONLY the JSON, no markdown."""

    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=3000,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()

        plan = json.loads(raw)
        return plan
    except Exception as e:
        print(f"[orchestrator] Analysis failed: {e}")
        return {
            "app_type": "unknown",
            "app_description": "Could not analyze",
            "risk_ranking": ["general functionality"],
            "test_plan": {"happy_path": [], "edge_cases": [], "security": []},
            "reasoning": "Defaulting to generic test strategy",
        }


def format_plan_for_display(plan: dict) -> str:
    """Format orchestrator output as readable stream for frontend."""
    lines = [
        f"🧠 App Type: {plan.get('app_type', 'unknown').upper()}",
        f"📋 {plan.get('app_description', '')}",
        "",
        "⚠️  Risk Ranking:",
    ]
    for i, risk in enumerate(plan.get("risk_ranking", []), 1):
        lines.append(f"   {i}. {risk}")

    test_plan = plan.get("test_plan", {})
    lines += [
        "",
        f"✅ Happy Path Tests: {len(test_plan.get('happy_path', []))}",
        f"🔶 Edge Case Tests: {len(test_plan.get('edge_cases', []))}",
        f"🔴 Security Tests: {len(test_plan.get('security', []))}",
        "",
        f"💭 Strategy: {plan.get('reasoning', '')}",
        "",
        "🚀 Dispatching parallel sub-agents...",
    ]

    return "\n".join(lines)
