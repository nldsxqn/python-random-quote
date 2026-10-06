"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiUrl, wsUrl } from "@/lib/server-url";

type LinkState = "Checking" | "Connected" | "Disconnected";

export default function HomePage() {
  const [backend, setBackend] = useState<LinkState>("Checking");
  const [socketState, setSocketState] = useState<LinkState>("Checking");

  useEffect(() => {
    let stopped = false;

    async function checkHealth(): Promise<void> {
      try {
        const response = await fetch(apiUrl("/health"), { cache: "no-store" });
        if (!response.ok) {
          if (!stopped) {
            setBackend("Disconnected");
          }
          return;
        }
        const body = (await response.json()) as { status?: string };
        if (!stopped) {
          setBackend(body.status === "ok" ? "Connected" : "Disconnected");
        }
      } catch {
        if (!stopped) {
          setBackend("Disconnected");
        }
      }
    }

    void checkHealth();
    const timer = window.setInterval(() => {
      void checkHealth();
    }, 3000);

    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;

    function connect(): void {
      if (stopped) {
        return;
      }
      ws = new WebSocket(wsUrl("/ws"));
      ws.onmessage = (event: MessageEvent<string>) => {
        try {
          const message = JSON.parse(event.data) as { type?: string };
          if (!stopped && message.type === "CONNECTED") {
            setSocketState("Connected");
          }
        } catch {
          if (!stopped) {
            setSocketState("Disconnected");
          }
        }
      };
      ws.onerror = () => {
        if (!stopped) {
          setSocketState("Disconnected");
        }
      };
      ws.onclose = () => {
        if (stopped) {
          return;
        }
        setSocketState("Disconnected");
        reconnectTimer = window.setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      stopped = true;
      window.clearInterval(timer);
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
      ws?.close();
    };
  }, []);

  return (
    <main className="page">
      <h1>OpenPokerLab</h1>
      <section className="panel" aria-label="Connection status">
        <StatusBlock label="Backend" state={backend} />
        <StatusBlock label="WebSocket" state={socketState} />
      </section>
      <p className="note">
        <Link href="/play">Play</Link>
        {" · "}
        <Link href="/replay">Replay</Link>
        {" · "}
        <Link href="/analyze">Analyze</Link>
        {" · "}
        <Link href="/trainer">Trainer</Link>
        {" · "}
        <Link href="/settings">Settings</Link>
      </p>
    </main>
  );
}

function StatusBlock({ label, state }: { label: string; state: LinkState }) {
  return (
    <div className="block">
      <h2>{label}</h2>
      <p className="state">
        <span className="dot" data-state={state} aria-hidden="true">
          ●
        </span>{" "}
        {state}
      </p>
    </div>
  );
}
