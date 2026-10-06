import React from "react";
import { useAuth } from "../context/AuthContext";
import { ArrowRight, CheckCircle2, KeyRound, Zap, Quote, ShieldCheck } from "lucide-react";

export default function HomePage({ navigate, searchParams }) {
  const { user } = useAuth();
  const signedOut = searchParams.get("signed_out") === "1";

  return (
    <div className="stagger">
      <div>
        <h1>Async standups,<br />zero-hallucination.</h1>
        <p className="subtitle">
          Every digest line links back to the exact words its author wrote. No paraphrasing. No ambiguity.
        </p>
      </div>

      {signedOut && !user && (
        <div className="notice-box notice-info" style={{ marginBottom: 0 }}>
          <CheckCircle2 size={17} />
          <span>You have been signed out successfully.</span>
        </div>
      )}

      <div className="card-hero">
        {user ? (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: "50%",
                  background: "linear-gradient(135deg, var(--accent) 0%, #a78bfa 100%)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 15,
                  fontWeight: 800,
                  color: "white",
                  flexShrink: 0,
                }}
              >
                {user.display_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
              </div>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 1 }}>
                  Welcome back, {user.display_name}!
                </h3>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {user.team_name} · signed in
                </span>
              </div>
            </div>

            <p style={{ color: "var(--text-secondary)", marginBottom: 22, lineHeight: 1.6, fontSize: 14 }}>
              Submit your standup update or catch up on your team's latest verified digests — all claims are extractive and auditable.
            </p>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate("/submit")}
              >
                Submit today's update <ArrowRight size={14} />
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
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <KeyRound size={22} color="var(--accent-bright)" />
              <h3 style={{ fontSize: 17, fontWeight: 700 }}>Sign in with your team code</h3>
            </div>
            <p style={{ color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 18, fontSize: 14 }}>
              Each team has one short code, shared by everyone on it. Enter the code and your name. No passwords, no accounts to create.
            </p>
            <button type="button" className="btn btn-primary" onClick={() => navigate("/login")}>
              Sign in <ArrowRight size={14} />
            </button>
          </div>
        )}
      </div>

      <div className="feature-grid">
        <div className="feature-card">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Quote size={15} color="var(--accent-bright)" />
            <div className="feature-label">Extractive Faithfulness</div>
          </div>
          <p className="feature-desc">
            Synthesized lines are verbatim source spans. The summarizer enforces zero-hallucination accuracy on blockers — every claim must trace back to the raw submission.
          </p>
        </div>

        <div className="feature-card">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <ShieldCheck size={15} color="var(--accent-bright)" />
            <div className="feature-label">Verifiable Citations</div>
          </div>
          <p className="feature-desc">
            Every claim links to its source item evidence with exact character-offset highlighting and tamper-evident audit chain entries.
          </p>
        </div>

        <div className="feature-card">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Zap size={15} color="var(--accent-bright)" />
            <div className="feature-label">Ecosystem Integration</div>
          </div>
          <p className="feature-desc">
            Full bidirectional support for Microsoft Teams bot ingestion, outbox-drained GitHub issue tracking, and privacy-respecting retention policies.
          </p>
        </div>
      </div>
    </div>
  );
}
