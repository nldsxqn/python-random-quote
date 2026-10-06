"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiUrl } from "@/lib/server-url";

type HandSummary = {
  id: number;
  room_id: string;
  completed_at: string;
  small_blind: number;
  big_blind: number;
  players: { seat: number; nickname: string; position: string }[];
};

type ReplayPlayer = {
  seat: number;
  nickname: string;
  position: string;
  stack: number;
  hole_cards: string[] | null;
  is_bot: boolean;
};

type ReplayState = {
  index: number;
  step_count: number;
  street: string;
  board: string[];
  boards: string[][];
  pot: number;
  rake: number;
  bounty: number;
  action: { action: string; street: string; seat: number | null; amount: number | null; put_in?: number } | null;
  players: ReplayPlayer[];
  jumps: { flop: number | null; turn: number | null; river: number | null; showdown: number | null };
  showdown: boolean;
};

type HandDetail = {
  id: number;
  step_count: number;
  jumps: ReplayState["jumps"];
  players: { seat: number; nickname: string }[];
};

export default function ReplayPage() {
  const [roomId, setRoomId] = useState<string | null>(null);
  const [hands, setHands] = useState<HandSummary[]>([]);
  const [handId, setHandId] = useState<number | null>(null);
  const [detail, setDetail] = useState<HandDetail | null>(null);
  const [viewer, setViewer] = useState<number | null>(null);
  const [index, setIndex] = useState(0);
  const [state, setState] = useState<ReplayState | null>(null);
  const [autoplay, setAutoplay] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setRoomId(params.get("room"));
  }, []);

  useEffect(() => {
    const query = roomId ? `?room_id=${encodeURIComponent(roomId)}` : "";
    void fetch(apiUrl(`/hands${query}`))
      .then(async (response) => {
        if (!response.ok) {
          setError("Could not load hands");
          return;
        }
        const body = (await response.json()) as { hands: HandSummary[] };
        setHands(body.hands);
      })
      .catch(() => setError("Could not reach the server"));
  }, [roomId]);

  useEffect(() => {
    if (handId === null) {
      return;
    }
    const seat = viewer === null ? "" : `?viewer_seat=${viewer}`;
    void fetch(apiUrl(`/hands/${handId}${seat}`))
      .then(async (response) => {
        if (!response.ok) {
          setError("Could not load that hand");
          return;
        }
        const body = (await response.json()) as HandDetail;
        setDetail(body);
        setIndex(0);
        if (viewer === null && body.players.length > 0) {
          setViewer(body.players[0].seat);
        }
      })
      .catch(() => setError("Could not reach the server"));
  }, [handId, viewer]);

  useEffect(() => {
    if (handId === null) {
      return;
    }
    const seat = viewer === null ? "" : `&viewer_seat=${viewer}`;
    void fetch(apiUrl(`/hands/${handId}/state?index=${index}${seat}`))
      .then(async (response) => {
        if (!response.ok) {
          setError("Could not load that action");
          return;
        }
        setState((await response.json()) as ReplayState);
      })
      .catch(() => setError("Could not reach the server"));
  }, [handId, index, viewer]);

  useEffect(() => {
    if (!autoplay || detail === null) {
      return;
    }
    const timer = window.setInterval(() => {
      setIndex((current) => {
        if (current + 1 >= detail.step_count) {
          setAutoplay(false);
          return current;
        }
        return current + 1;
      });
    }, 700);
    return () => window.clearInterval(timer);
  }, [autoplay, detail]);

  function jump(target: number | null): void {
    if (target === null) {
      return;
    }
    setAutoplay(false);
    setIndex(target);
  }

  const action = state?.action;
  const actionText = action
    ? `${action.street} ${action.action}${action.amount !== null && action.amount !== undefined ? ` ${action.amount}` : ""}`
    : "";

  return (
    <main className="play">
      <h1>Replay</h1>
      <p className="note">
        <Link href="/play">Table</Link>
      </p>
      <p className="error" data-testid="error">
        {error}
      </p>
      <section className="table" aria-label="Saved hands">
        <h2>Hands</h2>
        <ul className="hand-list" data-testid="hand-list">
          {hands.length === 0 ? <li>No saved hands yet.</li> : null}
          {hands.map((hand) => (
            <li key={hand.id}>
              <button
                type="button"
                data-testid="hand-row"
                data-hand={hand.id}
                onClick={() => {
                  setAutoplay(false);
                  setViewer(null);
                  setHandId(hand.id);
                }}
              >
                #{hand.id} {hand.small_blind}/{hand.big_blind}{" "}
                {hand.players.map((player) => player.nickname).join(", ")}
              </button>
            </li>
          ))}
        </ul>
      </section>
      {state && detail ? (
        <section className="table felt" aria-label="Hand replay">
          <h2 data-testid="replay-street">{state.street}</h2>
          <p className="meta" data-testid="replay-pot">
            Pot {state.pot}
            {state.showdown ? ` · rake ${state.rake} · bounty ${state.bounty}` : ""}
          </p>
          <p className="meta" data-testid="replay-action">
            {actionText}
          </p>
          <div className="cards" data-testid="replay-board">
            {state.board.length === 0 ? <span className="card">—</span> : null}
            {state.board.map((card) => (
              <span className="card" key={card}>
                {card}
              </span>
            ))}
          </div>
          {state.boards.length > 1 ? (
            <div data-testid="replay-runs">
              {state.boards.map((board, run) => (
                <p className="meta" key={board.join("-")}>
                  Run {run + 1}: {board.join(" ")}
                </p>
              ))}
            </div>
          ) : null}
          <ul className="seats">
            {state.players.map((player) => (
              <li className="seat" data-testid="replay-seat" data-seat={player.seat} key={player.seat}>
                <strong>
                  {player.nickname} {player.position}
                </strong>
                <div>Stack {player.stack}</div>
                <div>{player.hole_cards ? player.hole_cards.join(" ") : "hidden"}</div>
              </li>
            ))}
          </ul>
          <div className="row">
            <button
              type="button"
              data-testid="prev-action"
              disabled={index <= 0}
              onClick={() => {
                setAutoplay(false);
                setIndex((current) => Math.max(0, current - 1));
              }}
            >
              Previous
            </button>
            <button
              type="button"
              data-testid="next-action"
              disabled={index + 1 >= detail.step_count}
              onClick={() => {
                setAutoplay(false);
                setIndex((current) => current + 1);
              }}
            >
              Next
            </button>
            <button type="button" data-testid="autoplay" onClick={() => setAutoplay((current) => !current)}>
              {autoplay ? "Stop" : "Autoplay"}
            </button>
            <button type="button" data-testid="jump-flop" disabled={detail.jumps.flop === null} onClick={() => jump(detail.jumps.flop)}>
              Flop
            </button>
            <button type="button" data-testid="jump-turn" disabled={detail.jumps.turn === null} onClick={() => jump(detail.jumps.turn)}>
              Turn
            </button>
            <button type="button" data-testid="jump-river" disabled={detail.jumps.river === null} onClick={() => jump(detail.jumps.river)}>
              River
            </button>
            <button
              type="button"
              data-testid="jump-showdown"
              disabled={detail.jumps.showdown === null}
              onClick={() => jump(detail.jumps.showdown)}
            >
              Showdown
            </button>
          </div>
        </section>
      ) : null}
    </main>
  );
}
