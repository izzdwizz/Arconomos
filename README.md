# Oikonomos (E-konomos)

An AI operator that holds, splits and grows a small business's USDC on Arc: every income deposit is divided into tax, bills, goals, owner pay and savings, and an agent adjusts those splits as it forecasts what is coming.

Built for the Tameion Agents Hackathon (Sep 27 – Oct 10, 2026), targeting RFB 01 (Intelligent Business Treasury) and RFB 04 (Autonomous Business Operator).

See [`docs/PRD.md`](docs/PRD.md) for the full product requirements and architecture.

## Repo layout

```
oikonomos/
├── contracts/            # Foundry: Vault, Inbox, VaultFactory, YieldPool, PayeeModule (v2)
│   ├── src/  test/  script/
├── backend/              # one Python package, three entry points
│   ├── app/api/          # FastAPI routes
│   ├── app/indexer/      # event polling, classification
│   ├── app/agent/        # forecast, planner, policy, executor, decision log
│   ├── app/chain/        # web3 clients, ABIs, Circle wallet signer
│   ├── app/db/           # models, migrations
│   └── tests/            # unit, integration (anvil + Postgres), scenarios
├── web/                  # Next.js app: setup wizard, dashboard, agent log
├── e2e/                  # Playwright against a local stack
└── .github/workflows/
```

## Getting started

- **Contracts:** `cd contracts && forge test`
- **Database:** `docker compose up -d postgres` (Postgres 16, exposed on `localhost:5433` to avoid clashing with a local Postgres on the default port)
- **Backend:**
  ```
  cd backend
  uv sync --extra dev
  cp .env.example .env   # DATABASE_URL points at the docker-compose Postgres above
  uv run alembic upgrade head
  uv run pytest -m "not integration"   # fast unit + API tests (SQLite in-memory)
  uv run pytest -m integration         # spins up its own throwaway Postgres via testcontainers
  uv run uvicorn app.api.main:app --reload
  ```
- **Web:** `cd web && npm install && npm run dev`

Funds never pass through our servers: they land in contracts the user owns, and the backend only reads the chain and sends operator calls the contracts allow.
