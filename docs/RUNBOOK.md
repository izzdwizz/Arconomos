# Running Oikonomos locally

This document walks through everything needed to bring the whole system up on your own
machine — the contracts, the Postgres database, the FastAPI backend, the agent/indexer
worker, and the Next.js web app — and then to actually exercise it end to end by hand: sign
in, create a vault, send it money, watch the indexer notice the deposit and the agent make
a decision, and read that decision back out through the API. It is written for someone
doing this for the first time, so it favours spelling things out over brevity. Where a step
only needs to be done once (installing a tool, running a migration for the first time) that
is called out explicitly, so you can skip straight to the "day to day" commands once your
machine is set up.

Read the [PRD](PRD.md) first if you have not already — this document assumes you know what
a vault, an inbox, a bucket and the agent's decision log are, and focuses purely on the
mechanics of running the software.

Before you start, it is worth knowing plainly what is finished and what is not, so nothing
below surprises you:

- The contracts, the database schema, and the backend API (auth, dashboard, decisions,
  rules, tax, bills, goals, vault deployment, integrations) are implemented and tested.
- The agent's cycle (forecast → policy check → chain action → decision log) and the
  indexer's chain-wide deposit scanner are implemented, tested against a live local chain,
  and wired into a recurring scheduler.
- The web app has a landing page and a dashboard page (balances and the agent's decision
  log feed), themed to match the Arc-402 paywall frontend. **It does not yet have a setup
  wizard screen** — creating a vault today means calling the API directly (with `curl`, as
  this document shows), not clicking through a form.
- The backend's Privy authentication is **stubbed**, not real, for local development: it
  accepts any bearer token of the exact shape `stub:<any-id>:<a wallet address>` and treats
  it as an authenticated session. It does **not** yet verify real Privy-issued JWTs. This
  matters a lot for how you test end to end — see the callout in
  [Section 5](#5-a-note-on-privy-and-why-you-should-test-the-api-directly-for-now) before
  you try wiring the web app's real sign-in flow to the backend, because right now that
  combination will not work: the web app will authenticate you with the real Privy service,
  but the backend will reject the resulting token.
- The `e2e/` Playwright suite is designed in the PRD but intentionally not built yet (the
  CI workflow's `e2e` job was removed for the same reason) — paused by request while this
  document was written instead.

None of that blocks you from running the whole system and watching it work — it just means
the way you will drive it today is mostly through `curl` and `cast` rather than clicking
buttons in a browser. That is exactly what Section 5 walks through.

## 1. Prerequisites

Install these once. Version numbers are what this project was built and tested against;
close nearby versions should be fine, but if something behaves unexpectedly, matching the
exact version below is the first thing to try.

| Tool | Why you need it | Version used here | Install |
| --- | --- | --- | --- |
| **Foundry** (`forge`, `cast`, `anvil`) | Compiling, testing and locally running the Solidity contracts | forge 1.8.3 | `curl -L https://foundry.paradigm.xyz \| bash`, then open a new shell and run `foundryup` |
| **uv** | The Python package/venv manager the backend uses instead of raw `pip` | 0.12.x | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Python** | The backend's language | 3.12+ | `uv` will fetch an interpreter for you if one isn't already on your machine — you don't need to install Python separately |
| **Node.js** | The web app's runtime | 20.x | Use whatever you normally use to manage Node (nvm, Volta, the official installer) |
| **Docker Desktop** | Runs the local Postgres database, and the throwaway Postgres containers the backend's integration tests spin up via `testcontainers` | any recent version | [docker.com](https://www.docker.com/products/docker-desktop/) |
| **git** | You already have this if you cloned the repo | — | — |

Confirm everything is on your `PATH` before continuing:

```bash
forge --version
cast --version
anvil --version
uv --version
node --version
docker info
```

`docker info` should print a block of text without an error about not being able to connect
to the daemon — if it errors, open Docker Desktop and wait for it to finish starting before
moving on.

## 2. One-time repo setup

From the repository root:

```bash
cd contracts
forge install foundry-rs/forge-std@v1.16.2 --no-commit
forge install OpenZeppelin/openzeppelin-contracts@v5.7.0 --no-commit
forge build
cd ..
```

`contracts/lib/` is deliberately not committed to git (it's in `.gitignore`), so this
install step is what populates it — you'll see it happen again inside CI for the same
reason. `forge build` compiles everything into `contracts/out/`, which the backend's own
test helpers (and the manual deployment steps in Section 4) read directly for ABIs and
bytecode.

```bash
cd backend
uv sync --extra dev
cp .env.example .env
cd ..
```

`uv sync` creates `backend/.venv` and installs every dependency, including the `dev` extras
(pytest, ruff, mypy, testcontainers) needed to run the test suite later. Section 3 below
walks through what to put in the `.env` file you just copied — don't try to run anything
yet, since several of those values don't exist until you deploy contracts in Section 4.

```bash
cd web
npm install
cp .env.local.example .env.local
cd ..
```

A note on `npm install` versus `npm ci`: this project's CI pipeline uses `npm install`
rather than the stricter `npm ci`, because `@privy-io/react-auth` pulls in a large,
loosely-pinned tree of wallet-adapter packages (Solana, WalletConnect, various mobile
wallet SDKs) whose exact resolved versions aren't perfectly stable across separate install
runs. `npm install` resolves from the version ranges in `package.json` and works reliably;
`npm ci`'s stricter lockfile-must-match-exactly check does not, for this particular
dependency tree. Use `npm install` here too, not `npm ci`.

That's the entire one-time setup. Everything from here on is either "start this service"
or "run this command," and none of it needs to be repeated unless you wipe your Docker
volumes or delete `node_modules`/`.venv`.

## 3. Environment variables

There are two `.env` files: `backend/.env` (read by the FastAPI app and the agent worker)
and `web/.env.local` (read by the Next.js app, and — because of Next's `NEXT_PUBLIC_`
convention — baked into the browser bundle, so never put a secret in a `NEXT_PUBLIC_`
variable). The tables below describe every variable in each file: what it's for, what to
set it to for local development, and — since you mentioned already running the Arc-402
paywall project — which values you can copy straight out of that project's own `.env`
files instead of inventing new ones.

### 3.1 What you can genuinely reuse from the Arc-402 project

A few of these values are not secrets — they identify a shared piece of public
infrastructure (an RPC endpoint, a chain ID, a deployed token's address, a Privy app's
public identifier) rather than a credential — so reusing the exact same value across both
projects is not just convenient, it's the *correct* thing to do: you want both projects
pointed at the same chain and the same token. Here is exactly what to copy, read directly
out of `Blockade-402/frontend/.env`, `Blockade-402/middleware/.env` and
`Blockade-402/contracts/.env`:

| Value | What it is | Where it lives in Blockade-402 |
| --- | --- | --- |
| `https://rpc.testnet.arc.io` | Arc's public testnet RPC endpoint | `ARC_RPC_URL` in `contracts/.env` and `middleware/.env`, `VITE_ARC_RPC_URL` in `frontend/.env` |
| `5042002` | Arc testnet's chain ID | `ARC_CHAIN_ID` in `middleware/.env`, `VITE_ARC_CHAIN_ID` in `frontend/.env` |
| `0x3600000000000000000000000000000000000000` | Arc testnet's native USDC contract address (a precompile-style address, not something either project deployed) | `USDC_ADDRESS` in `contracts/.env` |
| Your Privy **App ID** (a public client identifier, safe to reuse — it is not a secret and is already visible in Blockade-402's own deployed frontend bundle) | Identifies which Privy application both frontends log into | `PRIVY_APP_ID` in `middleware/.env`, `VITE_PRIVY_APP_ID` in `frontend/.env` |

If you do reuse the Privy App ID, go to the [Privy Dashboard](https://dashboard.privy.io),
open that app, and under its login/domain settings add `http://localhost:3000` to the
allowed origins — Blockade-402's frontend already has its own origin allowlisted there, and
this app's origin needs to be added alongside it, not instead of it. **Read the callout in
Section 5 first, though** — because of the stubbed backend auth described at the top of
this document, setting the real Privy App ID in `web/.env.local` right now will make the
web app's own sign-in *succeed* but every subsequent API call *fail* with 401, since the
backend only accepts stub tokens. It is genuinely fine, and probably better for now, to
leave `NEXT_PUBLIC_PRIVY_APP_ID` blank until real backend verification is implemented.

Two more values exist in Blockade-402 that are secrets, not public identifiers, so this
document deliberately does not print them here — instead, copy the value yourself from your
own `.env` file into this project's `.env`:

- **A funded testnet private key.** `Blockade-402/contracts/.env`'s `PRIVATE_KEY` already
  holds Arc testnet ETH for gas (it's the key that deployed and operates the paywall
  contracts there). You can reuse that same key here for `RELAYER_PRIVATE_KEY` and/or
  `OPERATOR_PRIVATE_KEY` (see the table below) if you want to test against real Arc
  testnet instead of a local anvil chain — see Section 4's "Path B." Using one key for both
  roles is fine for local testing; keep them as separate keys in anything resembling
  production, since the relayer deploys vaults and the operator moves money inside them —
  different privilege levels.
- **An LLM API key.** `Blockade-402/middleware/.env`'s `OPENAI_API_KEY` (or the Groq key
  it's actually holding, since that project routes through Groq's OpenAI-compatible
  endpoint) can be reused for this project's `OPENAI_API_KEY`. It is entirely optional for
  local testing, though — see the note on `OPENAI_API_KEY` below.

### 3.2 `backend/.env` reference

| Variable | Purpose | What to set it to locally |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy connection string for Postgres | Leave as the `.env.example` default, `postgresql+psycopg://oikonomos:oikonomos@localhost:5433/oikonomos` — it matches the credentials and port `docker-compose.yml` sets up in Section 4. The port is `5433`, not Postgres's usual `5432`, specifically so this doesn't collide with a Postgres instance you may already be running for something else. |
| `PRIVY_APP_ID` / `PRIVY_APP_SECRET` | Would be used for real Privy JWT verification | Leave blank. Nothing reads these yet — the backend's auth is stubbed, as explained above. Setting them does nothing today. |
| `WEBHOOK_SIGNING_SECRET` | HMAC-SHA256 key used to sign outgoing integration webhooks (`deposit.allocated`, `decision.made`, etc.) | The `.env.example` default (`dev-only-change-me`) is fine for local use. |
| `ARC_RPC_URL` | Which chain the backend's `ChainClient` talks to | `http://127.0.0.1:8545` if you're running a local `anvil` (Path A in Section 4), or `https://rpc.testnet.arc.io` (reused from Blockade-402, see above) if you're using real Arc testnet (Path B). |
| `ARC_CHAIN_ID` | Expected chain ID — mostly informational; `ChainClient` actually asks the connected node for its real chain ID when it signs a transaction, so this rarely needs to match perfectly, but keep it accurate for clarity | `31337` for anvil's default chain ID, or `5042002` (reused from Blockade-402) for Arc testnet. |
| `OPERATOR_PRIVATE_KEY` | The private key the **agent worker** signs its on-chain actions with (`adjustSplit`, `rebalance`, `sweepToYield`, `payOwner`, …) | For anvil: one of anvil's well-known default dev keys — see Section 4's Path A, which uses `0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d` (anvil's account #1). For Arc testnet: your reused Blockade-402 key, or a separate funded key if you'd rather keep the roles apart. |
| `OPENAI_API_KEY` | If set, the agent uses the real `OpenAIModelClient` (tool-calling, actual model reasoning); if left blank, it falls back to `ScriptedModelClient`, a small set of deterministic rules that mirror the same decisions without calling out to a model | Optional. Leave blank for your first end-to-end run — you'll still see real decisions logged and real on-chain actions taken, just from the scripted rules rather than a language model. Fill in your reused Blockade-402 key once you want to see the real model's reasoning. |
| `RELAYER_PRIVATE_KEY` | The private key the **API** signs with when deploying a new vault (`POST /v1/vaults`) — this is what lets a brand-new user create a vault without ever needing gas themselves | For anvil: anvil's account #0, `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80`. For Arc testnet: your reused Blockade-402 key. |
| `VAULT_FACTORY_ADDRESS` | Address of the deployed `VaultFactory` contract | Doesn't exist yet at setup time — Section 4 has you deploy the factory and then fill this in. |
| `YIELD_POOL_ADDRESS` | Address of the deployed `YieldPool` contract (shared by every vault) | Same as above — filled in after Section 4's deploy steps. |
| `DEFAULT_OPERATOR_ADDRESS` | The address every newly-deployed vault is configured to trust as its operator | The **address** corresponding to `OPERATOR_PRIVATE_KEY` above (for anvil's account #1, that's `0x70997970C51812dc3A010C7d01b50e0d17dc79C8`). |

### 3.3 `web/.env.local` reference

| Variable | Purpose | What to set it to locally |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | Base URL the web app calls for every API request | `http://localhost:8000`, matching where you'll run `uvicorn` in Section 4. |
| `NEXT_PUBLIC_PRIVY_APP_ID` | Privy application ID for client-side sign-in | Leave **blank** for now (see the callout above and in Section 5) — the app runs in a graceful "auth unconfigured" fallback mode when this is empty, which is the right mode for testing everything except the literal sign-in button. If you do want to see the real Privy login screen render, you can fill in the reused App ID from Section 3.1 — just know that clicking through it today will end in a 401 against the backend, since the two halves of auth aren't connected yet. |

## 4. Standing up the pieces

There are two ways to get a chain to point at: a local `anvil` instance (fast, free, fully
disposable — recommended for your first run and for day-to-day iteration) or Arc's real
testnet (slower, needs real testnet ETH for gas, but exercises the actual network this
product ships on). Both are described below; pick one before continuing. Everything after
this — the database, the backend, the agent worker, the web app — is identical either way.

### 4.1 Start Postgres

```bash
docker compose up -d postgres
```

This starts the container defined in the repo root's `docker-compose.yml`: Postgres 16,
database `oikonomos`, user/password `oikonomos`/`oikonomos`, exposed on `localhost:5433`.
Give it a few seconds, then confirm it's actually accepting connections:

```bash
docker exec arconomos-postgres-1 pg_isready -U oikonomos
```

You should see `accepting connections`. Leave this running for the rest of this document —
you only need to repeat this step if you reboot your machine or explicitly stop the
container.

### 4.2 Path A — local anvil chain (recommended first run)

In its own terminal window, left running for as long as you want the chain to exist:

```bash
anvil
```

This starts a fresh local chain on `http://127.0.0.1:8545`, pre-funded with ten well-known
development accounts (the same ones anvil always uses — safe to publish, since they never
hold real funds). This document uses account `#0`
(`0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`) as the deployer/relayer and account `#1`
(`0x70997970C51812dc3A010C7d01b50e0d17dc79C8`) as the agent operator, matching the keys
already listed in Section 3.2's table.

Now, in a different terminal, deploy the full contract stack by hand — this is the same
sequence `tests/integration/anvil_deploy.py` automates for the test suite, spelled out here
as plain `forge create`/`cast send` commands so you can watch each piece come up:

```bash
cd contracts

DEPLOYER=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
DEPLOYER_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
OPERATOR=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
RPC=http://127.0.0.1:8545

# 1. A mock USDC token (real Arc testnet already has real USDC deployed, so this step is
#    anvil-only — skip it entirely for Path B).
USDC=$(forge create src/mocks/MockUSDC.sol:MockUSDC \
  --rpc-url $RPC --private-key $DEPLOYER_KEY --broadcast --json | jq -r .deployedTo)
echo "USDC: $USDC"

# 2. The vault factory. Its constructor deploys its own Inbox implementation internally.
FACTORY=$(forge create src/VaultFactory.sol:VaultFactory \
  --rpc-url $RPC --private-key $DEPLOYER_KEY --broadcast --json \
  --constructor-args $USDC $DEPLOYER | jq -r .deployedTo)
echo "FACTORY: $FACTORY"

# 3. The shared yield pool and its mock yield source (stands in for USYC, which needs a
#    Circle allowlisting ticket to use for real — see the PRD's risk table).
YIELD_POOL=$(forge create src/YieldPool.sol:YieldPool \
  --rpc-url $RPC --private-key $DEPLOYER_KEY --broadcast --json \
  --constructor-args $USDC $DEPLOYER | jq -r .deployedTo)
echo "YIELD_POOL: $YIELD_POOL"

YIELD_SOURCE=$(forge create src/mocks/MockYieldSource.sol:MockYieldSource \
  --rpc-url $RPC --private-key $DEPLOYER_KEY --broadcast --json \
  --constructor-args $USDC $YIELD_POOL | jq -r .deployedTo)
echo "YIELD_SOURCE: $YIELD_SOURCE"

cast send $YIELD_POOL "setYieldSource(address)" $YIELD_SOURCE \
  --rpc-url $RPC --private-key $DEPLOYER_KEY
```

Take the three addresses this just printed (`$FACTORY`, `$YIELD_POOL`, and note `$USDC` and
`$OPERATOR` too — you'll want all of them) and fill them into `backend/.env`:

```
ARC_RPC_URL=http://127.0.0.1:8545
ARC_CHAIN_ID=31337
OPERATOR_PRIVATE_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
RELAYER_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
VAULT_FACTORY_ADDRESS=<the $FACTORY address printed above>
YIELD_POOL_ADDRESS=<the $YIELD_POOL address printed above>
DEFAULT_OPERATOR_ADDRESS=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
```

Keep the `$USDC` address around too — you'll need it in Section 5 to mint yourself test
USDC to deposit.

### 4.3 Path B — real Arc testnet, reusing Blockade-402's configuration

Skip the local `MockUSDC` deploy entirely — Arc testnet already has real USDC at
`0x3600000000000000000000000000000000000000` (see Section 3.1). Deploy just the factory
and yield pool against the real network, using your reused, already-funded private key:

```bash
cd contracts

DEPLOYER_KEY=<your reused Blockade-402 private key>
DEPLOYER=<the address that key belongs to>
RPC=https://rpc.testnet.arc.io
USDC=0x3600000000000000000000000000000000000000

FACTORY=$(forge create src/VaultFactory.sol:VaultFactory \
  --rpc-url $RPC --private-key $DEPLOYER_KEY --broadcast --json \
  --constructor-args $USDC $DEPLOYER | jq -r .deployedTo)

YIELD_POOL=$(forge create src/YieldPool.sol:YieldPool \
  --rpc-url $RPC --private-key $DEPLOYER_KEY --broadcast --json \
  --constructor-args $USDC $DEPLOYER | jq -r .deployedTo)

YIELD_SOURCE=$(forge create src/mocks/MockYieldSource.sol:MockYieldSource \
  --rpc-url $RPC --private-key $DEPLOYER_KEY --broadcast --json \
  --constructor-args $USDC $YIELD_POOL | jq -r .deployedTo)

cast send $YIELD_POOL "setYieldSource(address)" $YIELD_SOURCE \
  --rpc-url $RPC --private-key $DEPLOYER_KEY
```

`MockYieldSource` is still what's used here, even on testnet — real USYC needs Circle to
approve an allowlisting ticket per address (the PRD's own risk table calls this out
explicitly), so the mock is the honest, currently-available stand-in until that ticket is
filed and approved. Fill the resulting addresses into `backend/.env` the same way Path A
does, but with `ARC_RPC_URL=https://rpc.testnet.arc.io`, `ARC_CHAIN_ID=5042002`, and your
reused key for both `OPERATOR_PRIVATE_KEY` and `RELAYER_PRIVATE_KEY` (or two separate
reused/funded keys, if you'd rather keep the roles apart as suggested in Section 3.1).

One practical difference from Path A: on real testnet, getting USDC into your own wallet to
deposit isn't as simple as calling `mint()` on a mock token — you'll need to acquire real
testnet USDC through whatever faucet or path Blockade-402 already used. This document
can't hand you funds; if this is a blocker, Path A is the faster way to see the whole system
work today.

### 4.4 Run the database migrations

With `backend/.env`'s `DATABASE_URL` pointed at the Postgres you started in 4.1:

```bash
cd backend
uv run alembic upgrade head
```

This creates all sixteen tables (`users`, `vaults`, `rules`, `tax_settings`, `bills`,
`goals`, `deposits`, `decisions`, and so on). You only need to run this again in the future
if a new migration is added.

### 4.5 Start the backend API

```bash
cd backend
uv run uvicorn app.api.main:app --reload --port 8000
```

Leave this running in its own terminal. Confirm it's alive:

```bash
curl http://localhost:8000/healthz
```

You should get back `{"status":"ok"}`.

### 4.6 Start the agent worker

In another terminal:

```bash
cd backend
uv run python -m app.agent.worker
```

This is the process that actually does the ongoing work: it polls for new deposits every
15 seconds (chain-wide, across every vault), runs the daily cycle at 06:00 and the weekly
cycle every Monday at 07:00, and — for any vault that got a new deposit — runs a
deposit-triggered cycle immediately. Every one of those cycles is what writes rows into the
`decisions` table you'll query in Section 5. If this process isn't running, deposits will
sit in their inbox unswept and nothing will ever show up in the decision log — this is the
piece most likely to be forgotten, so double check it's actually running before Section 5
if something seems stuck.

### 4.7 Start the web app

```bash
cd web
npm run dev
```

Open `http://localhost:3000`. You should see the landing page, styled to match the Arc-402
frontend (same accent purple, same pill buttons, same light/dark toggle). Signing in won't
get you anywhere useful yet for the reasons explained above and expanded on next — that's
expected, not a bug.

## 5. A note on Privy, and why you should test the API directly for now

Here is the exact shape of the gap, so there's no ambiguity about what works and what
doesn't: the web app's `useAuth()` hook is a thin abstraction over two possible
implementations. When `NEXT_PUBLIC_PRIVY_APP_ID` is blank, it uses a stub that reports
"not authenticated" and logs a warning if you try to sign in — safe, predictable, and
exactly why the app doesn't crash today even though Privy isn't wired up. When you fill in
a real Privy App ID, it switches to the real `@privy-io/react-auth` provider, and clicking
"Sign in" opens Privy's actual hosted login flow, which will genuinely work end to end
*on the client side* — you'll get a real, valid Privy access token. The problem is what
happens next: the web app sends that real token to `POST /v1/session`, and the backend's
`get_current_user` dependency runs it through `StubPrivyClient.verify_access_token`, which
does nothing more sophisticated than check whether the string starts with the literal
prefix `"stub:"`. A real Privy JWT doesn't, so the backend returns 401, and the app is stuck
showing "Sign in" forever with a silent auth failure underneath. Implementing
`StubPrivyClient`'s real counterpart (verifying a Privy-issued JWT against Privy's
verification key server-side) is the natural next piece of work — it wasn't in scope for
this pass.

None of that stops you from testing the real, working system today — it just means you
drive it with `curl`, supplying your own stub token, rather than through the browser. A
stub token is any string of the form `stub:<anything you want as an id>:<a wallet
address>` — the backend creates a `users` row for that identity the first time it sees it,
exactly the way a real first sign-in would. Every example in Section 6 below uses this.

## 6. Manual end-to-end walkthrough

With Postgres, the chain (anvil or testnet), the backend, the agent worker and the web app
all running per Section 4, here is the full loop by hand: create a session, deploy a vault,
send it money, watch the indexer and agent notice and act on it, and read the result back
out.

Set a couple of shell variables to keep the commands below short (use your own wallet
address here — any well-formed `0x…` 40-hex-character address works, since nothing checks
that it's a real, funded account for the *owner* role specifically):

```bash
API=http://localhost:8000
WALLET=0x1234567890123456789012345678901234567890
TOKEN="stub:manual-test-user:$WALLET"
```

**Create your session.** This is the call that creates your `users` row:

```bash
curl -s -X POST $API/v1/session -H "Authorization: Bearer $TOKEN" | jq
```

You should get back your new user's `id` and `wallet`.

**Create your vault.** This is the call the (not-yet-built) setup wizard would eventually
make on your behalf, bundling every setup-time choice — tax rate, guardrails, known-source
rules, bills, goals, owner-pay settings — into one request. It's the same
`POST /v1/vaults` endpoint either way:

```bash
curl -s -X POST $API/v1/vaults -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
  "country": "US",
  "income_type": "freelance",
  "tax_rate_bps": 2000,
  "tax_delay_hours": 72,
  "default_kind": "transfer",
  "known_sources": [],
  "bills": [
    {"name": "Rent", "amount": 100000000, "due_date": "2026-11-01T00:00:00Z", "priority": 1}
  ],
  "goals": [
    {"name": "New equipment", "target_amount": 500000000, "target_date": "2027-01-01T00:00:00Z"}
  ],
  "owner_pay": {"enabled": false}
}' | jq
```

A `tax_rate_bps` of `2000` means 20% (basis points, same units the contract uses).
`bills[].amount` and `goals[].target_amount` are in USDC's 6-decimal base units, matching
the on-chain ERC-20 representation everywhere else in this system — `100000000` is
$100.00, `500000000` is $500.00. This call genuinely deploys a real `Vault` and two `Inbox`
clones on whichever chain you configured, signed and paid for by the relayer key, so it
will take a few seconds while the transaction is mined. The response gives you back the
addresses you'll need next:

```bash
curl -s $API/v1/vaults/me -H "Authorization: Bearer $TOKEN" | jq
```

Save `vault_addr` and `income_inbox` from that response into shell variables:

```bash
VAULT=<vault_addr from the response above>
INCOME_INBOX=<income_inbox from the response above>
```

**Send it money.** On anvil (Path A), mint yourself test USDC straight into the income
inbox — this is exactly what a real customer's payment landing in that address would look
like on-chain:

```bash
cast send $USDC "mint(address,uint256)" $INCOME_INBOX 500000000 \
  --rpc-url http://127.0.0.1:8545 --private-key $DEPLOYER_KEY
```

(On Arc testnet, this is the step where you'd instead send real testnet USDC to
`$INCOME_INBOX` from a wallet that holds some.)

At this point the money is sitting in the inbox, tagged as income by the inbox's own
identity, but not yet inside the vault — nothing has called `sweep()` yet. Anyone can call
it (that's deliberate — see the PRD), so call it yourself to see the mechanical allocation
happen immediately:

```bash
cast send $INCOME_INBOX "sweep()" --rpc-url http://127.0.0.1:8545 --private-key $DEPLOYER_KEY
```

**Watch the indexer and agent pick it up.** The agent worker you started in Section 4.6 is
polling every 15 seconds. Within that window, it will notice the new `Deposited` event on
your vault, record it in the `deposits` table, refresh the cached bucket balances, and run
a deposit-triggered agent cycle — which writes a row into `decisions` and, if the scripted
model (or the real one, if you set `OPENAI_API_KEY`) proposes anything the policy check
accepts, sends a real follow-up transaction. Give it 15–20 seconds, then check the log:

```bash
curl -s $API/v1/decisions -H "Authorization: Bearer $TOKEN" | jq
```

You should see at least one entry with `"trigger": "deposit"` and a plain-language
`"reason"` — this is the same hash-chained decision log described in the PRD, and you can
follow `prev_hash`/`hash` across entries to see the chain for yourself.

**Read the balances back.**

```bash
curl -s $API/v1/dashboard/summary -H "Authorization: Bearer $TOKEN" | jq
```

With a 20% tax rate and the default remaining split, you should see `Tax` holding roughly
$100 of your $500 deposit, with the rest distributed across `Bills`, `Goals`, `OwnerPay`,
`Buffer` and `Savings` — and the numbers should match what you'd get by calling the
contract directly:

```bash
cast call $VAULT "getBucketBalances()(uint256[6])" --rpc-url http://127.0.0.1:8545
```

**Exercise the rest of the CRUD surface**, all under the same `$TOKEN`:

```bash
# Bills
curl -s $API/v1/bills -H "Authorization: Bearer $TOKEN" | jq
curl -s -X PATCH $API/v1/bills/<bill_id> -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"amount": 120000000}' | jq

# Goals
curl -s $API/v1/goals -H "Authorization: Bearer $TOKEN" | jq

# Rules (known-source classification for direct-to-vault deposits)
curl -s -X PUT $API/v1/rules -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
  "default_kind": "transfer",
  "known_sources": [{"sender": "0xSOMEPAYWALLCONTRACT", "kind": "income", "label": "My paywall"}]
}' | jq

# Tax settings
curl -s $API/v1/tax -H "Authorization: Bearer $TOKEN" | jq
```

If you want to see a genuinely rejected policy decision rather than an accepted one, try
depositing again shortly after the first deposit and watch the weekly-guardrail or
buffer-floor checks in `app/agent/policy.py` do their job — or read
`backend/tests/agent/test_policy.py` and `test_cycle.py`, which exercise exactly those
paths without needing a live chain at all.

## 7. Running the automated test suites

Useful for confirming your local setup matches what CI runs, or after you change anything.

```bash
# Contracts — 20 tests, including a fuzzed invariant suite
cd contracts && forge test

# Backend — fast unit tests (no Docker/anvil needed)
cd backend && uv run pytest tests -m "not integration" -v

# Backend — integration tests (spins up its own throwaway Postgres via testcontainers,
# and its own anvil instances — needs Docker running and `anvil` on PATH, but not the
# anvil/Postgres you started manually in Section 4; it's fully self-contained)
cd backend && uv run pytest tests -m integration -v

# Web — lint, unit tests, and a production build
cd web && npm run lint
cd web && npm run test
cd web && npm run build
```

## 8. Stopping everything

Ctrl-C the `uvicorn`, `app.agent.worker`, `npm run dev`, and `anvil` processes in whichever
terminals they're running in. Postgres keeps running in the background until you stop it
explicitly:

```bash
docker compose stop postgres
```

Your data survives in a Docker volume (`arconomos_postgres_data`) across `stop`/`start`
cycles; only `docker compose down -v` actually deletes it.
