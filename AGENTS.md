# AGENTS.md

Instructions for later agents working in this repository. Read this file before writing code.

## Goal

OpenPokerLab is a long-term self-hosted No-Limit Hold'em cash-game platform for entertainment, research, and training. There is no real-money deposit, withdrawal, cash settlement, or third-party poker-room automation.

## Current phase

Phase 0 through Phase 9 are done. The planned phases are complete.

Phase 1 is the standard NLHE cash engine in `backend/app/engine/`. It does not import FastAPI. PokerKit is used only behind `evaluate` for five-card ranking. Betting, streets, and pots are local code.

Phase 2 is in-memory multiplayer in `backend/app/services/` and `backend/app/api/`. One process, no Redis. Identity is nickname + `guest_token` + invite code. Play goes through `WebSocket /ws/room`. `/play` is the table page.

Phase 4 bots sit in that room and act through the same validated action path. They only see a player observation.

Phase 5 writes every completed hand, including bot hands, to SQLite when the hand finishes. Replay and statistics read those rows. `/replay` is the replay page.

Phase 6 is `backend/app/solver/`. `MockSolverAdapter` is a stable labeled mock. `ReferenceSolverAdapter` solves one heads-up postflop decision. River enumeration may set `metadata.exact` true and is labeled `heads-up one-decision`. Flop and turn use Monte Carlo in that same tree and set `metadata.exact` false. The reference adapter still returns unavailable for multiway and preflop. Never write the label Exact GTO. During a hand, both competitive and study mode attach a mix on the acting human's view, including multiway and preflop. Heads-up postflop keeps that one-decision solver when it applies, and `exact` is true only in the cases that solver already treats as exact. Three or more dealt players, or three or more still contesting, use `approximate_mix`: inferred ranges, a small equity sample, then a mix over the legal actions. That result has `metadata.exact` false and the label `Approximate frequencies, not exact GTO.` Competitive mode omits the mix when it is not that player's turn. Bots keep using `player_view` and do not see the mix. Jobs are written only by `POST /solver/solve`.

Phase 7 is `/analyze` and `/trainer`. Analysis rebuilds a stored hand and lists important decisions: large pot (at least 10 big blinds), large bet, all-in, 3-bet pot, turn, and river. It shows the played hand as a tree, the table, strategy, EV, and a 13×13 range matrix. EV loss in big blinds is the best action EV minus the hero action EV. Default bands: under 0.1 Good, 0.1–0.5 Small, 0.5–2 Medium, 2–5 Large, over 5 Critical. Bounds are query parameters. Multiway results are labeled Approximate Analysis and are not exact. Mistakes other than Good become `TrainerSpot` rows. The trainer hides frequencies, EV, the original action, and EV loss until the user picks an action. Filters are street, position, severity, and date.

Phase 8 is `docs/SOLVER_DESIGN.md`. `ZetaAdapter` returns unavailable and does not vendor zeta. `MccfrSolverAdapter` is external-sampling MCCFR on the same heads-up one-decision tree as vanilla CFR. Multiway stays unavailable or approximate and is never Exact GTO.

Phase 9 stays play-money. Short deck is `evaluate_short` in `app.engine.short_deck` and does not change `evaluate`. Insurance is a simplified all-in quote before the river, labeled simplified, and it is off unless the room enables it. A double-board bomb pot is `boards: 2` only. Mississippi straddles from the button and acts last preflop. A custom straddle is a chosen seat and acts last. UTG still works. A tournament is one freezeout table with blind levels, bust-out, and a chip winner. There is no cash prize. `/settings` exposes the database path and can change the current room's rules, bots, GTO mode, and variant.

Do not add real-money deposit, withdrawal, or cash settlement. Do not label an approximate solve Exact GTO.

## Architecture

```
browser → FastAPI → services → poker engine → SQLite
                              → SolverAdapter
```

FastAPI talks to `RoomService` / `RoomHub`, and those call the engine. Rule plugins are in `backend/app/rules/`. Bots are in `backend/app/bots/` and must not import the cash-game object, the deck provider, or room internals. Solvers are in `backend/app/solver/`. The engine does not import that package.

The engine must not import FastAPI. Room code must not let a client choose cards, the deck, or pots.

## Hard constraints

- Server-authoritative game play: the client never decides cards, pots, or winners. `/ws/room` builds every `GAME_STATE` and card message per connection. Opponents' hole cards stay hidden until showdown, and only seats that reached showdown are revealed. Spectators use the same hiding rules and cannot act.
- Randomness goes through `DeckProvider`: `SystemRandomDeck` (`secrets.SystemRandom`) in production; `SeededDeck` and `RiggedDeck` in tests.
- PokerKit ranks hands inside `app.engine.evaluator` only. Do not move the state machine into PokerKit. Do not vendor third-party source.
- Reference solvers are research notes only. Do not copy their code: `noambrown/poker_solver`, `lewismj/zeta`, `pokerth`, `rootsec1/poker`.
- Bots (`RuleBot`, `EquityBot`, `StrategyBot`) may only see a player observation: own hole cards, board, pot, stacks, legal actions, position, street, and action history. No opponent hole cards and no deck. The host adds and removes them. A bot acts immediately on `ACTION_REQUIRED`, so the time bank does not fold it.
- Realtime GTO is Study Mode only: heads-up, a single postflop decision. Competitive mode is the default and hides the mix during the hand. Post-hand analysis is allowed. Multiway during a hand uses the fixed unavailable sentence. Do not label an approximate result Exact GTO.
- Rules are plugins and stay off unless a room enables them. Host changes apply on the next hand. Included: ante, UTG / Mississippi / custom straddle, 72o bounty, run-it-twice, rake, single-board and double-board bomb pots, buy-in, auto top-up, time bank, and simplified insurance. Short deck is a table variant, not a change to hold'em rankings. A tournament is one play-money freezeout with no cash prize.
- Identity is nickname plus invite code plus `guest_token`. No passwords. A disconnect keeps the seat until leave.
- No Redis in v1. A future Redis adapter may be mentioned in docs only.
- `/` is the status page. `/play` is the table. `/replay` is hand replay. `/analyze` reviews a stored hand. `/trainer` drills saved mistakes. `/settings` shows the database path and room options. `/play` may show study-mode advice.
- `legacy/quote-bot/` is an unrelated Learning Lab starter. Leave it unchanged.
- Do not rewrite git history to remove that starter.

## Interfaces that must not be broken

`GET /health` returns HTTP 200 and JSON:

```json
{"status":"ok","service":"openpokerlab","database":"ok"}
```

`database` is `"ok"` when SQLAlchemy can run `SELECT 1` against the configured SQLite URL. Alembic creates the poker tables. Health does not inspect them.

`WebSocket /ws` accepts the connection and sends one hello before any other server message:

```json
{"type":"CONNECTED","payload":{"service":"openpokerlab"}}
```

Do not put decks, cards, or hidden state on this socket. Echo is optional and is not implemented.

`WebSocket /ws/room` is the table socket. The first client message is `{"type":"JOIN","payload":{"guest_token":"..."}}`. Replies include `ROOM_JOINED`, `PLAYER_JOINED`, `PLAYER_LEFT`, `PLAYER_RECONNECTED`, `HAND_STARTED`, `CARDS_DEALT`, `ACTION_REQUIRED`, `ACTION_RESULT`, `FLOP`, `TURN`, `RIVER`, `SHOWDOWN`, `HAND_COMPLETE`, `GAME_STATE`, `ERROR`, and, when run-it-twice is offered, `RIT_OFFER`, `RIT_VOTE`, and `RIT_RESULT`. A player action is `{"type":"PLAYER_ACTION","request_id":"...","payload":{"action":"raise","amount":120}}`. `raise` amount is the street total (`Action.raise_to`). `bet` amount is chips put in. A run-it-twice vote is `{"type":"RIT_VOTE","request_id":"...","payload":{"accept":true}}`. When the time bank is on, `ACTION_REQUIRED` includes `remaining_seconds` and `deadline`.

Host-only HTTP: `POST /rooms/{id}/start`, `/pause`, `/settings`, `/bots`, and `/bots/remove`. Blind and rule changes apply on the next hand, never mid-hand. Non-host attempts return `ERROR` with HTTP 403. Sitting posts 1000 play-money chips the first time, unless buy-in limits are on; `POST /rooms/{id}/sit` may send `amount`, and `POST /rooms/{id}/chips` adds play-money chips. A bot seat gets a nickname and an internal guest token that is not returned to the browser.

CORS allows the Next.js app on localhost, `127.0.0.1`, and private LAN hosts, including a single-label PC name. It echoes that origin. It is not a credentialed wildcard, and a public origin is rejected.

Settings environment names: `API_HOST`, `API_PORT`, `DATABASE_URL`. Frontend: `NEXT_PUBLIC_API_URL`. When that variable is unset, the browser uses the page hostname on port 8000, and the socket uses `ws` or `wss` to match the page. `NEXT_PUBLIC_WS_URL` overrides only the `/ws` hello socket.

Engine contracts:

- `CashGame(stacks, button=, small_blind=, big_blind=, deck=, rules=None)` then `start_hand()` and `apply(action, seat=None)`. `rules` defaults to no-op `HandRules`. Concrete rules are not imported by the engine.
- `Action.fold/check/call/bet/raise_to/all_in`. Chips are integers. `bet` is chips put in; `raise_to` is the street total.
- `IllegalActionError` leaves the hand unchanged.
- Streets: `WAITING`, `POSTING_BLINDS`, `PREFLOP`, `FLOP`, `TURN`, `RIVER`, `SHOWDOWN`, `PAYOUT`, `HAND_COMPLETE`.
- Statuses: `ACTIVE`, `FOLDED`, `ALL_IN`, `SITTING_OUT`, `DISCONNECTED`, `ELIMINATED`. Only the first three plus post-hand `ELIMINATED` have behavior.
- `public_view(viewer)` hides other hole cards unless that seat reached showdown.
- `DeckProvider.shuffle` returns a 52-card permutation, index 0 drawn first. Rigged prefixes are consumed first, in deal order: from the small blind, clockwise, two cards each, then burn, flop, burn, turn, burn, river. Heads-up, the button is the small blind and receives the first card.

## Bot status

Implemented in `backend/app/bots/`. `PokerBot.decide(observation)` returns an action. The room builds the observation with `player_view` and applies the choice through `act`. `RuleBot` uses hand strength, position, pot odds, thresholds, and a seeded mix. `EquityBot` compares Monte Carlo equity with pot odds, using effective stack, SPR, and position (`tightness`, `aggression`, `bluff_frequency`, `simulation_count`). `StrategyBot` looks up `StrategyStore` by blinds, position, stack depth, board, and action history. A hit samples that mix. A miss uses `EquityBot`. The shipped fixture is `backend/app/bots/fixtures/btn_open.json` (button opens to 6). Tests cover a hidden observation, the fixture and the fallback, host add/remove, 10000 seeded RuleBot hands, and a short EquityBot run.

## Hand history

Completed hands are stored with SQLAlchemy. `HandHistory.save_room` runs from the room when the street becomes `HAND_COMPLETE`. The row has the hand id, room id, time, table settings, rule settings, button, blinds, players, starting stacks, hole cards, actions (street, player, action, amount, pot before, stack before, time), flop, turn, river, all-ins, side pots, run-it-twice boards, showdown, winners, pot payout, bounty payout, rake, and ending stacks.

Replay: `GET /hands`, `GET /hands/{id}`, `GET /hands/{id}/state?index=`. Before the flop is dealt, the state has no flop cards. Opponents' hole cards appear only on the showdown step. `viewer_seat` sees that seat's own hole cards from the first step. `/replay` steps with previous, next, autoplay, and jumps to flop, turn, river, and showdown.

Statistics come from stored hands, plus stored `decision_analysis` rows for the EV sums. The JSON fields are hands played, VPIP, PFR, 3Bet, CBet, BB/100, `fold_to_3bet`, `wtsd`, `wssd`, `aggression_factor`, `fold_to_cbet`, `ev_bb`, `gto_ev_bb`, `ev_loss_bb`, and `mistake_counts`. Filters are player, position, date range, blinds, rules configuration, and an optional `street`. Definitions are in `backend/app/history/stats.py` and `README.md`. `POST /solver/solve` writes `analysis_jobs` and `decision_analysis`. Post-hand analysis writes those rows and, for a mistake, `trainer_spots`. `player_statistics` is unused; `/stats` calculates from the hand and analysis rows.

```bash
cd /workspace/backend
.venv/bin/alembic upgrade head
```

## Solver status

Implemented in `backend/app/solver/`. There is no vendored third-party solver.

- `MockSolverAdapter` returns a fixed mix. `metadata.solver` is `mock`, `metadata.mock` is true, and `metadata.exact` is false. It ignores the request. It is for tests and the UI, not a strategy.
- `ReferenceSolverAdapter` solves one heads-up postflop decision. River enumeration may set `metadata.exact` true. The label is `heads-up one-decision`. Flop and turn use Monte Carlo in that same tree and set `metadata.exact` false. Multiway and preflop return unavailable. The label Exact GTO is never written.
- `MccfrSolverAdapter` runs external-sampling MCCFR on that same heads-up one-decision tree. A river solve may be `exact` and keeps the label `heads-up one-decision`. It is not a full-game solve.
- `ZetaAdapter` does not vendor zeta. `health_check` returns `unavailable`. `solve_spot` returns an empty result with `metadata.available` false and the reason `zeta is not vendored`.

`GET /solver/health?adapter=` selects `mock`, `reference`, `mccfr`, or `zeta`. `POST /solver/solve` is the only call that writes a solver job. Study mode may attach a heads-up postflop mix to the human view. Competitive mode is the default and does not. Bots do not see GTO.

## Rule-plugin status

Implemented in `backend/app/engine/plugins.py` (`HandRules`) and `backend/app/rules/`. A room's settings object selects them. Disabled rules leave the hand as standard NLHE. Bounty and rake are reported apart from the pot. Run-it-twice needs a unanimous yes after the flop or turn when everyone still contesting is all-in. The time bank uses an injected clock in tests (`ManualClock`); the production clock may wait, and tests must not sleep.

## How to test

From `backend/` with the project virtualenv:

```bash
pytest
ruff check .
```

Frontend, from `frontend/`:

```bash
npm run lint
npm run build
```

`backend/.venv/bin/pytest` covers Phase 0 (`GET /health`, WebSocket `CONNECTED`), the Phase 1 engine, Phase 2 rooms (`backend/tests/test_rooms.py`), Phase 3 rules (`backend/tests/test_rules.py`), Phase 4 bots (`backend/tests/test_bots.py`), and Phase 5 history (`backend/tests/test_history.py`). Solver tests are `backend/tests/test_solver.py`. Post-hand analysis and the trainer are `backend/tests/test_analyze.py`. Short deck, insurance, double-board bomb pots, straddles, and the freezeout are `backend/tests/test_variants.py`. Tests set `DATABASE_URL=sqlite:///:memory:` in `backend/tests/conftest.py`. The RuleBot simulation asserts 10000 hands when they finish within about 60 seconds. History tests migrate a temporary SQLite file with Alembic.

```bash
cd /workspace/backend
.venv/bin/pytest
.venv/bin/ruff check .
```

## Common commands

```bash
# This Linux machine: python3-venv is unavailable. Do not apt-install it.
python3 -m pip install --user virtualenv
python3 -m virtualenv backend/.venv
backend/.venv/bin/pip install -e "./backend[dev]"

cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

cd frontend
npm install
npm run dev
```

On a machine where `python -m venv` works (typical Windows 10/11), use that instead of `virtualenv`. See `README.md`.

## Decisions already made

Do not re-ask these. Phases 0 through 9 are already delivered. The record is `docs/ARCHITECTURE.md`. There is no further planned phase. Do not add real-money deposit, withdrawal, or a cash prize.
