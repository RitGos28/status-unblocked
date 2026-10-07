import React, { useState, useEffect } from "react";
import { api, downloads } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Download } from "lucide-react";
import { Loading, Notice, PageHeader, SignInRequired, whenUtc } from "../components/ui";

const SOURCES = {
  webform: "the web form",
  teams: "Teams",
  cli: "the command line",
  csv: "a spreadsheet import",
};

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

  if (!user) return <SignInRequired navigate={navigate} what="see your data" />;
  if (loading) return <Loading />;
  if (error || !data) return <Notice tone="danger">{error || "Could not load your data."}</Notice>;

  const views = data.events.filter((e) => e.action === "evidence.viewed");

  return (
    <div>
      <PageHeader
        title="My data"
        lead="Everything stored about you, and every recorded access to it."
        actions={
          <a className="btn btn-sm" href={downloads.myExport()} download>
            <Download size={13} /> Download as JSON
          </a>
        }
      />

      <h2>Who has opened your updates</h2>
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
                  <td className="num">{whenUtc(e.when)}</td>
                  <td>{e.by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">Nobody has opened the evidence for your updates yet.</p>
      )}

      <h2>Your updates</h2>
      {data.updates.length === 0 && <p className="muted">You have not filed any updates.</p>}
      {data.updates.map((u) => (
        <div key={u.id} className="card">
          <div className="meta mb-8">
            <span>
              <strong>{u.day}</strong>
            </span>
            <span>via {SOURCES[u.source] || u.source}</span>
            {u.replaced_by_a_later_update && <span>replaced by a later update that day</span>}
            {u.removed_by_retention_at && (
              <span>full text removed by retention on {u.removed_by_retention_at.slice(0, 10)}</span>
            )}
          </div>
          {u.raw_text ? (
            <pre className="raw-display">{u.raw_text}</pre>
          ) : (
            <ul style={{ paddingLeft: 18 }}>
              {u.lines.map((line) => (
                <li key={line.id}>
                  {line.removed_by_retention ? (
                    <span className="muted">a {line.kind} line, removed by retention</span>
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
                <td className="num">{whenUtc(e.when)}</td>
                <td>{e.by}</td>
                <td>{e.what}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
