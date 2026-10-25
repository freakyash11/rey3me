// Typed wrapper around the FastAPI backend (same origin in production, proxied in dev).

export interface Metrics {
  n: number;
  mae?: number;
  rmse?: number;
  bias?: number;
  mape?: number | null;
  p10?: number;
  p50?: number;
  p90?: number;
  p90_abs?: number;
  max_abs?: number;
  mean_actual?: number;
}

export interface Meta {
  source: string;
  scope: { from: string; to: string };
  defaultDecisionTime: string;
  actualDays: string[];
  forecastRuns: { count: number; first: string; last: string };
}

export interface DayPoint {
  time: string;
  actual: number | null;
  forecast: number | null;
  low: number | null;
  high: number | null;
}

export interface DayAhead {
  date: string;
  decision: string;
  leadHours: number;
  run: { published: string; ageMinutes: number; hours: number; nextRun: string | null; runsBeforeDelivery: number };
  forecastEnergyMWh: number;
  firmEnergyMWh: number | null;
  forecastMin: number | null;
  forecastMax: number | null;
  calibration: Metrics & { days: number; from: string | null; to: string | null };
  dayMetrics: Metrics | null;
  series: DayPoint[];
}

export interface Accuracy {
  horizon: number;
  from: string;
  to: string;
  metrics: Metrics;
  histogram: { from: number; to: number; count: number }[];
  daily: { day: string; mae: number; bias: number }[];
  series: { time: string; forecast: number; actual: number; published: string }[];
}

export interface Horizons {
  from: string;
  to: string;
  horizons: { horizon: number; n: number; mae: number; rmse: number; bias: number; p90_abs: number }[];
  dayAheadRule: Metrics & { decisionTime: string };
}

async function get<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && qs.set(k, String(v)));
  const res = await fetch(`/api/${path}${qs.size ? `?${qs}` : ""}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  meta: () => get<Meta>("meta"),
  dayAhead: (date: string, decision?: string) => get<DayAhead>("dayahead", { date, decision }),
  accuracy: (horizon: number, from?: string, to?: string) => get<Accuracy>("accuracy", { horizon, from, to }),
  horizons: (from?: string, to?: string) => get<Horizons>("accuracy/horizons", { from, to }),
};
