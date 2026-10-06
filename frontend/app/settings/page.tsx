"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { buyInBounds, defaultBuyIn } from "@/lib/buy-in";
import { useI18n } from "@/lib/i18n";
import { apiUrl } from "@/lib/server-url";
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
  const { t } = useI18n();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [gtoMode, setGtoMode] = useState("competitive");
  const [variant, setVariant] = useState("nlhe");
  const [botKind, setBotKind] = useState("rule");
  const [straddle, setStraddle] = useState("utg");
  const [buyInAmount, setBuyInAmount] = useState("1000");
  const [buyLimits, setBuyLimits] = useState<{ min: number; max: number } | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    void fetch(apiUrl("/settings"))
      .then((response) => response.json())
      .then((body: Catalog) => setCatalog(body));
    const saved = window.sessionStorage.getItem(STORAGE_KEY);
    if (!saved) {
      return;
    }
    try {
      const parsed = JSON.parse(saved) as { roomId?: string; guestToken?: string };
      if (parsed.roomId && parsed.guestToken) {
        const next = { roomId: parsed.roomId, guestToken: parsed.guestToken };
        setSession(next);
        void fetch(apiUrl(`/rooms/${next.roomId}?guest_token=${encodeURIComponent(next.guestToken)}`))
          .then((response) => (response.ok ? response.json() : null))
          .then((body: { settings?: { rules?: Record<string, unknown>; big_blind?: number } } | null) => {
            const rules = body?.settings?.rules;
            const blind = body?.settings?.big_blind ?? 2;
            setBuyLimits(buyInBounds(rules, blind));
            setBuyInAmount(String(defaultBuyIn(rules, blind)));
          })
          .catch(() => undefined);
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
    const response = await fetch(apiUrl(`/rooms/${session.roomId}${path}`), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ guest_token: session.guestToken, ...extra }),
    });
    if (response.ok) {
      setMessage("Saved");
      return;
    }
    const raw = await response.text();
    setMessage(serverText(raw) || "The table rejected that change");
  }

  function addBot(): void {
    const parsed = Number(buyInAmount);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      setMessage("buy-in must be a positive integer");
      return;
    }
    if (buyLimits && (parsed < buyLimits.min || parsed > buyLimits.max)) {
      setMessage(`buy-in must be from ${buyLimits.min} to ${buyLimits.max}`);
      return;
    }
    void post("/bots", { kind: botKind, amount: parsed });
  }

  return (
    <main className="study">
      <h1>{t("Settings")}</h1>
      <p className="note">
        <Link href="/play">{t("Play")}</Link>
        {" · "}
        <Link href="/analyze">{t("Analyze")}</Link>
      </p>
      <p data-testid="database-path">{t("Database")} {catalog?.database_path ?? "…"}</p>
      <p data-testid="cash-settlement">
        {t("Cash settlement")} {catalog?.cash_settlement ? t("on") : t("off")}
      </p>
      <label>
        {t("GTO mode")}
        <select
          data-testid="settings-gto"
          value={gtoMode}
          onChange={(event) => setGtoMode(event.target.value)}
        >
          {(catalog?.gto_modes ?? ["competitive", "study"]).map((mode) => (
            <option key={mode} value={mode}>
              {t(mode)}
            </option>
          ))}
        </select>
      </label>
      <div className="row">
        <button type="button" onClick={() => void post("/settings", { gto_mode: gtoMode })}>
          {t("Save GTO mode")}
        </button>
      </div>
      <label>
        {t("Variant")}
        <select
          data-testid="settings-variant"
          value={variant}
          onChange={(event) => setVariant(event.target.value)}
        >
          {(catalog?.variants ?? ["nlhe"]).map((item) => (
            <option key={item} value={item}>
              {t(item)}
            </option>
          ))}
        </select>
      </label>
      <div className="row">
        <button type="button" onClick={() => void post("/settings", { variant })}>
          {t("Save variant")}
        </button>
      </div>
      <label>
        {t("Straddle")}
        <select
          data-testid="settings-straddle"
          value={straddle}
          onChange={(event) => setStraddle(event.target.value)}
        >
          {(catalog?.straddle_styles ?? ["utg"]).map((style) => (
            <option key={style} value={style}>
              {t(style)}
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
          {t("Save straddle")}
        </button>
        <button
          type="button"
          onClick={() => void post("/settings", { rules: { bomb_pot: { amount: 1, boards: 2 } } })}
        >
          {t("Double-board bomb")}
        </button>
        <button type="button" onClick={() => void post("/settings", { rules: { insurance: true } })}>
          {t("Simplified insurance")}
        </button>
      </div>
      <label>
        {t("Bot")}
        <select
          data-testid="settings-bot"
          value={botKind}
          onChange={(event) => setBotKind(event.target.value)}
        >
          {(catalog?.bot_kinds ?? ["rule"]).map((kind) => (
            <option key={kind} value={kind}>
              {t(kind)}
            </option>
          ))}
        </select>
      </label>
      <div className="row" data-testid="settings-buy-in">
        <label htmlFor="settings-buy-in-amount">{t("Buy-in")}</label>
        <input
          id="settings-buy-in-amount"
          data-testid="settings-buy-in-amount"
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
        <button type="button" data-testid="settings-add-bot" onClick={addBot}>
          {t("Add bot")}
        </button>
      </div>
      <p className="meta">{t(message)}</p>
    </main>
  );
}

function serverText(raw: string): string {
  if (!raw.trim()) {
    return "";
  }
  try {
    const payload = JSON.parse(raw) as {
      payload?: { message?: string };
      detail?: unknown;
    };
    if (payload.payload?.message) {
      return payload.payload.message;
    }
    if (Array.isArray(payload.detail)) {
      const first = payload.detail[0] as { msg?: unknown };
      if (typeof first?.msg === "string") {
        return first.msg;
      }
    }
  } catch {
    return raw;
  }
  return raw;
}
