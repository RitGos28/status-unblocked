import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import { CheckCircle2, RefreshCw, BookOpen, AlertCircle, BarChart3, Clock } from "lucide-react";

export default function DigestsPage({ navigate, searchParams }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState([]);
  const [buildingId, setBuildingId] = useState(null);
  const [error, setError] = useState(null);

  const submitted = searchParams.get("submitted");

  const loadDigests = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.listDigests();
      if (res && res.rows) {
        setRows(res.rows);
      }
    } catch (err) {
      setError(err.message || "Failed to load digests.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) loadDigests();
  }, [user]);

  if (!user) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "40px 30px" }}>
        <BookOpen size={32} color="var(--text-muted)" style={{ marginBottom: 14 }} />
        <h3 style={{ marginBottom: 8 }}>Sign In Required</h3>
        <p className="muted" style={{ marginBottom: 20 }}>
          Sign in with your team's code and your name to read digests.
        </p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/login")}>
          Sign in
        </button>
      </div>
    );
  }

  const handleBuild = async (cycleId) => {
    setBuildingId(cycleId);
    setError(null);
    try {
      const res = await api.buildDigest(cycleId);
      if (res && res.digest_id) {
        navigate(`/digest/${res.digest_id}`);
      }
    } catch (err) {
      setError(err.message || "Failed to build digest.");
      setBuildingId(null);
    }
  };

  const openCount  = rows.filter((r) => r.cycle.state === "open").length;
  const totalCount = rows.length;

  return (
    <div className="stagger">
      <div className="page-header">
        <div>
          <h1>Digests</h1>
          <p className="subtitle" style={{ marginBottom: 0 }}>
            Your team's daily summary, built from everyone's updates. One per team per day.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-outline"
          onClick={loadDigests}
          disabled={loading}
          style={{ fontSize: 13, padding: "7px 14px" }}
        >
          <RefreshCw size={13} style={loading ? { animation: "spin 0.65s linear infinite" } : {}} />
          Refresh
        </button>
      </div>

      {/* Stats */}
      {!loading && totalCount > 0 && (
        <div className="stat-row">
          <div className="stat-chip">
            <BarChart3 size={13} />
            <strong>{totalCount}</strong> cycles total
          </div>
          <div className="stat-chip">
            <Clock size={13} />
            <strong>{openCount}</strong> open
          </div>
        </div>
      )}

      {submitted && (
        <div className="notice-box notice-success">
          <CheckCircle2 size={17} />
          <span>Update recorded — it will be incorporated into today's digest.</span>
        </div>
      )}

      {error && (
        <div className="notice-box notice-warning">
          <AlertCircle size={17} />
          <span>{error}</span>
        </div>
      )}

      {loading && rows.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "40px 24px" }}>
          <span className="loading-spinner" style={{ width: 26, height: 26 }} />
          <p className="muted" style={{ marginTop: 14 }}>Loading digests…</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "40px 24px" }}>
          <BookOpen size={30} color="var(--text-muted)" style={{ marginBottom: 12 }} />
          <p style={{ margin: 0, color: "var(--text-secondary)" }}>
            Nothing yet.{" "}
            <button
              type="button"
              onClick={() => navigate("/submit")}
              style={{
                background: "none",
                border: "none",
                color: "var(--accent-bright)",
                fontWeight: 600,
                cursor: "pointer",
                padding: 0,
                fontSize: "inherit",
              }}
            >
              Submit an update
            </button>{" "}
            to open a cycle.
          </p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Team</th>
                <th>Updates</th>
                <th>Status</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isBuilding = buildingId === r.cycle.id;
                return (
                  <tr key={r.cycle.id}>
                    <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                      {r.cycle.local_date}
                    </td>
                    <td style={{ color: "var(--text-secondary)" }}>{r.team_name}</td>
                    <td>
                      <span className="code-inline">{r.update_count}</span>
                    </td>
                    <td>
                      <span className={`badge-state ${r.cycle.state === "open" ? "open" : "closed"}`}>
                        {r.cycle.state}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div className="table-actions" style={{ justifyContent: "flex-end" }}>
                        {r.digest && (
                          <button
                            type="button"
                            className="btn btn-accent-outline"
                            style={{ padding: "5px 12px", fontSize: 13 }}
                            onClick={() => navigate(`/digest/${r.digest.id}`)}
                          >
                            <BookOpen size={12} /> Read
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ padding: "5px 12px", fontSize: 13 }}
                          disabled={isBuilding}
                          onClick={() => handleBuild(r.cycle.id)}
                        >
                          {isBuilding ? (
                            <>
                              <span className="loading-spinner" style={{ width: 12, height: 12 }} />
                              Building…
                            </>
                          ) : r.digest ? (
                            "Rebuild"
                          ) : (
                            "Build digest"
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
