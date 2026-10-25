import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type DayPoint, type Meta } from "../api";
import { AXIS, GRID, Y_DOMAIN, StatTile, TooltipBox, useFetch } from "../components/common";
import { addDays, dateTime, duration, gw, gwh, kTick, longDate, signedGw, timeOfDay } from "../format";

export default function DayAhead({ meta }: { meta: Meta }) {
  const [day, setDay] = useState("2026-01-15");
  const [daysBefore, setDaysBefore] = useState(1);
  const [time, setTime] = useState(meta.defaultDecisionTime);
  const decision = `${addDays(day, -daysBefore)}T${time}`;
  const { data, error, loading } = useFetch(() => api.dayAhead(day, decision), [day, decision]);

  const chartData = useMemo(
    () =>
      (data?.series ?? []).map((p) => ({
        ...p,
        t: Date.parse(p.time),
        band: p.low != null && p.high != null ? [p.low, p.high] : null,
      })),
    [data],
  );

  return (
    <>
      <div className="controls">
        <label>
          Delivery day
          <input type="date" value={day} min={meta.scope.from} max={meta.scope.to} onChange={(e) => e.target.value && setDay(e.target.value)} />
        </label>
        <label>
          Decision day
          <select value={daysBefore} onChange={(e) => setDaysBefore(Number(e.target.value))}>
            <option value={1}>D-1 ({addDays(day, -1)})</option>
            <option value={2}>D-2 ({addDays(day, -2)})</option>
          </select>
        </label>
        <label>
          Decision time (UK)
          <input type="time" step={1800} value={time} onChange={(e) => e.target.value && setTime(e.target.value)} />
        </label>
        <span className="hint">Shows the latest forecast published before your decision time.</span>
      </div>

      {error && <div className="card error">{error}</div>}
      {loading && !data && <div className="loading">Loading forecast…</div>}
      {data && (
        <div style={{ opacity: loading ? 0.6 : 1, transition: "opacity .15s" }}>
          <div className="hero">
            <div className="card">
              <h2>Expected wind generation</h2>
              <p className="sub">{longDate(data.date)}</p>
              <div className="hero-figure">{gwh(data.forecastEnergyMWh)}</div>
              <div className="hero-note">
                Average {gw(data.forecastEnergyMWh / Math.max(data.run.hours, 1))}, between {gw(data.forecastMin)} and {gw(data.forecastMax)}.
              </div>
              {data.calibration.n > 0 && (
                <div className="insight">
                  At this lead time over the previous {data.calibration.days} days, forecasts were off by{" "}
                  <strong>{gw(data.calibration.mae, 2)}</strong> on average and ran{" "}
                  <strong>{signedGw(data.calibration.bias)}</strong> {(data.calibration.bias ?? 0) >= 0 ? "high" : "low"}. With 90% confidence, wind
                  output will be at least <strong>{gwh(data.firmEnergyMWh)}</strong>. Buy the rest of your requirement in the day-ahead market.
                </div>
              )}
            </div>
            <div className="tiles">
              <StatTile
                label="Firm wind (90% confidence)"
                value={gwh(data.firmEnergyMWh)}
                detail="Forecast less the historical P90 over-forecast"
              />
              <StatTile
                label="Forecast published"
                value={dateTime(data.run.published)}
                detail={`${duration(data.run.ageMinutes)} before your decision`}
              />
              <StatTile
                label="Next forecast run"
                value={data.run.nextRun ? dateTime(data.run.nextRun) : "None before delivery"}
                detail={`${data.run.runsBeforeDelivery} more runs before delivery starts`}
              />
              <StatTile
                label="Error band (P10–P90)"
                value={`${signedGw(-(data.calibration.p90 ?? 0), 1)} / ${signedGw(-(data.calibration.p10 ?? 0), 1)}`}
                detail={
                  data.calibration.from
                    ? `Calibrated on ${data.calibration.from} to ${data.calibration.to}`
                    : "Not enough history"
                }
              />
              <StatTile
                label="Lead time"
                value={`${Math.round(data.leadHours)}–${Math.round(data.leadHours + 23)} h`}
                detail="From decision to each delivery hour"
              />
              <StatTile
                label="Outcome on the day (MAE)"
                value={data.dayMetrics ? gw(data.dayMetrics.mae, 2) : "Pending"}
                detail={data.dayMetrics ? `Bias ${signedGw(data.dayMetrics.bias)} vs actual` : "Actuals not yet available"}
              />
            </div>
          </div>

          <div className="card">
            <h2>Forecast available at decision time vs actual generation</h2>
            <p className="sub">National wind (MW). The shaded band is the likely range of actual output, based on recent forecast errors.</p>
            <div className="legend">
              <span><i className="key-line" style={{ background: "var(--series-actual)" }} />Actual (half-hourly)</span>
              <span><i className="key-line" style={{ background: "var(--series-forecast)" }} />Forecast (hourly)</span>
              <span><i className="key-band" style={{ background: "var(--series-forecast)" }} />P10–P90 range</span>
            </div>
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid {...GRID} />
                <XAxis
                  dataKey="t"
                  type="number"
                  scale="time"
                  domain={["dataMin", "dataMax"]}
                  tickFormatter={(t) => timeOfDay(new Date(t).toISOString())}
                  {...AXIS}
                />
                <YAxis tickFormatter={kTick} width={40} {...AXIS} axisLine={false} domain={Y_DOMAIN} />
                <Tooltip
                  cursor={{ stroke: "var(--axis)" }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0].payload as DayPoint;
                    return (
                      <TooltipBox
                        title={timeOfDay(p.time)}
                        rows={[
                          { label: "Actual", value: gw(p.actual, 2), color: "var(--series-actual)" },
                          ...(p.forecast != null
                            ? [
                                { label: "Forecast", value: gw(p.forecast, 2), color: "var(--series-forecast)" },
                                { label: "P10–P90", value: `${gw(p.low)} – ${gw(p.high)}`, color: "var(--series-forecast)", band: true },
                              ]
                            : []),
                        ]}
                      />
                    );
                  }}
                />
                <Area dataKey="band" stroke="none" fill="var(--series-forecast)" fillOpacity={0.12} connectNulls isAnimationActive={false} />
                <Line dataKey="actual" stroke="var(--series-actual)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                <Line dataKey="forecast" stroke="var(--series-forecast)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
            <details className="table-view">
              <summary>Show data table</summary>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Time (UK)</th><th>Actual MW</th><th>Forecast MW</th><th>P10 MW</th><th>P90 MW</th></tr>
                  </thead>
                  <tbody>
                    {data.series.map((p) => (
                      <tr key={p.time}>
                        <td>{timeOfDay(p.time)}</td>
                        <td>{p.actual?.toLocaleString("en-GB") ?? ""}</td>
                        <td>{p.forecast?.toLocaleString("en-GB") ?? ""}</td>
                        <td>{p.low?.toLocaleString("en-GB") ?? ""}</td>
                        <td>{p.high?.toLocaleString("en-GB") ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        </div>
      )}
    </>
  );
}
