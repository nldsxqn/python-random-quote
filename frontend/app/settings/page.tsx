"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const STORAGE_KEY = "openpokerlab.play";

type Catalog = {
  database_path: string;
  gto_modes: string[];
  bot_kinds: string[];
  variants: string[];
  straddle_styles: string[];
  cash_settlement: boolean;
};

type Session = {
  roomId: string;
  guestToken: string;
};

export default function SettingsPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [gtoMode, setGtoMode] = useState("competitive");
  const [variant, setVariant] = useState("nlhe");
  const [botKind, setBotKind] = useState("rule");
  const [straddle, setStraddle] = useState("utg");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void fetch(`${API_URL}/settings`)
      .then((response) => response.json())
      .then((body: Catalog) => setCatalog(body));
    const saved = window.sessionStorage.getItem(STORAGE_KEY);
    if (!saved) {
      return;
    }
    try {
      const parsed = JSON.parse(saved) as { roomId?: string; guestToken?: string };
      if (parsed.roomId && parsed.guestToken) {
        setSession({ roomId: parsed.roomId, guestToken: parsed.guestToken });
      }
    } catch {
      setSession(null);
    }
  }, []);

  async function post(path: string, extra: Record<string, unknown>): Promise<void> {
    if (!session) {
      setMessage("Open a table from Play first");
      return;
    }
    const response = await fetch(`${API_URL}/rooms/${session.roomId}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ guest_token: session.guestToken, ...extra }),
    });
    setMessage(response.ok ? "Saved" : "The table rejected that change");
  }

  return (
    <main className="study">
      <h1>Settings</h1>
      <p className="note">
        <Link href="/play">Play</Link>
        {" · "}
        <Link href="/analyze">Analyze</Link>
      </p>
      <p data-testid="database-path">Database {catalog?.database_path ?? "…"}</p>
      <p data-testid="cash-settlement">
        Cash settlement {catalog?.cash_settlement ? "on" : "off"}
      </p>
      <label>
        GTO mode
        <select
          data-testid="settings-gto"
          value={gtoMode}
          onChange={(event) => setGtoMode(event.target.value)}
        >
          {(catalog?.gto_modes ?? ["competitive", "study"]).map((mode) => (
            <option key={mode} value={mode}>
              {mode}
            </option>
          ))}
        </select>
      </label>
      <div className="row">
        <button type="button" onClick={() => void post("/settings", { gto_mode: gtoMode })}>
          Save GTO mode
        </button>
      </div>
      <label>
        Variant
        <select
          data-testid="settings-variant"
          value={variant}
          onChange={(event) => setVariant(event.target.value)}
        >
          {(catalog?.variants ?? ["nlhe"]).map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
      <div className="row">
        <button type="button" onClick={() => void post("/settings", { variant })}>
          Save variant
        </button>
      </div>
      <label>
        Straddle
        <select
          data-testid="settings-straddle"
          value={straddle}
          onChange={(event) => setStraddle(event.target.value)}
        >
          {(catalog?.straddle_styles ?? ["utg"]).map((style) => (
            <option key={style} value={style}>
              {style}
            </option>
          ))}
        </select>
      </label>
      <div className="row">
        <button
          type="button"
          onClick={() =>
            void post("/settings", {
              rules: {
                straddle:
                  straddle === "custom"
                    ? { style: "custom", amount_bb: 2, seat: 0 }
                    : { style: straddle, amount_bb: 2 },
              },
            })
          }
        >
          Save straddle
        </button>
        <button
          type="button"
          onClick={() => void post("/settings", { rules: { bomb_pot: { amount: 1, boards: 2 } } })}
        >
          Double-board bomb
        </button>
        <button type="button" onClick={() => void post("/settings", { rules: { insurance: true } })}>
          Simplified insurance
        </button>
      </div>
      <label>
        Bot
        <select
          data-testid="settings-bot"
          value={botKind}
          onChange={(event) => setBotKind(event.target.value)}
        >
          {(catalog?.bot_kinds ?? ["rule"]).map((kind) => (
            <option key={kind} value={kind}>
              {kind}
            </option>
          ))}
        </select>
      </label>
      <div className="row">
        <button type="button" data-testid="settings-add-bot" onClick={() => void post("/bots", { kind: botKind })}>
          Add bot
        </button>
      </div>
      <p className="meta">{message}</p>
    </main>
  );
}
