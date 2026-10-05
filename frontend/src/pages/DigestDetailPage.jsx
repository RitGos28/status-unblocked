import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { ExternalLink, Quote, FileText, ArrowLeft, AlertTriangle } from "lucide-react";

export default function DigestDetailPage({ digestId, navigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showMarkdown, setShowMarkdown] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const loadDigest = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getDigest(digestId);
        if (isMounted) {
          setData(res);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || "Failed to load digest.");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadDigest();
    return () => {
      isMounted = false;
    };
  }, [digestId]);

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: 40 }}>
        <span className="loading-spinner" style={{ width: 28, height: 28 }} />
        <p className="muted" style={{ marginTop: 14 }}>Loading digest...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <h1>Unable to load digest</h1>
        <div className="notice-box notice-warning">
          <AlertTriangle size={18} />
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

  const { digest, cycle, team_name, sections } = data;
  const generatedTime = new Date(digest.generated_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ padding: "4px 8px", fontSize: 13, color: "var(--text-muted)" }}
          onClick={() => navigate("/digests")}
        >
          <ArrowLeft size={14} /> Digests
        </button>
      </div>

      <h1>{team_name}</h1>
      <p className="subtitle">
        Standup {cycle.local_date} &middot; built {generatedTime} UTC by{" "}
        <code className="code-inline">
          {digest.summarizer_name} {digest.summarizer_version}
        </code>
      </p>

      {sections.length === 0 ? (
        <div className="card">
          <p style={{ margin: 0 }}>No updates were submitted for this cycle.</p>
        </div>
      ) : (
        sections.map((section) => (
          <div key={section.kind} style={{ marginBottom: 24 }}>
            <h2>{section.title}</h2>
            <div className="card card-elevated" style={{ padding: "10px 20px" }}>
              {section.claims.map((claim) => (
                <div key={claim.id} className="claim-row">
                  <span className="claim-who">{claim.member_name}</span>
                  <div className="claim-content">
                    <span className="claim-text">{claim.text}</span>
                    {claim.rule_explanation && (
                      <span className="claim-why">{claim.rule_explanation}</span>
                    )}
                  </div>
                  <div className="claim-badges">
                    {claim.issue && (
                      <a
                        className="badge-issue"
                        href={claim.issue.url}
                        target="_blank"
                        rel="noreferrer"
                        title="Tracked as a GitHub issue"
                      >
                        #{claim.issue.number}
                        {claim.issue.age_days ? ` · ${claim.issue.age_days}d` : ""}
                        <ExternalLink size={10} />
                      </a>
                    )}
                    {claim.citations &&
                      claim.citations.map((c, i) => (
                        <button
                          key={i}
                          type="button"
                          className="badge-cite"
                          title="See the exact words this came from"
                          onClick={() => navigate(`/evidence/${c.source_id}`)}
                        >
                          <Quote size={10} /> source
                        </button>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}

      {digest.withheld_count > 0 && (
        <div className="notice-box notice-warning">
          <AlertTriangle size={18} />
          <span>
            {digest.withheld_count} item(s) withheld: failed source verification, or removed by their author.
          </span>
        </div>
      )}

      {digest.truncated_count > 0 && (
        <div className="notice-box notice-warning">
          <AlertTriangle size={18} />
          <span>
            {digest.truncated_count} more item(s) not shown: a section reached its line limit.
          </span>
        </div>
      )}

      <div style={{ marginTop: 28, paddingTop: 18, borderTop: "1px solid var(--border-subtle)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <p className="muted" style={{ margin: 0 }}>
          Every line above is a verbatim quote, checked against its stored source before this page was written.
        </p>
        <button
          type="button"
          className="btn btn-outline"
          style={{ fontSize: 13, padding: "6px 12px" }}
          onClick={() => setShowMarkdown(!showMarkdown)}
        >
          <FileText size={13} /> {showMarkdown ? "Hide Markdown" : "View Markdown"}
        </button>
      </div>

      {showMarkdown && (
        <div style={{ marginTop: 16 }}>
          <pre className="raw-display" style={{ maxHeight: 300, overflowY: "auto" }}>
            {digest.body_md}
          </pre>
        </div>
      )}
    </div>
  );
}
