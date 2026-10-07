import React, { useState, useEffect } from "react";
import { api, downloads } from "../api/client";
import {
  ExternalLink,
  Quote,
  FileText,
  ArrowLeft,
  AlertTriangle,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Download,
} from "lucide-react";

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
        if (isMounted) setData(res);
      } catch (err) {
        if (isMounted) setError(err.message || "Failed to load digest.");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    loadDigest();
    return () => { isMounted = false; };
  }, [digestId]);

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "50px 24px" }}>
        <span className="loading-spinner" style={{ width: 30, height: 30 }} />
        <p className="muted" style={{ marginTop: 16 }}>Loading digest…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="stagger">
        <h1>Unable to load digest</h1>
        <div className="notice-box notice-warning">
          <AlertTriangle size={17} />
          <span>{error}</span>
        </div>
        <button type="button" className="btn btn-outline" onClick={() => navigate("/digests")}>
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

  const totalClaims = sections.reduce((sum, s) => sum + s.claims.length, 0);

  return (
    <div className="stagger">
      {/* Back */}
      <div>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ padding: "5px 10px", fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}
          onClick={() => navigate("/digests")}
        >
          <ArrowLeft size={13} /> Digests
        </button>

        <h1>{team_name}</h1>
        <p className="subtitle">
          The team's daily summary for {cycle.local_date}, built from everyone's updates
          &middot; built {generatedTime} UTC
        </p>

        {/* Meta chips */}
        <div className="stat-row" style={{ marginBottom: 24 }}>
          <div className="stat-chip">
            <Quote size={12} />
            <strong>{totalClaims}</strong> claims
          </div>
          <div className="stat-chip">
            <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {digest.summarizer_name} {digest.summarizer_version}
            </code>
          </div>
          <div className="stat-chip">
            <ShieldCheck size={12} />
            Audit-chained
          </div>
        </div>
      </div>

      {/* Sections */}
      {sections.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "36px 24px" }}>
          <p style={{ margin: 0, color: "var(--text-secondary)" }}>
            No updates were submitted for this cycle.
          </p>
        </div>
      ) : (
        sections.map((section) => (
          <div key={section.kind}>
            <h2>{section.title}</h2>
            {section.hint && <p className="section-hint">{section.hint}</p>}
            <div className="card card-elevated" style={{ padding: "6px 22px" }}>
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

      {/* Warnings */}
      {digest.withheld_count > 0 && (
        <div className="notice-box notice-warning">
          <AlertTriangle size={17} />
          <span>
            {digest.withheld_count} item(s) withheld — failed source verification, or removed by their author.
          </span>
        </div>
      )}

      {digest.truncated_count > 0 && (
        <div className="notice-box notice-warning">
          <AlertTriangle size={17} />
          <span>
            {digest.truncated_count} more item(s) not shown — a section reached its line limit.
          </span>
        </div>
      )}

      {/* Footer */}
      <div
        style={{
          marginTop: 28,
          paddingTop: 18,
          borderTop: "1px solid var(--border-subtle)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div className="notice-box notice-info" style={{ margin: 0, flex: 1, minWidth: 220 }}>
          <ShieldCheck size={16} />
          <span style={{ fontSize: 13 }}>
            Every line above is a verbatim quote, verified against its stored source.
          </span>
        </div>
        <a
          className="btn btn-outline"
          style={{ fontSize: 13, padding: "7px 14px", flexShrink: 0 }}
          href={downloads.digestMarkdown(digest.id)}
          download
        >
          <Download size={13} /> Markdown
        </a>
        <a
          className="btn btn-outline"
          style={{ fontSize: 13, padding: "7px 14px", flexShrink: 0 }}
          href={downloads.digestCsv(digest.id)}
          download
        >
          <Download size={13} /> Spreadsheet (CSV)
        </a>
        <button
          type="button"
          className="btn btn-outline"
          style={{ fontSize: 13, padding: "7px 14px", flexShrink: 0 }}
          onClick={() => setShowMarkdown(!showMarkdown)}
        >
          <FileText size={13} />
          {showMarkdown ? (
            <><ChevronUp size={12} /> Hide Markdown</>
          ) : (
            <><ChevronDown size={12} /> View Markdown</>
          )}
        </button>
      </div>

      {showMarkdown && (
        <div style={{ marginTop: 14, animation: "fadeUp 0.3s ease forwards" }}>
          <pre className="raw-display" style={{ maxHeight: 320, overflowY: "auto" }}>
            {digest.body_md}
          </pre>
        </div>
      )}
    </div>
  );
}
