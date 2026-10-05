import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import { Send, AlertCircle, CheckCircle } from "lucide-react";

export default function SubmitPage({ navigate }) {
  const { user } = useAuth();
  const [progress, setProgress] = useState("");
  const [blockers, setBlockers] = useState("");
  const [plan, setPlan] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!user) {
    return (
      <div className="card">
        <h3>Sign In Required</h3>
        <p className="muted" style={{ marginTop: 8 }}>
          You must be signed in with a team member magic link to submit an update.
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const res = await api.submitUpdate({
        progress,
        blockers,
        plan,
      });

      if (res && res.success) {
        navigate(`/digests?submitted=${res.update_id}`);
      }
    } catch (err) {
      console.error("Submission failed:", err);
      setError(err.message || "Failed to submit update. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <h1>Today's update</h1>
      <p className="subtitle">
        Three short answers. Roughly ninety seconds. Only what you type here is stored.
      </p>

      {error && (
        <div className="notice-box notice-warning">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="card card-elevated" style={{ padding: "24px 26px" }}>
          <p className="muted" style={{ marginBottom: 20 }}>
            Submitting as <strong>{user.display_name}</strong>. Submitting again today replaces this update in the digest.
          </p>

          <div className="form-group">
            <label htmlFor="progress">
              <span>Progress</span>
              <span className="hint">what moved since last standup</span>
            </label>
            <textarea
              id="progress"
              value={progress}
              onChange={(e) => setProgress(e.target.value)}
              placeholder="e.g. Merged the search index rebuild."
              disabled={submitting}
            />
          </div>

          <div className="form-group">
            <label htmlFor="blockers">
              <span>Blockers</span>
              <span className="hint">what is stopping you &mdash; this is the part people read</span>
            </label>
            <textarea
              id="blockers"
              value={blockers}
              onChange={(e) => setBlockers(e.target.value)}
              placeholder="e.g. Waiting on a design review for the billing page."
              disabled={submitting}
            />
          </div>

          <div className="form-group" style={{ marginBottom: 10 }}>
            <label htmlFor="plan">
              <span>Today</span>
              <span className="hint">what you are picking up</span>
            </label>
            <textarea
              id="plan"
              value={plan}
              onChange={(e) => setPlan(e.target.value)}
              placeholder="e.g. Write the rollback plan for the payments change."
              disabled={submitting}
            />
          </div>

          <div style={{ marginTop: 24, display: "flex", alignItems: "center", gap: 14 }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting}
            >
              {submitting ? (
                <>
                  <span className="loading-spinner" /> Submitting...
                </>
              ) : (
                <>
                  <Send size={15} /> Submit update
                </>
              )}
            </button>
          </div>
        </div>
      </form>

      <p className="muted" style={{ marginTop: 20 }}>
        Your update goes into <strong>{user.team_name}</strong>'s digest, visible to everyone on the team equally and to no one outside it. There is no manager-only view.
      </p>
    </div>
  );
}
