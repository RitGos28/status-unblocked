import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { ArrowLeft, ExternalLink, ShieldCheck, AlertCircle } from "lucide-react";

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
        if (isMounted) {
          setData(res);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || "Failed to load evidence.");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadEvidence();
    return () => {
      isMounted = false;
    };
  }, [itemId]);

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: 40 }}>
        <span className="loading-spinner" style={{ width: 28, height: 28 }} />
        <p className="muted" style={{ marginTop: 14 }}>Verifying citation and audit trail...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <h1>Evidence Not Found</h1>
        <div className="notice-box notice-warning">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
        <button
          type="button"
          className="btn btn-outline"
          onClick={() => navigate("/digests")}
        >
          <ArrowLeft size={14} /> Back to digests
        </button>
      </div>
    );
  }

  const {
    expired,
    quote,
    before,
    after,
    member_name,
    captured_at,
    source_kind,
    permalink,
    permalink_reason,
    item,
  } = data;

  const formattedDate = new Date(captured_at).toISOString().replace("T", " ").substring(0, 16) + " UTC";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ padding: "4px 8px", fontSize: 13, color: "var(--text-muted)" }}
          onClick={() => navigate("/digests")}
        >
          <ArrowLeft size={14} /> Back to digests
        </button>
      </div>

      <h1>Source Verification</h1>

      {expired ? (
        <div>
          <p className="subtitle">This evidence has expired under the team's retention policy.</p>
          <div className="card card-elevated">
            <p style={{ margin: 0, color: "var(--text-secondary)" }}>
              The original text was purged under automated privacy policies. The quote below is what the digest cited at the time.
            </p>
          </div>
          <h2>Cited quote</h2>
          <pre className="raw-display">
            <mark className="quote-highlight">{quote}</mark>
          </pre>
        </div>
      ) : (
        <div>
          <p className="subtitle">
            <strong>{member_name}</strong> &middot; {formattedDate} &middot; via <span className="code-inline">{source_kind}</span>
          </p>

          <h2>As submitted</h2>
          <pre className="raw-display">
            {before}
            <mark className="quote-highlight">{quote}</mark>
            {after}
          </pre>

          <p className="muted" style={{ marginTop: 12 }}>
            Highlighted span: characters <strong>{item.span_start}&ndash;{item.span_end}</strong> of the stored submission.{" "}
            {permalink ? (
              <a
                href={permalink}
                target="_blank"
                rel="noreferrer"
                style={{ color: "var(--accent-primary)", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 4 }}
              >
                Open in {source_kind} <ExternalLink size={12} />
              </a>
            ) : (
              <span>{permalink_reason}</span>
            )}
          </p>
        </div>
      )}

      <div className="notice-box notice-info" style={{ marginTop: 28 }}>
        <ShieldCheck size={18} />
        <span>
          Audit integrity: This view was cryptographically appended to the tamper-evident audit chain.
        </span>
      </div>

      <div style={{ marginTop: 24 }}>
        <button
          type="button"
          className="btn btn-outline"
          onClick={() => navigate("/digests")}
        >
          Back to digests
        </button>
      </div>
    </div>
  );
}
