"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";

export type TableSeat = {
  seat: number;
  nickname: string;
  stack: number;
  status?: string;
  committed_street?: number;
  hole_cards: string[] | null;
  is_actor?: boolean;
};

export type TableProps = {
  street: string | null;
  board: string[];
  boards?: string[][];
  pot: number;
  buttonSeat: number | null;
  smallBlindSeat: number | null;
  bigBlindSeat: number | null;
  handNumber: number | null;
  remainingSeconds: number | null;
  actorSeat?: number | null;
  heroSeat: number | null;
  players: TableSeat[];
  showdown?: boolean;
};

const RED_SUITS = new Set(["h", "d"]);

export function PlayingCard({ code }: { code: string }) {
  const suit = code.slice(-1).toLowerCase();
  return (
    <span className={RED_SUITS.has(suit) ? "playing-card red" : "playing-card"} data-card={code}>
      {code}
    </span>
  );
}

export function CardBack() {
  return <span className="playing-card back" aria-hidden="true" />;
}

export default function PokerTable(props: TableProps) {
  const { t } = useI18n();
  const seconds = useCountdown(props.remainingSeconds, props.actorSeat ?? null);
  const seated = ring(props.players, props.heroSeat);
  const live = Boolean(props.street && props.street !== "WAITING" && props.street !== "HAND_COMPLETE");

  return (
    <div className="table-scene" data-testid="poker-table">
      <div className="felt-oval" />
      <div className="table-center">
        {props.handNumber != null ? (
          <p className="table-note" data-testid="hand-number">
            {t("Hand")} {props.handNumber}
          </p>
        ) : null}
        <p className="table-note" data-testid="hand-status">
          {t(props.street ?? "WAITING")}
        </p>
        {props.boards && props.boards.length > 1 ? (
          <div data-testid="board" data-runs="true">
            {props.boards.map((run, index) => (
              <div className="board-cards" key={run.join("-") || index}>
                <span className="table-note">
                  {t("Run")} {index + 1}
                </span>
                {run.map((code) => (
                  <PlayingCard code={code} key={`${index}-${code}`} />
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div className="board-cards" data-testid="board">
            {props.board.map((code) => (
              <PlayingCard code={code} key={code} />
            ))}
          </div>
        )}
        <p className="pot-chip" data-testid="pot">
          {t("Pot")} {props.pot}
        </p>
      </div>
      {seated.map((player, index) => {
        const hero = props.heroSeat !== null && player.seat === props.heroSeat;
        const cards = holeCards(player, live, Boolean(props.showdown));
        return (
          <div
            className="table-seat"
            data-actor={player.is_actor ? "true" : "false"}
            data-hero={hero ? "true" : "false"}
            data-seat={player.seat}
            key={player.seat}
            style={seatStyle(index, seated.length)}
          >
            <div className="seat-cards" data-testid={hero ? "hole-cards" : undefined}>
              {cards.kind === "faces"
                ? cards.codes.map((code) => <PlayingCard code={code} key={code} />)
                : null}
              {cards.kind === "backs" ? (
                <>
                  <CardBack />
                  <CardBack />
                </>
              ) : null}
            </div>
            <div className="seat-plate">
              <span className="avatar" aria-hidden="true">
                {player.nickname.slice(0, 1) || "?"}
              </span>
              <div className="seat-copy">
                <strong>{player.nickname}</strong>
                <div>
                  {t("Stack")} {player.stack}
                </div>
                <div data-testid="seat-bet">
                  {t("Current bet")} {player.committed_street ?? 0}
                </div>
                {player.is_actor && seconds !== null ? (
                  <div className="action-timer" data-testid="action-timer">
                    {seconds}s
                  </div>
                ) : null}
              </div>
              <div className="seat-marks">
                {player.seat === props.buttonSeat ? (
                  <span className="dealer-button" data-testid="dealer-button">
                    {t("D")}
                  </span>
                ) : null}
                {player.seat === props.smallBlindSeat ? (
                  <span className="blind-mark" data-testid="seat-sb">
                    {t("SB")}
                  </span>
                ) : null}
                {player.seat === props.bigBlindSeat ? (
                  <span className="blind-mark" data-testid="seat-bb">
                    {t("BB")}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function holeCards(
  player: TableSeat,
  live: boolean,
  showdown: boolean,
): { kind: "faces"; codes: string[] } | { kind: "backs" } | { kind: "none" } {
  const codes = player.hole_cards ?? [];
  if (codes.length > 0) {
    return { kind: "faces", codes };
  }
  if (showdown || player.status === "FOLDED" || player.status === "ELIMINATED") {
    return { kind: "none" };
  }
  if (!live) {
    return { kind: "none" };
  }
  return { kind: "backs" };
}

function ring(players: TableSeat[], heroSeat: number | null): TableSeat[] {
  if (players.length === 0) {
    return [];
  }
  const ordered = [...players].sort((left, right) => left.seat - right.seat);
  const anchor = heroSeat ?? ordered[0].seat;
  const start = ordered.findIndex((player) => player.seat === anchor);
  const at = start < 0 ? 0 : start;
  return [...ordered.slice(at), ...ordered.slice(0, at)];
}

function seatStyle(index: number, count: number): { left: string; top: string } {
  const angle = Math.PI / 2 + (2 * Math.PI * index) / Math.max(count, 1);
  const x = 50 + 38 * Math.cos(angle);
  const y = 50 + 34 * Math.sin(angle);
  return { left: `${x}%`, top: `${y}%` };
}

function useCountdown(remaining: number | null, actor: number | null): number | null {
  const [left, setLeft] = useState<number | null>(remaining);

  useEffect(() => {
    setLeft(remaining);
    if (remaining === null) {
      return;
    }
    const timer = window.setInterval(() => {
      setLeft((current) => (current === null ? null : Math.max(0, current - 1)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [remaining, actor]);

  return left;
}
