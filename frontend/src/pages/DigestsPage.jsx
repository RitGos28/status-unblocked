import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import { BookOpen, RefreshCw } from "lucide-react";
import { EmptyState, Loading, Notice, PageHeader, SignInRequired, whenUtc } from "../components/ui";

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
      if (res && res.rows) setRows(res.rows);
    } catch (err) {
      setError(err.message || "Could not load digests.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) loadDigests();
  }, [user]);

  if (!user) return <SignInRequired navigate={navigate} what="read digests" />;

  const handleBuild = async (cycleId) => {
    setBuildingId(cycleId);
    setError(null);
    try {
      const res = await api.buildDigest(cycleId);
      if (res && res.digest_id) navigate(`/digest/${res.digest_id}`);
    } catch (err) {
      setError(err.message || "Could not build the digest.");
      setBuildingId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Digests"
        lead="One per day for your team, built from everyone's updates at the cutoff or on demand."
        actions={
          <button type="button" className="btn btn-sm" onClick={loadDigests} disabled={loading}>
            <RefreshCw size={13} className={loading ? "spin" : ""} /> Refresh
          </button>
        }
      />

      {submitted && (
        <Notice tone="success">Update recorded. It will be in today's digest when it is built.</Notice>
      )}
      {error && <Notice tone="danger">{error}</Notice>}

      {loading && rows.length === 0 ? (
        <Loading label="Loading digests…" />
      ) : rows.length === 0 ? (
        <EmptyState icon={BookOpen} title="No standup days yet">
          The first update of the day opens a day for the team.{" "}
          <button type="button" className="btn-link" onClick={() => navigate("/submit")}>
            Submit an update
          </button>
          .
        </EmptyState>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Day</th>
                <th>Updates</th>
                <th>Digest</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isBuilding = buildingId === r.cycle.id;
                return (
                  <tr key={r.cycle.id}>
                    <td>
                      <strong>{r.cycle.local_date}</strong>
                      <div className="muted small">
                        {r.cycle.state === "digested"
                          ? "Digest built"
                          : r.cycle.state === "closed"
                            ? "Closed"
                            : "Collecting updates"}
                      </div>
                    </td>
                    <td className="num">{r.update_count}</td>
                    <td className="muted">
                      {r.digest ? `built ${whenUtc(r.digest.generated_at)} UTC` : "not built"}
                    </td>
                    <td>
                      <div className="table-actions">
                        {r.digest && (
                          <button
                            type="button"
                            className="btn btn-sm"
                            onClick={() => navigate(`/digest/${r.digest.id}`)}
                          >
                            Read
                          </button>
                        )}
                        {r.final ? (
                          <span className="muted small">Updates removed by retention</span>
                        ) : (
                          <button
                            type="button"
                            className={`btn btn-sm ${r.digest ? "btn-ghost" : "btn-primary"}`}
                            disabled={isBuilding}
                            onClick={() => handleBuild(r.cycle.id)}
                          >
                            {isBuilding ? "Building…" : r.digest ? "Rebuild" : "Build digest"}
                          </button>
                        )}
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
