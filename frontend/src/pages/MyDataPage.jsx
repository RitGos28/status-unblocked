import React, { useState, useEffect } from "react";
import { api, downloads } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Database, Download, Eye } from "lucide-react";

const SOURCES = {
  webform: "the web form",
  teams: "Teams",
  cli: "the command line",
  csv: "a spreadsheet import",
};

// "2026-10-06T09:30:00+00:00" -> "2026-10-06 09:30"
const when = (iso) => iso.slice(0, 16).replace("T", " ");

export default function MyDataPage({ navigate }) {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!user) return undefined;
    let isMounted = true;
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getMyData();
        if (isMounted) setData(res);
      } catch (err) {
        if (isMounted) setError(err.message || "Could not load your data.");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
  }, [user]);

  if (!user) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "40px 30px" }}>
        <Database size={32} color="var(--text-muted)" style={{ marginBottom: 14 }} />
        <h3 style={{ marginBottom: 8 }}>Sign In Required</h3>
        <p className="muted" style={{ marginBottom: 20 }}>
          Sign in with your team's code and your name to see what is stored about you.
        </p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/login")}>
          Sign in
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 40 }}>
        <span className="loading-spinner" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="notice-box notice-warn">
        <span>{error || "Could not load your data."}</span>
      </div>
    );
  }

  const views = data.events.filter((e) => e.action === "evidence.viewed");

  return (
    <div className="stagger">
      <div className="page-header">
        <div>
          <h1>My data</h1>
          <p className="subtitle" style={{ marginBottom: 0 }}>
            Everything stored about you, and every recorded access to it.
          </p>
        </div>
        <a className="btn btn-outline" href={downloads.myExport()} download>
          <Download size={13} /> Download it as JSON
        </a>
      </div>

      <h2>
        <Eye size={16} style={{ verticalAlign: "-2px" }} /> Who has opened your updates
      </h2>
      <div className="card card-elevated">
        {views.length ? (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>When (UTC)</th>
                  <th>Who</th>
                </tr>
              </thead>
              <tbody>
                {views.map((e, i) => (
                  <tr key={i}>
                    <td>{when(e.when)}</td>
                    <td>{e.by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            Nobody has opened your updates' evidence pages yet.
          </p>
        )}
      </div>

      <h2>Your updates</h2>
      {data.updates.length === 0 && (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>You have not filed any updates.</p>
        </div>
      )}
      {data.updates.map((u) => (
        <div key={u.id} className="card card-elevated">
          <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
            {u.day} · via {SOURCES[u.source] || u.source}
            {u.replaced_by_a_later_update && " · replaced by a later update that day"}
            {u.removed_by_retention_at &&
              ` · full text removed by retention on ${u.removed_by_retention_at.slice(0, 10)}`}
          </p>
          {u.raw_text ? (
            <pre className="raw-display">{u.raw_text}</pre>
          ) : (
            <ul>
              {u.lines.map((line) => (
                <li key={line.id}>
                  {line.removed_by_retention ? (
                    <span className="muted">(a {line.kind} line, removed by retention)</span>
                  ) : (
                    line.text
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}

      <h2>Everything recorded about you</h2>
      <div className="card card-elevated">
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>When (UTC)</th>
                <th>Who</th>
                <th>What</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((e, i) => (
                <tr key={i}>
                  <td>{when(e.when)}</td>
                  <td>{e.by}</td>
                  <td>{e.what}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
