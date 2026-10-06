# Solver design

OpenPokerLab solves one heads-up postflop decision. It does not solve a full game, and it does not copy `noambrown/poker_solver`, `lewismj/zeta`, `pokerth`, or `rootsec1/poker`. Those names are research references only. Zeta is not a dependency and its source is not in this repository.

The poker engine does not import FastAPI and does not import `app.solver`. Adapters may import the engine's cards and the hold'em evaluator.

## Request and result

`SolverAdapter.solve_spot(SolveRequest) -> SolveResult` plus `health_check`.

`SolveRequest` is one spot: game type, player count, board, pot, effective stack, hero and villain positions, both ranges, action history, and bet sizes.

`SolveResult` is the hero actions, frequencies, action EVs, a strategy object, exploitability, and metadata. Callers have to read metadata before they treat a number as a strategy.

## What a solve is

The tree has two shapes.

- Nobody has bet yet. Hero checks or bets one of the listed sizes. If hero bets, villain folds or calls. An uncalled bet returns the bet. A called bet awards `share * (pot + 2 * size) - size` to hero. A check awards `share * pot`.
- Villain has already bet. Hero folds (EV 0) or calls (`share * (pot + to_call) - to_call`).

`share` is hero's equity against one villain combo. On the river it is 1, 0, or 0.5 from the hold'em evaluator, over every combo in the two ranges. On the flop or turn the same tree uses a Monte Carlo share, and `metadata.exact` is false.

Vanilla CFR (`ReferenceSolverAdapter`) walks every pair and regret-matches. Villain's regret is the amount by which an action fails to minimize hero's EV. MCCFR (`MccfrSolverAdapter`) is external sampling on that same tree: each iteration draws one pair, and the traversing player updates every action while the other player is sampled. Both can set `metadata.exact` true only for an untruncated heads-up river. The label is `heads-up one-decision`.

`MockSolverAdapter` ignores the spot and returns a fixed mix. Its metadata says mock.

## What is not exact

- Preflop. The adapters return `available: false` and `exact: false`.
- More than two players. Real time, the study view says exactly: `Real-time multiway GTO analysis is not available. Post-hand analysis will be available after the hand.` Post-hand review may still show a number, and that number is labeled Approximate Analysis with `exact` false.
- Flop and turn Monte Carlo.
- A truncated range. Ranges longer than 80 combos are cut, and the result is not exact.
- A raise facing a bet. That action is outside this one-decision tree.
- Zeta. `ZetaAdapter` returns unavailable. It does not import or vendor zeta.

None of these results are labeled Exact GTO. A river enumeration is a solved one-decision tree for the ranges that were passed in. It is not a claim about the whole game.

## Who sees a mix

Competitive mode is the default. During a hand the human view has no frequencies. Study mode may attach `you.gto` for a human in a heads-up postflop spot. Bots call `player_view` and never receive that object. `POST /solver/solve` is the call that writes `analysis_jobs`. Polling the table does not.

## Adding another adapter

Implement `solve_spot` and `health_check`. Set `metadata.solver`, `metadata.exact`, and `metadata.label`. If the spot is not the heads-up one-decision tree above, return `exact: false` and do not use the words Exact GTO. Do not add a native extension or a copied C++ solver to make the label stronger.
