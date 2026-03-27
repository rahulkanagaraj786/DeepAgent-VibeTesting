# Demo Repos for Vibe Testing

Pre-baked test targets for the hackathon demo. Use these if live demo breaks.

## Recommended Test Repos

### 1. Express + JWT Auth (Node.js)
```
https://github.com/gothinkster/node-express-realworld-example-app
```
- Framework: Express.js
- Auth: JWT
- Known edge cases: missing auth headers, invalid tokens, empty article slugs
- Expected findings: auth bypass on some routes, missing rate limiting

### 2. FastAPI Full Stack (Python)
```
https://github.com/tiangolo/full-stack-fastapi-template
```
- Framework: FastAPI
- Auth: OAuth2 + JWT
- Known edge cases: user creation with duplicate email, permission escalation
- Expected findings: IDOR on user endpoints, weak password validation

## How to Run

1. Copy `.env.example` to `.env` and fill in your keys
2. Start the backend:
   ```bash
   cd blaxel-swagger-finder
   pip install -r requirements.txt
   python backend.py
   ```
3. Start the frontend:
   ```bash
   cd Columbia-Hackathon-Test-Pilot-Frontend
   npm install
   npm run dev
   ```
4. Open http://localhost:5173
5. Paste one of the repo URLs above and click "Start Pipeline"

## Expected Pipeline Output

For `node-express-realworld-example-app`:
- Framework detected: express
- Routes extracted: ~15 endpoints
- Spec inferred via LLM (no swagger.json in repo)
- Orchestrator: identifies auth flows as highest risk
- Deep reasoning: flags missing rate limiting on /api/users/login

For `full-stack-fastapi-template`:
- Framework detected: fastapi
- OpenAPI spec found at `/app/openapi.json`
- Orchestrator: identifies user management as highest risk
- Deep reasoning: flags potential IDOR on /api/v1/users/{user_id}

## Fallback Screenshots

If live demo breaks, screenshots are in `demo/screenshots/` (add manually after first run).
