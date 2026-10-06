export type ChipBounds = { min: number; max: number };

type BuyInSpec = { min?: unknown; max?: unknown; unit?: unknown };

export function buyInBounds(
  rules: Record<string, unknown> | undefined,
  bigBlind: number,
): ChipBounds | null {
  const raw = rules?.buy_in;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const spec = raw as BuyInSpec;
  if (typeof spec.min !== "number" || typeof spec.max !== "number" || spec.min <= 0) {
    return null;
  }
  if (spec.unit === "bb") {
    const blind = bigBlind > 0 ? bigBlind : 1;
    return { min: spec.min * blind, max: spec.max * blind };
  }
  return { min: spec.min, max: spec.max };
}

export function defaultBuyIn(rules: Record<string, unknown> | undefined, bigBlind: number): number {
  return buyInBounds(rules, bigBlind)?.min ?? 1000;
}
