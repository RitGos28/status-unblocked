import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Briefcase, Calendar, Check, Copy, Plus, RefreshCw, Trash2, X } from "lucide-react";
import {
  Avatar,
  EmptyState,
  Loading,
  Notice,
  PriorityBadge,
  Segmented,
  SignInRequired,
  Stat,
  StatusSelect,
  Tabs,
  STATUS_LABELS,
} from "../components/ui";

const STATUS_FILTERS = ["all", "pending", "in_progress", "completed", "blocked"];

const TAB_IDS = ["tasks", "summary", "members", "teamcode"];

export default function ManagerPage({ navigate, searchParams }) {
  const { user } = useAuth();
  const [tasks, setTasks] = useState([]);
  const [teamInfo, setTeamInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  // ?tab=summary opens that tab directly, so a tab can be linked to.
  const requested = searchParams ? searchParams.get("tab") : null;
  const [activeTab, setActiveTab] = useState(TAB_IDS.includes(requested) ? requested : "tasks");
  const [statusFilter, setStatusFilter] = useState("all");

  // null = checking, false = locked, true = unlocked
  const [isManager, setIsManager] = useState(null);
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authenticating, setAuthenticating] = useState(false);
  const [authError, setAuthError] = useState(null);

  const [summaryScope, setSummaryScope] = useState("daily");
  const [summaryData, setSummaryData] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [summaryCopied, setSummaryCopied] = useState(false);

  const [showTaskModal, setShowTaskModal] = useState(false);
  const [savingTask, setSavingTask] = useState(false);

  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberTz, setNewMemberTz] = useState("Asia/Kolkata");
  const [savingMember, setSavingMember] = useState(false);

  const [customCodeInput, setCustomCodeInput] = useState("");
  const [savingCode, setSavingCode] = useState(false);
  const [codeCopied, setCodeCopied] = useState(false);

  const [feedback, setFeedback] = useState(null); // { tone, message }

  const checkManagerAuth = async () => {
    try {
      const res = await api.getManagerStatus();
      if (res && res.is_manager) {
        setIsManager(true);
        loadData();
      } else {
        setIsManager(false);
        setLoading(false);
      }
    } catch {
      setIsManager(false);
      setLoading(false);
    }
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const [tasksRes, teamRes] = await Promise.all([api.getManagerTasks(), api.getTeam()]);
      setTasks(tasksRes.tasks || []);
      setTeamInfo(teamRes.team || null);
    } catch (err) {
      if (err.status === 401) setIsManager(false);
      else setFeedback({ tone: "danger", message: err.message || "Could not load the dashboard." });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) checkManagerAuth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  useEffect(() => {
    if (activeTab === "summary" && user && isManager) loadSummary(summaryScope);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, summaryScope, isManager]);

  const loadSummary = async (scope) => {
    try {
      setLoadingSummary(true);
      const res = await api.getManagerSummary(scope);
      setSummaryData(res);
    } catch (err) {
      if (err.status === 401) setIsManager(false);
      else setFeedback({ tone: "danger", message: err.message || "Could not build the summary." });
    } finally {
      setLoadingSummary(false);
    }
  };

  const handleManagerLogin = async (e) => {
    e.preventDefault();
    if (!authUsername.trim() || !authPassword) return;
    try {
      setAuthenticating(true);
      setAuthError(null);
      const res = await api.loginManager(authUsername.trim(), authPassword);
      if (res.is_manager) {
        setIsManager(true);
        setAuthUsername("");
        setAuthPassword("");
        loadData();
      }
    } catch (err) {
      setAuthError(err.message || "That username and password do not match.");
    } finally {
      setAuthenticating(false);
    }
  };

  const handleLockManager = async () => {
    try {
      await api.lockManager();
    } catch {
      // Locking locally is enough.
    } finally {
      setIsManager(false);
      setTasks([]);
      setSummaryData(null);
    }
  };

  const handleCreateTask = async (draft) => {
    try {
      setSavingTask(true);
      const res = await api.createManagerTask({
        title: draft.title.trim(),
        description: draft.description.trim(),
        assigned_to_id: draft.assignee || null,
        priority: draft.priority,
        due_date: draft.dueDate || null,
      });
      setTasks((prev) => [res.task, ...prev]);
      setShowTaskModal(false);
      setFeedback({ tone: "success", message: `Task "${res.task.title}" created.` });
    } catch (err) {
      setFeedback({ tone: "danger", message: err.message || "Could not create the task." });
    } finally {
      setSavingTask(false);
    }
  };

  const handleUpdateStatus = async (taskId, newStatus) => {
    try {
      const res = await api.updateManagerTask(taskId, { status: newStatus });
      setTasks((prev) => prev.map((t) => (t.id === taskId ? res.task : t)));
    } catch (err) {
      setFeedback({ tone: "danger", message: err.message || "Could not update the task." });
    }
  };

  const handleDeleteTask = async (taskId) => {
    if (!window.confirm("Delete this task?")) return;
    try {
      await api.deleteManagerTask(taskId);
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
      setFeedback({ tone: "success", message: "Task deleted." });
    } catch (err) {
      setFeedback({ tone: "danger", message: err.message || "Could not delete the task." });
    }
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!newMemberName.trim()) return;
    try {
      setSavingMember(true);
      const res = await api.addManagerMember({
        name: newMemberName.trim(),
        tz: newMemberTz.trim() || "UTC",
      });
      setNewMemberName("");
      const teamRes = await api.getTeam();
      setTeamInfo(teamRes.team || null);
      setFeedback({
        tone: "success",
        message: `${res.member.display_name} is on the team. They sign in with the team code and that name.`,
      });
    } catch (err) {
      setFeedback({ tone: "danger", message: err.message || "Could not add the member." });
    } finally {
      setSavingMember(false);
    }
  };

  const handleUpdateTeamCode = async (customCode) => {
    try {
      setSavingCode(true);
      const res = await api.updateTeamCode(customCode);
      setTeamInfo((prev) => (prev ? { ...prev, join_code: res.join_code } : prev));
      setCustomCodeInput("");
      setFeedback({ tone: "success", message: `The team code is now ${res.join_code}.` });
    } catch (err) {
      setFeedback({ tone: "danger", message: err.message || "Could not change the team code." });
    } finally {
      setSavingCode(false);
    }
  };

  const copy = (text, setCopiedFn) => {
    navigator.clipboard.writeText(text);
    setCopiedFn(true);
    setTimeout(() => setCopiedFn(false), 2000);
  };

  const copySummaryMarkdown = () => {
    if (!summaryData) return;
    const s = summaryData;
    const who = (t) => (t.assigned_to_name ? ` (${t.assigned_to_name})` : "");
    const lines = [
      `# ${s.headline}`,
      `Generated: ${new Date(s.generated_at).toLocaleString()}`,
      "",
      "## Tasks",
      `- Total: ${s.stats.total_tasks}`,
      `- Completed: ${s.stats.completed} (${s.stats.completion_rate}%)`,
      `- In progress: ${s.stats.in_progress}`,
      `- Blocked: ${s.stats.blocked}`,
      `- Standup updates: ${s.stats.updates_submitted}`,
      "",
      "## Completed",
      ...(s.completed_tasks.length ? s.completed_tasks.map((t) => `- [x] ${t.title}${who(t)}`) : ["- None"]),
      "",
      "## In progress",
      ...(s.in_progress_tasks.length ? s.in_progress_tasks.map((t) => `- [ ] ${t.title}${who(t)}`) : ["- None"]),
      "",
      "## Blockers",
      ...(s.standup_blockers.length ? s.standup_blockers.map((b) => `- ${b.member_name}: ${b.blocker}`) : ["- None reported"]),
      "",
      "## By member",
      ...s.member_breakdowns.map(
        (m) =>
          `### ${m.member_name}\n- Tasks: ${m.tasks_completed}/${m.tasks_total} completed\n- Progress: ${
            m.latest_progress || "No update"
          }\n- Plan: ${m.latest_plan || "None"}`
      ),
    ];
    copy(lines.join("\n"), setSummaryCopied);
  };

  if (!user) return <SignInRequired navigate={navigate} what="open the manager dashboard" />;

  if (isManager === null || (loading && tasks.length === 0 && !authError && isManager !== false)) {
    return <Loading label="Checking access…" />;
  }

  if (isManager === false) {
    return (
      <div className="narrow">
        <h1>Manager</h1>
        <p className="lead mb-24">
          Assign tasks, add members and read a summary of the team's work. This needs the
          manager username and password, which are separate from the team code.
        </p>
        <div className="card">
          {authError && <Notice tone="danger">{authError}</Notice>}
          <form onSubmit={handleManagerLogin}>
            <div className="form-group">
              <label htmlFor="mgr-user">
                <span>Username</span>
              </label>
              <input
                id="mgr-user"
                type="text"
                value={authUsername}
                onChange={(e) => setAuthUsername(e.target.value)}
                required
                autoFocus
                autoComplete="username"
                spellCheck={false}
              />
            </div>
            <div className="form-group">
              <label htmlFor="mgr-pass">
                <span>Password</span>
              </label>
              <input
                id="mgr-pass"
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>
            <button
              type="submit"
              className="btn btn-primary btn-block mt-8"
              disabled={authenticating || !authUsername.trim() || !authPassword}
            >
              {authenticating ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
        <p className="muted mt-16">
          Demo credentials: <code className="code">manager</code> / <code className="code">status2026</code>
        </p>
      </div>
    );
  }

  const filteredTasks = tasks.filter((t) => statusFilter === "all" || t.status === statusFilter);
  const memberNames = teamInfo?.members || [];
  const count = (status) => tasks.filter((t) => t.status === status).length;

  const TABS = [
    { id: "tasks", label: "Tasks", count: tasks.length },
    { id: "summary", label: "Summary" },
    { id: "members", label: "Members", count: memberNames.length },
    { id: "teamcode", label: "Team code" },
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Manager</h1>
          <p className="lead">{teamInfo?.name || user.team_name}</p>
        </div>
        <div className="page-header-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={handleLockManager}>
            Lock
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowTaskModal(true)}>
            <Plus size={14} /> New task
          </button>
        </div>
      </div>

      {feedback && (
        <Notice tone={feedback.tone} onDismiss={() => setFeedback(null)}>
          {feedback.message}
        </Notice>
      )}

      <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

      {activeTab === "tasks" && (
        <div>
          <div className="stats mb-16">
            <Stat label="Open" value={tasks.length - count("completed")} />
            <Stat label="In progress" value={count("in_progress")} tone="accent" />
            <Stat label="Completed" value={count("completed")} tone="success" />
            <Stat label="Blocked" value={count("blocked")} tone={count("blocked") ? "danger" : ""} />
          </div>

          <div className="filter-bar">
            <div className="filter-group" role="group" aria-label="Filter by status">
              {STATUS_FILTERS.map((st) => (
                <button
                  key={st}
                  type="button"
                  className={`filter-chip ${statusFilter === st ? "active" : ""}`}
                  onClick={() => setStatusFilter(st)}
                >
                  {st === "all" ? "All" : STATUS_LABELS[st]}
                </button>
              ))}
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={loadData} title="Refresh">
              <RefreshCw size={13} className={loading ? "spin" : ""} /> Refresh
            </button>
          </div>

          {loading ? (
            <Loading />
          ) : filteredTasks.length === 0 ? (
            <EmptyState
              icon={Briefcase}
              title={statusFilter === "all" ? "No tasks yet" : `No ${STATUS_LABELS[statusFilter].toLowerCase()} tasks`}
              action={
                statusFilter === "all" && (
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowTaskModal(true)}>
                    <Plus size={14} /> New task
                  </button>
                )
              }
            >
              {statusFilter === "all" ? "Assign a task to someone on the team." : null}
            </EmptyState>
          ) : (
            <div className="card card-flush">
              <div className="list">
                {filteredTasks.map((task) => (
                  <div key={task.id} className="task">
                    <div className="task-main">
                      <div className={`task-title ${task.status === "completed" ? "done" : ""}`}>
                        {task.title}
                      </div>
                      {task.description && <div className="task-desc">{task.description}</div>}
                      <div className="meta task-meta">
                        <span>{task.assigned_to_name || "Unassigned"}</span>
                        <PriorityBadge priority={task.priority} />
                        {task.due_date && (
                          <span className="meta-item">
                            <Calendar size={12} /> Due {task.due_date}
                          </span>
                        )}
                        {task.completed_at && (
                          <span>Done {new Date(task.completed_at).toLocaleDateString()}</span>
                        )}
                      </div>
                    </div>
                    <div className="task-aside">
                      <StatusSelect value={task.status} onChange={(v) => handleUpdateStatus(task.id, v)} />
                      <button
                        type="button"
                        className="btn btn-danger-ghost btn-sm btn-icon"
                        onClick={() => handleDeleteTask(task.id)}
                        title="Delete task"
                        aria-label="Delete task"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === "summary" && (
        <SummaryTab
          scope={summaryScope}
          setScope={setSummaryScope}
          data={summaryData}
          loading={loadingSummary}
          copied={summaryCopied}
          onCopy={copySummaryMarkdown}
          onRefresh={() => loadSummary(summaryScope)}
        />
      )}

      {activeTab === "members" && (
        <div>
          <h2>Add a member</h2>
          <p className="section-hint">
            They appear on the Team page at once and sign in with the team code and this name.
          </p>
          <div className="card">
            <form onSubmit={handleAddMember}>
              <div className="grid-2">
                <div className="form-group">
                  <label htmlFor="member_name">
                    <span>Name</span>
                  </label>
                  <input
                    id="member_name"
                    type="text"
                    value={newMemberName}
                    onChange={(e) => setNewMemberName(e.target.value)}
                    placeholder="Rahul Deshmukh"
                    required
                    disabled={savingMember}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="member_tz">
                    <span>Time zone</span>
                    <span className="hint">sets their standup day</span>
                  </label>
                  <input
                    id="member_tz"
                    type="text"
                    value={newMemberTz}
                    onChange={(e) => setNewMemberTz(e.target.value)}
                    placeholder="Asia/Kolkata"
                    spellCheck={false}
                    disabled={savingMember}
                  />
                </div>
              </div>
              <div className="form-actions">
                <button type="submit" className="btn btn-primary" disabled={savingMember || !newMemberName.trim()}>
                  {savingMember ? "Adding…" : "Add member"}
                </button>
              </div>
            </form>
          </div>

          <h2>Members ({memberNames.length})</h2>
          <div className="card card-flush">
            <div className="list">
              {(teamInfo?.members_detailed || memberNames.map((n) => ({ display_name: n }))).map((m) => (
                <div key={m.id || m.display_name} className="list-row" style={{ alignItems: "center" }}>
                  <Avatar name={m.display_name} />
                  <div className="list-main">
                    <span className="list-text">{m.display_name}</span>
                  </div>
                  <span className="muted small">
                    {m.tz || ""}
                    {m.display_name === user.display_name ? (m.tz ? " · you" : "you") : ""}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === "teamcode" && (
        <div>
          <h2>Team code</h2>
          <p className="section-hint">
            What every member of {teamInfo?.name || "the team"} types to sign in, with their name.
          </p>
          <div className="card">
            <div className="row">
              <code className="code-display">{teamInfo?.join_code || "…"}</code>
              <button type="button" className="btn btn-sm" onClick={() => copy(teamInfo?.join_code || "", setCodeCopied)}>
                {codeCopied ? <Check size={13} /> : <Copy size={13} />} {codeCopied ? "Copied" : "Copy"}
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => handleUpdateTeamCode(null)}
                disabled={savingCode}
                title="Replace the code with a new random one"
              >
                <RefreshCw size={13} /> Issue a new code
              </button>
            </div>
            <p className="muted mt-16">
              Issuing a new code does not sign anyone out. Share the new one with the team.
            </p>
          </div>

          <h2>Set a specific code</h2>
          <p className="section-hint">
            To keep the code you already use elsewhere, for example on a local copy of the app,
            enter it here so both accept the same one.
          </p>
          <div className="card">
            <div className="form-row" style={{ maxWidth: 440 }}>
              <input
                type="text"
                className="input-caps"
                value={customCodeInput}
                onChange={(e) => setCustomCodeInput(e.target.value)}
                placeholder="CORE-7K3MQ"
                spellCheck={false}
                disabled={savingCode}
              />
              <button
                type="button"
                className="btn btn-primary"
                style={{ flex: "0 0 auto" }}
                onClick={() => handleUpdateTeamCode(customCodeInput)}
                disabled={savingCode || !customCodeInput.trim()}
              >
                {savingCode ? "Saving…" : "Save code"}
              </button>
            </div>
          </div>
        </div>
      )}

      {showTaskModal && (
        <TaskModal
          members={assignees(tasks, teamInfo)}
          saving={savingTask}
          onClose={() => setShowTaskModal(false)}
          onSubmit={handleCreateTask}
        />
      )}
    </div>
  );
}

function SummaryTab({ scope, setScope, data, loading, copied, onCopy, onRefresh }) {
  const SCOPES = [
    { value: "daily", label: "Today" },
    { value: "project", label: "All time" },
  ];
  return (
    <div>
      <div className="row-between mb-16">
        <div>
          <h2 style={{ margin: 0 }}>Summary</h2>
          <p className="section-hint" style={{ margin: "4px 0 0" }}>
            Task status, completed work and reported blockers, from the tasks and standup updates.
          </p>
        </div>
        <div className="row">
          <Segmented options={SCOPES} value={scope} onChange={setScope} />
          <button type="button" className="btn btn-ghost btn-sm btn-icon" onClick={onRefresh} title="Refresh" aria-label="Refresh">
            <RefreshCw size={13} className={loading ? "spin" : ""} />
          </button>
          <button type="button" className="btn btn-sm" onClick={onCopy} disabled={!data}>
            {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy as Markdown"}
          </button>
        </div>
      </div>

      {loading ? (
        <Loading label="Building the summary…" />
      ) : !data ? (
        <EmptyState title="No summary yet" />
      ) : (
        <div>
          <div className="card card-pad-sm mb-16">
            <strong>{data.headline}</strong>
            <div className="muted small mt-8">Generated {new Date(data.generated_at).toLocaleString()}</div>
          </div>

          <div className="stats mb-24">
            <Stat label="Completion" value={`${data.stats.completion_rate}%`} tone="success" />
            <Stat label="Completed" value={data.stats.completed} />
            <Stat label="In progress" value={data.stats.in_progress} tone="accent" />
            <Stat
              label="Blockers"
              value={data.stats.blocked + data.standup_blockers.length}
              tone={data.stats.blocked + data.standup_blockers.length > 0 ? "danger" : ""}
            />
            <Stat label="Updates filed" value={data.stats.updates_submitted} />
          </div>

          <h2>Completed</h2>
          <div className="card card-flush">
            {data.completed_tasks.length === 0 ? (
              <p className="muted" style={{ padding: "12px 16px" }}>
                Nothing marked completed in this period.
              </p>
            ) : (
              <div className="list">
                {data.completed_tasks.map((t) => (
                  <div key={t.id} className="list-row">
                    <span className="list-who">{t.assigned_to_name || "Unassigned"}</span>
                    <div className="list-main">
                      <span className="list-text">{t.title}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <h2>Blockers</h2>
          <div className="card card-flush">
            {data.standup_blockers.length === 0 && data.blocked_tasks.length === 0 ? (
              <p className="muted" style={{ padding: "12px 16px" }}>
                No blockers reported.
              </p>
            ) : (
              <div className="list">
                {data.standup_blockers.map((b, i) => (
                  <div key={`s${i}`} className="list-row">
                    <span className="list-who">{b.member_name}</span>
                    <div className="list-main">
                      <span className="list-text">{b.blocker}</span>
                      <span className="list-note">from today's standup update</span>
                    </div>
                  </div>
                ))}
                {data.blocked_tasks.map((t) => (
                  <div key={t.id} className="list-row">
                    <span className="list-who">{t.assigned_to_name || "Unassigned"}</span>
                    <div className="list-main">
                      <span className="list-text">{t.title}</span>
                      <span className="list-note">task marked blocked</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <h2>By member</h2>
          <div className="grid-cards">
            {data.member_breakdowns.map((m) => (
              <div key={m.member_id} className="card card-pad-sm">
                <div className="row-between mb-8">
                  <strong>{m.member_name}</strong>
                  <span className="badge">
                    {m.tasks_completed}/{m.tasks_total} tasks done
                  </span>
                </div>
                {m.latest_progress || m.latest_blockers || m.latest_plan ? (
                  <dl className="kv">
                    {m.latest_progress && (
                      <>
                        <dt>Progress</dt>
                        <dd>{m.latest_progress}</dd>
                      </>
                    )}
                    {m.latest_blockers && (
                      <>
                        <dt>Blocker</dt>
                        <dd>{m.latest_blockers}</dd>
                      </>
                    )}
                    {m.latest_plan && (
                      <>
                        <dt>Today</dt>
                        <dd>{m.latest_plan}</dd>
                      </>
                    )}
                  </dl>
                ) : (
                  <p className="muted">No standup update yet today.</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TaskModal({ members, saving, onClose, onSubmit }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignee, setAssignee] = useState("");
  const [priority, setPriority] = useState("medium");
  const [dueDate, setDueDate] = useState("");

  const submit = (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    onSubmit({ title, description, assignee, priority, dueDate });
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="task-modal-title" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3 id="task-modal-title">New task</h3>
          <button type="button" className="btn btn-ghost btn-sm btn-icon" onClick={onClose} aria-label="Close">
            <X size={15} />
          </button>
        </div>

        <form onSubmit={submit}>
          <div className="form-group">
            <label htmlFor="task_title">
              <span>Title</span>
            </label>
            <input
              id="task_title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Fix connection pooling on staging"
              required
              autoFocus
              disabled={saving}
            />
          </div>

          <div className="form-group">
            <label htmlFor="task_desc">
              <span>Details</span>
              <span className="hint">optional</span>
            </label>
            <textarea
              id="task_desc"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Context, links, acceptance criteria"
              disabled={saving}
            />
          </div>

          <div className="grid-2">
            <div className="form-group">
              <label htmlFor="task_assignee">
                <span>Assign to</span>
              </label>
              <select id="task_assignee" value={assignee} onChange={(e) => setAssignee(e.target.value)} disabled={saving}>
                <option value="">Unassigned</option>
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="task_priority">
                <span>Priority</span>
              </label>
              <select id="task_priority" value={priority} onChange={(e) => setPriority(e.target.value)} disabled={saving}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="task_due">
              <span>Due date</span>
              <span className="hint">optional</span>
            </label>
            <input id="task_due" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} disabled={saving} />
          </div>

          <div className="form-actions">
            <button type="button" className="btn" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving || !title.trim()}>
              {saving ? "Creating…" : "Create task"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Members to assign to: the team's list, or, failing that, whoever already has a task.
function assignees(tasks, teamInfo) {
  if (teamInfo?.members_detailed?.length) return teamInfo.members_detailed;
  const map = new Map();
  tasks.forEach((t) => {
    if (t.assigned_to_id && t.assigned_to_name) {
      map.set(t.assigned_to_id, { id: t.assigned_to_id, display_name: t.assigned_to_name });
    }
  });
  return Array.from(map.values());
}
