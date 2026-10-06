# Architecture

Phase 0 is the HTTP skeleton. Phase 1 is the NLHE engine. Phase 2 is in-memory multiplayer. Phase 3 is optional rule plugins. Boxes marked later are not code in this repository.

## Runtime shape

```
Browser (Next.js, frontend/)
    HTTP  GET /health
    HTTP  /rooms ...
    WebSocket /ws          hello only
    WebSocket /ws/room     table play
        |
        v
FastAPI (backend/app)
    settings, CORS, health, hello socket, room routes
        |
        v
RoomService / RoomHub (in memory, one process)
        |
        v
poker engine (backend/app/engine)
    streets, betting, pots  — local
    evaluate()              — PokerKit ranks the best five cards only

SQLite via SQLAlchemy
    connectivity check only (SELECT 1)
    no players / hands / actions tables

Later, not implemented:

SolverAdapter                    (not v1 realtime outside Study Mode)
Redis adapter                    (not in v1; document only)
bots, hand history, SQLite poker tables
```

The poker engine does not import FastAPI. When multiplayer exists, FastAPI talks to services, and services talk to the engine.

## Server-authoritative rule

The browser displays state and sends intents. It never decides cards, pots, or winners. `WebSocket /ws` is still only the hello. Table play is `WebSocket /ws/room`: each connection gets a player view. Opponent hole cards, the deck, and future board cards are not sent. Showdown reveals only players who reached it. Spectators cannot act.

## Randomness

`DeckProvider` supplies cards. Production uses `secrets.SystemRandom` (`SystemRandomDeck`). Tests use `SeededDeck` or `RiggedDeck`. Deal order consumes the front of that deck.

## Phase plan

| Phase | Scope | State |
| --- | --- | --- |
| 0 | Repo skeleton, health, WebSocket hello, status page, SQLite ping | Done |
| 1 | Standard NLHE cash engine only: 2–9 players, blinds, streets, showdown, pot and side pot, tests. No bots, GTO, or extra rules | Done |
| 2 | In-memory multiplayer: nickname, guest token, invite code, host controls, `/ws/room`, `/play`. No Redis. Nickname was delivered here | Done |
| 3 | Rule plugins: ante, UTG straddle, 72o bounty, run-it-twice, rake, single-board bomb pot, buy-in, auto top-up, time bank. Short deck and insurance stay deferred | Done |
| 4 | RuleBot, EquityBot, StrategyBot. Observation only. They act through the room | Done |
| 5 | Hand history, replay, statistics, and the SQLite tables for them | Done |
| 6 | One-decision GTO: mock adapter, heads-up river enumeration, Monte Carlo flop/turn, study vs competitive | Done |
| 7 | Analyze and trainer: important decisions, EV loss, 13×13 matrix, hidden answers | Done |
| 8 | Solver boundary: design note, unavailable ZetaAdapter, MCCFR on the one-decision tree | Done |
| 9 | Play-money short deck, insurance, double-board bombs, straddles, freezeout, `/settings` | Done |

`/` is the status page. `/play` is the table. `/replay` is hand replay. `GET /solver/health` and `POST /solver/solve` are the solver API. `/analyze` and `/trainer` review stored hands. `/settings` shows the database path and room options. There is no cash settlement.

## Explicitly out of the tree

- Copied solver source. Research names only: `noambrown/poker_solver`, `lewismj/zeta`, `pokerth`, `rootsec1/poker`. The local adapter is original code
- Real-money deposit, withdrawal, or cash settlement
- Redis

PokerKit is an installed dependency used by `app.engine.evaluator` only. Its source is not vendored, and it does not run the hand.
