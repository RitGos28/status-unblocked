import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import { CheckCircle2, RefreshCw, BookOpen, AlertCircle } from "lucide-react";

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
      console.error("Failed to load digests:", err);
      setError(err.message || "Failed to load digests.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) {
      loadDigests();
    }
  }, [user]);

  if (!user) {
    return (
      <div className="card">
        <h3>Sign In Required</h3>
        <p className="muted" style={{ marginTop: 8 }}>
          Please sign in to read digests. Open your team magic link.
        </p>
        <button
          type="button"
          className="btn btn-primary"
          style={{ marginTop: 16 }}
          onClick={() => navigate("/")}
        >
          Go to Home
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
      console.error("Failed to build digest:", err);
      setError(err.message || "Failed to build digest.");
      setBuildingId(null);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1>Digests</h1>
          <p className="subtitle">One per team per day.</p>
        </div>
        <button
          type="button"
          className="btn btn-outline"
          onClick={loadDigests}
          disabled={loading}
          style={{ fontSize: 13, padding: "6px 12px" }}
        >
          <RefreshCw size={13} className={loading ? "loading-spinner" : ""} /> Refresh
        </button>
      </div>

      {submitted && (
        <div className="notice-box notice-success">
          <CheckCircle2 size={18} />
          <span>Update recorded. It will be incorporated into today's digest.</span>
        </div>
      )}

      {error && (
        <div className="notice-box notice-warning">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {loading && rows.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 36 }}>
          <span className="loading-spinner" style={{ width: 24, height: 24 }} />
          <p className="muted" style={{ marginTop: 12 }}>Loading digests...</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="card">
          <p style={{ margin: 0 }}>
            Nothing yet.{" "}
            <a
              href="#/submit"
              onClick={(e) => {
                e.preventDefault();
                navigate("/submit");
              }}
              style={{ color: "var(--accent-primary)", fontWeight: 600 }}
            >
              Submit an update
            </a>{" "}
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
                <th>State</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isBuilding = buildingId === r.cycle.id;
                return (
                  <tr key={r.cycle.id}>
                    <td style={{ fontWeight: 600 }}>{r.cycle.local_date}</td>
                    <td>{r.team_name}</td>
                    <td>
                      <span className="code-inline">{r.update_count}</span>
                    </td>
                    <td>
                      <span
                        className={`badge-state ${
                          r.cycle.state === "open" ? "open" : "closed"
                        }`}
                      >
                        {r.cycle.state}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div className="table-actions" style={{ justifyContent: "flex-end" }}>
                        {r.digest && (
                          <button
                            type="button"
                            className="btn btn-outline"
                            style={{ padding: "5px 11px", fontSize: 13 }}
                            onClick={() => navigate(`/digest/${r.digest.id}`)}
                          >
                            <BookOpen size={13} /> Read digest
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ padding: "5px 11px", fontSize: 13 }}
                          disabled={isBuilding}
                          onClick={() => handleBuild(r.cycle.id)}
                        >
                          {isBuilding ? (
                            <>
                              <span className="loading-spinner" /> Building...
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
