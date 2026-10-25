import { useEffect, useState, type ReactNode } from "react";
import { niceMax } from "../format";

export function useFetch<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    load()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((e: Error) => alive && setState({ error: e.message, loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function StatTile({ label, value, detail }: { label: string; value: ReactNode; detail?: ReactNode }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {detail && <div className="detail">{detail}</div>}
    </div>
  );
}

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
  band?: boolean;
}

export function TooltipBox({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div className="tooltip">
      <div className="t-title">{title}</div>
      {rows.map((r) => (
        <div className="t-row" key={r.label}>
          <span>
            {r.color && <i className={r.band ? "key-band" : "key-line"} style={{ background: r.color }} />}
            {r.label}
          </span>
          <b>{r.value}</b>
        </div>
      ))}
    </div>
  );
}

export const Y_DOMAIN: [number, (max: number) => number] = [0, niceMax];

export const AXIS = { stroke: "var(--axis)", tickLine: false } as const;
export const GRID = { stroke: "var(--grid)", vertical: false } as const;
