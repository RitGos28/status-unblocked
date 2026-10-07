/**
 * API client for Status Unblocked FastAPI backend.
 * Uses credentials: "include" so the session cookie is passed along.
 */

const API_BASE = "";

async function request(url, options = {}) {
  const config = {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...options.headers,
    },
    credentials: "include",
    ...options,
  };

  const response = await fetch(`${API_BASE}${url}`, config);
  
  if (!response.ok) {
    let errorDetail = "An unexpected error occurred.";
    try {
      const errorJson = await response.json();
      errorDetail = errorJson.detail || errorJson.title || errorDetail;
    } catch {
      // Non-JSON response
    }
    const err = new Error(errorDetail);
    err.status = response.status;
    throw err;
  }

  // Handle empty responses
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

// Plain links for the browser to download; same team checks as the pages.
export const downloads = {
  digestMarkdown: (digestId) => `${API_BASE}/api/digest/${digestId}.md`,
  digestCsv: (digestId) => `${API_BASE}/api/digest/${digestId}.csv`,
  myExport: () => `${API_BASE}/api/me/export`,
};

export const api = {
  // Auth & Current Member
  getCurrentUser: () => request("/api/me"),
  login: (teamCode, name) =>
    request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ team_code: teamCode, name }),
    }),
  logout: () => request("/api/auth/logout", { method: "POST" }),

  // Submissions
  submitUpdate: (data) =>
    request("/api/submit", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Digests
  listDigests: () => request("/api/digests"),
  getDigest: (digestId) => request(`/api/digest/${digestId}`),
  buildDigest: (cycleId) =>
    request(`/api/digests/build/${cycleId}`, {
      method: "POST",
    }),

  // Evidence
  getEvidence: (itemId) => request(`/api/evidence/${itemId}`),

  // Team
  getTeam: () => request("/api/me/team"),

  // My data (the JSON export is a plain link: exportUrl)
  getMyData: () => request("/api/me/data"),

  // Teams
  getTeamsLink: () => request("/api/me/teams"),
};

// The manager portal: its own username/password sign-in, under /api/manager.
export const managerApi = {
  me: () => request("/api/manager/me"),
  login: (username, password) =>
    request("/api/manager/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request("/api/manager/logout", { method: "POST" }),
  listTeams: () => request("/api/manager/teams"),
  getTeam: (teamId) => request(`/api/manager/teams/${teamId}`),
  addMember: (teamId, displayName, tz) =>
    request(`/api/manager/teams/${teamId}/members`, {
      method: "POST",
      body: JSON.stringify({ display_name: displayName, tz }),
    }),
  getSummary: (teamId, days) => request(`/api/manager/teams/${teamId}/summary?days=${days}`),
  buildDigest: (cycleId) => request(`/api/manager/digests/build/${cycleId}`, { method: "POST" }),
  getDigest: (digestId) => request(`/api/manager/digest/${digestId}`),
  getEvidence: (itemId) => request(`/api/manager/evidence/${itemId}`),
};
