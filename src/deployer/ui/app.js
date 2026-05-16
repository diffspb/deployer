const state = {
  environments: [],
  projects: [],
  jobs: [],
  webhookEvents: [],
  version: null,
  currentView: { name: "dashboard" },
  theme: localStorage.getItem("deployer-theme") || "light",
  toast: "",
  loadError: "",
  addProject: null,
  deployModal: null,
  logsDrawer: null,
  jobDrawer: null,
  runtimeStatus: {},
  filters: {
    query: "",
    environment: "",
    status: "",
  },
  pollTimer: null,
};

const root = document.getElementById("deployer-root");
document.documentElement.dataset.theme = state.theme;

const icons = {
  plus: "M12 4v16m-8-8h16",
  server: "M4 6h16v5H4zm0 7h16v5H4zM7 8h.01M7 15h.01",
  play: "M8 5v14l11-7z",
  stop: "M6 6h12v12H6z",
  refresh: "M20 12a8 8 0 10-2.34 5.66M20 12v5h-5",
  trash: "M3 6h18M8 6V4h8v2m-9 0l1 14h8l1-14",
  close: "M18 6L6 18M6 6l12 12",
  moon: "M20 15.4A8.5 8.5 0 018.6 4 8.5 8.5 0 1020 15.4z",
  sun: "M12 3v2m0 14v2m9-9h-2M5 12H3m15.4-6.4L17 7M7 17l-1.4 1.4M18.4 18.4L17 17M7 7L5.6 5.6M12 8a4 4 0 100 8 4 4 0 000-8z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  history: "M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8m9-4v8l4 2",
  external: "M14 5h5v5M10 14L19 5M19 14v5H5V5h5",
  gear: "M10.3 4.3c.4-1.7 2.9-1.7 3.4 0a1.7 1.7 0 002.5 1c1.5-.9 3.3.9 2.4 2.4a1.7 1.7 0 001 2.5c1.7.4 1.7 2.9 0 3.4a1.7 1.7 0 00-1 2.5c.9 1.5-.9 3.3-2.4 2.4a1.7 1.7 0 00-2.5 1c-.5 1.7-3 1.7-3.4 0a1.7 1.7 0 00-2.5-1c-1.5.9-3.3-.9-2.4-2.4a1.7 1.7 0 00-1-2.5c-1.7-.5-1.7-3 0-3.4a1.7 1.7 0 001-2.5c-.9-1.5.9-3.3 2.4-2.4a1.7 1.7 0 002.5-1zM12 9a3 3 0 100 6 3 3 0 000-6z",
};

function icon(name, size = 15) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${icons[name] || ""}"></path></svg>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function js(value) {
  return escapeHtml(JSON.stringify(value));
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`);
  return data;
}

function projectKey(environment, project) {
  return `${environment}/${project}`;
}

function projectColor(name) {
  const colors = [
    "oklch(0.50 0.15 220)",
    "oklch(0.48 0.13 160)",
    "oklch(0.54 0.15 45)",
    "oklch(0.50 0.15 25)",
    "oklch(0.46 0.10 285)",
  ];
  const sum = [...name].reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[sum % colors.length];
}

function initials(name) {
  return name.split("-").map((part) => part[0]).join("").slice(0, 3);
}

function shortCommit(value) {
  return value ? value.slice(0, 7) : "-";
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatBuildDate(value) {
  if (!value || value === "unknown") return "unknown date";
  return new Date(value).toLocaleString();
}

function deployPolicyLabel(project) {
  if (!project?.deploy_mode || project.deploy_mode === "manual") return "manual";
  return `${project.deploy_mode} · ${project.deploy_source || "-"} · ${project.deploy_pattern_type || "-"} · ${project.deploy_pattern || "-"}`;
}

function projectByName(environment, name) {
  return state.projects.find((project) => project.environment === environment && project.name === name) || null;
}

function projectsForEnvironment(environment) {
  return state.projects.filter((project) => project.environment === environment);
}

function latestJob(environment, project) {
  return state.jobs.find((job) => job.environment === environment && job.project === project);
}

function activeJob(environment, project) {
  return state.jobs.find((job) => job.environment === environment && job.project === project && ["queued", "running"].includes(job.status));
}

function statusFor(environment, project) {
  return state.runtimeStatus[projectKey(environment, project)] || {
    loading: false,
    state: "unknown",
    health: "unknown",
    raw: "",
  };
}

function parseStatus(environment, project, response) {
  const summary = response?.summary || {};
  const containers = Array.isArray(summary.containers) ? summary.containers : [];
  const states = containers.map((item) => item.state);
  const running = Boolean(summary.running);
  const stopped = states.some((value) => ["exited", "stopped", "dead", "created", "removing"].includes(value));
  return {
    loading: false,
    state: running ? "running" : stopped || response?.status === "success" ? "stopped" : "unknown",
    health: summary.health || "unknown",
    raw: response?.log || "",
  };
}

function badge(status, text) {
  const cls = status === "success" ? "success" : status === "failed" ? "failed" : status === "running" ? "running" : "";
  return `<span class="badge ${cls}"><span class="dot"></span>${escapeHtml(text)}</span>`;
}

function renderRuntimeStatus(environment, project) {
  const status = statusFor(environment, project);
  if (status.loading) return `<div class="status-stack">${badge("", "loading")}</div>`;
  const stateBadge = status.state === "running"
    ? badge("success", "running")
    : status.state === "stopped"
      ? badge("", "stopped")
      : badge("failed", "unknown");
  const healthBadge = status.health === "healthy"
    ? badge("success", "healthy")
    : status.health === "unhealthy"
      ? badge("failed", "unhealthy")
      : status.health === "starting"
        ? badge("running", "starting")
        : badge("", "no health");
  return `<div class="status-stack">${stateBadge}${healthBadge}</div>`;
}

function renderVersion(project) {
  return `
    <div class="version-stack">
      <div class="mono">${escapeHtml(project.current_ref || project.current_version || project.default_ref || "-")}</div>
      <div class="subtle mono">${escapeHtml(shortCommit(project.current_commit))}</div>
    </div>
  `;
}

async function loadAll() {
  try {
    const [environmentsPayload, jobsPayload, webhooksPayload, versionPayload] = await Promise.all([
      api("/api/environments"),
      api("/api/jobs?limit=100"),
      api("/api/webhook-events?limit=50"),
      api("/api/version"),
    ]);
    state.environments = environmentsPayload.environments || [];
    state.jobs = jobsPayload.jobs || [];
    state.webhookEvents = webhooksPayload.events || [];
    state.version = versionPayload;
    const projectLists = await Promise.all(
      state.environments.map((environment) => api(`/api/environments/${encodeURIComponent(environment.name)}/projects`)),
    );
    state.projects = projectLists.flatMap((item) => item.projects || []);
    state.loadError = "";
    syncCurrentView();
    if (state.currentView.name === "project") {
      await refreshProject(state.currentView.environment, state.currentView.project);
    }
    render();
  } catch (error) {
    state.loadError = error.message;
    render();
  }
}

function syncCurrentView() {
  if (state.currentView.name === "environment" && !state.environments.some((item) => item.name === state.currentView.environment)) {
    state.currentView = { name: "dashboard" };
  }
  if (state.currentView.name === "project" && !projectByName(state.currentView.environment, state.currentView.project)) {
    state.currentView = { name: "dashboard" };
  }
}

async function refreshStatuses() {
  const projects = state.projects;
  projects.forEach((project) => {
    state.runtimeStatus[projectKey(project.environment, project.name)] = { ...statusFor(project.environment, project.name), loading: true };
  });
  render();
  const results = await Promise.all(projects.map(async (project) => {
    try {
      const response = await api(`/api/environments/${encodeURIComponent(project.environment)}/projects/${encodeURIComponent(project.name)}/status`);
      return { project, status: parseStatus(project.environment, project.name, response) };
    } catch (error) {
      return { project, status: { loading: false, state: "unknown", health: "unknown", raw: error.message } };
    }
  }));
  results.forEach(({ project, status }) => {
    state.runtimeStatus[projectKey(project.environment, project.name)] = status;
  });
  render();
}

async function refreshStatus(environment, project) {
  state.runtimeStatus[projectKey(environment, project)] = { ...statusFor(environment, project), loading: true };
  render();
  try {
    const response = await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/status`);
    state.runtimeStatus[projectKey(environment, project)] = parseStatus(environment, project, response);
  } catch (error) {
    state.runtimeStatus[projectKey(environment, project)] = { loading: false, state: "unknown", health: "unknown", raw: error.message };
  }
  render();
}

async function refreshActivity() {
  try {
    const [jobsPayload, webhooksPayload] = await Promise.all([
      api("/api/jobs?limit=100"),
      api("/api/webhook-events?limit=50"),
    ]);
    state.jobs = jobsPayload.jobs || [];
    state.webhookEvents = webhooksPayload.events || [];
    if (state.currentView.name === "project") {
      await refreshProject(state.currentView.environment, state.currentView.project);
    }
    render();
  } catch (error) {
    console.warn("Activity refresh failed", error);
  }
}

async function refreshProjectActivity(environment, project) {
  try {
    const [jobsPayload, webhooksPayload] = await Promise.all([
      api("/api/jobs?limit=100"),
      api("/api/webhook-events?limit=50"),
    ]);
    state.jobs = jobsPayload.jobs || [];
    state.webhookEvents = webhooksPayload.events || [];
    await refreshProject(environment, project);
    render();
  } catch (error) {
    setToast(error.message);
  }
}

function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = window.setInterval(() => {
    refreshActivity();
    refreshStatuses();
  }, 5000);
}

function setToast(message) {
  state.toast = message;
  render();
  setTimeout(() => {
    if (state.toast === message) {
      state.toast = "";
      render();
    }
  }, 3000);
}

function render() {
  root.innerHTML = `
    <div class="app-shell">
      ${renderSidebar()}
      <main class="main">
        ${renderTopbar()}
        <section class="content">
          ${state.loadError ? renderError(state.loadError) : ""}
          ${renderCurrentView()}
        </section>
      </main>
      ${state.addProject ? renderAddProjectPanel() : ""}
      ${state.deployModal ? renderDeployModal() : ""}
      ${state.logsDrawer ? renderLogsDrawer() : ""}
      ${state.jobDrawer ? renderJobDrawer() : ""}
      ${state.toast ? `<div class="toast">${escapeHtml(state.toast)}</div>` : ""}
    </div>
  `;
}

function renderSidebar() {
  return `
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">P</div>
        <div>
          <div class="brand-title">PaaS Deployer</div>
          <div class="brand-subtitle">environment projects</div>
        </div>
      </div>
      <div class="nav-block">
        <div class="nav-label">Workspace</div>
        <button class="nav-item ${state.currentView.name === "dashboard" ? "active" : ""}" onclick="openDashboard()">${icon("server")} Environments</button>
        <button class="nav-item ${state.currentView.name === "jobs" ? "active" : ""}" onclick="openJobs()">${icon("list")} Jobs</button>
        <button class="nav-item ${state.currentView.name === "webhooks" ? "active" : ""}" onclick="openWebhooks()">${icon("history")} Webhooks</button>
      </div>
      <div class="nav-block service-list">
        <div class="nav-label">Projects</div>
        ${state.environments.map(renderSidebarEnvironment).join("")}
      </div>
      <div class="nav-block">
        <button class="nav-item" onclick="toggleTheme()">${icon(state.theme === "dark" ? "sun" : "moon")} ${state.theme === "dark" ? "Light theme" : "Dark theme"}</button>
      </div>
    </aside>
  `;
}

function renderSidebarEnvironment(environment) {
  const projects = projectsForEnvironment(environment.name);
  return `
    <div class="tree-item">
      <button class="nav-item ${state.currentView.name === "environment" && state.currentView.environment === environment.name ? "active" : ""}" onclick="openEnvironment(${js(environment.name)})">
        <span class="badge mono">${escapeHtml(environment.name)}</span>
        <span class="ellipsis">${projects.length} projects</span>
      </button>
      <div class="tree-children">
        ${projects.map((project) => `
          <button class="nav-item child ${state.currentView.name === "project" && state.currentView.environment === project.environment && state.currentView.project === project.name ? "active" : ""}" onclick="openProject(${js(project.environment)}, ${js(project.name)})">
            <span class="tree-indent"></span>
            <span class="dot" style="color:${projectColor(project.name)}"></span>
            <span class="ellipsis">${escapeHtml(project.name)}</span>
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function renderTopbar() {
  const activeJobs = state.jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  const failedJobs = state.jobs.filter((job) => job.status === "failed").length;
  const title = state.currentView.name === "project"
    ? `${state.currentView.environment}/${state.currentView.project}`
    : state.currentView.name === "environment"
      ? `Environment: ${state.currentView.environment}`
      : state.currentView.name === "jobs"
        ? "Runtime jobs"
        : state.currentView.name === "webhooks"
          ? "Webhook events"
          : "Environments dashboard";
  const versionText = state.version
    ? `api ${state.version.backend_version || "-"} · ui ${state.version.frontend_version || "-"} · build ${shortCommit(state.version.build_commit)} · ${formatBuildDate(state.version.build_date)}`
    : "version loading";
  return `
    <header class="topbar">
      <div>
        <h1>${escapeHtml(title)}</h1>
        <div class="hint">${state.environments.length} environments · ${state.projects.length} projects · ${activeJobs} active jobs · ${failedJobs} failed jobs · ${escapeHtml(versionText)}</div>
      </div>
      <div class="spacer"></div>
      ${state.currentView.name === "project" ? `<button class="btn secondary" onclick="refreshStatus(${js(state.currentView.environment)}, ${js(state.currentView.project)})">${icon("refresh")} Refresh status</button>` : ""}
      ${state.currentView.name === "project" ? `<button class="btn secondary" onclick="refreshProjectActivity(${js(state.currentView.environment)}, ${js(state.currentView.project)})">${icon("history")} Refresh jobs</button>` : ""}
      ${state.currentView.name === "jobs" || state.currentView.name === "webhooks" ? `<button class="btn secondary" onclick="refreshActivityOnly()">${icon("refresh")} Refresh activity</button>` : ""}
      <button class="btn secondary" onclick="refreshData()">${icon("refresh")} Refresh</button>
      ${state.currentView.name !== "jobs" && state.currentView.name !== "webhooks" ? `<button class="btn primary" onclick="openAddProject()">${icon("plus")} Add project</button>` : ""}
    </header>
  `;
}

function renderCurrentView() {
  if (state.currentView.name === "jobs") return renderJobsView();
  if (state.currentView.name === "webhooks") return renderWebhooksView();
  if (state.currentView.name === "environment") return renderEnvironmentView();
  if (state.currentView.name === "project") return renderProjectView();
  return renderDashboard();
}

function renderDashboard() {
  const query = state.filters.query.toLowerCase();
  const filteredProjects = state.projects.filter((project) => {
    if (state.filters.environment && project.environment !== state.filters.environment) return false;
    if (query && ![project.environment, project.name, project.source_url, project.source_path, project.current_ref, project.current_commit].some((value) => String(value || "").toLowerCase().includes(query))) return false;
    if (state.filters.status && statusFor(project.environment, project.name).state !== state.filters.status) return false;
    return true;
  });
  return `
    <div class="toolbar">
      <div>
        <div class="headline">Environment Projects</div>
        <div class="muted">Projects are owned by environments. There is no shared service attachment layer.</div>
      </div>
    </div>
    <div class="filter-bar card">
      <div class="field grow"><label>Search</label><input class="input" value="${escapeHtml(state.filters.query)}" placeholder="project, ref, commit, source" oninput="setFilter('query', this.value)"></div>
      <div class="field"><label>Environment</label><select class="select" onchange="setFilter('environment', this.value)"><option value="">all</option>${state.environments.map((env) => `<option value="${escapeHtml(env.name)}" ${state.filters.environment === env.name ? "selected" : ""}>${escapeHtml(env.name)}</option>`).join("")}</select></div>
      <div class="field"><label>Status</label><select class="select" onchange="setFilter('status', this.value)"><option value="">all</option><option value="running" ${state.filters.status === "running" ? "selected" : ""}>running</option><option value="stopped" ${state.filters.status === "stopped" ? "selected" : ""}>stopped</option><option value="unknown" ${state.filters.status === "unknown" ? "selected" : ""}>unknown</option></select></div>
    </div>
    <section class="card page-card">
      ${filteredProjects.length ? renderProjectTable(filteredProjects, true) : renderEmpty("No projects match the current filters")}
    </section>
  `;
}

function renderEnvironmentView() {
  const environment = state.environments.find((item) => item.name === state.currentView.environment);
  if (!environment) return renderEmpty("Unknown environment");
  const projects = projectsForEnvironment(environment.name);
  return `
    <div class="page-stack">
      <section class="card page-card">
        <div class="page-header">
          <div>
            <div class="headline-small">${escapeHtml(environment.name)}</div>
            <div class="muted mono">${escapeHtml(environment.url_prefix ? `*.${environment.url_prefix}.busypage.ru` : "*.busypage.ru")}</div>
          </div>
          <button class="btn primary" onclick="openAddProject(${js(environment.name)})">${icon("plus")} Add project</button>
        </div>
        <div class="runtime-page-grid">
          <div class="fact"><span class="fact-label">URL prefix</span><span class="fact-value mono">${escapeHtml(environment.url_prefix || "(none)")}</span></div>
          <div class="fact"><span class="fact-label">Projects</span><span class="fact-value mono">${projects.length}</span></div>
        </div>
      </section>
      <section class="card page-card">
        ${projects.length ? renderProjectTable(projects, false) : renderEmpty(`No projects in ${environment.name}`)}
      </section>
    </div>
  `;
}

function renderProjectTable(projects, showEnvironment) {
  return `
    <div class="table table-wide">
      <div class="table-row table-head environment-services-head">
        <div>Project</div>
        ${showEnvironment ? "<div>Env</div>" : ""}
        <div>Links</div>
        <div>Status</div>
        <div>Version</div>
        <div>Policy</div>
        <div>Actions</div>
      </div>
      ${projects.map((project) => renderProjectRow(project, showEnvironment)).join("")}
    </div>
  `;
}

function renderProjectRow(project, showEnvironment) {
  const active = activeJob(project.environment, project.name);
  const last = latestJob(project.environment, project.name);
  const failed = !active && last?.status === "failed";
  return `
    <div class="table-row ${showEnvironment ? "services-table-row" : "environment-services-row"}">
      <div class="service-cell">
        <div class="service-icon small" style="background:${projectColor(project.name)}">${escapeHtml(initials(project.name))}</div>
        <div>
          <button class="service-link-button" onclick="openProject(${js(project.environment)}, ${js(project.name)})">${escapeHtml(project.name)}</button>
          <div class="subtle mono ellipsis">${escapeHtml(project.source_url || project.source_path || "-")}</div>
        </div>
      </div>
      ${showEnvironment ? `<div><span class="badge">${escapeHtml(project.environment)}</span></div>` : ""}
      <div>${renderProjectLinks(project)}</div>
      <div>
        ${renderRuntimeStatus(project.environment, project.name)}
        ${active ? `<div class="subtle mono top-gap">${escapeHtml(active.action)}</div>` : ""}
        ${failed ? `<div class="failure-note top-gap">last ${escapeHtml(last.action)} failed</div>` : ""}
      </div>
      <div>${renderVersion(project)}</div>
      <div><span class="badge">${escapeHtml(deployPolicyLabel(project))}</span>${project.candidate_ref ? `<div class="badge running top-gap">candidate ${escapeHtml(project.candidate_ref)}</div>` : ""}</div>
      <div class="quick-actions">
        <button class="btn ghost" onclick="openProject(${js(project.environment)}, ${js(project.name)})">Settings</button>
        <button class="btn ghost" onclick="openLogs(${js(project.environment)}, ${js(project.name)})">Logs</button>
        <button class="btn primary" onclick="openDeploy(${js(project.environment)}, ${js(project.name)})">Deploy</button>
      </div>
    </div>
  `;
}

function renderProjectLinks(project) {
  const links = project.public_urls || [];
  if (!links.length) return `<span class="subtle">not exposed</span>`;
  return links.map((url) => `<a class="table-link mono" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>`).join("<br>");
}

function renderProjectView() {
  const project = projectByName(state.currentView.environment, state.currentView.project);
  if (!project) return renderEmpty("Unknown project");
  const jobs = state.jobs.filter((job) => job.environment === project.environment && job.project === project.name);
  const webhookEvents = state.webhookEvents.filter((event) => (event.matched_projects || []).includes(`${project.environment}/${project.name}`));
  return `
    <div class="page-stack">
      <section class="card page-card">
        <div class="page-header">
          <div class="service-title">
            <div class="service-icon" style="background:${projectColor(project.name)}">${escapeHtml(initials(project.name))}</div>
            <div>
              <h2 class="service-name">${escapeHtml(project.environment)}/${escapeHtml(project.name)}</h2>
              <div class="muted">Environment-owned project. Runtime config is stored in deployer.</div>
            </div>
          </div>
          <div class="row wrap">${renderRuntimeStatus(project.environment, project.name)}</div>
        </div>
        <div class="runtime-page-grid">
          <div class="fact"><span class="fact-label">Source</span><span class="fact-value mono">${escapeHtml(project.source_url || project.source_path || "-")}</span></div>
          <div class="fact"><span class="fact-label">Compose files</span><span class="fact-value mono">${escapeHtml((project.compose_files || []).join(", ") || "(generated)")}</span></div>
          <div class="fact"><span class="fact-label">Current ref</span><span class="fact-value mono">${escapeHtml(project.current_ref || project.default_ref || "-")}</span></div>
          <div class="fact"><span class="fact-label">Current commit</span><span class="fact-value mono">${escapeHtml(shortCommit(project.current_commit))}</span></div>
          <div class="fact"><span class="fact-label">Deploy policy</span><span class="fact-value mono">${escapeHtml(deployPolicyLabel(project))}</span></div>
        </div>
        ${project.candidate_ref ? renderCandidate(project) : ""}
        <div class="runtime-button-row">
          <button class="btn primary" onclick="openDeploy(${js(project.environment)}, ${js(project.name)})">${icon("play")} Deploy</button>
          <button class="btn secondary" onclick="refreshStatus(${js(project.environment)}, ${js(project.name)})">${icon("refresh")} Refresh status</button>
          ${project.candidate_ref ? `<button class="btn primary" onclick="deployCandidate(${js(project.environment)}, ${js(project.name)})">${icon("play")} Deploy candidate</button>` : ""}
          <button class="btn secondary" onclick="runtimeAction(${js(project.environment)}, ${js(project.name)}, 'restart')">${icon("refresh")} Restart</button>
          <button class="btn secondary" onclick="runtimeAction(${js(project.environment)}, ${js(project.name)}, 'stop')">${icon("stop")} Stop</button>
          <button class="btn danger" onclick="runtimeAction(${js(project.environment)}, ${js(project.name)}, 'down')">${icon("trash")} Down</button>
          <button class="btn secondary" onclick="openLogs(${js(project.environment)}, ${js(project.name)})">${icon("list")} Logs</button>
        </div>
      </section>
      <section class="card page-card">
        <div class="page-header"><div><div class="section-title">Configuration</div><div class="muted">Components, endpoints, dependencies, and env vars for this environment project.</div></div></div>
        ${renderProjectConfig(project)}
      </section>
      <section class="card page-card">
        <div class="page-header"><div><div class="section-title">Recent jobs</div><div class="muted">Latest runtime actions for this project.</div></div></div>
        ${renderJobsTable(jobs.slice(0, 8))}
      </section>
      <section class="card page-card">
        <div class="page-header"><div><div class="section-title">Recent webhook events</div><div class="muted">External triggers matched to this project.</div></div></div>
        ${renderWebhookEventsTable(webhookEvents.slice(0, 5))}
      </section>
    </div>
  `;
}

function renderCandidate(project) {
  return `
    <div class="inline-error candidate-box">
      <div class="error-title">Deploy candidate</div>
      <div class="error-list">
        <div>ref: <span class="mono">${escapeHtml(project.candidate_ref)}</span></div>
        <div>commit: <span class="mono">${escapeHtml(shortCommit(project.candidate_commit))}</span></div>
        <div>event: <span class="mono">#${escapeHtml(project.candidate_event_id)}</span></div>
      </div>
    </div>
  `;
}

function renderProjectConfig(project) {
  const components = project.components || [];
  const endpoints = project.endpoints || [];
  const dependencies = project.dependencies || [];
  const envEntries = Object.entries(project.env || {});
  return `
    <div class="config-grid">
      <div class="preview-panel">
        <div class="section-title">Components</div>
        ${components.length ? components.map((item) => `
          <div class="fact compact">
            <span class="fact-label">${escapeHtml(item.name)}</span>
            <span class="fact-value mono">${escapeHtml(item.mode)} · ${escapeHtml(item.compose_service || item.image || item.build_context || "-")}</span>
            <span class="fact-actions">
              <button class="link-btn" onclick="editComponent(${js(project.environment)}, ${js(project.name)}, ${js(item)})">Edit</button>
              <button class="link-btn danger" onclick="deleteComponent(${js(project.environment)}, ${js(project.name)}, ${js(item.name)})">Delete</button>
            </span>
          </div>
        `).join("") : `<div class="muted">No components.</div>`}
        <form class="inline-form top-gap" onsubmit="addComponent(event, ${js(project.environment)}, ${js(project.name)})">
          <input class="input" name="name" placeholder="name" required>
          <select class="select" name="mode"><option value="compose">compose</option><option value="build">build</option><option value="image">image</option></select>
          <input class="input" name="target" placeholder="compose service / build context / image" required>
          <input class="input" name="port" placeholder="port">
          <button class="btn secondary" type="submit">${icon("plus")} Add</button>
        </form>
      </div>
      <div class="preview-panel">
        <div class="section-title">Endpoints</div>
        ${endpoints.length ? endpoints.map((item) => `
          <div class="fact compact">
            <span class="fact-label">${escapeHtml(item.name)}</span>
            <span class="fact-value mono">${escapeHtml(item.public_url || item.subdomain || item.host || "-")}${item.healthcheck_path ? ` · health ${escapeHtml(item.healthcheck_path)}` : ""}</span>
            <span class="fact-actions">
              <button class="link-btn" onclick="editEndpoint(${js(project.environment)}, ${js(project.name)}, ${js(item)})">Edit</button>
              <button class="link-btn danger" onclick="deleteEndpoint(${js(project.environment)}, ${js(project.name)}, ${js(item.name)})">Delete</button>
            </span>
          </div>
        `).join("") : `<div class="muted">No endpoints.</div>`}
        <form class="inline-form top-gap" onsubmit="addEndpoint(event, ${js(project.environment)}, ${js(project.name)})">
          <input class="input" name="name" placeholder="name" required>
          <input class="input" name="component" placeholder="component" required>
          <input class="input" name="subdomain" placeholder="subdomain" required>
          <input class="input" name="port" placeholder="port" required>
          <select class="select" name="auth"><option value="none">none</option><option value="sso">sso</option></select>
          <input class="input" name="healthcheck_path" placeholder="health path, e.g. /health">
          <button class="btn secondary" type="submit">${icon("plus")} Add</button>
        </form>
      </div>
      <div class="preview-panel">
        <div class="section-title">Environment</div>
        ${envEntries.length ? envEntries.map(([key, value]) => `<div class="fact compact"><span class="fact-label mono">${escapeHtml(key)}</span><span class="fact-value mono">${escapeHtml(value)}</span></div>`).join("") : `<div class="muted">No env vars.</div>`}
        <form class="inline-form top-gap" onsubmit="setProjectEnv(event, ${js(project.environment)}, ${js(project.name)})">
          <input class="input" name="key" placeholder="KEY" required>
          <input class="input" name="value" placeholder="value">
          <button class="btn secondary" type="submit">Set</button>
        </form>
      </div>
      <div class="preview-panel">
        <div class="section-title">Dependencies</div>
        ${dependencies.length ? dependencies.map((item) => `
          <div class="fact compact">
            <span class="fact-label">${escapeHtml(item.name)}</span>
            <span class="fact-value mono">${escapeHtml(item.type)} · ${escapeHtml(item.target)}</span>
            <span class="fact-actions">
              <button class="link-btn" onclick="editDependency(${js(project.environment)}, ${js(project.name)}, ${js(item)})">Edit</button>
              <button class="link-btn danger" onclick="deleteDependency(${js(project.environment)}, ${js(project.name)}, ${js(item.name)})">Delete</button>
            </span>
          </div>
        `).join("") : `<div class="muted">No dependencies.</div>`}
        <form class="inline-form top-gap" onsubmit="addDependency(event, ${js(project.environment)}, ${js(project.name)})">
          <input class="input" name="name" placeholder="name" required>
          <input class="input" name="type" placeholder="type" required>
          <input class="input" name="target" placeholder="target" required>
          <input class="input" name="output" placeholder="KEY=value">
          <button class="btn secondary" type="submit">${icon("plus")} Add</button>
        </form>
      </div>
    </div>
  `;
}

function renderJobsView() {
  return `
    <section class="card page-card">
      <div class="page-header"><div><div class="headline-small">Jobs</div><div class="muted">Runtime job history and output.</div></div></div>
      ${renderJobsTable(state.jobs)}
    </section>
  `;
}

function renderJobsTable(jobs) {
  if (!jobs.length) return renderEmpty("No jobs yet");
  return `
    <div class="table table-wide">
      <div class="table-row table-head services-table-head"><div>ID</div><div>Project</div><div>Action</div><div>Status</div><div>Ref</div><div>Created</div><div>Output</div></div>
      ${jobs.map((job) => `
        <div class="table-row services-table-row">
          <div class="mono">#${job.id}</div>
          <div class="mono">${escapeHtml(job.environment)}/${escapeHtml(job.project)}</div>
          <div>${escapeHtml(job.action)}</div>
          <div>${badge(job.status, job.status)}</div>
          <div class="mono">${escapeHtml(job.ref || job.version || "-")}</div>
          <div>${escapeHtml(formatTime(job.created_at))}</div>
          <div><button class="btn ghost" onclick="openJob(${job.id})">Output</button></div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderWebhooksView() {
  return `
    <section class="card page-card">
      <div class="page-header">
        <div>
          <div class="headline-small">Webhook events</div>
          <div class="muted">GitHub push events, matched projects, scheduled deploys, and gated candidates.</div>
        </div>
      </div>
      ${renderWebhookEventsTable(state.webhookEvents)}
    </section>
  `;
}

function renderWebhookEventsTable(events) {
  if (!events.length) return renderEmpty("No webhook events yet");
  return `
    <div class="table table-wide">
      <div class="table-row table-head services-table-head"><div>ID</div><div>Event</div><div>Ref</div><div>Action</div><div>Projects</div><div>Created</div></div>
      ${events.map((event) => `
        <div class="table-row services-table-row">
          <div class="mono">#${event.id}</div>
          <div>${escapeHtml(event.provider)} / ${escapeHtml(event.event_type)}</div>
          <div class="mono">${escapeHtml(event.ref_name || "-")} <span class="subtle">${escapeHtml(shortCommit(event.commit_hash))}</span></div>
          <div>${badge(event.status === "accepted" ? "success" : "", event.action)}</div>
          <div class="mono">${escapeHtml((event.matched_projects || []).join(", ") || "-")}</div>
          <div>${escapeHtml(formatTime(event.created_at))}</div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderAddProjectPanel() {
  const environmentOptions = state.environments.map((env) => `<option value="${escapeHtml(env.name)}" ${state.addProject.environment === env.name ? "selected" : ""}>${escapeHtml(env.name)}</option>`).join("");
  return `
    <div class="drawer-backdrop" onclick="closeAddProject()"></div>
    <aside class="drawer">
      <div class="drawer-head">
        <div><div class="section-title">Add project</div><div class="muted">Create a project inside one environment.</div></div>
        <button class="btn ghost" onclick="closeAddProject()">${icon("close")}</button>
      </div>
      <form class="form-stack" onsubmit="submitAddProject(event)">
        <div class="field"><label>Environment</label><select class="select" name="environment" required>${environmentOptions}</select></div>
        <div class="field"><label>Name</label><input class="input" name="name" placeholder="tasktrack" required></div>
        <div class="field"><label>Source type</label><select class="select" name="source_type" onchange="state.addProject.sourceType=this.value;render()"><option value="git">git</option><option value="local">local</option></select></div>
        <div class="field"><label>Git URL or local path</label><input class="input mono" name="source" placeholder="git@github.com:org/repo.git or /srv/project" required></div>
        <div class="field"><label>Default ref</label><input class="input mono" name="default_ref" placeholder="main/dev/tag"></div>
        <div class="field"><label>Compose files</label><input class="input mono" name="compose_files" value="docker-compose.yml" placeholder="comma separated; empty = generated"></div>
        <div class="field"><label>Deploy mode</label><select class="select" name="deploy_mode"><option value="manual">manual</option><option value="webhook_auto">webhook_auto</option><option value="webhook_gated">webhook_gated</option></select></div>
        <div class="field"><label>Webhook source</label><select class="select" name="deploy_source"><option value="">none</option><option value="branch">branch</option><option value="tag">tag</option></select></div>
        <div class="field"><label>Webhook pattern</label><input class="input mono" name="deploy_pattern" placeholder="dev or ^v[0-9]+$"></div>
        <div class="field"><label>Pattern type</label><select class="select" name="deploy_pattern_type"><option value="">none</option><option value="exact">exact</option><option value="regex">regex</option></select></div>
        <button class="btn primary" type="submit">${icon("plus")} Add project</button>
      </form>
    </aside>
  `;
}

function renderDeployModal() {
  return `
    <div class="modal-backdrop" onclick="closeDeploy()"></div>
    <div class="modal">
      <div class="modal-head">
        <div><div class="section-title">Deploy ${escapeHtml(state.deployModal.environment)}/${escapeHtml(state.deployModal.project)}</div><div class="muted">Checkout ref is optional; project default ref is used when empty.</div></div>
        <button class="btn ghost" onclick="closeDeploy()">${icon("close")}</button>
      </div>
      <form class="form-stack" onsubmit="submitDeploy(event)">
        <div class="field"><label>Ref</label><input class="input mono" name="ref" placeholder="branch, tag, commit"></div>
        <label class="check-line"><input type="checkbox" name="dry_run"> Dry run</label>
        <button class="btn primary" type="submit">${icon("play")} Deploy</button>
      </form>
    </div>
  `;
}

function renderLogsDrawer() {
  return `
    <div class="drawer-backdrop" onclick="closeLogs()"></div>
    <aside class="drawer wide-drawer">
      <div class="drawer-head">
        <div><div class="section-title">Logs ${escapeHtml(state.logsDrawer.environment)}/${escapeHtml(state.logsDrawer.project)}</div></div>
        <button class="btn ghost" onclick="closeLogs()">${icon("close")}</button>
      </div>
      <pre class="log-box">${escapeHtml(state.logsDrawer.log || "Loading...")}</pre>
    </aside>
  `;
}

function renderJobDrawer() {
  const job = state.jobDrawer;
  const log = job.log || job.error || "No output recorded yet.";
  return `
    <div class="drawer-backdrop" onclick="closeJob()"></div>
    <aside class="drawer wide-drawer">
      <div class="drawer-head">
        <div><div class="section-title">Job #${job.id}</div><div class="muted">${escapeHtml(job.environment)}/${escapeHtml(job.project)} · ${escapeHtml(job.action)}</div></div>
        <div class="row">
          <button class="btn secondary" onclick="refreshOpenJob()">${icon("refresh")} Refresh job</button>
          <button class="btn ghost" onclick="closeJob()">${icon("close")}</button>
        </div>
      </div>
      <div class="job-meta-grid">
        <div class="fact compact"><span class="fact-label">Status</span><span class="fact-value">${badge(job.status, job.status)}</span></div>
        <div class="fact compact"><span class="fact-label">Ref</span><span class="fact-value mono">${escapeHtml(job.ref || job.version || "-")}</span></div>
        <div class="fact compact"><span class="fact-label">Started</span><span class="fact-value">${escapeHtml(formatTime(job.started_at))}</span></div>
        <div class="fact compact"><span class="fact-label">Finished</span><span class="fact-value">${escapeHtml(formatTime(job.finished_at))}</span></div>
      </div>
      ${job.error ? `<div class="inline-error job-error"><div class="error-title">Error</div><div class="error-list"><div>${escapeHtml(job.error)}</div></div></div>` : ""}
      ${job.log_truncated ? `<div class="muted log-note">Output is truncated by API limit. Use CLI or container logs for the full output.</div>` : ""}
      <pre class="log-box">${escapeHtml(log)}</pre>
    </aside>
  `;
}

function renderEmpty(message = "Nothing here yet") {
  return `<div class="empty compact-empty"><div style="font-weight:800">${escapeHtml(message)}</div></div>`;
}

function renderError(message) {
  return `<div class="inline-error banner-error"><div class="error-title">Error</div><div class="error-list"><div>${escapeHtml(message)}</div></div></div>`;
}

function openDashboard() {
  state.currentView = { name: "dashboard" };
  render();
}

function openEnvironment(environment) {
  state.currentView = { name: "environment", environment };
  render();
}

async function openProject(environment, project) {
  state.currentView = { name: "project", environment, project };
  await refreshProject(environment, project);
  render();
}

function openJobs() {
  state.currentView = { name: "jobs" };
  render();
}

function openWebhooks() {
  state.currentView = { name: "webhooks" };
  render();
}

function openAddProject(environment = "") {
  state.addProject = { environment: environment || state.environments[0]?.name || "", sourceType: "git" };
  render();
}

function closeAddProject() {
  state.addProject = null;
  render();
}

async function submitAddProject(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const environment = form.get("environment");
  const sourceType = form.get("source_type");
  const source = String(form.get("source") || "").trim();
  const composeFiles = String(form.get("compose_files") || "").split(",").map((item) => item.trim()).filter(Boolean);
  const payload = {
    name: String(form.get("name") || "").trim(),
    source_type: sourceType,
    default_ref: String(form.get("default_ref") || "").trim() || null,
    compose_files: composeFiles,
    deploy_mode: form.get("deploy_mode"),
    deploy_source: String(form.get("deploy_source") || "").trim() || null,
    deploy_pattern: String(form.get("deploy_pattern") || "").trim() || null,
    deploy_pattern_type: String(form.get("deploy_pattern_type") || "").trim() || null,
  };
  if (sourceType === "git") payload.git_url = source;
  else payload.path = source;
  try {
    await api(`/api/environments/${encodeURIComponent(environment)}/projects`, { method: "POST", body: JSON.stringify(payload) });
    state.addProject = null;
    setToast("Project added");
    await loadAll();
  } catch (error) {
    setToast(error.message);
  }
}

function openDeploy(environment, project) {
  state.deployModal = { environment, project };
  render();
}

function closeDeploy() {
  state.deployModal = null;
  render();
}

async function submitDeploy(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const { environment, project } = state.deployModal;
  const job = await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/deploy`, {
    method: "POST",
    body: JSON.stringify({
      ref: String(form.get("ref") || "").trim() || null,
      dry_run: Boolean(form.get("dry_run")),
    }),
  });
  state.deployModal = null;
  upsertJob(job);
  setToast("Deploy job scheduled");
  await openJob(job.id);
}

async function deployCandidate(environment, project) {
  const job = await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/deploy-candidate`, {
    method: "POST",
    body: JSON.stringify({ dry_run: false }),
  });
  upsertJob(job);
  setToast("Candidate deploy scheduled");
  await openJob(job.id);
}

async function runtimeAction(environment, project, action) {
  const job = await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/${action}`, {
    method: "POST",
    body: JSON.stringify({ dry_run: false }),
  });
  upsertJob(job);
  setToast(`${action} job scheduled`);
  await openJob(job.id);
}

async function openLogs(environment, project) {
  state.logsDrawer = { environment, project, log: "Loading..." };
  render();
  try {
    const response = await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/logs?tail=300`);
    state.logsDrawer = { environment, project, log: response.log || "" };
  } catch (error) {
    state.logsDrawer = { environment, project, log: error.message };
  }
  render();
}

function closeLogs() {
  state.logsDrawer = null;
  render();
}

async function openJob(id) {
  state.jobDrawer = {
    id,
    environment: "",
    project: "",
    action: "",
    status: "loading",
    log: "Loading job output...",
  };
  render();
  try {
    state.jobDrawer = await api(`/api/jobs/${id}?log_limit=120000`);
  } catch (error) {
    state.jobDrawer = {
      id,
      environment: "",
      project: "",
      action: "",
      status: "failed",
      error: error.message,
      log: error.message,
    };
  }
  render();
}

async function refreshOpenJob() {
  if (!state.jobDrawer?.id) return;
  await openJob(state.jobDrawer.id);
}

function upsertJob(job) {
  const index = state.jobs.findIndex((item) => item.id === job.id);
  if (index >= 0) state.jobs[index] = job;
  else state.jobs.unshift(job);
}

function closeJob() {
  state.jobDrawer = null;
  render();
}

async function addComponent(event, environment, project) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const mode = form.get("mode");
  const target = String(form.get("target") || "").trim();
  const payload = {
    name: String(form.get("name") || "").trim(),
    mode,
    port: Number(form.get("port")) || null,
  };
  if (mode === "compose") payload.compose_service = target;
  if (mode === "build") payload.build_context = target;
  if (mode === "image") payload.image = target;
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/components`, { method: "POST", body: JSON.stringify(payload) });
  await refreshProject(environment, project);
  render();
}

async function editComponent(environment, project, component) {
  const mode = prompt("Component mode: compose, build, image", component.mode || "compose");
  if (mode === null) return;
  const target = prompt("Compose service / build context / image", component.compose_service || component.build_context || component.image || "");
  if (target === null) return;
  const portText = prompt("Port, empty for none", component.port || "");
  if (portText === null) return;
  const payload = {
    name: component.name,
    mode,
    port: Number(portText) || null,
    env: component.env || {},
  };
  if (mode === "compose") payload.compose_service = target.trim();
  if (mode === "build") payload.build_context = target.trim();
  if (mode === "image") payload.image = target.trim();
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/components/${encodeURIComponent(component.name)}`, { method: "PATCH", body: JSON.stringify(payload) });
  await refreshProject(environment, project);
  render();
}

async function deleteComponent(environment, project, component) {
  if (!confirm(`Delete component ${component}? Endpoints attached to it will also be deleted.`)) return;
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/components/${encodeURIComponent(component)}`, { method: "DELETE" });
  await refreshProject(environment, project);
  render();
}

async function addEndpoint(event, environment, project) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    name: String(form.get("name") || "").trim(),
    component: String(form.get("component") || "").trim(),
    subdomain: String(form.get("subdomain") || "").trim(),
    port: Number(form.get("port")),
    auth: form.get("auth"),
    healthcheck_path: String(form.get("healthcheck_path") || "").trim() || null,
  };
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/endpoints`, { method: "POST", body: JSON.stringify(payload) });
  await refreshProject(environment, project);
  render();
}

async function editEndpoint(environment, project, endpoint) {
  const component = prompt("Component", endpoint.component || "");
  if (component === null) return;
  const subdomain = prompt("Subdomain, empty if using host", endpoint.subdomain || "");
  if (subdomain === null) return;
  const host = prompt("Host, empty if using subdomain", endpoint.host || "");
  if (host === null) return;
  const portText = prompt("Port", endpoint.port || "");
  if (portText === null) return;
  const auth = prompt("Auth: none or sso", endpoint.auth || "none");
  if (auth === null) return;
  const healthcheckPath = prompt("Health path, empty for none", endpoint.healthcheck_path || "");
  if (healthcheckPath === null) return;
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/endpoints/${encodeURIComponent(endpoint.name)}`, {
    method: "PATCH",
    body: JSON.stringify({
      name: endpoint.name,
      component: component.trim(),
      subdomain: subdomain.trim() || null,
      host: host.trim() || null,
      port: Number(portText),
      auth: auth.trim() || "none",
      middlewares: endpoint.middlewares || [],
      path_prefix: endpoint.path_prefix || null,
      healthcheck_path: healthcheckPath.trim() || null,
    }),
  });
  await refreshProject(environment, project);
  render();
}

async function deleteEndpoint(environment, project, endpoint) {
  if (!confirm(`Delete endpoint ${endpoint}?`)) return;
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/endpoints/${encodeURIComponent(endpoint)}`, { method: "DELETE" });
  await refreshProject(environment, project);
  render();
}

async function addDependency(event, environment, project) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const output = String(form.get("output") || "").trim();
  const outputs = {};
  if (output.includes("=")) {
    const [key, ...parts] = output.split("=");
    outputs[key] = parts.join("=");
  }
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/dependencies`, {
    method: "POST",
    body: JSON.stringify({
      name: String(form.get("name") || "").trim(),
      type: String(form.get("type") || "").trim(),
      target: String(form.get("target") || "").trim(),
      outputs,
    }),
  });
  await refreshProject(environment, project);
  render();
}

async function editDependency(environment, project, dependency) {
  const type = prompt("Dependency type", dependency.type || "");
  if (type === null) return;
  const target = prompt("Dependency target", dependency.target || "");
  if (target === null) return;
  const outputsText = prompt("Outputs JSON object", JSON.stringify(dependency.outputs || {}));
  if (outputsText === null) return;
  let outputs = {};
  try {
    outputs = outputsText.trim() ? JSON.parse(outputsText) : {};
  } catch (error) {
    setToast(`Invalid outputs JSON: ${error.message}`);
    return;
  }
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/dependencies/${encodeURIComponent(dependency.name)}`, {
    method: "PATCH",
    body: JSON.stringify({
      name: dependency.name,
      type: type.trim(),
      target: target.trim(),
      outputs,
    }),
  });
  await refreshProject(environment, project);
  render();
}

async function deleteDependency(environment, project, dependency) {
  if (!confirm(`Delete dependency ${dependency}?`)) return;
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/dependencies/${encodeURIComponent(dependency)}`, { method: "DELETE" });
  await refreshProject(environment, project);
  render();
}

async function setProjectEnv(event, environment, project) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}/env`, {
    method: "POST",
    body: JSON.stringify({
      key: String(form.get("key") || "").trim(),
      value: String(form.get("value") || ""),
    }),
  });
  await refreshProject(environment, project);
  render();
}

async function refreshProject(environment, project) {
  const detail = await api(`/api/environments/${encodeURIComponent(environment)}/projects/${encodeURIComponent(project)}`);
  const index = state.projects.findIndex((item) => item.environment === environment && item.name === project);
  if (index >= 0) state.projects[index] = detail;
  else state.projects.push(detail);
}

function setFilter(key, value) {
  state.filters[key] = value;
  render();
}

async function refreshData() {
  await loadAll();
  setToast("Refreshed");
}

async function refreshActivityOnly() {
  await refreshActivity();
  setToast("Activity refreshed");
}

function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  localStorage.setItem("deployer-theme", state.theme);
  document.documentElement.dataset.theme = state.theme;
  render();
}

loadAll();
