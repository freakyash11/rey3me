import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { useFetch } from "./components/common";
import Accuracy from "./pages/Accuracy";
import DayAhead from "./pages/DayAhead";
import "./styles.css";

const TABS = [
  { id: "dayahead", label: "Day-ahead view" },
  { id: "accuracy", label: "Forecast accuracy" },
] as const;

function App() {
  type TabId = (typeof TABS)[number]["id"];
  const [tab, setTabState] = useState<TabId>(location.hash === "#accuracy" ? "accuracy" : "dayahead");
  const setTab = (id: TabId) => {
    setTabState(id);
    history.replaceState(null, "", `#${id}`);
  };
  const meta = useFetch(api.meta, []);

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <img src="/favicon.svg" width={32} height={32} alt="" />
          <div>
            <h1>Wind Forecast Monitor</h1>
            <small>GB national wind: Elexon forecasts vs actuals, January 2026 decisions</small>
          </div>
        </div>
        <nav className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {meta.error && <div className="card error">Could not reach the API: {meta.error}</div>}
      {meta.loading && <div className="loading">Loading…</div>}
      {meta.data && (tab === "dayahead" ? <DayAhead meta={meta.data} /> : <Accuracy meta={meta.data} />)}

      <footer>
        Data: Elexon BMRS{" "}
        <a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream">FUELHH</a> (actual, fuelType WIND) and{" "}
        <a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream">WINDFOR</a> (forecast). Times are UK local.
        {meta.data && ` Source: ${meta.data.source}.`}
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
