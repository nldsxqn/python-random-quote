# Development progress

## Existing tree

`/workspace` was not empty. It was an unrelated GitHub Learning Lab quote-bot starter (`README.md`, `get-quote.py`, `quotes.txt`) with an existing `.git` remote. Those three files were moved unchanged into `legacy/quote-bot/`. Git history was not rewritten. OpenPokerLab was then added at the repository root, including a new `README.md`.

## Environment

Checked on this Linux machine. Nothing in this table was installed via system packages. `uv`, Docker, and Visual Studio Build Tools were left missing. Rust, Cargo, and CMake were already present and are unused by Phase 0.

| Tool | Result |
| --- | --- |
| Git | Present, 2.43.0 |
| Python | Present as `python3` 3.12.3. The `python` command is Missing |
| pip | Present, pip 24.0 (`pip` / `pip3`) |
| uv | Missing |
| Node.js | Present, v22.14.0 |
| npm | Present, 10.9.7 |
| pnpm | Present, 10.33.3 |
| Rust | Present, rustc 1.83.0 |
| Cargo | Present, cargo 1.83.0 |
| CMake | Present, 3.28.3 |
| Visual Studio Build Tools | Missing (Windows-only; this machine is Linux) |
| SQLite | Present, 3.45.1 |
| Docker | Missing |

`python3 -m venv` fails here because `ensurepip` is not installed (`python3-venv` is absent). The backend virtualenv was created with `python3 -m virtualenv` after `python3 -m pip install --user virtualenv`. PATH was not changed.

## Phase 0 delivered

- FastAPI app: `GET /health`, WebSocket `/ws` hello, CORS for `localhost:3000`
- Pydantic settings and a SQLAlchemy SQLite `SELECT 1` reported as `database: "ok"`
- No poker schema on the HTTP side
- pytest for health and the `CONNECTED` WebSocket message
- Ruff configuration
- Next.js + TypeScript home page that polls `/health` and opens the WebSocket
- Docs, `.env.example`, `.gitignore`, `AGENTS.md`

## How to run

```bash
cd /workspace
python3 -m pip install --user virtualenv
python3 -m virtualenv backend/.venv
backend/.venv/bin/pip install -e "./backend[dev]"

cd /workspace/backend
.venv/bin/pytest
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd /workspace/frontend
npm install
npm run dev
```

Health: `curl http://127.0.0.1:8000/health`

Home page: `http://127.0.0.1:3000`

## Phase 1 delivered

`backend/app/engine/` is a standard NLHE cash engine. It does not import FastAPI. `/health` and `/ws` are unchanged. The engine is now called by the room service.

Included: 2–9 players, button / SB / BB, 52-card deck, hole cards and burn + flop/turn/river, the listed streets, fold/check/call/bet/raise/all-in, main pot, side pots, split pots, odd chip, showdown, fold-win without revealing cards, `DeckProvider` (`SystemRandomDeck`, `SeededDeck`, `RiggedDeck`), and elimination at stack 0. PokerKit is used only to rank the best five cards. No ante, straddle, rake, bounty, run-it-twice, bomb pot, time bank, bots, or solver.

Engine tests:

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
```

## Phase 2 delivered

In-memory rooms on one process. No Redis. No hand SQLite schema. No bots.

- `POST /rooms`, `POST /rooms/join`, sit, stand, leave, host start / pause / settings
- `WebSocket /ws/room` with per-connection views
- Blind changes apply on the next hand
- `/play` can create or join, sit, and act
- Tests in `backend/tests/test_rooms.py`

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
cd /workspace/frontend
npm run lint
```

## Phase 3 delivered

Optional cash-game rules. The engine calls `HandRules` in `backend/app/engine/plugins.py` and does not import FastAPI or `app.rules`. Concrete rules live in `backend/app/rules/`. A room settings object selects them. Host changes apply on the next hand only. With every switch off, hands match Phase 1.

- Ante (`normal` or `bb_ante`) goes into the pot before hole cards
- UTG straddle only. Mississippi and custom are rejected
- Buy-in min/max in bb or chips, checked when sitting or adding chips. No wallet
- Auto top-up adds play-money chips at the start of a hand and records the amount
- Time bank: the server owns the deadline. Timeout folds when facing a bet, otherwise checks. Tests use `ManualClock` and do not sleep
- 72o bounty, off unless enabled. Showdown win required by default. Payments sit outside the pots. A short stack pays what it has and is marked partial
- Run it twice, off unless enabled. Offered only when every contesting player is all-in after the flop or turn. Unanimous yes. Each pot is split; run 1 gets an odd chip. Side pots keep their eligible players. Messages: `RIT_OFFER`, `RIT_VOTE`, `RIT_RESULT`
- Rake, off unless enabled, taken at payout. No-flop-no-drop skips a hand that ends before the flop
- Single-board bomb pot, off unless enabled. Double-board is rejected

`/play` shows a host rules form, yes/no when run-it-twice is offered, and rake and bounty apart from the pot. Tests are in `backend/tests/test_rules.py`.

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
cd /workspace/frontend
npm run lint
```

## Phase 4 delivered

Bots sit in a room and act through the same validated path as humans. They do not import the cash game, the deck, or other players' hole cards. The observation is the player view a human socket receives, plus position and action history.

- `PokerBot.decide(observation)` in `backend/app/bots/`
- `RuleBot`: hand strength, position, pot odds, thresholds, seeded mix
- `EquityBot`: Monte Carlo equity versus pot odds, with effective stack, SPR, and position. Parameters are tightness, aggression, bluff_frequency, and simulation_count
- `StrategyBot`: `StrategyStore` lookup. A hit samples the mix. A miss uses `EquityBot`. Fixture: `backend/app/bots/fixtures/btn_open.json`
- Host-only `POST /rooms/{id}/bots` and `POST /rooms/{id}/bots/remove`. The seat has a nickname and an internal guest token
- On `ACTION_REQUIRED` for a bot, the server asks the bot immediately, so the time bank does not fold it
- `/play` lets the host add or remove a RuleBot, EquityBot, or StrategyBot

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
```

## Phase 5 delivered

Every completed hand, including a bot hand, is written to SQLite through SQLAlchemy when the hand reaches `HAND_COMPLETE`. Alembic revision `hand_history_001` creates `players`, `rooms`, `hands`, `hand_players`, `actions`, `boards`, `pots`, `rule_events`, and the empty reserved tables `analysis_jobs`, `decision_analysis`, `player_statistics`, and `trainer_spots`. Health remains `SELECT 1`.

A stored hand can be replayed without the live room: hand id, room id, time, table settings, rule settings, button, blinds, players, starting stacks, hole cards, actions (street, player, action, amount, pot before, stack before, time), flop, turn, river, all-ins, side pots, run-it-twice boards, showdown, winners, pot payout, bounty payout, rake, and ending stacks.

`GET /hands`, `GET /hands/{id}`, and `GET /hands/{id}/state?index=` are the replay API. Before the flop is dealt, that state does not include flop cards. Opponents' hole cards appear only at the showdown step. The requesting seat's own hole cards are present from the start.

`GET /stats` computes hands played, VPIP, PFR, 3Bet, CBet, and BB/100 from stored hands. Filters: player, position, date range, blinds, and rules configuration.

- Hands played: hands in which the player was dealt cards.
- VPIP: percent of those hands with a voluntary preflop call, bet, raise, or all-in. Blinds, antes, straddles, bombs, checks, and folds do not count.
- PFR: percent of hands with a preflop raise, including an all-in that raises. A short all-in that only calls does not.
- 3Bet: reraises made while facing exactly one earlier preflop raise, divided by those chances. Null when there was no chance. An open and a 4-bet do not count.
- CBet: times the last preflop raiser bets the flop before anyone else, divided by the times that player could still be first to bet. Null when there was no chance.
- BB/100: average of (ending stack - starting stack) / big blind, times 100. Bounty and rake are already in the ending stack.

`/replay` lists hands and steps with previous, next, autoplay, and jumps to flop, turn, river, and showdown. It shows the pot, stacks, and the action. `/play` links to it.

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/alembic upgrade head
```

## Phase 6 delivered

`backend/app/solver/` is a one-decision solver boundary. The engine does not import it.

- `SolverAdapter.solve_spot(SolveRequest) -> SolveResult` and `health_check`
- `MockSolverAdapter` returns check 0.55 / bet 0.45, villain fold 0.4 / call 0.6, and metadata that says mock
- `ReferenceSolverAdapter` enumerates a heads-up river (check, bet sizes, or fold/call) with vanilla CFR. `metadata.exact` may be true. The label is `heads-up one-decision`, never Exact GTO
- Flop and turn use Monte Carlo equity inside that same tree and set `metadata.exact` false
- Multiway and preflop return `available: false` and `exact: false`
- On the hero's turn, competitive and study mode both put a mix on `you.gto`. Heads-up postflop can still use the one-decision solver. Multiway and preflop use a fast approximation with `exact` false. Bots still use `player_view` and do not see the mix
- The live multiway sentence is no longer returned. The visible Chinese label for the approximation is 近似频率，不是精确 GTO
- `GET /solver/health` and `POST /solver/solve`. The solve route writes `analysis_jobs` and `decision_analysis`. Alembic revision `analysis_002`
- `/play` has a host control for competitive / study

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
```

## Phase 7 delivered

`/analyze` rebuilds a stored hand. Important decisions are a large pot (at least 10 big blinds), a large bet, an all-in, a 3-bet pot, and every turn and river action. The response has the played line as a tree, the table at that decision, strategy, EV, and a 13×13 range matrix. EV loss in big blinds is the best action EV minus the hero action EV. Bands are configurable: under 0.1 Good, 0.1–0.5 Small, 0.5–2 Medium, 2–5 Large, over 5 Critical. Multiway results are labeled Approximate Analysis and `exact` is false.

`/trainer` stores a `TrainerSpot` for every scored mistake that is not Good. The list and the spot prompt hide frequencies, EV, the original action, and EV loss. `POST /trainer/spots/{id}/answer` reveals them after the user picks an action from that spot. Filters: street, position, severity, date. Alembic revision `trainer_003`.

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
```

## Phase 8 delivered

`docs/SOLVER_DESIGN.md` describes the one-decision tree, what may set `metadata.exact`, and what must not be called Exact GTO.

`ZetaAdapter` health and solve both return unavailable. The repository does not vendor zeta and the adapter does not import it.

`MccfrSolverAdapter` is external-sampling MCCFR on the same check/bet/fold/call tree as vanilla CFR. A heads-up river can be `exact` with label `heads-up one-decision`. Flop and turn stay Monte Carlo. Multiway and preflop stay unavailable. `GET /solver/health?adapter=mccfr` and `adapter=zeta` select them.

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
```

## Phase 9 delivered

Still play-money. No deposit, withdrawal, or cash prize.

- Short deck is a separate evaluator. Ranks are 6 through ace, A-6-7-8-9 is a straight, and a flush beats a full house. `evaluate` is unchanged, so hold'em still ranks a full house above a flush.
- Simplified insurance, off unless enabled, quotes the all-in favorite before the river. The premium comes from equity. The quoted player accepts or declines. Accepted chips move only inside the existing pot, so stacks stay non-negative. The label is `simplified`.
- A bomb pot with `boards: 2` deals two boards and awards each one separately. Run 1 receives the odd chip, the same rule as run-it-twice.
- Mississippi straddle: the button posts and acts last preflop. Custom straddle: the chosen seat posts and acts last. UTG still posts left of the big blind and acts last.
- One freezeout table: blind levels, a busted stack is out, and the last player with chips is the winner. There is no prize field.
- `GET /settings` returns the database path, GTO modes, bot kinds, variants, and straddle styles, with `cash_settlement: false`. `/settings` can update the open room.

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
```

The planned phases are complete.
