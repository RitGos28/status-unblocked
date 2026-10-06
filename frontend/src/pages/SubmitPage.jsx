import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import { Send, AlertCircle, FileText } from "lucide-react";

const FIELDS = [
  {
    id: "progress",
    label: "Progress",
    hint: "what moved since last standup",
    placeholder: "e.g. Merged the search index rebuild.",
    setter: "setProgress",
    getter: "progress",
  },
  {
    id: "blockers",
    label: "Blockers",
    hint: "what is stopping you — the part people read most",
    placeholder: "e.g. Waiting on a design review for the billing page.",
    setter: "setBlockers",
    getter: "blockers",
  },
  {
    id: "plan",
    label: "Today",
    hint: "what you are picking up",
    placeholder: "e.g. Write the rollback plan for the payments change.",
    setter: "setPlan",
    getter: "plan",
  },
];

export default function SubmitPage({ navigate }) {
  const { user } = useAuth();
  const [progress, setProgress] = useState("");
  const [blockers, setBlockers] = useState("");
  const [plan, setPlan] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const fieldState = { progress, blockers, plan };
  const fieldSetters = { setProgress, setBlockers, setPlan };

  if (!user) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "40px 30px" }}>
        <FileText size={32} color="var(--text-muted)" style={{ marginBottom: 14 }} />
        <h3 style={{ marginBottom: 8 }}>Sign In Required</h3>
        <p className="muted" style={{ marginBottom: 20 }}>
          You must be signed in with a team member magic link to submit an update.
        </p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/")}>
          Back to Home
        </button>
      </div>
    );
  }

  const charCount = [progress, blockers, plan].join("").length;
  const hasContent = charCount > 0;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.submitUpdate({ progress, blockers, plan });
      if (res && res.success) {
        navigate(`/digests?submitted=${res.update_id}`);
      }
    } catch (err) {
      setError(err.message || "Failed to submit update. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="stagger">
      <div>
        <h1>Today's update</h1>
        <p className="subtitle">
          Three short answers. Roughly ninety seconds. Only what you type here is stored.
        </p>
      </div>

      {error && (
        <div className="notice-box notice-warning">
          <AlertCircle size={17} />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="card card-elevated" style={{ padding: "28px 28px 24px" }}>
          {/* Submitter pill */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              background: "var(--accent-dim)",
              border: "1px solid var(--accent-border)",
              borderRadius: "var(--r-full)",
              padding: "5px 14px",
              marginBottom: 22,
              fontSize: 13,
              color: "var(--accent-bright)",
            }}
          >
            <div
              style={{
                width: 20,
                height: 20,
                borderRadius: "50%",
                background: "linear-gradient(135deg, var(--accent) 0%, #a78bfa 100%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 9,
                fontWeight: 800,
                color: "white",
              }}
            >
              {user.display_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
            </div>
            <strong>{user.display_name}</strong>
            <span style={{ opacity: 0.6 }}>·</span>
            <span style={{ opacity: 0.7 }}>{user.team_name}</span>
          </div>

          {FIELDS.map((f) => (
            <div className="form-group" key={f.id}>
              <label htmlFor={f.id}>
                <span>{f.label}</span>
                <span className="hint">{f.hint}</span>
              </label>
              <textarea
                id={f.id}
                value={fieldState[f.getter]}
                onChange={(e) => fieldSetters[f.setter](e.target.value)}
                placeholder={f.placeholder}
                disabled={submitting}
              />
            </div>
          ))}

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginTop: 8,
              flexWrap: "wrap",
              gap: 12,
            }}
          >
            <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>
              Goes into <strong style={{ color: "var(--text-secondary)" }}>{user.team_name}</strong>'s digest.
              Submitting again today replaces this update.
            </p>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || !hasContent}
              style={{ minWidth: 148 }}
            >
              {submitting ? (
                <>
                  <span className="loading-spinner" style={{ width: 14, height: 14 }} />
                  Submitting…
                </>
              ) : (
                <>
                  <Send size={14} /> Submit update
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
