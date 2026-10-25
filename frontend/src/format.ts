const TZ = "Europe/London";

export const gw = (mw: number | null | undefined, digits = 1) =>
  mw == null ? "–" : `${(mw / 1000).toFixed(digits)} GW`;

export const signedGw = (mw: number | null | undefined, digits = 2) =>
  mw == null ? "–" : `${mw > 0 ? "+" : mw < 0 ? "−" : ""}${Math.abs(mw / 1000).toFixed(digits)} GW`;

export const gwh = (mwh: number | null | undefined) =>
  mwh == null ? "–" : `${Math.round(mwh / 1000).toLocaleString("en-GB")} GWh`;

export const kTick = (mw: number) => `${+(mw / 1000).toFixed(1)}K`;

// Y domain rounded up to a multiple of 4 GW so the default 5 ticks land on whole GW.
export const niceMax = (max: number) => Math.max(4000, Math.ceil(max / 4000) * 4000);

export const timeOfDay = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", {
    timeZone: TZ,
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

export const shortDate = (isoDate: string) =>
  new Date(`${isoDate}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

export const longDate = (isoDate: string) =>
  new Date(`${isoDate}T12:00:00Z`).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

export const addDays = (isoDate: string, days: number) => {
  const d = new Date(`${isoDate}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};

export const duration = (minutes: number) => {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h ? `${h}h ${m.toString().padStart(2, "0")}m` : `${m}m`;
};
