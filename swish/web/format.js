// Formatting helpers. Money comes over the wire in whole dollars.

export function money(dollars, { signed = false } = {}) {
  const sign = dollars < 0 ? "−" : signed && dollars > 0 ? "+" : "";
  const abs = Math.abs(dollars);
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(abs >= 1e8 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${sign}$${Math.round(abs / 1000)}k`;
  return `${sign}$${Math.round(abs)}`;
}

export function millions(dollars, digits = 1) {
  const sign = dollars < 0 ? "−" : "";
  return `${sign}$${(Math.abs(dollars) / 1_000_000).toFixed(digits)}M`;
}

export function war(x, digits = 1) {
  return (x >= 0 ? "" : "−") + Math.abs(x).toFixed(digits);
}

export function pct(x, digits = 0) {
  if (x === null || x === undefined) return "—";
  return `${(x * 100).toFixed(digits)}%`;
}

export function ordinal(n) {
  const r = Math.round(n);
  const s = ["th", "st", "nd", "rd"];
  const v = r % 100;
  return r + (s[(v - 20) % 10] || s[v] || s[0]);
}

export function seasonLabel(endYear) {
  return `${endYear - 1}–${String(endYear).slice(2)}`;
}

export function feet(inches) {
  if (!inches) return "";
  return `${Math.floor(inches / 12)}′${inches % 12}″`;
}
