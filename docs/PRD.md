# Oikonomos — PRD & Architecture

Sep 27, 2026 · @Izuchukwu Uchendu

## Summary

Oikonomos is an AI operator that holds, splits and grows a small business's USDC on Arc: every income deposit is divided into tax, bills, goals, owner pay and savings, and an agent adjusts those splits as it forecasts what is coming. It is built for freelancers, creators and one-person businesses who are not crypto-native: they sign in with email or phone, fund a wallet, set their rules once, and watch a dashboard.

It targets the Tameion Agents Hackathon (Sep 27 – Oct 10, 2026), mainly RFB 01 (Intelligent Business Treasury) and RFB 04 (Autonomous Business Operator). The existing Arc x402 paywall is kept as the first income source: it pays straight into an Oikonomos account, so every paid AI answer is split automatically.

v1 holds and grows money (savings, goals, tax reserve). v2 pays things from it (suppliers, bills, subscriptions); v2 is designed here so v1 does not have to be rebuilt later.

## Product requirements

### Who it is for

- **Primary:** non-web3 freelancers, creators and solo business owners with irregular income. Hackathon cohort: 3–5 of them, onboarded by us.
- **Secondary:** builders who sell pay-per-use digital services (the paywall is the first). Their income arrives on-chain automatically.

### Problems it solves

| Problem | What Oikonomos does |
| --- | --- |
| Tracking is manual micro-work | Every deposit is an on-chain event; no bank link, no receipt scanning |
| Tax money gets spent | Tax share is split off at deposit time and held behind a withdrawal delay |
| Irregular (lumpy) expenses are forgotten | Named sinking funds with due dates; the agent raises their share ahead of time |
| Rigid budgets get abandoned after one overspend | The agent re-plans the rest of the period and explains the change; nothing is marked failed |
| Idle money earns nothing | Reserve buckets are swept into yield (USYC) and redeemed before they are needed |
| Irregular income, irregular pay | Income is smoothed into a steady owner paycheck from a buffer |

### Goals for the hackathon

1. 3 real sellers complete setup and deposit at least weekly during the event.
2. The agent makes decisions a cron job could not: changes split shares, times yield sweeps, smooths pay, and explains each one.
3. The paywall's revenue flows into Oikonomos with zero manual steps.
4. A dashboard a non-crypto user understands without help.

### Scope

| Area | v1 (hackathon) | v2 (designed, not built) |
| --- | --- | --- |
| Wallet | Privy email/phone login, embedded wallet | Same |
| Funding | Deposits of USDC; paywall payouts | Payment links / invoices customers pay directly |
| Classification | Rules set at setup (income vs transfer); editable later | Rules learned from history |
| Buckets | Tax, bills, goals, owner pay, buffer, savings | Same + per-payee budgets |
| Yield | USYC sweep and redeem | Same |
| Owner pay | Scheduled draw to the owner's own wallet | Same |
| Paying others | Not in v1 | Allowlisted payees, per-payee and per-day limits, scheduled bills |
| Currency | USDC | EURC and FX via App Kit Swap |
| Dashboard | Balances, flows, goals, projections, agent log | Spending analytics by payee |

### Non-goals

- Tracking spending that happens off-chain (naira card or bank spend). A withdrawal to the owner is recorded as an owner draw; tracking honestly ends there.
- Computing tax owed or filing returns. Oikonomos sets aside an estimated percentage the user confirms.
- Custody by us. Funds sit in a vault the user owns; the agent can move money only between the user's own buckets.

### Success metrics (reported in the submission)

| Metric | Target by Oct 10 |
| --- | --- |
| Sellers onboarded and active | 3 |
| Deposits processed | 10+ |
| USDC under management (testnet) | Report actual |
| Agent decisions logged, with reasons | 100+ |
| Paywall payments auto-split | Report actual |

## Setup flow

All classification is decided once, at setup, so the user is never asked about an individual deposit. They can change any rule later from Settings, and can reclassify a past deposit from the agent log if they want to, but nothing ever waits on them.

1. **Sign in with Privy** (email or phone). An embedded wallet is created; no seed phrase is shown.
2. **Create the vault.** The app calls the factory to deploy the user's vault. The user's wallet is the owner; the Oikonomos agent is given the limited operator role (see Smart contracts).
3. **How money reaches you.** The user gets two deposit addresses, both owned by their vault:
   1. **Income address**: anything sent here is income, and the tax share is applied. This is the address they give to clients, platforms and the paywall.
   2. **Top-up address**: anything sent here is a transfer (their own money moving in). No tax is applied.
   3. **Default for anything else** sent straight to the vault: income or transfer, chosen once.
   4. **Known sources (optional):** name a sender address and pick income or transfer (e.g. "Paywall contract = income").
4. **Tax.** Pick country and income type. Oikonomos shows a default set-aside rate with a link to its public source, clearly labelled as an estimate. The user confirms or edits it, and sets the withdrawal delay on the tax bucket (default 72 hours).
5. **Bills and irregular expenses.** Monthly bills (amount, due day) and irregular ones (insurance, rent renewal, equipment) with an amount and a due date.
6. **Goals.** Name, target amount, target date, priority.
7. **Owner pay.** Typical monthly income (a rough figure the forecast starts from), then a weekly or monthly pay amount, or "let the agent suggest one" after two weeks of history. Plus a buffer size (e.g. one month of pay). \[this is optional, they can wish to have this setup or not, by default the money sits in the platform and grows\]
8. **Guardrails for the agent.** Maximum change to any split share per week (default 10 points), minimum tax share (never below the confirmed rate), and whether yield is on \[we'd have to create prompts around this, somewhere it can be accessed by the agent before making decisions, also saving context somewhere\].
9. **Review and fund.** A one-screen summary of the rules, then the income and top-up addresses with a QR code.

Classification precedence when a deposit lands: known-source rule, then which address it arrived at, then the default.

## System architecture

Funds never pass through our servers: they land in contracts the user owns, and the backend only reads the chain and sends operator calls the contracts allow.

&#91;embedded content: system architecture · 3 layers, 10 components\]

Deposits and paywall payouts reach the user's inboxes; the indexer sees them, the agent plans, and its signed calls move money only between the user's own buckets and the yield pool.

| Component | Responsibility | Runs on |
| --- | --- | --- |
| Web app | Privy sign-in, setup wizard, dashboard, agent log | Vercel |
| API | Setup, rules, dashboard queries, webhooks for integrators | Railway or Fly.io (Docker) |
| Indexer | Polls Arc RPC for USDC `Transfer` logs into inboxes and for vault events; classifies each deposit; writes the ledger | Same host as API, own process |
| Agent worker | Runs on every deposit and on a schedule; forecasts, proposes actions, checks policy, signs and sends | Same host, own process |
| Postgres | Users, rules, ledger, forecasts, append-only decision log | Neon or Supabase |
| Inboxes | Two small contracts per user that receive USDC and forward it to the vault with a tag | Arc |
| Vault | Holds the user's USDC; bucket accounting; split rules; owner and operator roles; tax timelock | Arc |
| Yield pool | One allowlisted contract that holds USYC for all vaults and tracks each vault's shares | Arc |
| Memo | Arc's predeployed Memo contract; the agent writes a daily hash of the decision log | Arc |

**Design rules**

- The chain is the source of truth for balances; Postgres is a cache plus the decision log. Any row can be rebuilt from events.
- The agent never holds user funds and cannot send money outside a user's vault in v1. The contract enforces this, not the prompt.
- Every agent action is logged before it is sent, with the inputs it saw, and the log is anchored on-chain daily.

## Smart contracts

Five contracts, Solidity 0.8.x with Foundry and OpenZeppelin v5. The key property: the agent's role can move money between a user's own buckets and the yield pool, and can pay the owner's fixed payout address, but can never send funds anywhere else in v1.

| Contract | What it does |
| --- | --- |
| `VaultFactory` | Deploys a `Vault` and two `Inbox` clones (EIP-1167) per user with CREATE2, so addresses can be shown before deployment. Called by our relayer, so a new user needs no gas. |
| `Inbox` | Receives USDC. `sweep()` (callable by anyone) forwards its balance to the vault with a fixed tag: `INCOME` or `TRANSFER`. The tag is set at creation and can be changed but the change takes effect at the beginning of the next month. the default would be transfer if the setup step is skipped. |
| `Vault` | Holds the user's USDC. Tracks bucket balances and `unallocated`. Enforces split rules, roles, guardrails and the tax timelock. |
| `YieldPool` | One contract for all vaults, allowlisted for USYC. Buys and sells USYC through the Teller and tracks each vault's shares (ERC-4626-style accounting). Behind an `IYieldSource` interface. |
| `PayeeModule` (v2) | Allowlisted payees with per-payment and per-period limits and a 24-hour activation delay. Plugged into the vault as a module, so v1 code does not change. |

### Vault roles

| Action | Owner (user) | Operator (agent) |
| --- | --- | --- |
| Allocate a deposit by the current split | yes | yes |
| Change split shares | yes, freely | only within guardrails: max change per bucket per 7 days, tax never below the confirmed rate |
| Move between buckets | yes | yes, except out of Tax |
| Sweep to or redeem from the yield pool | yes | yes, registered pool only |
| Pay owner (scheduled pay) \[optional, by default inactive — money sits in the vault and grows\] | n/a | yes, to the owner's fixed payout address, capped per period |
| Withdraw from Tax | request, then execute after the delay (default 72 h) | never |
| Withdraw from other buckets | yes, any address | never |
| Set guardrails, payout address, pause or replace operator | yes | never |

Owner actions are EIP-712 signed messages that our relayer submits, so users never need USDC for gas in their Privy wallet. The vault checks the owner's signature and a nonce.

### Deposit classification on-chain

- Via an inbox: the tag comes from the inbox and cannot be spoofed.
- Sent straight to the vault: it arrives as `unallocated`, and the operator allocates it with the kind the user's rules give (known-source rule, then default). The call records the source transaction hash, so the decision is auditable. A clear log of decisions made and transactions needs to be viewed under the dashboards analytics section for transparency.

### Key events

`Deposited(inbox, kind, amount, srcTx)` · `Allocated(depositId, kind, bucketAmounts)` · `SplitChanged(oldBps, newBps, by)` · `Rebalanced(from, to, amount, reasonHash)` · `YieldMoved(bucket, usdc, shares, direction)` · `OwnerPaid(amount, period)` · `TaxReleaseRequested(amount, unlockAt)` · `TaxReleased(amount, to)`

Every operator call carries a `reasonHash`: the hash of the decision-log entry that justified it. Anyone can match an on-chain action to its written reason.

### Invariants (fuzzed in tests)

1. Sum of buckets + unallocated + value of yield shares = what the vault owns.
2. The operator can never reduce the Tax bucket.
3. Operator calls never send USDC to any address except the vault, the registered pool, or the owner's payout address.
4. After a split change by the operator, no share has moved more than the guardrail allows in any 7-day window.

### USYC: what is allowed

USYC is permissioned: only allowlisted addresses can hold it. On testnet, allowlisting is requested through a Circle Support ticket and takes about 24–48 hours ([Arc docs](https://docs.arc.io/arc/references/contract-addresses)). That is why one `YieldPool` holds USYC for everyone, not each user's vault. On mainnet, USYC is limited to eligible institutions outside the US with a $100,000 minimum, so a production yield path is an open question (see Risks). A `MockYieldSource` with the same interface covers tests and is the fallback if allowlisting is late.

## Agent design

Code does the arithmetic, the language model chooses and explains, and a deterministic policy check sits between the model and the chain. The model never produces a number that is sent on-chain without that check.

### When it runs

- **On every deposit:** allocate by the current split (mechanical, no model call), then check whether anything should change.
- **Daily:** forecast, check bills and goals due soon, decide on yield moves and owner pay.
- **Weekly:** review splits against the forecast; propose or make share changes within guardrails.
- **On an owner action** (withdrawal, rule change): re-plan the rest of the period.

### One cycle

1. **Observe.** Snapshot from the ledger: bucket balances, yield position, bills and irregular expenses due in the next 20 days, goals, income history.
2. **Forecast (code).** Weekly income as a median with low and high bands, from recent weeks resampled. For the first weeks, the typical monthly income the user gave at setup stands in. Output: expected cash in and cash needed per week for 12 weeks.&#32;&#32;
3. **Plan (model).** The model gets the snapshot, forecast and guardrails, and picks from a fixed set of typed actions using tool calls. Each action carries its parameters and a plain-language reason.
4. **Check (code).** Every proposed action is validated against the same guardrails as the contract plus stricter off-chain ones, then simulated with `eth_call`. Anything that fails is dropped and logged as rejected.
5. **Log.** A decision entry is written and hashed before anything is sent.
6. **Act.** The transaction is signed by the agent's Circle wallet and sent with the entry's hash as `reasonHash`; the entry is updated with the transaction hash.
7. **Explain.** One line for the dashboard feed, e.g. "Raised Rent from 15% to 22% for the next two deposits: rent is due Nov 1 and the bucket is ₦X short at the current pace."

### Actions the agent can take

| Action | Typical trigger | Bounded by |
| --- | --- | --- |
| `allocate` | Deposit arrives | Current split; tax share on income is never skipped |
| `adjust_split` | A bill or goal is off pace; income forecast changes | Max change per bucket per 7 days; tax floor |
| `rebalance` | A bucket is short now and another has slack | Never out of Tax |
| `sweep_to_yield` | Reserve buckets hold more than the next 14 days of needs | Minimum amount per move; registered pool only |
| `redeem` | A bill is due within 2 days, or a forecast shortfall | Only what is needed plus a margin |
| `pay_owner` | Scheduled pay date | Buffer never below its floor; cap per period |
| `flag` | Goal at risk, pay not sustainable, unusual deposit | Needs the owner; no money moves |

**Owner pay smoothing.** Pay is the lower of the owner's target and what is sustainable: buffer plus low-band forecast income over the next 8 weeks, minus bills and tax due. If the sustainable figure falls below the target, the agent pays the lower amount and flags it with the reason.

**Overspending.** If the owner withdraws more than planned from a bucket, the agent re-plans the remaining weeks: it spreads the gap across later deposits, reduces goal contributions first and bills last, and explains the change. Nothing is marked as failed.

### Decision log entry

| Field | Contents |
| --- | --- |
| `id`, `prev_hash`, `hash` | Hash chain, so no entry can be edited or removed unnoticed |
| `trigger` | deposit, daily, weekly, owner action |
| `inputs_hash` + `snapshot` | What the agent saw: balances, forecast, rules |
| `proposed` | Actions the model proposed, with parameters |
| `policy_result` | Accepted or rejected, and which rule |
| `reason` | The plain-language explanation shown to the user |
| `tx_hash` | The on-chain result, if any |
| `signature` | Signed by the agent key |

Once a day the agent writes the latest log hash to Arc's Memo contract, so the whole log can be checked against the chain.

### Model and evaluation

- One model provider behind a small interface (Anthropic or OpenAI; the paywall already uses OpenAI).
- A scenario suite checks behaviour, not wording: e.g. "income drops 60% for 3 weeks", "annual insurance due in 20 days", "owner withdraws twice the plan". Each scenario asserts which actions are proposed and that the policy check holds. These run in CI with the model mocked, and nightly against the real model.

## API design

REST over HTTPS, JSON, versioned under `/v1`, documented with the OpenAPI spec FastAPI generates. Users authenticate with their Privy access token, which the API verifies server-side. Businesses that integrate (like the paywall) use an API key scoped to one vault.

### Endpoints

| Method and path | Purpose |
| --- | --- |
| `POST /v1/session` | Verify the Privy token; create the user on first sign-in |
| `GET /v1/tax-defaults?country=NG&type=freelance` | Default set-aside rate, source link and date retrieved |
| `POST /v1/vaults` | Deploy vault and inboxes via the relayer; returns their addresses |
| `GET /v1/vaults/me` | Vault, inbox addresses, roles, deployment status |
| `PUT /v1/rules` | Default kind for direct deposits; known-source rules |
| `PUT /v1/tax` | Confirmed rate and withdrawal delay |
| `GET/POST/PATCH/DELETE /v1/bills`, `/v1/goals` | Bills, irregular expenses and goals |
| `PUT /v1/owner-pay`, `PUT /v1/guardrails` | Owner pay settings and agent limits |
| `POST /v1/owner-intents` | Relay an EIP-712-signed owner action (withdraw, split change, tax release) |
| `GET /v1/dashboard/summary` | Balance per bucket, yield position, unallocated |
| `GET /v1/dashboard/flows?from=&to=&interval=week` | Money in, split, out over time |
| `GET /v1/dashboard/projections` | 12-week forecast bands, goal completion dates, bill coverage |
| `GET /v1/deposits` · `PATCH /v1/deposits/{id}` | List deposits; optional reclassification |
| `GET /v1/decisions?cursor=` · `GET /v1/decisions/{id}` | Agent log; one entry with its hash, signature and transaction |
| `POST /v1/integrations` | Create an integration and API key for a business the user owns |
| `POST /v1/integrations/{id}/events` | Attach metadata to a payment: label, customer reference, cost of serving it |
| `POST /v1/integrations/{id}/webhooks` | Register a webhook URL |

**Webhooks** (signed with HMAC-SHA256, retried with backoff): `deposit.received`, `deposit.allocated`, `decision.made`, `flag.raised`, `owner.paid`.

### Data model (Postgres)

| Table | Key columns |
| --- | --- |
| `users` | privy\_id, wallet, country, created\_at |
| `vaults` | user\_id, vault\_addr, income\_inbox, topup\_inbox, payout\_addr, deployed\_tx |
| `rules` | vault\_id, default\_kind, known\_sources (sender, kind, label) |
| `tax_settings` | vault\_id, rate\_bps, delay\_hours, source\_default\_id |
| `tax_defaults` | country, income\_type, rate\_bps, source\_url, retrieved\_at |
| `bills`, `goals` | vault\_id, name, amount, due or target date, recurrence, priority |
| `deposits` | vault\_id, tx\_hash, log\_index, sender, amount, kind, kind\_source (inbox / rule / default), integration\_event\_id |
| `allocations` | deposit\_id, bucket, amount, decision\_id |
| `bucket_balances` | vault\_id, bucket, amount, as\_of\_block (rebuilt from events) |
| `forecasts` | vault\_id, run\_at, week, income\_low, income\_mid, income\_high, needed |
| `decisions` | id, vault\_id, prev\_hash, hash, trigger, snapshot, proposed, policy\_result, reason, tx\_hash, signature |
| `integrations`, `integration_events` | vault\_id, name, key\_hash; tx\_hash, label, cost, reference |
| `indexer_cursor` | chain\_id, last\_block |

Amounts are stored as integers in USDC's 6-decimal units, matching the ERC-20 interface. The native gas balance uses 18 decimals, so code never mixes the two ([Arc docs](https://docs.arc.io/arc/references/contract-addresses)).

## Paywall integration

The paywall plugs in by changing one address: its payouts go to the owner's Oikonomos income address instead of a plain wallet. Nothing else is required. Two optional steps add cost data and notifications.

### Level 1: change where the money goes (required, no code)

Today `PaymentVerifier.pay()` moves USDC from the customer to the resource owner's address. Set that address to the owner's **income inbox**. If the middleware later moves to Circle's hosted x402 [Facilitator Service](https://developers.circle.com/agent-stack), which accepts x402 payments on Arc, the same address becomes its `payTo`.

What then happens to one paid question:

1. A customer pays a few cents in USDC; `PaymentSettled` fires and the USDC lands in the income inbox.
2. The paywall serves the answer as it does today. It does not wait for Oikonomos.
3. The indexer sees the inbox balance grow. Once it passes a threshold (default $1) or once a day, the agent calls `sweep()`.
4. The sweep forwards the balance to the vault tagged `INCOME`, and the agent allocates it by the current split: tax, bills, buffer, owner pay, goals.
5. The dashboard shows it as paywall income, and the agent log records the allocation.

**Why sweeps are batched.** An Arc transaction costs about $0.01, which is a large share of a few-cent payment. Sweeping every payment would waste much of the revenue, so small payments are pooled and swept together.

### Level 2: report what each sale cost (optional, \~30 lines)

After serving a paid answer, the middleware posts the transaction hash and the cost of serving it (the OpenAI token cost) to `POST /v1/integrations/{id}/events`. The call is idempotent on the transaction hash and runs in the background, so a failure never blocks the customer.

```python
# middleware/app/oikonomos.py
async def report_sale(tx_hash: str, price_usdc: int, llm_cost_usdc: int) -> None:
    await client.post(
        f"{OIKO_URL}/v1/integrations/{OIKO_INTEGRATION_ID}/events",
        headers={"Authorization": f"Bearer {OIKO_API_KEY}"},
        json={"tx_hash": tx_hash, "label": "AI answer",
              "amount": price_usdc, "cost": llm_cost_usdc},
    )
```

With this, the dashboard shows revenue, cost and margin per answer, and the agent can forecast the OpenAI bill and fund the Bills bucket for it. In v1 the owner still pays OpenAI by card, withdrawing from the Bills bucket.

### Level 3: webhooks (optional)

The paywall can subscribe to `deposit.allocated` or `flag.raised`, for example to show the owner a "this week's earnings" line inside the paywall's own admin page.

### What changes in the paywall repo

| Change | Where |
| --- | --- |
| `PAYOUT_ADDRESS` env var set to the income inbox | middleware config and contract registration |
| `oikonomos.py` client + background task after `serve` | Level 2 only |
| Tests: payout goes to the configured address; reporting failure never blocks a response; duplicate reports are ignored | `tests/test_oikonomos.py` |

### Beyond the paywall

Any business that sells a per-use digital service can integrate the same way: point payouts at the income inbox, optionally post costs. For non-web3 sellers, the equivalent in v2 is an Oikonomos payment link or invoice that customers pay directly into the income inbox.

## Tech stack

The stack stays the same as the paywall's where possible (Foundry, FastAPI, web3.py, Privy), so both codebases share tooling and people.

| Layer | Choice | Why |
| --- | --- | --- |
| Contracts | Solidity 0.8.x, Foundry, OpenZeppelin v5 (Clones, EIP712, SafeERC20) | Fast tests with fuzzing and invariants; same as the paywall |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, managed with uv | One language with the paywall middleware; uv matches the ARC CLI |
| Chain access | web3.py v7 | Reads events, simulates with `eth_call`, sends operator calls |
| Scheduling | APScheduler in the agent process; Postgres advisory locks so two workers never act on one vault at once | No extra queue to run for 3–5 users |
| Forecasting | numpy and pandas | Simple, testable statistics; no ML model needed at this scale |
| Language model | Anthropic or OpenAI SDK with tool calls, behind one interface | Swappable; mocked in tests |
| Agent and relayer keys | Circle Wallets (developer-controlled) via the Circle API / CLI | Keys never sit in our env files; counts toward Circle tool use |
| Frontend | Next.js (App Router), TypeScript, Tailwind, TanStack Query | Standard, fast to build |
| Wallet | Privy React SDK, email or phone login, embedded wallet; viem's built-in `arcTestnet` chain | Non-crypto users never see a seed phrase |
| Charts | Recharts | Bucket balances, flows, forecast bands |
| Database | Postgres (Neon or Supabase) | Managed, free tier is enough |
| Hosting | Vercel (web); Railway or Fly.io for API, indexer, agent as three processes from one image | Git-push deploys |
| Monitoring | Sentry, structured JSON logs | Errors and agent failures surface quickly |
| Network | Arc testnet, chain ID 5042002; RPC from [Arc docs](https://docs.arc.io/arc/references/connect-to-arc) or the Canteen-hosted RPC in the ARC CLI | Hackathon runs on testnet |

### Repo layout

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

## TDD plan and CI/CD

Every behaviour starts as a failing test; code is written only to make it pass, then refactored. Money rules are tested at two levels: the contract enforces them, and the agent's policy check refuses to propose anything the contract would reject.

### First tests to write, in order

**Contracts (`forge test`, local anvil only until green)**

1. `test_InboxSweepTagsIncome` and `test_InboxSweepTagsTransfer`
2. `test_AllocateIncomeAppliesSplit` (rounding remainder goes to Buffer)
3. `test_AllocateTransferSkipsTax`
4. `test_OperatorCannotWithdrawTax` and `test_OperatorCannotSendToOutsider`
5. `test_OperatorSplitChangeRespectsWeeklyCap` and `test_TaxShareNeverBelowFloor`
6. `test_TaxReleaseNeedsDelay`
7. `test_OwnerIntentSignatureAndNonce` (replay rejected)
8. `test_YieldSweepAndRedeemAccounting` against `MockYieldSource`
9. Invariant tests for the four invariants in Smart contracts, run with a fuzzing handler

**Backend (pytest)**

1. Indexer: `test_transfer_to_income_inbox_recorded_as_income`, `test_direct_deposit_uses_known_source_rule_then_default`, `test_reorg_safe_cursor` (reprocessing a block range creates no duplicates)
2. Forecast: `test_cold_start_uses_setup_income`, `test_bands_widen_with_volatile_income` (property-based with Hypothesis)
3. Policy: `test_rejects_split_change_over_cap`, `test_rejects_redeem_more_than_needed`, `test_pay_owner_respects_buffer_floor`
4. Agent: `test_logs_decision_before_sending`, `test_hash_chain_detects_edit`, `test_model_output_with_unknown_action_is_rejected`
5. API: `test_privy_token_required`, `test_user_cannot_read_other_vault`, `test_integration_event_idempotent_on_tx_hash`, `test_webhook_signature`
6. Scenarios (model mocked in CI, real nightly): income drop, lumpy bill, owner overspend, yield timing before a bill

**Web (Vitest + Testing Library; Playwright for flows)**

1. Setup wizard: cannot finish without confirming the tax rate; shows source link
2. Dashboard: bucket totals equal the summary endpoint; forecast chart renders bands
3. E2E: sign in (Privy test mode) → setup → deposit on local anvil → allocation appears → agent log entry visible

### Pipeline

| Stage | Runs on | What it does | Blocks merge |
| --- | --- | --- | --- |
| Lint and types | every push | `forge fmt --check`, ruff, mypy, eslint, `tsc` | yes |
| Contracts | every push | `forge test` with fuzz and invariant runs, coverage report, Slither static analysis | yes |
| Backend unit | every push | pytest, model and chain mocked | yes |
| Backend integration | every push | pytest against anvil with deployed contracts and a throwaway Postgres (testcontainers) | yes |
| Web | every push | Vitest | yes |
| E2E | pull request | Docker Compose (anvil + API + indexer + agent + web), Playwright | yes |
| Preview | pull request | Vercel preview of the web app | no |
| Staging deploy | merge to main | Build one image; run Alembic migrations; deploy API, indexer, agent to Railway or Fly; smoke test against Arc testnet | n/a |
| Contract deploy | manual trigger | `forge script` to Arc testnet with a protected GitHub environment and required approval; addresses committed to `deployments/testnet.json` | n/a |
| Nightly | schedule | Scenario suite against the real model; long invariant runs; a small real deposit on testnet end to end | alerts only |

Secrets (Circle API key, model key, Privy app secret, database URL) live in GitHub environments and the host's secret store, never in the repo.

## Build plan, risks and open questions

The plan puts working vaults on testnet by Oct 1 and sellers on the product from Oct 4, because traction is 30% of judging and needs a week of real use.

&#91;embedded content: build plan · Sep 27 to Oct 10, 2026\]

Submit a first version by Oct 8; the form accepts resubmissions until the deadline. The Arc x402 microgrant is due Oct 14, so the paywall's own payment loop must be working by Oct 3.

### Risks

| Risk | Effect | Mitigation |
| --- | --- | --- |
| USYC allowlisting is slow, or testnet USYC is not functional (a June 2026 builder report found a stub contract) | No real yield in the demo | File the Circle ticket on day 1; ship `MockYieldSource` and label any simulated yield clearly |
| USYC on mainnet is for eligible institutions only, $100k minimum | Pooled yield may not be allowed in production | Treat production yield as an open question; keep yield behind `IYieldSource` |
| Sellers cannot easily buy USDC | Onboarding stalls | On testnet, fund each seller with test USDC equal to what they actually earned; state this in the submission |
| Gas for sweeps, allocations and relayed owner actions | Our relayer pays; could add up | Batch sweeps; cap per-user daily calls; in production, a small fee bucket |
| The model proposes a bad action | Money moved wrongly | Policy check plus contract guardrails; small amounts; every action logged with its reason |
| Tax estimate is wrong for someone | Loss of trust | Labelled as an estimate, source linked, user-confirmed and editable |
| Managing and pooling other people's money is regulated in many places | Blocks a mainnet launch | Non-custodial vaults; legal review before mainnet |
| Privy's support for Arc | Setup blocked | A half-day spike on day 1: Privy with viem's `arcTestnet` chain |

### Open questions

- [ ] Which countries are the first sellers in? This decides the tax defaults to research.\
Answer: There needs to be an onboarding flow, before wallet connect we present a form where we collect the required data. Based on the selected country of origin/residence, we map the tax situation of the country.
- [ ] Model provider: stay with OpenAI like the paywall, or use Anthropic?\
answer: Stay with Open AI
- [ ] Final product name.\
Answer: E-konomos
- [ ] Who pays gas in production: a fee bucket, a subscription, or a share of yield?\
Answer: a fee bucket.
- [ ] Is pooled USYC acceptable on mainnet, or does each user need their own eligibility?\
Answer: For the time-being we'll inquire on this, but for the now mainnet can do without USYC, it can be part of the implementation but inactive.

### Sources

- [Tameion Agents Hackathon](https://tameion.thecanteenapp.com/) (dates, judging, RFBs)
- [Arc contract addresses](https://docs.arc.io/arc/references/contract-addresses) (USDC decimals, USYC allowlisting and eligibility, Memo, Gateway)
- [Connect to Arc](https://docs.arc.io/arc/references/connect-to-arc) (chain IDs, RPC, viem chains)
- [Circle Agent Stack](https://developers.circle.com/agent-stack) (agent wallets, Facilitator Service)
- [USYC subscribe and redeem](https://developers.circle.com/tokenized/usyc/subscribe-and-redeem) (Teller `buy` and `sell`)
- [Testnet USYC stub report](https://github.com/circlefin/arc-defi-lending-and-borrowing/issues/1)
