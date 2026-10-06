"use client";

import Link from "next/link";
import { useState } from "react";

import { useI18n } from "@/lib/i18n";
import { apiUrl } from "@/lib/server-url";

type Decision = {
  street: string;
  seat: number;
  position: string;
  action: string;
  pot: number;
  reasons: string[];
  ev_loss_bb: number | null;
  severity: string | null;
  frequencies: Record<string, number>;
  evs: Record<string, number>;
  matrix: number[][];
  table: {
    board: string[];
    pot: number;
    players: { seat: number; nickname: string; stack: number; position: string }[];
  };
  metadata?: { label?: string; exact?: boolean };
  hero_cards: string[];
};

type Report = {
  hand_id: number;
  board: string[];
  tree: { kind: string; children: TreeNode[] };
  decisions: Decision[];
};

type TreeNode = {
  street?: string;
  seat?: number;
  action?: string;
  amount?: number | null;
  children: TreeNode[];
};

export default function AnalyzePage() {
  const { t } = useI18n();
  const [handId, setHandId] = useState("1");
  const [report, setReport] = useState<Report | null>(null);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState("");

  async function load(): Promise<void> {
    setError("");
    const response = await fetch(apiUrl(`/analyze/hands/${handId}`));
    if (!response.ok) {
      setReport(null);
      setError("That hand is not stored");
      return;
    }
    const body = (await response.json()) as Report;
    setReport(body);
    setSelected(0);
  }

  const decision = report?.decisions[selected];

  return (
    <main className="study">
      <h1>{t("Analyze")}</h1>
      <p className="note">
        <Link href="/play">{t("Play")}</Link>
        {" · "}
        <Link href="/trainer">{t("Trainer")}</Link>
      </p>
      <div className="row">
        <input
          data-testid="analyze-hand-id"
          value={handId}
          aria-label={t("Hand id")}
          onChange={(event) => setHandId(event.target.value)}
        />
        <button type="button" data-testid="analyze-load" onClick={() => void load()}>
          {t("Load hand")}
        </button>
      </div>
      {report ? (
        <section>
          <p className="meta" data-testid="analyze-board">
            {t("Board")} {report.board.join(" ") || t("none")}
          </p>
          <Tree node={report.tree} />
          {report.decisions.length === 0 ? <p>{t("No decisions to review.")}</p> : null}
          <ul data-testid="decision-list">
            {report.decisions.map((item, index) => (
              <li key={`${item.street}-${item.seat}-${index}`}>
                <button type="button" onClick={() => setSelected(index)}>
                  {t(item.street)} {item.position} {t(item.action)}
                  {item.severity ? ` · ${t(item.severity)}` : ""}
                  {item.metadata?.label ? ` · ${item.metadata.label}` : ""}
                </button>
              </li>
            ))}
          </ul>
          {decision ? <DecisionView decision={decision} /> : null}
        </section>
      ) : null}
      <p className="error">{t(error)}</p>
    </main>
  );
}

function DecisionView({ decision }: { decision: Decision }) {
  const { t } = useI18n();
  return (
    <div data-testid="decision-detail">
      <p className="meta">
        {decision.metadata?.label} · {t("Pot")} {decision.table.pot} · {decision.table.board.join(" ")}
      </p>
      <ul className="seats">
        {decision.table.players.map((player) => (
          <li className="seat" key={player.seat}>
            <strong>
              {player.nickname} {player.position}
            </strong>
            <div>{t("Stack")} {player.stack}</div>
          </li>
        ))}
      </ul>
      <p data-testid="decision-strategy">
        {Object.entries(decision.frequencies)
          .map(([action, frequency]) => `${t(action)} ${Math.round(frequency * 100)}%`)
          .join(" · ") || t("No strategy")}
      </p>
      <p data-testid="decision-ev">
        {Object.entries(decision.evs)
          .map(([action, value]) => `${t(action)} ${value.toFixed(2)}`)
          .join(" · ")}
        {decision.ev_loss_bb === null ? "" : ` · ${t("EV loss")} ${decision.ev_loss_bb.toFixed(2)} BB`}
      </p>
      <p>{t("Hero")} {decision.hero_cards.join(" ")}</p>
      <Matrix grid={decision.matrix} />
    </div>
  );
}

function Matrix({ grid }: { grid: number[][] }) {
  if (grid.length === 0) {
    return null;
  }
  const peak = Math.max(1, ...grid.flat());
  return (
    <div className="matrix" data-testid="range-matrix">
      {grid.flat().map((value, index) => (
        <span key={index} style={{ opacity: 0.25 + (0.75 * value) / peak }}>
          {value || ""}
        </span>
      ))}
    </div>
  );
}

function Tree({ node }: { node: TreeNode }) {
  const { t } = useI18n();
  return (
    <ul data-testid="hand-tree">
      {node.action ? (
        <li>
          {node.street ? t(node.street) : ""} {t("seat")} {node.seat} {t(node.action)}
          {node.amount ? ` ${node.amount}` : ""}
        </li>
      ) : null}
      {node.children.map((child, index) => (
        <li key={`${child.street}-${index}`}>
          <Tree node={child} />
        </li>
      ))}
    </ul>
  );
}
