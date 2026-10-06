"use client";

import { Fragment, useEffect, useRef, useState } from "react";

import { displayName, useI18n } from "@/lib/i18n";

export type TableSeat = {
  seat: number;
  nickname: string;
  stack: number;
  status?: string;
  committed_street?: number;
  hole_cards: string[] | null;
  is_actor?: boolean;
};

export type TableWinner = {
  seat: number;
  amount: number;
  category?: string | null;
  cards?: string[] | null;
};

export type TableAction = {
  action: string;
  seat: number | null;
  token: string;
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
  onSit?: (seat: number) => void;
  winners?: Array<TableWinner | number>;
  latestAction?: TableAction | null;
};

const SUITS: Record<string, string> = { s: "♠", h: "♥", d: "♦", c: "♣" };

export function PlayingCard({
  code,
  hero = false,
  mark,
}: {
  code: string;
  hero?: boolean;
  mark?: "win" | "dim";
}) {
  const rankChar = code[0]?.toUpperCase() ?? "";
  const suitKey = code.slice(-1).toLowerCase();
  const red = suitKey === "h" || suitKey === "d";
  const rank = rankChar === "T" ? "10" : rankChar;
  const suit = SUITS[suitKey] ?? suitKey;
  const tone = mark === "win" ? " win" : mark === "dim" ? " dim" : "";
  return (
    <span
      className={`playing-card${red ? " red" : ""}${hero ? " hero-card" : ""}${tone}`}
      data-card={code}
      data-winning={mark === "win" ? "true" : undefined}
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

const CHIP_ACTIONS = new Set(["bet", "call", "raise", "all_in"]);

function listedWinners(raw: Array<TableWinner | number> | undefined): TableWinner[] {
  if (!raw) {
    return [];
  }
  const rows: TableWinner[] = [];
  for (const item of raw) {
    if (typeof item === "number") {
      rows.push({ seat: item, amount: 0 });
      continue;
    }
    if (typeof item?.seat === "number") {
      rows.push(item);
    }
  }
  return rows;
}

export default function PokerTable(props: TableProps) {
  const { t } = useI18n();
  const clock = useCountdown(props.remainingSeconds, props.actorSeat ?? null);
  const counted = props.seatCount ?? Math.max(2, ...props.players.map((player) => player.seat + 1), 2);
  const occupied = Math.min(9, Math.max(2, counted, ...props.players.map((player) => player.seat + 1)));
  const anchor = props.heroSeat !== null && props.heroSeat < occupied ? props.heroSeat : 0;
  const bySeat = new Map(props.players.map((player) => [player.seat, player]));
  const live = Boolean(props.street && props.street !== "WAITING" && props.street !== "HAND_COMPLETE");
  const slots = Array.from({ length: occupied }, (_, seat) => seat);
  const winners = listedWinners(props.winners);
  const winnerBySeat = new Map(winners.map((winner) => [winner.seat, winner]));
  const winningCodes = new Set(winners.flatMap((winner) => winner.cards ?? []));
  const markCard = winningCodes.size > 0 ? (code: string) => (winningCodes.has(code) ? "win" : "dim") : undefined;
  const categories = [...new Set(winners.map((winner) => winner.category).filter((name): name is string => Boolean(name)))];
  const shownRef = useRef<Map<number, "backs" | string[]>>(new Map());
  const opened = useRef(false);
  const [folding, setFolding] = useState<{ seat: number; cards: "backs" | string[]; token: string } | null>(null);
  const [flights, setFlights] = useState<{ seat: number; token: string }[]>([]);

  useEffect(() => {
    const action = props.latestAction;
    if (!opened.current) {
      opened.current = true;
      return;
    }
    if (!action || action.seat == null) {
      return;
    }
    if (action.action === "fold") {
      const previous = shownRef.current.get(action.seat) ?? "backs";
      setFolding({ seat: action.seat, cards: previous, token: action.token });
      const timer = window.setTimeout(() => {
        setFolding((current) => (current?.token === action.token ? null : current));
      }, 460);
      return () => window.clearTimeout(timer);
    }
    if (!CHIP_ACTIONS.has(action.action)) {
      return;
    }
    const token = action.token;
    const seat = action.seat;
    setFlights((current) => [...current, { seat, token }]);
    const timer = window.setTimeout(() => {
      setFlights((current) => current.filter((item) => item.token !== token));
    }, 480);
    return () => window.clearTimeout(timer);
  }, [props.latestAction]);

  return (
    <div className={props.layout === "embedded" ? "table-scene embedded" : "table-scene"}>
      <div className="stadium" data-testid="poker-table" data-seats={occupied}>
      <div className="table-rail" />
      <div className="felt-oval">
        <div className="betting-line" />
        <div className="felt-suits" aria-hidden="true">
          <span>♠</span>
          <span className="red">♥</span>
          <span className="red">♦</span>
          <span>♣</span>
        </div>
      </div>
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
                  <PlayingCard code={code} key={`${index}-${code}`} mark={markCard?.(code)} />
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div className="board-cards" data-testid="board">
            {props.board.map((code) => (
              <PlayingCard code={code} key={code} mark={markCard?.(code)} />
            ))}
          </div>
        )}
        <div className="pot-row">
          <ChipStack amount={props.pot} />
          <p className="pot-chip" data-testid="pot">
            {t("Pot")} {props.pot}
          </p>
        </div>
        {categories.length > 0 ? (
          <p className="win-category" data-testid="winning-category">
            {categories.map((name) => t(name)).join(" · ")}
          </p>
        ) : null}
      </div>
      {slots.map((seat) => {
        const player = bySeat.get(seat) ?? null;
        const place = slotStyle(seat, occupied, anchor);
        if (!player) {
          return (
            <div className="table-seat empty" key={`empty-${seat}`} style={place}>
              {props.onSit ? (
                <button
                  type="button"
                  className="empty-seat"
                  data-testid="empty-seat"
                  data-seat={seat}
                  aria-label={`${t("Empty seat")} ${seat}`}
                  onClick={() => props.onSit?.(seat)}
                />
              ) : (
                <span className="empty-seat" data-testid="empty-seat" data-seat={seat} aria-label={t("Empty seat")} />
              )}
            </div>
          );
        }
        const hero = props.heroSeat !== null && player.seat === props.heroSeat;
        const dealt = holeCards(player, live, Boolean(props.showdown));
        const leaving = folding?.seat === player.seat ? folding : null;
        const cards = leaving
          ? leaving.cards === "backs"
            ? { kind: "backs" as const }
            : { kind: "faces" as const, codes: leaving.cards }
          : dealt;
        if (!leaving && cards.kind === "backs") {
          shownRef.current.set(player.seat, "backs");
        }
        if (!leaving && cards.kind === "faces") {
          shownRef.current.set(player.seat, cards.codes);
        }
        const bet = player.committed_street ?? 0;
        const acting = Boolean(player.is_actor && clock.left !== null && clock.total > 0);
        const prize = winnerBySeat.get(player.seat);
        return (
          <Fragment key={player.seat}>
            {bet > 0 ? (
              <div className="bet-spot" style={betStyle(seat, occupied, anchor)}>
                <ChipStack amount={bet} testId="seat-bet" />
              </div>
            ) : null}
          <div
            className={`table-seat${prize ? " winner" : ""}`}
            data-actor={player.is_actor ? "true" : "false"}
            data-hero={hero ? "true" : "false"}
            data-winner={prize ? "true" : "false"}
            data-seat={player.seat}
            style={place}
          >
            {prize ? (
              <div className="winner-banner" data-testid="winner" data-seat={player.seat}>
                <strong>{t("Winner")}</strong>
                <span>{prize.amount}</span>
              </div>
            ) : null}
            <div className={`seat-cards${leaving ? " folding" : ""}`} data-testid={hero ? "hole-cards" : undefined}>
              {cards.kind === "faces"
                ? cards.codes.map((code) => <PlayingCard code={code} hero={hero} key={code} mark={markCard?.(code)} />)
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
                <strong>{displayName(player.nickname, t)}</strong>
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
      {flights.map((flight) => (
        <div key={flight.token} className="chip-flight" data-testid="chip-flight" style={slotStyle(flight.seat, occupied, anchor)}>
          <span className="chip tone-1" />
        </div>
      ))}
      </div>
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
  return stadiumPoint(index, count, 0.045);
}

function betStyle(seat: number, count: number, anchor: number): { left: string; top: string } {
  const index = (seat - anchor + count) % count;
  return stadiumPoint(index, count, 0.2);
}

/** Racetrack perimeter. Index 0 is bottom center; later seats run left, across the top, then right. */
function stadiumPoint(index: number, count: number, inset: number): { left: string; top: string } {
  const aspect = 2.15;
  const halfH = 0.5;
  const halfW = aspect / 2;
  const capCenter = halfW - halfH;
  const radius = halfH - inset;
  const straight = 2 * capCenter;
  const arc = Math.PI * radius;
  const total = 2 * straight + 2 * arc;
  let dist = (index / count) * total;
  let x = 0;
  let y = radius;
  const bottomHalf = straight / 2;
  if (dist <= bottomHalf) {
    x = -dist;
    y = radius;
  } else {
    dist -= bottomHalf;
    if (dist <= arc) {
      const theta = Math.PI / 2 + dist / radius;
      x = -capCenter + radius * Math.cos(theta);
      y = radius * Math.sin(theta);
    } else {
      dist -= arc;
      if (dist <= straight) {
        x = -capCenter + dist;
        y = -radius;
      } else {
        dist -= straight;
        if (dist <= arc) {
          const theta = -Math.PI / 2 + dist / radius;
          x = capCenter + radius * Math.cos(theta);
          y = radius * Math.sin(theta);
        } else {
          dist -= arc;
          x = capCenter - dist;
          y = radius;
        }
      }
    }
  }
  return {
    left: `${((x + halfW) / (2 * halfW)) * 100}%`,
    top: `${((y + halfH) / (2 * halfH)) * 100}%`,
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
