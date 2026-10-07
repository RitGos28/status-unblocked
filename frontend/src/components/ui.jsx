import React from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

/* Small shared pieces, so every page states the same things the same way. */

export function PageHeader({ title, lead, actions }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {lead && <p className="lead">{lead}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}

export function SignInRequired({ navigate, what = "continue" }) {
  return (
    <div className="narrow">
      <div className="empty">
        <div className="empty-title">Sign in to {what}</div>
        <p>Use your team's code and the name your team lists you under.</p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/login")}>
          Sign in
        </button>
      </div>
    </div>
  );
}

export function Loading({ label = "Loading…" }) {
  return (
    <div className="loading">
      <span className="loading-spinner" />
      {label}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="empty">
      {Icon && <Icon size={22} />}
      {title && <div className="empty-title">{title}</div>}
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

const NOTICE_ICONS = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
};

export function Notice({ tone = "info", children, onDismiss }) {
  const Icon = NOTICE_ICONS[tone] || Info;
  return (
    <div className={`notice notice-${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon size={15} />
      <span>{children}</span>
      {onDismiss && (
        <button type="button" className="btn btn-ghost btn-sm notice-dismiss" onClick={onDismiss}>
          Dismiss
        </button>
      )}
    </div>
  );
}

export function Avatar({ name, size }) {
  const initials = (name || "?")
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return <span className={`avatar ${size === "lg" ? "lg" : ""}`}>{initials}</span>;
}

export function Badge({ tone, children }) {
  return <span className={`badge ${tone ? `badge-${tone}` : ""}`}>{children}</span>;
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={active === t.id}
          className={`tab ${active === t.id ? "active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {t.count != null && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented({ options, value, onChange }) {
  return (
    <div className="segmented">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={value === o.value ? "active" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Stat({ label, value, tone }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone || ""}`}>{value}</div>
    </div>
  );
}

// "2026-10-06T09:30:00+00:00" -> "2026-10-06 09:30"
export const whenUtc = (iso) => (iso ? iso.slice(0, 16).replace("T", " ") : "");

export const STATUS_LABELS = {
  pending: "Pending",
  in_progress: "In progress",
  completed: "Completed",
  blocked: "Blocked",
};

export const STATUS_TONES = {
  pending: "neutral",
  in_progress: "accent",
  completed: "success",
  blocked: "danger",
};

export const PRIORITY_LABELS = { low: "Low", medium: "Medium", high: "High", urgent: "Urgent" };
export const PRIORITY_TONES = { low: "neutral", medium: "neutral", high: "warning", urgent: "danger" };

export function StatusBadge({ status }) {
  return <Badge tone={STATUS_TONES[status] || "neutral"}>{STATUS_LABELS[status] || status}</Badge>;
}

export function PriorityBadge({ priority }) {
  if (!priority || priority === "medium") return null;
  return (
    <Badge tone={PRIORITY_TONES[priority] || "neutral"}>
      {PRIORITY_LABELS[priority] || priority}
    </Badge>
  );
}

export function StatusSelect({ value, onChange, disabled, size = "sm" }) {
  return (
    <select
      className={`status-select ${size === "md" ? "" : ""}`}
      data-status={value}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      aria-label="Status"
    >
      {Object.entries(STATUS_LABELS).map(([k, v]) => (
        <option key={k} value={k}>
          {v}
        </option>
      ))}
    </select>
  );
}
