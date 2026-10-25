import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Meta } from "../api";
import { AXIS, GRID, Y_DOMAIN, StatTile, TooltipBox, useFetch } from "../components/common";
import { dateTime, gw, kTick, shortDate, signedGw } from "../format";

function useDebounced<T>(value: T, ms = 250) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export default function Accuracy({ meta }: { meta: Meta }) {
  const [horizonInput, setHorizonInput] = useState(24);
  const [from, setFrom] = useState(meta.scope.from);
  const [to, setTo] = useState(meta.scope.to);
  const horizon = useDebounced(horizonInput);

  const acc = useFetch(() => api.accuracy(horizon, from, to), [horizon, from, to]);
  const hz = useFetch(() => api.horizons(from, to), [from, to]);
  const m = acc.data?.metrics;

  const series = useMemo(() => (acc.data?.series ?? []).map((p) => ({ ...p, t: Date.parse(p.time) })), [acc.data]);
  const hist = acc.data?.histogram ?? [];

  return (
    <>
      <div className="controls">
        <label>
          Forecast horizon: {horizonInput} h ahead
          <input type="range" min={0} max={48} step={1} value={horizonInput} onChange={(e) => setHorizonInput(Number(e.target.value))} />
        </label>
        <label>
          From
          <input type="date" value={from} max={to} onChange={(e) => e.target.value && setFrom(e.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={to} min={from} onChange={(e) => e.target.value && setTo(e.target.value)} />
        </label>
        <span className="hint">For each hour, uses the latest forecast published at least {horizonInput} h before it.</span>
      </div>

      {acc.error && <div className="card error">{acc.error}</div>}
      {m && (
        <div className="tiles">
          <StatTile label="Mean absolute error" value={gw(m.mae, 2)} detail={`${(((m.mae ?? 0) / (m.mean_actual ?? 1)) * 100).toFixed(0)}% of mean output (${gw(m.mean_actual)})`} />
          <StatTile label="Bias (forecast − actual)" value={signedGw(m.bias)} detail={(m.bias ?? 0) > 0 ? "Forecasts tend to run high" : "Forecasts tend to run low"} />
          <StatTile label="RMSE" value={gw(m.rmse, 2)} detail="Penalises large misses" />
          <StatTile label="P90 absolute error" value={gw(m.p90_abs, 2)} detail="90% of hours missed by less than this" />
          <StatTile label="MAPE" value={m.mape != null ? `${m.mape.toFixed(1)}%` : "–"} detail="Hours with actual ≥ 1 GW" />
          <StatTile label="Hours compared" value={m.n.toLocaleString("en-GB")} detail={`${shortDate(acc.data!.from)} – ${shortDate(acc.data!.to)}`} />
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <h2>Error grows with forecast horizon</h2>
          <p className="sub">MAE and P90 absolute error (MW) by hours ahead. The vertical line marks the selected horizon.</p>
          <div className="legend">
            <span><i className="key-line" style={{ background: "var(--series-actual)" }} />MAE</span>
            <span><i className="key-line" style={{ background: "var(--series-forecast)" }} />P90 |error|</span>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={hz.data?.horizons ?? []} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="horizon" type="number" domain={[0, 48]} ticks={[0, 6, 12, 18, 24, 30, 36, 42, 48]} tickFormatter={(h) => `${h}h`} {...AXIS} />
              <YAxis tickFormatter={kTick} width={40} {...AXIS} axisLine={false} domain={Y_DOMAIN} />
              <ReferenceLine x={horizonInput} stroke="var(--text-muted)" />
              <Tooltip
                cursor={{ stroke: "var(--axis)" }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const p = payload[0].payload;
                  return (
                    <TooltipBox
                      title={`${p.horizon} h ahead`}
                      rows={[
                        { label: "MAE", value: gw(p.mae, 2), color: "var(--series-actual)" },
                        { label: "P90 |error|", value: gw(p.p90_abs, 2), color: "var(--series-forecast)" },
                        { label: "Bias", value: signedGw(p.bias) },
                      ]}
                    />
                  );
                }}
              />
              <Line dataKey="mae" stroke="var(--series-actual)" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="p90_abs" stroke="var(--series-forecast)" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          {hz.data && (
            <div className="insight">
              With the day-ahead rule (latest forecast before D-1 {hz.data.dayAheadRule.decisionTime}), MAE was{" "}
              <strong>{gw(hz.data.dayAheadRule.mae, 2)}</strong> and bias <strong>{signedGw(hz.data.dayAheadRule.bias)}</strong> over{" "}
              {hz.data.dayAheadRule.n} delivery hours.
            </div>
          )}
        </div>

        <div className="card">
          <h2>Distribution of errors</h2>
          <p className="sub">Hours by forecast error at {horizon} h ahead (forecast − actual, GW, 0.5 GW bins). Bars right of 0 are over-forecasts.</p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={hist} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap={2}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="from" tickFormatter={(v) => `${v / 1000}`} {...AXIS} minTickGap={12} />
              <YAxis width={40} {...AXIS} axisLine={false} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: "var(--grid)", opacity: 0.5 }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const b = payload[0].payload;
                  return <TooltipBox title={`${signedGw(b.from)} to ${signedGw(b.to)}`} rows={[{ label: "Hours", value: String(b.count) }]} />;
                }}
              />
              <Bar dataKey="count" fill="var(--series-actual)" radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Actual vs forecast at {horizon} h ahead</h2>
        <p className="sub">Hourly national wind generation (MW).</p>
        <div className="legend">
          <span><i className="key-line" style={{ background: "var(--series-actual)" }} />Actual</span>
          <span><i className="key-line" style={{ background: "var(--series-forecast)" }} />Forecast ({horizon} h ahead)</span>
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t) => shortDate(new Date(t).toISOString().slice(0, 10))} {...AXIS} />
            <YAxis tickFormatter={kTick} width={40} {...AXIS} axisLine={false} domain={Y_DOMAIN} />
            <Tooltip
              cursor={{ stroke: "var(--axis)" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload;
                return (
                  <TooltipBox
                    title={dateTime(p.time)}
                    rows={[
                      { label: "Actual", value: gw(p.actual, 2), color: "var(--series-actual)" },
                      { label: "Forecast", value: gw(p.forecast, 2), color: "var(--series-forecast)" },
                      { label: "Error", value: signedGw(p.forecast - p.actual) },
                      { label: "Published", value: dateTime(p.published) },
                    ]}
                  />
                );
              }}
            />
            <Line dataKey="actual" stroke="var(--series-actual)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="forecast" stroke="var(--series-forecast)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Daily mean absolute error</h2>
        <p className="sub">Helps spot days when the forecast was unreliable, e.g. fast-moving weather fronts.</p>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={acc.data?.daily ?? []} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap={2}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="day" tickFormatter={shortDate} {...AXIS} interval="preserveStartEnd" minTickGap={24} />
            <YAxis tickFormatter={kTick} width={40} {...AXIS} axisLine={false} domain={Y_DOMAIN} />
            <Tooltip
              cursor={{ fill: "var(--grid)", opacity: 0.5 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload;
                return (
                  <TooltipBox title={shortDate(d.day)} rows={[{ label: "MAE", value: gw(d.mae, 2) }, { label: "Bias", value: signedGw(d.bias) }]} />
                );
              }}
            />
            <Bar dataKey="mae" fill="var(--series-actual)" radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
        <details className="table-view">
          <summary>Show data table</summary>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Day</th><th>MAE MW</th><th>Bias MW</th></tr></thead>
              <tbody>
                {(acc.data?.daily ?? []).map((d) => (
                  <tr key={d.day}><td>{d.day}</td><td>{Math.round(d.mae).toLocaleString("en-GB")}</td><td>{Math.round(d.bias).toLocaleString("en-GB")}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </>
  );
}
