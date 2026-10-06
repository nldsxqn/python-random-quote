"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { buyInBounds, defaultBuyIn } from "@/lib/buy-in";
import { useI18n } from "@/lib/i18n";
import { apiUrl, wsUrl } from "@/lib/server-url";

type PlayerRow = {
  seat: number;
  nickname: string;
  stack: number;
  status: string;
  committed_street: number;
  hole_cards: string[] | null;
  is_button: boolean;
  is_actor: boolean;
  is_bot?: boolean;
  bot_kind?: string | null;
};

type RoomView = {
  room_id: string;
  invite_code: string;
  host: string;
  settings: {
    small_blind: number;
    big_blind: number;
    seats: number;
    paused: boolean;
    pending_big_blind: number | null;
    rules: Record<string, unknown>;
    pending_rules: Record<string, unknown> | null;
    gto_mode?: string;
  };
  players: PlayerRow[];
  spectators: string[];
  game: {
    street: string | null;
    board: string[];
    pot: number;
    actor_seat: number | null;
    to_call: number;
    min_raise_to: number | null;
    legal_actions: string[];
    big_blind: number;
    rake: number;
    bounty: number;
    rit_offer: boolean;
    rit_seats: number[];
    boards: string[][];
    remaining_seconds: number | null;
  };
  you: {
    nickname: string;
    seat: number | null;
    is_host: boolean;
    hole_cards: string[] | null;
    gto?: {
      message?: string;
      frequencies?: Record<string, number>;
      metadata?: { exact?: boolean; label?: string };
    };
  };
};

type Session = {
  roomId: string;
  inviteCode: string;
  guestToken: string;
  nickname: string;
};

const STORAGE_KEY = "openpokerlab.play";

export default function PlayPage() {
  const { t } = useI18n();
  const [nickname, setNickname] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [view, setView] = useState<RoomView | null>(null);
  const [error, setError] = useState("");
  const [amount, setAmount] = useState("");
  const [buyInAmount, setBuyInAmount] = useState("1000");
  const socketRef = useRef<WebSocket | null>(null);
  const suggestedBuyIn = view ? defaultBuyIn(view.settings.rules, view.settings.big_blind) : 1000;
  const buyLimits = view ? buyInBounds(view.settings.rules, view.settings.big_blind) : null;

  useEffect(() => {
    setBuyInAmount(String(suggestedBuyIn));
  }, [suggestedBuyIn]);

  useEffect(() => {
    const saved = window.sessionStorage.getItem(STORAGE_KEY);
    if (!saved) {
      return;
    }
    try {
      setSession(JSON.parse(saved) as Session);
    } catch {
      window.sessionStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (!session) {
      return;
    }
    let stopped = false;
    let socket: WebSocket | null = null;
    let retry: number | undefined;

    function connect(): void {
      if (stopped || !session) {
        return;
      }
      socket = new WebSocket(wsUrl("/ws/room"));
      socketRef.current = socket;
      socket.onopen = () => {
        socket?.send(
          JSON.stringify({ type: "JOIN", payload: { guest_token: session.guestToken } }),
        );
      };
      socket.onmessage = (event: MessageEvent<string>) => {
        const message = JSON.parse(event.data) as { type?: string; payload?: RoomView & { message?: string } };
        if (stopped) {
          return;
        }
        if (message.type === "GAME_STATE" && message.payload) {
          setView(message.payload);
          setError("");
        }
        if (message.type === "ERROR") {
          setError(message.payload?.message ?? "Something went wrong");
        }
      };
      socket.onclose = () => {
        if (!stopped) {
          retry = window.setTimeout(connect, 1000);
        }
      };
    }

    connect();
    return () => {
      stopped = true;
      if (retry !== undefined) {
        window.clearTimeout(retry);
      }
      socket?.close();
      socketRef.current = null;
    };
  }, [session]);

  async function createRoom(): Promise<void> {
    await enter("/rooms", { nickname });
  }

  async function joinRoom(): Promise<void> {
    await enter("/rooms/join", { nickname, invite_code: inviteCode.trim().toUpperCase() });
  }

  async function enter(path: string, body: { nickname: string; invite_code?: string }): Promise<void> {
    setError("");
    try {
      const response = await fetch(apiUrl(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const raw = await response.text();
      if (!response.ok) {
        setError(serverMessage(raw));
        return;
      }
      const payload = JSON.parse(raw) as SessionResponse;
      const next = {
        roomId: payload.room_id,
        inviteCode: payload.invite_code,
        guestToken: payload.guest_token,
        nickname,
      };
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      setSession(next);
    } catch {
      setError("Could not reach the server");
    }
  }

  async function post(path: string, extra: Record<string, unknown> = {}): Promise<void> {
    if (!session) {
      return;
    }
    setError("");
    const response = await fetch(apiUrl(`/rooms/${session.roomId}${path}`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ guest_token: session.guestToken, ...extra }),
    });
    if (!response.ok) {
      setError(serverMessage(await response.text()));
    }
  }

  function sendAction(action: string, chips?: number): void {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError("Not connected");
      return;
    }
    const payload: { action: string; amount?: number } = { action };
    if (chips !== undefined) {
      payload.amount = chips;
    }
    socket.send(
      JSON.stringify({
        type: "PLAYER_ACTION",
        request_id: `${Date.now()}`,
        payload,
      }),
    );
  }

  function readBuyIn(): number | null {
    const parsed = Number(buyInAmount);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      setError("buy-in must be a positive integer");
      return null;
    }
    if (buyLimits && (parsed < buyLimits.min || parsed > buyLimits.max)) {
      setError(`buy-in must be from ${buyLimits.min} to ${buyLimits.max}`);
      return null;
    }
    return parsed;
  }

  function betOrRaise(action: "bet" | "raise"): void {
    const parsed = Number(amount);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      setError(action === "raise" ? "Enter the raise-to total" : "Enter a bet amount");
      return;
    }
    sendAction(action, parsed);
  }

  function sendVote(accept: boolean): void {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError("Not connected");
      return;
    }
    socket.send(
      JSON.stringify({
        type: "RIT_VOTE",
        request_id: `${Date.now()}`,
        payload: { accept },
      }),
    );
  }

  const legal = view?.game.legal_actions ?? [];
  const street = view?.game.street ?? "WAITING";

  return (
    <main className="play">
      <h1>OpenPokerLab</h1>
      <p className="note">
        <Link href="/">{t("Home")}</Link>
        {" · "}
        <Link href={view ? `/replay?room=${view.room_id}` : "/replay"} data-testid="replay-link">
          {t("Replay")}
        </Link>
        {" · "}
        <Link href="/analyze" data-testid="analyze-link">
          {t("Analyze")}
        </Link>
        {" · "}
        <Link href="/trainer" data-testid="trainer-link">
          {t("Trainer")}
        </Link>
        {" · "}
        <Link href="/settings" data-testid="settings-link">
          {t("Settings")}
        </Link>
      </p>
      {view ? (
        <section className="table" aria-label="Poker table">
          <p className="meta">
            {t("Invite")} <strong data-testid="room-invite">{view.invite_code}</strong>
            {" · "}
            {view.you.nickname}
            {view.you.is_host ? ` · ${t("host")}` : ""}
            {view.you.seat === null ? ` · ${t("spectator")}` : ` · ${t("seat")} ${view.you.seat}`}
          </p>
          <div className="felt">
            <h2 data-testid="hand-status">{t(street)}</h2>
            <p className="meta" data-testid="pot">
              {t("Pot")} {view.game.pot} · {t("blinds")} {view.settings.small_blind}/{view.game.big_blind}
            </p>
            <p className="meta">
              <span data-testid="rake">{t("Rake")} {view.game.rake}</span>
              {" · "}
              <span data-testid="bounty">{t("Bounty")} {view.game.bounty}</span>
              {view.game.remaining_seconds !== null ? ` · ${view.game.remaining_seconds}s` : ""}
            </p>
            {view.game.boards.length > 1 ? (
              <div data-testid="run-boards">
                {view.game.boards.map((board, index) => (
                  <p className="meta" key={board.join("-")}>
                    {t("Run")} {index + 1}: {board.join(" ")}
                  </p>
                ))}
              </div>
            ) : null}
            <div className="cards" data-testid="board">
              {view.game.board.length === 0 ? <span className="card">—</span> : null}
              {view.game.board.map((card) => (
                <span className="card" key={card}>
                  {card}
                </span>
              ))}
            </div>
            <ul className="seats">
              {view.players.map((player) => (
                <li className="seat" data-actor={player.is_actor} key={player.seat}>
                  <strong>
                    {player.nickname}
                    {player.is_button ? " (D)" : ""}
                  </strong>
                  <div>{t("Stack")} {player.stack}</div>
                  <div>
                    {t(player.status)}
                    {player.committed_street > 0 ? ` · ${player.committed_street}` : ""}
                  </div>
                </li>
              ))}
            </ul>
            <p data-testid="hole-cards">
              {t("Your cards")}: {view.you.hole_cards ? view.you.hole_cards.join(" ") : t("hidden")}
            </p>
            {view.you.gto ? (
              <p className="meta" data-testid="gto-advice">
                {view.you.gto.message
                  ? t(view.you.gto.message)
                  : Object.entries(view.you.gto.frequencies ?? {})
                      .map(([action, frequency]) => `${t(action)} ${Math.round(frequency * 100)}%`)
                      .join(" · ")}
              </p>
            ) : null}
          </div>
          {view.you.seat === null || view.you.is_host ? (
            <div className="row" data-testid="buy-in">
              <label htmlFor="buy-in-amount">{t("Buy-in")}</label>
              <input
                id="buy-in-amount"
                data-testid="buy-in-amount"
                inputMode="numeric"
                aria-label={t("Buy-in amount")}
                value={buyInAmount}
                onChange={(event) => setBuyInAmount(event.target.value)}
              />
              <span className="meta">
                {buyLimits
                  ? `${t("Limit")} ${buyLimits.min}–${buyLimits.max} ${t("chips")}`
                  : `1000 ${t("play-money chips")}`}
              </span>
            </div>
          ) : null}
          <div className="actions row">
            {view.you.seat === null ? (
              <button
                type="button"
                data-testid="sit"
                onClick={() => {
                  const chips = readBuyIn();
                  if (chips !== null) {
                    void post("/sit", { amount: chips });
                  }
                }}
              >
                {t("Sit")}
              </button>
            ) : null}
            <button type="button" data-testid="fold" disabled={!legal.includes("fold")} onClick={() => sendAction("fold")}>
              {t("Fold")}
            </button>
            <button type="button" data-testid="check" disabled={!legal.includes("check")} onClick={() => sendAction("check")}>
              {t("Check")}
            </button>
            <button type="button" data-testid="call" disabled={!legal.includes("call")} onClick={() => sendAction("call")}>
              {t("Call")}
              {view.game.to_call > 0 ? ` ${view.game.to_call}` : ""}
            </button>
            <input
              data-testid="amount"
              inputMode="numeric"
              value={amount}
              placeholder={view.game.min_raise_to ? `${t("raise to")} ${view.game.min_raise_to}` : t("amount")}
              onChange={(event) => setAmount(event.target.value)}
            />
            <button type="button" data-testid="bet" disabled={!legal.includes("bet")} onClick={() => betOrRaise("bet")}>
              {t("Bet")}
            </button>
            <button type="button" data-testid="raise" disabled={!legal.includes("raise")} onClick={() => betOrRaise("raise")}>
              {t("Raise")}
            </button>
          </div>
          {view.game.rit_offer && view.you.seat !== null && view.game.rit_seats.includes(view.you.seat) ? (
            <div className="row" data-testid="rit-offer">
              <button type="button" data-testid="rit-yes" onClick={() => sendVote(true)}>
                {t("Run it twice")}
              </button>
              <button type="button" data-testid="rit-no" onClick={() => sendVote(false)}>
                {t("Run once")}
              </button>
            </div>
          ) : null}
          {view.you.is_host ? (
            <HostControls
              paused={view.settings.paused}
              inHand={street !== "WAITING" && street !== "HAND_COMPLETE" && street !== null}
              onStart={() => void post("/start")}
              onPause={() => void post("/pause", { paused: !view.settings.paused })}
              onBlinds={(small, big) => void post("/settings", { small_blind: small, big_blind: big })}
              onRules={(rules) => void post("/settings", { rules })}
              pending={view.settings.pending_rules !== null}
              players={view.players}
              onAddBot={(kind) => {
                const chips = readBuyIn();
                if (chips !== null) {
                  void post("/bots", { kind, amount: chips });
                }
              }}
              onRemoveBot={(seat) => void post("/bots/remove", { seat })}
              gtoMode={view.settings.gto_mode ?? "competitive"}
              onGto={(mode) => void post("/settings", { gto_mode: mode })}
            />
          ) : null}
          <p className="error" data-testid="error">
            {t(error)}
          </p>
        </section>
      ) : (
        <section className="lobby">
          <label htmlFor="nickname">{t("Nickname")}</label>
          <input
            id="nickname"
            data-testid="nickname"
            value={nickname}
            maxLength={24}
            onChange={(event) => setNickname(event.target.value)}
          />
          <div className="row">
            <button type="button" data-testid="create-room" onClick={() => void createRoom()}>
              {t("Create room")}
            </button>
          </div>
          <label htmlFor="invite-code">{t("Invite code")}</label>
          <input
            id="invite-code"
            data-testid="invite-code"
            value={inviteCode}
            onChange={(event) => setInviteCode(event.target.value)}
          />
          <div className="row">
            <button type="button" data-testid="join-room" onClick={() => void joinRoom()}>
              {t("Join room")}
            </button>
          </div>
          <p className="error" data-testid="error">
            {t(error)}
          </p>
        </section>
      )}
    </main>
  );
}

function HostControls({
  paused,
  inHand,
  onStart,
  onPause,
  onBlinds,
  onRules,
  pending,
  players,
  onAddBot,
  onRemoveBot,
  gtoMode,
  onGto,
}: {
  paused: boolean;
  inHand: boolean;
  onStart: () => void;
  onPause: () => void;
  onBlinds: (small: number, big: number) => void;
  onRules: (rules: Record<string, unknown>) => void;
  pending: boolean;
  players: PlayerRow[];
  onAddBot: (kind: string) => void;
  onRemoveBot: (seat: number) => void;
  gtoMode: string;
  onGto: (mode: string) => void;
}) {
  const { t } = useI18n();
  const smallRef = useRef<HTMLInputElement>(null);
  const bigRef = useRef<HTMLInputElement>(null);
  const [botKind, setBotKind] = useState("rule");

  return (
    <div className="host">
      <div className="row">
        <button type="button" data-testid="start-hand" disabled={paused || inHand} onClick={onStart}>
          {t("Start hand")}
        </button>
        <button type="button" data-testid="pause" onClick={onPause}>
          {paused ? t("Resume") : t("Pause")}
        </button>
        <button
          type="button"
          data-testid="gto-mode"
          onClick={() => onGto(gtoMode === "study" ? "competitive" : "study")}
        >
          GTO {t(gtoMode)}
        </button>
      </div>
      <div className="row">
        <input ref={smallRef} data-testid="small-blind" defaultValue={1} aria-label={t("Small blind")} />
        <input ref={bigRef} data-testid="big-blind" defaultValue={2} aria-label={t("Big blind")} />
        <button
          type="button"
          onClick={() => {
            const small = Number(smallRef.current?.value);
            const big = Number(bigRef.current?.value);
            if (Number.isInteger(small) && Number.isInteger(big)) {
              onBlinds(small, big);
            }
          }}
        >
          {t("Update blinds")}
        </button>
      </div>
      <div className="row">
        <select
          data-testid="bot-kind"
          value={botKind}
          aria-label={t("Bot")}
          onChange={(event) => setBotKind(event.target.value)}
        >
          <option value="rule">{t("rule")}</option>
          <option value="equity">{t("equity")}</option>
          <option value="strategy">{t("strategy")}</option>
        </select>
        <button type="button" data-testid="add-bot" disabled={inHand} onClick={() => onAddBot(botKind)}>
          {t("Add bot")}
        </button>
        {players
          .filter((player) => player.is_bot)
          .map((player) => (
            <button
              type="button"
              data-testid="remove-bot"
              data-seat={player.seat}
              disabled={inHand}
              key={player.seat}
              onClick={() => onRemoveBot(player.seat)}
            >
              {t("Remove")} {player.nickname}
            </button>
          ))}
      </div>
      {pending ? <p className="note">{t("Rule changes apply on the next hand.")}</p> : null}
      <RulesForm onSave={onRules} />
    </div>
  );
}

function RulesForm({ onSave }: { onSave: (rules: Record<string, unknown>) => void }) {
  const { t } = useI18n();
  const [ante, setAnte] = useState(false);
  const [anteMode, setAnteMode] = useState("normal");
  const [anteAmount, setAnteAmount] = useState("1");
  const [straddle, setStraddle] = useState(false);
  const [straddleBb, setStraddleBb] = useState("2");
  const [buyIn, setBuyIn] = useState(false);
  const [buyMin, setBuyMin] = useState("50");
  const [buyMax, setBuyMax] = useState("200");
  const [buyUnit, setBuyUnit] = useState("bb");
  const [topUp, setTopUp] = useState(false);
  const [threshold, setThreshold] = useState("40");
  const [target, setTarget] = useState("100");
  const [clock, setClock] = useState(false);
  const [seconds, setSeconds] = useState("30");
  const [bounty, setBounty] = useState(false);
  const [bountyBb, setBountyBb] = useState("10");
  const [runTwice, setRunTwice] = useState(false);
  const [rake, setRake] = useState(false);
  const [percentage, setPercentage] = useState("5");
  const [cap, setCap] = useState("10");
  const [noFlop, setNoFlop] = useState(true);
  const [bomb, setBomb] = useState(false);
  const [bombAmount, setBombAmount] = useState("1");

  function save(): void {
    onSave({
      ante: ante ? { mode: anteMode, amount: Number(anteAmount) } : null,
      straddle: straddle ? { style: "utg", amount_bb: Number(straddleBb) } : null,
      buy_in: buyIn ? { min: Number(buyMin), max: Number(buyMax), unit: buyUnit } : null,
      auto_top_up: topUp
        ? { threshold_bb: Number(threshold), target_bb: Number(target) }
        : null,
      time_bank: clock ? { seconds: Number(seconds) } : null,
      seven_deuce: bounty ? { payment_per_player_bb: Number(bountyBb), require_showdown: true } : null,
      run_it_twice: runTwice,
      rake: rake
        ? { percentage: Number(percentage), cap: Number(cap), no_flop_no_drop: noFlop }
        : null,
      bomb_pot: bomb ? { amount: Number(bombAmount), boards: 1 } : null,
    });
  }

  return (
    <div className="rules" data-testid="rules-form">
      <label>
        <input type="checkbox" checked={ante} onChange={(event) => setAnte(event.target.checked)} />
        {t("Ante")}
        <select value={anteMode} onChange={(event) => setAnteMode(event.target.value)} aria-label={t("Ante mode")}>
          <option value="normal">{t("normal")}</option>
          <option value="bb_ante">{t("bb ante")}</option>
        </select>
        <input value={anteAmount} onChange={(event) => setAnteAmount(event.target.value)} aria-label={t("Ante amount")} />
      </label>
      <label>
        <input type="checkbox" checked={straddle} onChange={(event) => setStraddle(event.target.checked)} />
        {t("UTG straddle")}
        <input value={straddleBb} onChange={(event) => setStraddleBb(event.target.value)} aria-label={t("Straddle big blinds")} />
        {t("BB")}
      </label>
      <label>
        <input type="checkbox" checked={buyIn} onChange={(event) => setBuyIn(event.target.checked)} />
        {t("Buy-in")}
        <input value={buyMin} onChange={(event) => setBuyMin(event.target.value)} aria-label={t("Minimum buy-in")} />
        <input value={buyMax} onChange={(event) => setBuyMax(event.target.value)} aria-label={t("Maximum buy-in")} />
        <select value={buyUnit} onChange={(event) => setBuyUnit(event.target.value)} aria-label={t("Buy-in unit")}>
          <option value="bb">{t("bb")}</option>
          <option value="chips">{t("chips")}</option>
        </select>
      </label>
      <label>
        <input type="checkbox" checked={topUp} onChange={(event) => setTopUp(event.target.checked)} />
        {t("Auto top-up")}
        <input value={threshold} onChange={(event) => setThreshold(event.target.value)} aria-label={t("Top-up threshold")} />
        <input value={target} onChange={(event) => setTarget(event.target.value)} aria-label={t("Top-up target")} />
      </label>
      <label>
        <input type="checkbox" checked={clock} onChange={(event) => setClock(event.target.checked)} />
        {t("Time bank")}
        <input value={seconds} onChange={(event) => setSeconds(event.target.value)} aria-label={t("Time bank seconds")} />
      </label>
      <label>
        <input type="checkbox" checked={bounty} onChange={(event) => setBounty(event.target.checked)} />
        {t("72o bounty")}
        <input value={bountyBb} onChange={(event) => setBountyBb(event.target.value)} aria-label={t("Bounty big blinds")} />
        {t("BB")}
      </label>
      <label>
        <input type="checkbox" checked={runTwice} onChange={(event) => setRunTwice(event.target.checked)} />
        {t("Run it twice")}
      </label>
      <label>
        <input type="checkbox" checked={rake} onChange={(event) => setRake(event.target.checked)} />
        {t("Rake")}
        <input value={percentage} onChange={(event) => setPercentage(event.target.value)} aria-label={t("Rake percent")} />
        %
        <input value={cap} onChange={(event) => setCap(event.target.value)} aria-label={t("Rake cap")} />
        <input type="checkbox" checked={noFlop} onChange={(event) => setNoFlop(event.target.checked)} aria-label={t("No flop no drop")} />
        {t("no flop no drop")}
      </label>
      <label>
        <input type="checkbox" checked={bomb} onChange={(event) => setBomb(event.target.checked)} />
        {t("Bomb pot")}
        <input value={bombAmount} onChange={(event) => setBombAmount(event.target.value)} aria-label={t("Bomb amount")} />
      </label>
      <button type="button" data-testid="save-rules" onClick={save}>
        {t("Save rules")}
      </button>
    </div>
  );
}

function serverMessage(raw: string): string {
  if (!raw.trim()) {
    return "Could not enter the room";
  }
  try {
    const payload = JSON.parse(raw) as {
      payload?: { message?: string };
      detail?: unknown;
      message?: string;
    };
    if (payload.payload?.message) {
      return payload.payload.message;
    }
    if (typeof payload.message === "string" && payload.message) {
      return payload.message;
    }
    if (typeof payload.detail === "string" && payload.detail) {
      return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
      const parts = payload.detail
        .map((item) => {
          if (typeof item === "string") {
            return item;
          }
          if (item && typeof item === "object" && "msg" in item) {
            const msg = (item as { msg?: unknown }).msg;
            return typeof msg === "string" ? msg : "";
          }
          return "";
        })
        .filter(Boolean);
      if (parts.length > 0) {
        return parts.join("; ");
      }
    }
  } catch {
    return raw;
  }
  return raw;
}

type SessionResponse = {
  room_id: string;
  invite_code: string;
  guest_token: string;
};
