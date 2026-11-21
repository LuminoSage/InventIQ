const IN = new Intl.NumberFormat("en-IN");

export const n0 = (v: number) => IN.format(Math.round(v));
export const inr = (v: number) => "₹" + n0(v);
export const pct = (v: number | null | undefined, digits = 0) => (v == null ? "–" : (v * 100).toFixed(digits) + "%");

/** ₹ in lakh or crore, with an explicit sign by default. */
export function money(v: number, signed = true): string {
  const a = Math.abs(v);
  const sign = v < 0 ? "−" : signed ? "+" : "";
  return a >= 1e7 ? `${sign}₹${(a / 1e7).toFixed(2)} Cr` : `${sign}₹${(a / 1e5).toFixed(1)} L`;
}

export const signedPct = (v: number) => (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(0) + "%";

/** A log ratio shown as a percentage change. */
export const logPct = (v: number) => signedPct(Math.expm1(v));

export function shortDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
