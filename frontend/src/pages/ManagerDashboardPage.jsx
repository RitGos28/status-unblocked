import React, { useState, useEffect, useCallback } from "react";
import { managerApi } from "../api/client";
import {
  AlertCircle,
  AlertTriangle,
  BarChart3,
  BookOpen,
  Briefcase,
  CheckCircle2,
  Copy,
  Check,
  ExternalLink,
  KeyRound,
  LogOut,
  Quote,
  RefreshCw,
  UserPlus,
  Users,
} from "lucide-react";

const PERIODS = [7, 14, 30];
const TABS = [
  { id: "summary", label: "Summary", icon: BarChart3 },
  { id: "days", label: "Digests", icon: BookOpen },
  { id: "members", label: "Members", icon: Users },
];

export default function ManagerDashboardPage({ navigate }) {
  const [me, setMe] = useState(null);
  const [teams, setTeams] = useState([]);
  const [teamId, setTeamId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [summary, setSummary] = useState(null);
  const [days, setDays] = useState(7);
  const [tab, setTab] = useState("summary");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [buildingId, setBuildingId] = useState(null);

  // Who is signed in, and the teams to choose from.
  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      try {
        const who = await managerApi.me();
        if (!isMounted) return;
        if (!who.authenticated) {
          navigate("/manager/login");
          return;
        }
        setMe(who);
        const res = await managerApi.listTeams();
        if (!isMounted) return;
        setTeams(res.teams);
        if (res.teams.length && !teamId) setTeamId(res.teams[0].id);
      } catch (err) {
        if (isMounted) setError(err.message || "Could not load the manager portal.");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reloadTeam = useCallback(async () => {
    if (!teamId) return;
    try {
      setError(null);
      const [d, s] = await Promise.all([
        managerApi.getTeam(teamId),
        managerApi.getSummary(teamId, days),
      ]);
      setDetail(d);
      setSummary(s);
    } catch (err) {
      setError(err.message || "Could not load the team.");
    }
  }, [teamId, days]);

  useEffect(() => {
    reloadTeam();
  }, [reloadTeam]);

  const handleLogout = async () => {
    try {
      await managerApi.logout();
    } finally {
      navigate("/manager/login");
    }
  };

  const handleBuild = async (cycleId) => {
    setBuildingId(cycleId);
    setError(null);
    try {
      await managerApi.buildDigest(cycleId);
      await reloadTeam();
    } catch (err) {
      setError(err.message || "Failed to build the digest.");
    } finally {
      setBuildingId(null);
    }
  };

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "50px 24px" }}>
        <span className="loading-spinner" style={{ width: 30, height: 30 }} />
        <p className="muted" style={{ marginTop: 16 }}>Loading the manager portal…</p>
      </div>
    );
  }

  const team = detail ? detail.team : teams.find((t) => t.id === teamId);

  return (
    <div className="stagger">
      <div className="page-header">
        <div>
          <h1>Manager portal</h1>
          <p className="subtitle" style={{ marginBottom: 0 }}>
            One team at a time: its members, its digests, and what they add up to over a period.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div className="user-pill">
            <Briefcase size={13} />
            <span style={{ color: "var(--text-secondary)", fontWeight: 500, fontSize: 13 }}>
              {me ? me.username : "manager"}
            </span>
          </div>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={handleLogout}
            style={{ padding: "6px 10px", fontSize: 13, gap: 5 }}
            title="Sign out of the manager portal"
          >
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </div>

      {error && (
        <div className="notice-box notice-warning">
          <AlertTriangle size={17} />
          <span>{error}</span>
        </div>
      )}

      {teams.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "36px 24px" }}>
          <p style={{ margin: 0, color: "var(--text-secondary)" }}>
            There are no teams yet. Seed the demo or create a team from the backend.
          </p>
        </div>
      ) : (
        <>
          {/* Team picker */}
          <div className="stat-row" style={{ marginBottom: 6 }}>
            {teams.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`btn ${t.id === teamId ? "btn-primary" : "btn-outline"}`}
                style={{ fontSize: 13, padding: "7px 14px" }}
                onClick={() => setTeamId(t.id)}
              >
                <Users size={13} /> {t.name}
                <span style={{ opacity: 0.7 }}>· {t.member_count}</span>
              </button>
            ))}
          </div>

          {/* Tabs */}
          <nav className="nav-links" style={{ marginBottom: 4 }}>
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                className={`nav-link ${tab === id ? "active" : ""}`}
                onClick={() => setTab(id)}
              >
                <Icon size={14} /> {label}
              </button>
            ))}
          </nav>

          {!detail || !summary ? (
            <div style={{ textAlign: "center", padding: 40 }}>
              <span className="loading-spinner" />
            </div>
          ) : (
            <>
              {tab === "summary" && (
                <SummaryTab
                  summary={summary}
                  days={days}
                  setDays={setDays}
                  navigate={navigate}
                  onBuild={handleBuild}
                  buildingId={buildingId}
                />
              )}
              {tab === "days" && (
                <DaysTab
                  team={team}
                  days={detail.days}
                  navigate={navigate}
                  onBuild={handleBuild}
                  buildingId={buildingId}
                  onRefresh={reloadTeam}
                />
              )}
              {tab === "members" && (
                <MembersTab team={team} members={detail.members} onAdded={reloadTeam} />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

function SummaryTab({ summary, days, setDays, navigate, onBuild, buildingId }) {
  const { period, totals, by_day: byDay, blockers, by_member: byMember } = summary;

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 10,
        }}
      >
        <div>
          <h2 style={{ marginBottom: 2 }}>
            {summary.team.name}: {period.from} to {period.to}
          </h2>
          <p className="section-hint">
            Read from the digests, so every line is a verified quote. Nothing here is scored
            or ranked.
          </p>
        </div>
        <div className="stat-row">
          {PERIODS.map((n) => (
            <button
              key={n}
              type="button"
              className={`btn ${n === days ? "btn-primary" : "btn-outline"}`}
              style={{ fontSize: 12, padding: "5px 12px" }}
              onClick={() => setDays(n)}
            >
              {n} days
            </button>
          ))}
        </div>
      </div>

      <div className="stat-row" style={{ marginBottom: 22 }}>
        <div className="stat-chip">
          <strong>{totals.days_with_updates}</strong> days with updates
        </div>
        <div className="stat-chip">
          <strong>{totals.digests_built}</strong> digests built
        </div>
        <div className="stat-chip">
          <strong>{totals.updates}</strong> updates
        </div>
        <div className="stat-chip">
          <AlertCircle size={12} />
          <strong>{totals.open_blockers}</strong> open blockers
        </div>
      </div>

      <h2>Open blockers</h2>
      <p className="section-hint">
        Blockers the most recent digest still reports, with how many days each has been raised.
      </p>
      {blockers.open.length === 0 ? (
        <div className="card" style={{ padding: "18px 22px" }}>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 14 }}>
            <CheckCircle2 size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
            No open blockers in this period.
          </p>
        </div>
      ) : (
        <BlockerList blockers={blockers.open} navigate={navigate} />
      )}

      {blockers.earlier.length > 0 && (
        <>
          <h2>Earlier blockers</h2>
          <p className="section-hint">
            Raised in this period but not in the latest digest: resolved, or not repeated.
          </p>
          <BlockerList blockers={blockers.earlier} navigate={navigate} />
        </>
      )}

      <h2>Day by day</h2>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Day</th>
              <th>Updates</th>
              <th>Blockers</th>
              <th>Progress</th>
              <th>Plans</th>
              <th>Digest</th>
            </tr>
          </thead>
          <tbody>
            {byDay.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  No standup days in this period.
                </td>
              </tr>
            )}
            {[...byDay].reverse().map((d) => (
              <tr key={d.cycle_id}>
                <td>
                  <code className="code-inline">{d.local_date}</code>
                </td>
                <td>{d.update_count}</td>
                <td>{d.digest_id ? d.blockers : "–"}</td>
                <td>{d.digest_id ? d.progress : "–"}</td>
                <td>{d.digest_id ? d.plan : "–"}</td>
                <td>
                  {d.digest_id ? (
                    <button
                      type="button"
                      className="btn btn-outline"
                      style={{ fontSize: 12, padding: "5px 10px" }}
                      onClick={() => navigate(`/manager/digest/${d.digest_id}`)}
                    >
                      <BookOpen size={12} /> Read
                      {d.withheld > 0 ? ` · ${d.withheld} withheld` : ""}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-outline"
                      style={{ fontSize: 12, padding: "5px 10px" }}
                      disabled={buildingId === d.cycle_id || d.update_count === 0}
                      onClick={() => onBuild(d.cycle_id)}
                    >
                      <RefreshCw size={12} />
                      {buildingId === d.cycle_id ? "Building…" : "Build digest"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>By member</h2>
      <p className="section-hint">
        Each person's digest lines over the period, in their own words. Only people with a
        digested update appear.
      </p>
      {byMember.length === 0 ? (
        <div className="card" style={{ padding: "18px 22px" }}>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 14 }}>
            No digest lines in this period yet. Build a digest for a day with updates.
          </p>
        </div>
      ) : (
        byMember.map((person) => (
          <div key={person.member_id} style={{ marginBottom: 18 }}>
            <h3 style={{ fontSize: 15, marginBottom: 8 }}>{person.display_name}</h3>
            <div className="card card-elevated" style={{ padding: "6px 22px" }}>
              {person.lines.map((line) => (
                <div key={line.claim_id} className="claim-row">
                  <span className="claim-who">
                    <code className="code-inline" style={{ fontSize: 11 }}>
                      {line.day}
                    </code>
                  </span>
                  <div className="claim-content">
                    <span className="claim-text">{line.text}</span>
                    <span className="claim-why">
                      {line.section}
                      {line.rule_explanation ? ` · ${line.rule_explanation}` : ""}
                    </span>
                  </div>
                  <div className="claim-badges">
                    {(line.citations || []).map((c, i) => (
                      <button
                        key={i}
                        type="button"
                        className="badge-cite"
                        title="See the exact words this came from"
                        onClick={() => navigate(`/manager/evidence/${c.source_id}`)}
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
    </div>
  );
}

function BlockerList({ blockers, navigate }) {
  return (
    <div className="card card-elevated" style={{ padding: "6px 22px" }}>
      {blockers.map((b) => (
        <div key={b.claim_id} className="claim-row">
          <span className="claim-who">{b.member_name}</span>
          <div className="claim-content">
            <span className="claim-text">{b.text}</span>
            <span className="claim-why">
              {b.days_reported === 1
                ? `Reported on ${b.last_day}`
                : `Reported on ${b.days_reported} days, ${b.first_day} to ${b.last_day}`}
            </span>
          </div>
          <div className="claim-badges">
            {b.issue && (
              <a
                className="badge-issue"
                href={b.issue.url}
                target="_blank"
                rel="noreferrer"
                title="Tracked as a GitHub issue"
              >
                #{b.issue.number} <ExternalLink size={10} />
              </a>
            )}
            <button
              type="button"
              className="badge-cite"
              title="Open the digest this came from"
              onClick={() => navigate(`/manager/digest/${b.digest_id}`)}
            >
              <BookOpen size={10} /> digest
            </button>
            {(b.citations || []).map((c, i) => (
              <button
                key={i}
                type="button"
                className="badge-cite"
                title="See the exact words this came from"
                onClick={() => navigate(`/manager/evidence/${c.source_id}`)}
              >
                <Quote size={10} /> source
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function DaysTab({ team, days, navigate, onBuild, buildingId, onRefresh }) {
  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 10,
        }}
      >
        <div>
          <h2 style={{ marginBottom: 2 }}>{team.name}: standup days</h2>
          <p className="section-hint">
            Every day the team filed updates, with its digest. Build is the same build a member
            can press; the scheduler still announces the digest at the cutoff, once.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-outline"
          onClick={onRefresh}
          style={{ fontSize: 13, padding: "7px 14px" }}
        >
          <RefreshCw size={13} /> Refresh
        </button>
      </div>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Day</th>
              <th>State</th>
              <th>Updates</th>
              <th>Digest</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {days.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No updates have been filed for this team yet.
                </td>
              </tr>
            )}
            {days.map((row) => (
              <tr key={row.cycle.id}>
                <td>
                  <code className="code-inline">{row.cycle.local_date}</code>
                </td>
                <td>
                  <span className={`badge-state ${row.cycle.state === "open" ? "open" : "closed"}`}>
                    {row.cycle.state}
                  </span>
                </td>
                <td>{row.update_count}</td>
                <td>
                  {row.digest ? (
                    <span className="muted">
                      built {row.digest.generated_at.slice(0, 16).replace("T", " ")} UTC
                    </span>
                  ) : (
                    <span className="muted">not built</span>
                  )}
                </td>
                <td>
                  <div className="table-actions">
                    {row.digest && (
                      <button
                        type="button"
                        className="btn btn-primary"
                        style={{ fontSize: 12, padding: "5px 10px" }}
                        onClick={() => navigate(`/manager/digest/${row.digest.id}`)}
                      >
                        <BookOpen size={12} /> Read digest
                      </button>
                    )}
                    {row.final ? (
                      <span className="muted">Updates removed by retention</span>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-outline"
                        style={{ fontSize: 12, padding: "5px 10px" }}
                        disabled={buildingId === row.cycle.id || row.update_count === 0}
                        onClick={() => onBuild(row.cycle.id)}
                      >
                        <RefreshCw size={12} />
                        {buildingId === row.cycle.id
                          ? "Building…"
                          : row.digest
                            ? "Rebuild"
                            : "Build digest"}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MembersTab({ team, members, onAdded }) {
  const [name, setName] = useState("");
  const [tz, setTz] = useState("UTC");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [added, setAdded] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleAdd = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setAdded(null);
    try {
      const res = await managerApi.addMember(team.id, name, tz);
      setAdded(res.member);
      setName("");
      await onAdded();
    } catch (err) {
      setError(err.message || "Could not add the member.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(team.join_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div>
      <h2>Add a member to {team.name}</h2>
      <p className="section-hint">
        They sign in with the team's code and this exact name, and appear on every member's Team
        page straight away.
      </p>
      <div className="card card-elevated">
        {error && (
          <div className="notice-box notice-warning" style={{ marginBottom: 16 }}>
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}
        {added && (
          <div className="notice-box notice-success" style={{ marginBottom: 16 }}>
            <CheckCircle2 size={16} />
            <span>
              {added.display_name} is on {team.name}. Give them the team code below and the name
              exactly as written.
            </span>
          </div>
        )}
        <form onSubmit={handleAdd}>
          <div className="form-group">
            <label htmlFor="new_member_name">
              <span>Name</span>
              <span className="hint">as the team will list them</span>
            </label>
            <input
              id="new_member_name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Erin Novak"
              autoComplete="off"
              disabled={submitting}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="new_member_tz">
              <span>Time zone</span>
              <span className="hint">an IANA name, e.g. Asia/Kolkata</span>
            </label>
            <input
              id="new_member_tz"
              type="text"
              value={tz}
              onChange={(e) => setTz(e.target.value)}
              placeholder="UTC"
              autoComplete="off"
              spellCheck={false}
              disabled={submitting}
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || !name.trim()}
          >
            <UserPlus size={14} /> {submitting ? "Adding…" : "Add member"}
          </button>
        </form>
      </div>

      <h2>Team code</h2>
      <div className="card card-elevated">
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <KeyRound size={18} color="var(--accent-bright)" />
          <code
            className="code-inline"
            style={{ fontSize: 22, letterSpacing: "0.08em", padding: "6px 12px" }}
          >
            {team.join_code}
          </code>
          <button
            type="button"
            className="btn btn-outline"
            onClick={handleCopy}
            style={{ fontSize: 13, padding: "7px 14px" }}
          >
            {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <p className="muted" style={{ marginTop: 14, marginBottom: 0, fontSize: 13 }}>
          The same code every member sees on their Team page. A new member signs in with it and
          their name.
        </p>
      </div>

      <h2>Members ({members.length})</h2>
      <div className="card card-elevated" style={{ padding: "6px 22px" }}>
        {members.map((m) => (
          <div key={m.id} className="claim-row">
            <span className="claim-who">{m.display_name}</span>
            <div className="claim-content">
              <span className="claim-text muted" style={{ fontSize: 13 }}>
                {m.tz}
                {m.teams_linked ? " · Teams account linked" : ""}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
