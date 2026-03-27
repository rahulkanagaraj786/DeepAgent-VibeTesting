# Vibe Testing

**Autonomous AI QA agent — stress-test any GitHub repo end-to-end with zero manual setup.**

Built for the **Deep Agents Hackathon**. Paste a GitHub URL, and Vibe Testing clones the repo, infers the API spec, generates an MCP server, deploys it to TrueFoundry, then runs a deep-reasoning AI agent to find bugs and suggest exact fixes.

---

## Repository Structure

```
vibe-testing/
├── backend/                        # FastAPI server + agent pipeline
│   ├── server.py                   #   Main API server (SSE streaming)
│   ├── repo_scanner.py             #   Git clone + spec discovery
│   ├── orchestrator.py             #   AI test strategy planner
│   ├── agent_tester.py             #   MCP tool executor + deep reasoning loop
│   ├── memory_store.py             #   Aerospike persistent bug memory
│   └── requirements.txt
│
├── pipeline/                       # Core processing library
│   ├── spec_inference.py           #   Infer OpenAPI spec from any codebase (LLM)
│   ├── ingest.py                   #   Parse OpenAPI 3.x / Swagger 2.x / Postman
│   ├── mine.py                     #   Discover MCP tools from endpoints
│   ├── safety.py                   #   Safety classification & execution policy
│   ├── codegen.py                  #   LLM-powered MCP server code generation
│   ├── models.py                   #   Shared data models
│   └── logger.py                   #   Logging setup
│
├── frontend/                       # React + Vite UI
│   ├── src/
│   │   ├── components/
│   │   │   ├── pipeline/           #   Pipeline UI (sidebar, stepper, step content)
│   │   │   └── ui/                 #   shadcn/ui components
│   │   ├── hooks/
│   │   │   └── usePipeline.ts      #   SSE-driven pipeline state
│   │   └── pages/
│   │       ├── Index.tsx           #   Landing page
│   │       └── Pipeline.tsx        #   Main pipeline page
│   └── package.json
│
├── demo/                           # Pre-baked demo repos + instructions
├── examples/                       # Sample OpenAPI specs
├── generate.py                     # CLI: spec → MCP server (standalone)
└── .env.example                    # All required environment variables
```

## How It Works

```
  GitHub Repo URL
        │
        ▼
  ┌─────────────────┐
  │  Clone          │  git clone --depth 1
  └──────┬──────────┘
         ▼
  ┌─────────────────┐
  │  Spec Inference │  Find OpenAPI spec OR infer from code via Claude
  └──────┬──────────┘
         ▼
  ┌─────────────────┐
  │  Ingest         │  Parse endpoints, schemas, auth
  └──────┬──────────┘
         ▼
  ┌─────────────────┐
  │  Discover       │  Mine MCP tool capabilities
  └──────┬──────────┘
         ▼
  ┌─────────────────┐
  │  Generate       │  DeepSeek-V3 → FastMCP server.py
  └──────┬──────────┘
         ▼
  ┌─────────────────┐
  │  Deploy         │  TrueFoundry (with live observability)
  └──────┬──────────┘
         ▼
  ┌─────────────────┐
  │  Orchestrate    │  Claude plans happy path + edge cases + security tests
  └──────┬──────────┘
         ▼
  ┌─────────────────┐
  │  Deep Reasoning │  Root cause analysis + exact fix suggestions per bug
  └──────┬──────────┘
         ▼
  ┌─────────────────┐
  │  Memory         │  Aerospike tracks regressions across runs
  └──────┬──────────┘
         ▼
  Bug report with fix suggestions
```

## Quick Start

### 1. Environment

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, TFY_API_KEY, TFY_WORKSPACE_FQN, FEATHERLESS_API_KEY
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
python server.py
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:8080**, paste a GitHub repo URL, click "Start Testing".

### Standalone CLI

```bash
python generate.py examples/sample.yaml
python generate.py https://petstore.swagger.io/v2/swagger.json --name petstore
```

## Tech Stack

| Layer | Technology |
|---|---|
| AI / LLM | Claude (Anthropic) — orchestration, spec inference, reasoning |
| Code Gen | DeepSeek-V3 via Featherless |
| Deployment | TrueFoundry |
| Memory | Aerospike (regression tracking) |
| Backend | Python, FastAPI, SSE streaming |
| Frontend | React, Vite, TailwindCSS, shadcn/ui |
| Protocol | MCP (Model Context Protocol) via FastMCP |
