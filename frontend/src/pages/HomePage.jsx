import React from "react";
import { useAuth } from "../context/AuthContext";
import { ArrowRight, CheckCircle2, KeyRound, Sparkles } from "lucide-react";

export default function HomePage({ navigate, searchParams }) {
  const { user } = useAuth();
  const signedOut = searchParams.get("signed_out") === "1";

  return (
    <div>
      <h1>Status Unblocked</h1>
      <p className="subtitle">
        Async standup updates, summarised faithfully. Every line links back to the exact words its author wrote.
      </p>

      {signedOut && !user && (
        <div className="notice-box notice-info" style={{ marginBottom: 20 }}>
          <CheckCircle2 size={18} />
          <span>You have been signed out successfully.</span>
        </div>
      )}

      <div className="card card-elevated" style={{ padding: "26px 28px" }}>
        {user ? (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <Sparkles size={20} color="var(--accent-primary)" />
              <h3 style={{ fontSize: 17, fontWeight: 700 }}>
                Welcome back, {user.display_name}!
              </h3>
            </div>
            <p style={{ color: "var(--text-secondary)", marginBottom: 22, lineHeight: 1.6 }}>
              You are signed in to the <strong>{user.team_name}</strong> team. You can submit your daily standup or catch up on the team's latest verified digests.
            </p>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate("/submit")}
              >
                Submit today's update <ArrowRight size={15} />
              </button>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => navigate("/digests")}
              >
                Read team digests
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <KeyRound size={20} color="var(--accent-primary)" />
              <h3 style={{ fontSize: 17, fontWeight: 700 }}>Personal Magic Link Sign-in</h3>
            </div>
            <p style={{ color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 16 }}>
              Open the personal link your team gave you to sign in. There are no passwords; each link is cryptographically signed for one person and expires automatically.
            </p>
            <p className="muted">
              Demo tip: If running locally, generate login links by running{" "}
              <code className="code-inline">python -m scripts.issue_links</code> in the backend.
            </p>
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16, marginTop: 24 }}>
        <div className="card">
          <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 6, color: "var(--accent-primary)" }}>
            Extractive Faithfulness
          </h4>
          <p className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
            Synthesized lines are verbatim source spans. Summarizer rules enforce zero-hallucination accuracy on blockers.
          </p>
        </div>
        <div className="card">
          <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 6, color: "var(--accent-primary)" }}>
            Verifiable Citations
          </h4>
          <p className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
            Every claim links directly to its source item evidence with exact character offset highlighting and audit tracking.
          </p>
        </div>
        <div className="card">
          <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 6, color: "var(--accent-primary)" }}>
            Ecosystem Integration
          </h4>
          <p className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
            Full bidirectional support for Microsoft Teams bot ingestion, outbox-drained GitHub issue tracking, and audit chains.
          </p>
        </div>
      </div>
    </div>
  );
}
