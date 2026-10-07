import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { ArrowLeft, ExternalLink, Quote, ShieldCheck, AlertCircle, User, Clock, Hash } from "lucide-react";

export default function EvidencePage({ itemId, navigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const loadEvidence = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getEvidence(itemId);
        if (isMounted) setData(res);
      } catch (err) {
        if (isMounted) setError(err.message || "Failed to load evidence.");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    loadEvidence();
    return () => { isMounted = false; };
  }, [itemId]);

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "50px 24px" }}>
        <span className="loading-spinner" style={{ width: 30, height: 30 }} />
        <p className="muted" style={{ marginTop: 16 }}>Verifying citation and audit trail…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="stagger">
        <h1>Evidence Not Found</h1>
        <div className="notice-box notice-warning">
          <AlertCircle size={17} />
          <span>{error}</span>
        </div>
        <button type="button" className="btn btn-outline" onClick={() => navigate("/digests")}>
          <ArrowLeft size={14} /> Back to digests
        </button>
      </div>
    );
  }

  const {
    expired, quote, before, after,
    member_name, captured_at, source_kind,
    permalink, permalink_reason, item,
  } = data;

  const formattedDate =
    new Date(captured_at).toISOString().replace("T", " ").substring(0, 16) + " UTC";

  return (
    <div className="stagger">
      <div>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ padding: "5px 10px", fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}
          onClick={() => navigate("/digests")}
        >
          <ArrowLeft size={13} /> Back to digests
        </button>
        <h1>Source Verification</h1>
      </div>

      {expired ? (
        <div>
          <p className="subtitle">This evidence has expired under the team's retention policy.</p>
          <div className="card card-elevated">
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 14 }}>
              The original text was purged under automated privacy policies. The quote below is what the digest cited at the time.
            </p>
          </div>
          <h2>Cited Quote</h2>
          <pre className="raw-display">
            <mark className="quote-highlight">{quote}</mark>
          </pre>
        </div>
      ) : (
        <div>
          {/* Meta pills */}
          <div className="evidence-meta" style={{ marginBottom: 18 }}>
            <div className="evidence-pill">
              <User size={12} />
              <strong>{member_name}</strong>
            </div>
            <div className="evidence-pill">
              <Clock size={12} />
              {formattedDate}
            </div>
            <div className="evidence-pill">
              <Hash size={12} />
              <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{source_kind}</code>
            </div>
          </div>

          <h2>As Submitted</h2>
          <pre className="raw-display">
            {before}
            <mark className="quote-highlight">{quote}</mark>
            {after}
          </pre>

          <p className="muted" style={{ marginTop: 12, fontSize: 12.5 }}>
            Highlighted span: characters{" "}
            <strong style={{ color: "var(--text-secondary)" }}>
              {item.span_start}–{item.span_end}
            </strong>{" "}
            of the stored submission.{" "}
            {permalink ? (
              <a
                href={permalink}
                target="_blank"
                rel="noreferrer"
                style={{
                  color: "var(--accent-bright)",
                  fontWeight: 600,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                Open in {source_kind} <ExternalLink size={11} />
              </a>
            ) : (
              <span>{permalink_reason}</span>
            )}
          </p>
        </div>
      )}

      <div className="notice-box notice-info" style={{ marginTop: 24 }}>
        <ShieldCheck size={17} />
        <span style={{ fontSize: 13 }}>
          Audit integrity: This view was cryptographically appended to the tamper-evident audit chain.
        </span>
      </div>

      <div style={{ marginTop: 20 }}>
        <button type="button" className="btn btn-outline" onClick={() => navigate("/digests")}>
          <ArrowLeft size={14} /> Back to digests
        </button>
      </div>
    </div>
  );
}
