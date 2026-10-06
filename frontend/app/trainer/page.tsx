"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Prompt = {
  street: string;
  position: string;
  board: string[];
  pot: number;
  hero_cards: string[];
  actions: string[];
};

type Spot = {
  id: number;
  hand_id: number;
  street: string;
  position: string;
  severity: string;
  decided_at: string | null;
  prompt: Prompt;
};

type Reveal = {
  your_action: string;
  frequencies: Record<string, number>;
  evs: Record<string, number>;
  original_action: string;
  ev_loss: number;
};

export default function TrainerPage() {
  const [street, setStreet] = useState("");
  const [position, setPosition] = useState("");
  const [severity, setSeverity] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [spots, setSpots] = useState<Spot[]>([]);
  const [current, setCurrent] = useState<Spot | null>(null);
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const [error, setError] = useState("");

  async function load(): Promise<void> {
    const params = new URLSearchParams();
    if (street) {
      params.set("street", street);
    }
    if (position) {
      params.set("position", position);
    }
    if (severity) {
      params.set("severity", severity);
    }
    if (dateFrom) {
      params.set("date_from", dateFrom);
    }
    if (dateTo) {
      params.set("date_to", dateTo);
    }
    const response = await fetch(`${API_URL}/trainer/spots?${params.toString()}`);
    const body = (await response.json()) as { spots: Spot[] };
    setSpots(body.spots);
    setCurrent(null);
    setReveal(null);
  }

  useEffect(() => {
    void fetch(`${API_URL}/trainer/spots`)
      .then((response) => response.json())
      .then((body: { spots: Spot[] }) => {
        setSpots(body.spots);
      });
  }, []);

  async function choose(action: string): Promise<void> {
    if (!current) {
      return;
    }
    setError("");
    const response = await fetch(`${API_URL}/trainer/spots/${current.id}/answer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action }),
    });
    if (!response.ok) {
      setError("That action is not in this spot");
      return;
    }
    setReveal((await response.json()) as Reveal);
  }

  return (
    <main className="study">
      <h1>Trainer</h1>
      <p className="note">
        <Link href="/analyze">Analyze</Link>
        {" · "}
        <Link href="/play">Play</Link>
      </p>
      <div className="row">
        <input
          data-testid="filter-street"
          value={street}
          placeholder="street"
          aria-label="Street"
          onChange={(event) => setStreet(event.target.value)}
        />
        <input
          data-testid="filter-position"
          value={position}
          placeholder="position"
          aria-label="Position"
          onChange={(event) => setPosition(event.target.value)}
        />
        <input
          data-testid="filter-severity"
          value={severity}
          placeholder="severity"
          aria-label="Severity"
          onChange={(event) => setSeverity(event.target.value)}
        />
        <input
          data-testid="filter-from"
          value={dateFrom}
          placeholder="from"
          aria-label="From date"
          onChange={(event) => setDateFrom(event.target.value)}
        />
        <input
          data-testid="filter-to"
          value={dateTo}
          placeholder="to"
          aria-label="To date"
          onChange={(event) => setDateTo(event.target.value)}
        />
        <button type="button" data-testid="filter-apply" onClick={() => void load()}>
          Filter
        </button>
      </div>
      <ul data-testid="trainer-list">
        {spots.map((spot) => (
          <li key={spot.id}>
            <button
              type="button"
              onClick={() => {
                setCurrent(spot);
                setReveal(null);
              }}
            >
              {spot.street} {spot.position} {spot.severity}
            </button>
          </li>
        ))}
      </ul>
      {current ? (
        <section data-testid="trainer-spot">
          <p>
            {current.prompt.street} {current.prompt.position} · pot {current.prompt.pot}
          </p>
          <p data-testid="trainer-board">{current.prompt.board.join(" ")}</p>
          <p data-testid="trainer-cards">{current.prompt.hero_cards.join(" ")}</p>
          <div className="row">
            {current.prompt.actions.map((action) => (
              <button
                type="button"
                key={action}
                data-testid="trainer-action"
                onClick={() => void choose(action)}
              >
                {action}
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {reveal ? (
        <section data-testid="trainer-reveal">
          <p>Your action {reveal.your_action}</p>
          <p>
            {Object.entries(reveal.frequencies)
              .map(([action, frequency]) => `${action} ${Math.round(frequency * 100)}%`)
              .join(" · ")}
          </p>
          <p>
            {Object.entries(reveal.evs)
              .map(([action, value]) => `${action} ${value.toFixed(2)}`)
              .join(" · ")}
          </p>
          <p>
            Original {reveal.original_action} · EV loss {reveal.ev_loss.toFixed(2)} BB
          </p>
        </section>
      ) : null}
      <p className="error">{error}</p>
    </main>
  );
}
