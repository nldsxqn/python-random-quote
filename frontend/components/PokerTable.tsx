"use client";

import { Fragment, useEffect, useState } from "react";

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
  seatCount?: number | null;
  layout?: "screen" | "embedded";
};

const SUITS: Record<string, string> = { s: "♠", h: "♥", d: "♦", c: "♣" };

export function PlayingCard({ code, hero = false }: { code: string; hero?: boolean }) {
  const rankChar = code[0]?.toUpperCase() ?? "";
  const suitKey = code.slice(-1).toLowerCase();
  const red = suitKey === "h" || suitKey === "d";
  const rank = rankChar === "T" ? "10" : rankChar;
  const suit = SUITS[suitKey] ?? suitKey;
  return (
    <span
      className={`playing-card${red ? " red" : ""}${hero ? " hero-card" : ""}`}
      data-card={code}
      aria-label={code}
    >
      <span className="pip">
        {rank}
        <small>{suit}</small>
      </span>
      <span className="suit-big">{suit}</span>
      <span className="code">{code}</span>
    </span>
  );
}

export function CardBack({ hero = false }: { hero?: boolean }) {
  return <span className={`playing-card back${hero ? " hero-card" : ""}`} aria-hidden="true" />;
}

export function ChipStack({ amount, testId }: { amount: number; testId?: string }) {
  const layers = amount >= 100 ? 4 : amount >= 20 ? 3 : amount >= 5 ? 2 : 1;
  return (
    <span className="chip-stack" data-testid={testId}>
      {Array.from({ length: layers }, (_, index) => (
        <span className={`chip tone-${index % 4}`} key={index} />
      ))}
      <span className="chip-amount">{amount}</span>
    </span>
  );
}

export default function PokerTable(props: TableProps) {
  const { t } = useI18n();
  const clock = useCountdown(props.remainingSeconds, props.actorSeat ?? null);
  const occupied = Math.max(props.seatCount ?? 6, ...props.players.map((player) => player.seat + 1), 2);
  const anchor = props.heroSeat !== null && props.heroSeat < occupied ? props.heroSeat : 0;
  const bySeat = new Map(props.players.map((player) => [player.seat, player]));
  const live = Boolean(props.street && props.street !== "WAITING" && props.street !== "HAND_COMPLETE");
  const slots = Array.from({ length: occupied }, (_, seat) => seat);

  return (
    <div
      className={props.layout === "embedded" ? "table-scene embedded" : "table-scene"}
      data-testid="poker-table"
      data-seats={occupied}
    >
      <div className="wood-rail" />
      <div className="felt-oval" />
      <div className="table-center">
        <p className="table-note" data-testid="hand-status">
          {props.handNumber != null ? (
            <span data-testid="hand-number">
              {t("Hand")} {props.handNumber}
            </span>
          ) : null}
          {props.handNumber != null ? " · " : ""}
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
        <div className="pot-row">
          <ChipStack amount={props.pot} />
          <p className="pot-chip" data-testid="pot">
            {t("Pot")} {props.pot}
          </p>
        </div>
      </div>
      {slots.map((seat) => {
        const player = bySeat.get(seat) ?? null;
        const place = slotStyle(seat, occupied, anchor);
        if (!player) {
          return (
            <div className="table-seat empty" key={`empty-${seat}`} style={place}>
              <span className="empty-seat" aria-label={t("Empty seat")} />
            </div>
          );
        }
        const hero = props.heroSeat !== null && player.seat === props.heroSeat;
        const cards = holeCards(player, live, Boolean(props.showdown));
        const bet = player.committed_street ?? 0;
        const acting = Boolean(player.is_actor && clock.left !== null && clock.total > 0);
        return (
          <Fragment key={player.seat}>
            {bet > 0 ? (
              <div className="bet-spot" style={betStyle(seat, occupied, anchor)}>
                <ChipStack amount={bet} testId="seat-bet" />
              </div>
            ) : null}
          <div
            className="table-seat"
            data-actor={player.is_actor ? "true" : "false"}
            data-hero={hero ? "true" : "false"}
            data-seat={player.seat}
            style={place}
          >
            <div className="seat-cards" data-testid={hero ? "hole-cards" : undefined}>
              {cards.kind === "faces"
                ? cards.codes.map((code) => <PlayingCard code={code} hero={hero} key={code} />)
                : null}
              {cards.kind === "backs" ? (
                <>
                  <CardBack hero={hero} />
                  <CardBack hero={hero} />
                </>
              ) : null}
            </div>
            <div className="seat-plate">
              <span className={`avatar${acting ? " timing" : ""}`}>
                {acting ? <TimerRing left={clock.left ?? 0} total={clock.total} /> : null}
                <span aria-hidden="true">{player.nickname.slice(0, 1) || "?"}</span>
                {acting ? (
                  <span className="action-timer" data-testid="action-timer">
                    {clock.left}s
                  </span>
                ) : null}
              </span>
              <span className="seat-copy">
                <strong>{player.nickname}</strong>
                <span>
                  {t("Stack")} {player.stack}
                </span>
              </span>
              <span className="seat-marks">
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
                  <span className="blind-mark bb" data-testid="seat-bb">
                    {t("BB")}
                  </span>
                ) : null}
              </span>
            </div>
          </div>
          </Fragment>
        );
      })}
    </div>
  );
}

function TimerRing({ left, total }: { left: number; total: number }) {
  const radius = 18;
  const length = 2 * Math.PI * radius;
  const fraction = total <= 0 ? 0 : Math.max(0, Math.min(1, left / total));
  return (
    <svg className="timer-ring" viewBox="0 0 44 44" aria-hidden="true">
      <circle className="timer-track" cx="22" cy="22" r={radius} />
      <circle
        className="timer-left"
        cx="22"
        cy="22"
        r={radius}
        strokeDasharray={length}
        strokeDashoffset={length * (1 - fraction)}
      />
    </svg>
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

function slotStyle(seat: number, count: number, anchor: number): { left: string; top: string } {
  const index = (seat - anchor + count) % count;
  const angle = Math.PI / 2 + (2 * Math.PI * index) / count;
  return point(angle, 44, 40);
}

function betStyle(seat: number, count: number, anchor: number): { left: string; top: string } {
  const index = (seat - anchor + count) % count;
  const angle = Math.PI / 2 + (2 * Math.PI * index) / count;
  return point(angle, 26, 22);
}

function point(angle: number, rx: number, ry: number): { left: string; top: string } {
  return {
    left: `${50 + rx * Math.cos(angle)}%`,
    top: `${50 + ry * Math.sin(angle)}%`,
  };
}

function useCountdown(remaining: number | null, actor: number | null): { left: number | null; total: number } {
  const [left, setLeft] = useState<number | null>(remaining);
  const [total, setTotal] = useState(remaining ?? 0);

  useEffect(() => {
    setLeft(remaining);
    setTotal(remaining ?? 0);
    if (remaining === null) {
      return;
    }
    const timer = window.setInterval(() => {
      setLeft((current) => (current === null ? null : Math.max(0, current - 1)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [remaining, actor]);

  return { left, total };
}
