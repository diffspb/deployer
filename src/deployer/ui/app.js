const state = {
  services: [],
  jobs: [],
  currentView: "services",
  theme: localStorage.getItem("deployer-theme") || "light",
  toast: "",
  addOpen: false,
  addSourceType: "git",
  deployModal: null,
  envDrawer: null,
  logsDrawer: null,
  historyDrawer: null,
  serviceDrawer: null,
  jobsFilter: {
    service: "",
    environment: "",
  },
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
  git: "M7 7a2 2 0 104 0 2 2 0 00-4 0zm6 10a2 2 0 104 0 2 2 0 00-4 0zM9 9v2a4 4 0 004 4h2",
  gear: "M10.3 4.3c.4-1.7 2.9-1.7 3.4 0a1.7 1.7 0 002.5 1c1.5-.9 3.3.9 2.4 2.4a1.7 1.7 0 001 2.5c1.7.4 1.7 2.9 0 3.4a1.7 1.7 0 00-1 2.5c.9 1.5-.9 3.3-2.4 2.4a1.7 1.7 0 00-2.5 1c-.5 1.7-3 1.7-3.4 0a1.7 1.7 0 00-2.5-1c-1.5.9-3.3-.9-2.4-2.4a1.7 1.7 0 00-1-2.5c-1.7-.5-1.7-3 0-3.4a1.7 1.7 0 001-2.5c-.9-1.5.9-3.3 2.4-2.4a1.7 1.7 0 002.5-1zM12 9a3 3 0 100 6 3 3 0 000-6z",
  search: "M11 19a8 8 0 100-16 8 8 0 000 16zm10 2l-4.35-4.35",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  history: "M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8m9-4v8l4 2",
  file: "M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9zm0 0v6h6",
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

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.detail || `HTTP ${response.status}`);
  }
  return data;
}

function serviceColor(name) {
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

function serviceInitials(name) {
  return name
    .split("-")
    .map((part) => part[0])
    .join("")
    .slice(0, 3);
}

function shortCommit(value) {
  return value ? value.slice(0, 7) : "-";
}

function formatTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatSource(service) {
  return service.source_url || service.source_path || "-";
}

function envSummary(service, name) {
  return service.environments?.find((env) => env.name === name) || {};
}

function serviceByName(name) {
  return state.services.find((service) => service.name === name) || null;
}

function latestRuntimeJob(serviceName, environment) {
  return state.jobs.find((job) => job.service === serviceName && job.environment === environment);
}

function activeJobForRuntime(serviceName, environment) {
  return state.jobs.find(
    (job) =>
      job.service === serviceName &&
      job.environment === environment &&
      ["queued", "running"].includes(job.status),
  );
}

function runtimeStatusBadge(service, environment) {
  const activeJob = activeJobForRuntime(service.name, environment);
  const latestJob = latestRuntimeJob(service.name, environment);
  const env = envSummary(service, environment);
  if (activeJob) {
    return `<span class="badge running"><span class="dot"></span>${escapeHtml(activeJob.action)} ${escapeHtml(activeJob.status)}</span>`;
  }
  if (latestJob) {
    return jobBadge(latestJob.status, latestJob.action);
  }
  if (env.current_ref || env.current_version) {
    return `<span class="badge"><span class="dot"></span>configured</span>`;
  }
  return `<span class="badge"><span class="dot"></span>idle</span>`;
}

function sourceBadge(service) {
  const status = service.source_status;
  if (!status) return `<span class="badge">${escapeHtml(service.source_type)}</span>`;
  if (!status.available) return `<span class="badge failed"><span class="dot"></span>source failed</span>`;
  return `<span class="badge success"><span class="dot"></span>${service.source_type === "git" ? "fetched" : "source ok"}</span>`;
}

function jobBadge(status, action = "") {
  const cls =
    status === "success"
      ? "success"
      : status === "failed"
        ? "failed"
        : status === "running"
          ? "running"
          : "queued";
  return `<span class="badge ${cls}"><span class="dot"></span>${escapeHtml(action ? `${action} ${status}` : status || "unknown")}</span>`;
}

function environmentLabel(name) {
  return name === "prod" ? "Production" : "Development";
}

function defaultRef(service, environment) {
  if (environment === "prod") return service.default_branch || "main";
  return envSummary(service, "dev").current_ref || "develop";
}

async function loadAll() {
  const [services, jobs] = await Promise.all([api("/api/services"), api("/api/jobs?limit=100")]);
  const details = await Promise.all(services.map((service) => api(`/api/services/${service.name}`)));
  state.services = details;
  state.jobs = jobs.jobs || [];
  syncOverlayState();
  render();
}

function syncOverlayState() {
  if (state.serviceDrawer && !serviceByName(state.serviceDrawer.service)) state.serviceDrawer = null;
  if (state.envDrawer && !serviceByName(state.envDrawer.service)) state.envDrawer = null;
  if (state.logsDrawer && !serviceByName(state.logsDrawer.service)) state.logsDrawer = null;
  if (state.historyDrawer && !serviceByName(state.historyDrawer.service)) state.historyDrawer = null;
  if (state.deployModal && !serviceByName(state.deployModal.service)) state.deployModal = null;
  if (state.jobsFilter.service && !serviceByName(state.jobsFilter.service)) state.jobsFilter.service = "";
}

function setToast(message) {
  state.toast = message;
  render();
  setTimeout(() => {
    if (state.toast === message) {
      state.toast = "";
      render();
    }
  }, 3500);
}

function render() {
  root.innerHTML = `
    <div class="app-shell">
      ${renderSidebar()}
      <main class="main">
        ${renderTopbar()}
        <section class="content">
          ${state.currentView === "jobs" ? renderJobsView() : renderServicesView()}
        </section>
      </main>
      ${state.serviceDrawer ? renderServiceDrawer() : ""}
      ${state.envDrawer ? renderEnvDrawer() : ""}
      ${state.logsDrawer ? renderLogsDrawer() : ""}
      ${state.historyDrawer ? renderHistoryDrawer() : ""}
      ${state.addOpen ? renderAddPanel() : ""}
      ${state.deployModal ? renderDeployModal() : ""}
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
          <div class="brand-subtitle">personal control plane</div>
        </div>
      </div>
      <div class="nav-block">
        <div class="nav-label">Workspace</div>
        <button class="nav-item ${state.currentView === "services" ? "active" : ""}" onclick="setView('services')">${icon("server")} Services</button>
        <button class="nav-item ${state.currentView === "jobs" ? "active" : ""}" onclick="setView('jobs')">${icon("list")} Jobs</button>
      </div>
      <div class="nav-block service-list">
        <div class="nav-label">Catalog</div>
        ${state.services.map((service) => `
          <button class="nav-item" onclick="scrollToService('${escapeHtml(service.name)}')">
            <span class="dot" style="color:${serviceColor(service.name)}"></span>
            <span class="ellipsis">${escapeHtml(service.name)}</span>
          </button>
        `).join("")}
      </div>
      <div class="nav-block">
        <button class="nav-item" onclick="toggleTheme()">${icon(state.theme === "dark" ? "sun" : "moon")} ${state.theme === "dark" ? "Light theme" : "Dark theme"}</button>
      </div>
    </aside>
  `;
}

function renderTopbar() {
  const activeJobs = state.jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  const failedJobs = state.jobs.filter((job) => job.status === "failed").length;
  return `
    <header class="topbar">
      <div>
        <h1>${state.currentView === "jobs" ? "Runtime jobs" : "Services dashboard"}</h1>
        <div class="hint">${state.services.length} services · ${activeJobs} active jobs · ${failedJobs} failed jobs</div>
      </div>
      <div class="spacer"></div>
      <button class="btn secondary" onclick="refreshData()">${icon("refresh")} Refresh</button>
      ${state.currentView === "services" ? `<button class="btn primary" onclick="openAddService()">${icon("plus")} Add service</button>` : ""}
    </header>
  `;
}

function renderServicesView() {
  const successful = state.jobs.filter((job) => job.status === "success").length;
  const failed = state.jobs.filter((job) => job.status === "failed").length;
  return `
    <div class="toolbar">
      <div>
        <div class="headline">Runtime targets</div>
        <div class="muted">Each service owns two independent runtime targets: <span class="mono">prod</span> and <span class="mono">dev</span>.</div>
      </div>
      <div class="row wrap">
        <span class="badge success"><span class="dot"></span>${successful} successful</span>
        <span class="badge failed"><span class="dot"></span>${failed} failed</span>
      </div>
    </div>
    ${state.services.length ? `<div class="service-stack">${state.services.map(renderServiceRow).join("")}</div>` : renderEmpty()}
  `;
}

function renderServiceRow(service) {
  const color = serviceColor(service.name);
  return `
    <article class="service-row card" id="service-${escapeHtml(service.name)}">
      <div class="service-row-header">
        <div class="service-title">
          <div class="service-icon" style="background:${color}">${escapeHtml(serviceInitials(service.name))}</div>
          <div class="service-heading">
            <h2 class="service-name">${escapeHtml(service.name)}</h2>
            <div class="muted mono ellipsis">${escapeHtml(formatSource(service))}</div>
          </div>
        </div>
        <div class="service-meta">
          <div class="row wrap">
            ${sourceBadge(service)}
            ${service.source_status?.current_ref ? `<span class="badge">${escapeHtml(service.source_status.current_ref)}</span>` : ""}
            ${service.source_status?.current_commit ? `<span class="badge mono">${escapeHtml(shortCommit(service.source_status.current_commit))}</span>` : ""}
          </div>
          <div class="row">
            <button class="btn ghost" onclick="openServiceDrawer('${escapeHtml(service.name)}')">${icon("gear")} Source</button>
          </div>
        </div>
      </div>
      ${service.source_status?.error ? `<div class="inline-error">${escapeHtml(service.source_status.error)}</div>` : ""}
      <div class="runtime-grid">
        ${renderRuntimeCard(service, "prod")}
        ${renderRuntimeCard(service, "dev")}
      </div>
    </article>
  `;
}

function renderRuntimeCard(service, environment) {
  const env = envSummary(service, environment);
  const job = latestRuntimeJob(service.name, environment);
  const envCount = Object.keys(env.env || {}).length;
  return `
    <section class="runtime-card">
      <div class="runtime-head">
        <div>
          <div class="runtime-label">${escapeHtml(environmentLabel(environment))}</div>
          <div class="runtime-name mono">${escapeHtml(service.name)}/${escapeHtml(environment)}</div>
        </div>
        ${runtimeStatusBadge(service, environment)}
      </div>
      <div class="runtime-facts">
        <div class="fact">
          <span class="fact-label">Subdomain</span>
          <span class="fact-value mono">${escapeHtml(env.subdomain || service.name)}</span>
        </div>
        <div class="fact">
          <span class="fact-label">Ref</span>
          <span class="fact-value mono">${escapeHtml(env.current_ref || env.current_version || "-")}</span>
        </div>
        <div class="fact">
          <span class="fact-label">Commit</span>
          <span class="fact-value mono">${escapeHtml(shortCommit(env.current_commit))}</span>
        </div>
        <div class="fact">
          <span class="fact-label">Env vars</span>
          <span class="fact-value">${envCount}</span>
        </div>
        <div class="fact">
          <span class="fact-label">Last deploy</span>
          <span class="fact-value mono">${escapeHtml(env.last_deployment_id ? `#${env.last_deployment_id}` : "-")}</span>
        </div>
        <div class="fact">
          <span class="fact-label">Last job</span>
          <span class="fact-value">${job ? jobBadge(job.status, job.action) : `<span class="subtle">none</span>`}</span>
        </div>
      </div>
      <div class="runtime-actions">
        <button class="btn primary" onclick="openDeployModal('${escapeHtml(service.name)}', '${escapeHtml(environment)}')">${icon("play")} Deploy</button>
        <button class="btn secondary" onclick="runtimeAction('${escapeHtml(service.name)}', 'restart', '${escapeHtml(environment)}')">${icon("refresh")} Restart</button>
        <button class="btn secondary" onclick="runtimeAction('${escapeHtml(service.name)}', 'stop', '${escapeHtml(environment)}')">${icon("stop")} Stop</button>
        <button class="btn danger" onclick="runtimeAction('${escapeHtml(service.name)}', 'down', '${escapeHtml(environment)}')">${icon("trash")} Down</button>
        <button class="btn secondary" onclick="openLogsDrawer('${escapeHtml(service.name)}', '${escapeHtml(environment)}')">${icon("list")} Logs</button>
        <button class="btn secondary" onclick="openEnvDrawer('${escapeHtml(service.name)}', '${escapeHtml(environment)}')">${icon("gear")} Env</button>
        <button class="btn secondary" onclick="openHistoryDrawer('${escapeHtml(service.name)}', '${escapeHtml(environment)}')">${icon("history")} History</button>
      </div>
    </section>
  `;
}

function renderJobsView() {
  const filtered = state.jobs.filter((job) => {
    if (state.jobsFilter.service && job.service !== state.jobsFilter.service) return false;
    if (state.jobsFilter.environment && job.environment !== state.jobsFilter.environment) return false;
    return true;
  });
  return `
    <div class="toolbar">
      <div>
        <div class="headline">Job activity</div>
        <div class="muted">Recent deploy, restart, stop and down operations across all runtime targets.</div>
      </div>
    </div>
    <div class="filter-bar card">
      <div class="field grow">
        <label>Service</label>
        <select class="select" onchange="setJobsFilter('service', this.value)">
          <option value="">all services</option>
          ${state.services.map((service) => `<option value="${escapeHtml(service.name)}" ${state.jobsFilter.service === service.name ? "selected" : ""}>${escapeHtml(service.name)}</option>`).join("")}
        </select>
      </div>
      <div class="field grow">
        <label>Environment</label>
        <select class="select" onchange="setJobsFilter('environment', this.value)">
          <option value="">all environments</option>
          <option value="prod" ${state.jobsFilter.environment === "prod" ? "selected" : ""}>prod</option>
          <option value="dev" ${state.jobsFilter.environment === "dev" ? "selected" : ""}>dev</option>
        </select>
      </div>
    </div>
    <div class="table">
      <div class="table-row table-head jobs-table-head">
        <div>Service</div>
        <div>Action</div>
        <div>Status</div>
        <div>Target</div>
        <div>Ref</div>
        <div>Finished</div>
      </div>
      ${filtered.length ? filtered.map(renderGlobalJobRow).join("") : `<div class="table-empty muted">No jobs match the current filters.</div>`}
    </div>
  `;
}

function renderGlobalJobRow(job) {
  return `
    <div class="table-row jobs-table-row">
      <div class="mono">${escapeHtml(job.service)}</div>
      <div class="mono">${escapeHtml(job.action)}</div>
      <div>${jobBadge(job.status)}</div>
      <div class="mono">${escapeHtml(job.environment)}</div>
      <div class="mono">${escapeHtml(job.ref || job.version || "-")}</div>
      <div class="subtle">${escapeHtml(formatTime(job.finished_at || job.started_at || job.created_at))}</div>
    </div>
  `;
}

function renderEmpty() {
  return `
    <div class="empty">
      <div class="service-icon" style="background:var(--primary)">P</div>
      <div style="font-weight:800;font-size:18px">No services yet</div>
      <div>Add a git-backed service or a local service for debugging.</div>
      <button class="btn primary" onclick="openAddService()">${icon("plus")} Add first service</button>
    </div>
  `;
}

function renderServiceDrawer() {
  const service = serviceByName(state.serviceDrawer.service);
  if (!service) return "";
  return `
    <div class="overlay-backdrop" onclick="closeServiceDrawer()"></div>
    <aside class="drawer">
      <div class="drawer-header">
        <div class="row">
          <div class="service-icon" style="background:${serviceColor(service.name)}">${escapeHtml(serviceInitials(service.name))}</div>
          <div>
            <div class="drawer-title">${escapeHtml(service.name)}</div>
            <div class="muted">Source definition and shared settings.</div>
          </div>
          <div class="spacer"></div>
          <button class="btn ghost" onclick="closeServiceDrawer()">${icon("close")}</button>
        </div>
      </div>
      <div class="drawer-body">
        <div class="section">
          <div class="section-title">Source</div>
          <div class="field"><label>Source type</label><input class="input" value="${escapeHtml(service.source_type)}" disabled></div>
          <div class="field"><label>Source</label><input class="input mono" value="${escapeHtml(formatSource(service))}" disabled></div>
          <div class="field"><label>Default branch</label><input class="input mono" value="${escapeHtml(service.default_branch || "")}" disabled></div>
          <div class="field"><label>Managed checkout</label><input class="input mono" value="${escapeHtml(service.source_path)}" disabled></div>
          <div class="field"><label>Current ref</label><input class="input mono" value="${escapeHtml(service.source_status?.current_ref || "")}" disabled></div>
          <div class="field"><label>Current commit</label><input class="input mono" value="${escapeHtml(service.source_status?.current_commit || "")}" disabled></div>
          ${service.source_status?.error ? `<div class="field"><label>Source error</label><textarea class="textarea mono" disabled>${escapeHtml(service.source_status.error)}</textarea></div>` : ""}
        </div>
        <div class="section">
          <div class="section-title">Danger zone</div>
          <button class="btn danger" onclick="removeService('${escapeHtml(service.name)}')">${icon("trash")} Remove service from catalog</button>
        </div>
      </div>
    </aside>
  `;
}

function renderEnvDrawer() {
  const service = serviceByName(state.envDrawer.service);
  if (!service) return "";
  const environment = state.envDrawer.environment;
  const env = envSummary(service, environment);
  const pairs = Object.entries(env.env || {});
  return `
    <div class="overlay-backdrop" onclick="closeEnvDrawer()"></div>
    <aside class="drawer">
      <div class="drawer-header">
        <div class="row">
          <div>
            <div class="drawer-title">Env: ${escapeHtml(service.name)}/${escapeHtml(environment)}</div>
            <div class="muted">Environment variables are scoped to one runtime target.</div>
          </div>
          <div class="spacer"></div>
          <button class="btn ghost" onclick="closeEnvDrawer()">${icon("close")}</button>
        </div>
      </div>
      <div class="drawer-body">
        <form onsubmit="saveEnvVar(event, '${escapeHtml(service.name)}', '${escapeHtml(environment)}')" class="inline-form">
          <input class="input mono" name="key" placeholder="KEY" required>
          <input class="input mono" name="value" placeholder="value" required>
          <button class="btn primary" type="submit">${icon("plus")} Set</button>
        </form>
        <div class="table">
          <div class="table-row table-head env-table-head"><div>Key</div><div>Value</div><div></div></div>
          ${pairs.length ? pairs.map(([key, value]) => `
            <div class="table-row env-table-row">
              <div class="mono">${escapeHtml(key)}</div>
              <div class="mono value-wrap">${escapeHtml(value)}</div>
              <button class="btn ghost" onclick="unsetEnvVar('${escapeHtml(service.name)}', '${escapeHtml(environment)}', '${escapeHtml(key)}')">unset</button>
            </div>
          `).join("") : `<div class="table-empty muted">No variables configured for ${escapeHtml(service.name)}/${escapeHtml(environment)}.</div>`}
        </div>
      </div>
    </aside>
  `;
}

function renderLogsDrawer() {
  const drawer = state.logsDrawer;
  const service = serviceByName(drawer.service);
  if (!service) return "";
  return `
    <div class="overlay-backdrop" onclick="closeLogsDrawer()"></div>
    <aside class="drawer drawer-wide">
      <div class="drawer-header">
        <div class="row">
          <div>
            <div class="drawer-title">Logs: ${escapeHtml(drawer.service)}/${escapeHtml(drawer.environment)}</div>
            <div class="muted">Runtime logs and compose status for one target.</div>
          </div>
          <div class="spacer"></div>
          <button class="btn secondary" onclick="reloadLogsDrawer()">${icon("refresh")} Reload</button>
          <button class="btn ghost" onclick="closeLogsDrawer()">${icon("close")}</button>
        </div>
      </div>
      <div class="drawer-body">
        <div class="section">
          <div class="section-title">Status</div>
          <pre class="log-box compact">${escapeHtml(drawer.statusText || (drawer.loading ? "Loading status..." : "No status loaded."))}</pre>
        </div>
        <div class="section">
          <div class="section-title">Logs</div>
          <pre class="log-box">${escapeHtml(drawer.log || (drawer.loading ? "Loading logs..." : "No log output yet."))}</pre>
        </div>
      </div>
    </aside>
  `;
}

function renderHistoryDrawer() {
  const drawer = state.historyDrawer;
  const service = serviceByName(drawer.service);
  if (!service) return "";
  return `
    <div class="overlay-backdrop" onclick="closeHistoryDrawer()"></div>
    <aside class="drawer drawer-wide">
      <div class="drawer-header">
        <div class="row">
          <div>
            <div class="drawer-title">History: ${escapeHtml(drawer.service)}/${escapeHtml(drawer.environment)}</div>
            <div class="muted">Deployment history for one runtime target.</div>
          </div>
          <div class="spacer"></div>
          <button class="btn secondary" onclick="reloadHistoryDrawer()">${icon("refresh")} Reload</button>
          <button class="btn ghost" onclick="closeHistoryDrawer()">${icon("close")}</button>
        </div>
      </div>
      <div class="drawer-body">
        <div class="table">
          <div class="table-row table-head history-table-head">
            <div>ID</div>
            <div>Action</div>
            <div>Status</div>
            <div>Version</div>
            <div>Finished</div>
          </div>
          ${drawer.loading
            ? `<div class="table-empty muted">Loading history...</div>`
            : drawer.deployments.length
              ? drawer.deployments.map(renderHistoryRow).join("")
              : `<div class="table-empty muted">No deployments for ${escapeHtml(drawer.service)}/${escapeHtml(drawer.environment)}.</div>`}
        </div>
      </div>
    </aside>
  `;
}

function renderHistoryRow(record) {
  return `
    <div class="table-row history-table-row">
      <div class="mono">#${escapeHtml(record.id)}</div>
      <div class="mono">${escapeHtml(record.action)}</div>
      <div>${jobBadge(record.status)}</div>
      <div class="mono">${escapeHtml(record.version || "-")}</div>
      <div class="subtle">${escapeHtml(formatTime(record.finished_at || record.started_at))}</div>
    </div>
  `;
}

function renderAddPanel() {
  return `
    <div class="overlay-backdrop" onclick="closeAddService()"></div>
    <aside class="drawer">
      <div class="drawer-header">
        <div class="row">
          <div>
            <div class="drawer-title">Add service</div>
            <div class="muted">Register a git source or a local debug project.</div>
          </div>
          <div class="spacer"></div>
          <button class="btn ghost" onclick="closeAddService()">${icon("close")}</button>
        </div>
      </div>
      <div class="drawer-body">
        <form onsubmit="createService(event)">
          <div class="field"><label>Name</label><input class="input mono" name="name" placeholder="my-service" required></div>
          <div class="field">
            <label>Source type</label>
            <select class="select" name="source_type" onchange="setAddSourceType(this.value)">
              <option value="git" ${state.addSourceType === "git" ? "selected" : ""}>git</option>
              <option value="local" ${state.addSourceType === "local" ? "selected" : ""}>local</option>
            </select>
          </div>
          ${state.addSourceType === "git"
            ? `
              <div class="field"><label>Git URL</label><input class="input mono" name="git_url" placeholder="git@example.com:me/app.git" required></div>
              <div class="field"><label>Default branch</label><input class="input mono" name="default_branch" placeholder="main"></div>
            `
            : `
              <div class="field"><label>Local path</label><input class="input mono" name="path" placeholder="/tmp/paas-test-app" required></div>
            `}
          <div class="row actions-end">
            <button type="button" class="btn ghost" onclick="closeAddService()">Cancel</button>
            <button class="btn primary" type="submit">${icon("plus")} Add service</button>
          </div>
        </form>
      </div>
    </aside>
  `;
}

function renderDeployModal() {
  const modal = state.deployModal;
  const service = serviceByName(modal.service);
  if (!service) return "";
  return `
    <div class="overlay-backdrop modal-backdrop" onclick="closeDeployModal()"></div>
    <div class="modal">
      <div class="modal-header">
        <div>
          <div class="drawer-title">Deploy ${escapeHtml(modal.service)}/${escapeHtml(modal.environment)}</div>
          <div class="muted">The runtime target is fixed. Choose only the git ref to deploy.</div>
        </div>
        <button class="btn ghost" onclick="closeDeployModal()">${icon("close")}</button>
      </div>
      <form class="modal-body" onsubmit="submitDeploy(event)">
        <div class="field">
          <label>Ref / branch / tag / commit</label>
          <input class="input mono" name="ref" value="${escapeHtml(modal.ref)}" list="deploy-refs" required>
          <datalist id="deploy-refs">
            ${(modal.refs || []).map((item) => `<option value="${escapeHtml(item.name)}"></option>`).join("")}
          </datalist>
        </div>
        <div class="field">
          <label>Source status</label>
          <input class="input" value="${escapeHtml(service.source_status?.available ? "source fetched" : "source unavailable")}" disabled>
        </div>
        ${modal.error ? `<div class="inline-error">${escapeHtml(modal.error)}</div>` : ""}
        <div class="row actions-end">
          <button type="button" class="btn ghost" onclick="closeDeployModal()">Cancel</button>
          <button class="btn primary" type="submit">${icon("play")} Deploy</button>
        </div>
      </form>
    </div>
  `;
}

function refreshData() {
  loadAll()
    .then(() => setToast("Data refreshed"))
    .catch((error) => setToast(error.message));
}

function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  localStorage.setItem("deployer-theme", state.theme);
  document.documentElement.dataset.theme = state.theme;
  render();
}

function setView(view) {
  state.currentView = view;
  render();
}

function scrollToService(name) {
  state.currentView = "services";
  render();
  requestAnimationFrame(() => {
    const element = document.getElementById(`service-${name}`);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
}

function setJobsFilter(key, value) {
  state.jobsFilter[key] = value;
  render();
}

function openAddService() {
  state.addOpen = true;
  render();
}

function closeAddService() {
  state.addOpen = false;
  render();
}

function setAddSourceType(sourceType) {
  state.addSourceType = sourceType;
  render();
}

function openServiceDrawer(service) {
  state.serviceDrawer = { service };
  render();
}

function closeServiceDrawer() {
  state.serviceDrawer = null;
  render();
}

function openEnvDrawer(service, environment) {
  state.envDrawer = { service, environment };
  render();
}

function closeEnvDrawer() {
  state.envDrawer = null;
  render();
}

async function openLogsDrawer(service, environment) {
  state.logsDrawer = {
    service,
    environment,
    loading: true,
    log: "",
    statusText: "",
  };
  render();
  await reloadLogsDrawer();
}

function closeLogsDrawer() {
  state.logsDrawer = null;
  render();
}

async function reloadLogsDrawer() {
  if (!state.logsDrawer) return;
  const { service, environment } = state.logsDrawer;
  state.logsDrawer = { ...state.logsDrawer, loading: true };
  render();
  try {
    const [logs, status] = await Promise.all([
      api(`/api/services/${service}/logs?environment=${environment}&tail=300`),
      api(`/api/services/${service}/status?environment=${environment}`),
    ]);
    state.logsDrawer = {
      service,
      environment,
      loading: false,
      log: logs.log,
      statusText: status.log,
    };
    render();
  } catch (error) {
    state.logsDrawer = {
      service,
      environment,
      loading: false,
      log: `Error: ${error.message}`,
      statusText: `Error: ${error.message}`,
    };
    render();
  }
}

async function openHistoryDrawer(service, environment) {
  state.historyDrawer = {
    service,
    environment,
    loading: true,
    deployments: [],
  };
  render();
  await reloadHistoryDrawer();
}

function closeHistoryDrawer() {
  state.historyDrawer = null;
  render();
}

async function reloadHistoryDrawer() {
  if (!state.historyDrawer) return;
  const { service, environment } = state.historyDrawer;
  state.historyDrawer = { ...state.historyDrawer, loading: true };
  render();
  try {
    const history = await api(`/api/services/${service}/history?environment=${environment}&limit=50`);
    state.historyDrawer = {
      service,
      environment,
      loading: false,
      deployments: history.deployments || [],
    };
    render();
  } catch (error) {
    state.historyDrawer = {
      service,
      environment,
      loading: false,
      deployments: [],
    };
    setToast(error.message);
  }
}

async function openDeployModal(service, environment) {
  const svc = serviceByName(service);
  state.deployModal = {
    service,
    environment,
    ref: svc ? defaultRef(svc, environment) : "",
    refs: [],
    error: "",
  };
  render();
  try {
    const response = await api(`/api/services/${service}/refs`);
    if (!state.deployModal || state.deployModal.service !== service || state.deployModal.environment !== environment) {
      return;
    }
    state.deployModal = {
      ...state.deployModal,
      refs: response.refs || [],
    };
    render();
  } catch (error) {
    if (!state.deployModal) return;
    state.deployModal = {
      ...state.deployModal,
      error: error.message,
    };
    render();
  }
}

function closeDeployModal() {
  state.deployModal = null;
  render();
}

async function submitDeploy(event) {
  event.preventDefault();
  if (!state.deployModal) return;
  const form = new FormData(event.target);
  const ref = String(form.get("ref") || "").trim();
  if (!ref) {
    setToast("Ref is required");
    return;
  }
  const { service, environment } = state.deployModal;
  closeDeployModal();
  await scheduleJob(service, "deploy", environment, { ref });
}

async function createService(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = Object.fromEntries(form.entries());
  Object.keys(payload).forEach((key) => {
    if (payload[key] === "") delete payload[key];
  });
  try {
    await api("/api/services", { method: "POST", body: JSON.stringify(payload) });
    state.addOpen = false;
    await loadAll();
    setToast(`Service ${payload.name} added`);
  } catch (error) {
    setToast(error.message);
  }
}

async function saveEnvVar(event, service, environment) {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api(`/api/services/${service}/env/${environment}`, {
      method: "POST",
      body: JSON.stringify({ key: form.get("key"), value: form.get("value") }),
    });
    event.target.reset();
    await loadAll();
    setToast(`Environment variable saved for ${service}/${environment}`);
  } catch (error) {
    setToast(error.message);
  }
}

async function unsetEnvVar(service, environment, key) {
  try {
    await api(`/api/services/${service}/env/${environment}/${encodeURIComponent(key)}`, { method: "DELETE" });
    await loadAll();
    setToast(`Environment variable removed from ${service}/${environment}`);
  } catch (error) {
    setToast(error.message);
  }
}

async function runtimeAction(service, action, environment) {
  if (["down", "stop"].includes(action) && !confirm(`${action} ${service}/${environment}?`)) return;
  await scheduleJob(service, action, environment);
}

async function scheduleJob(service, action, environment, extra = {}) {
  try {
    const job = await api(`/api/services/${service}/${action}`, {
      method: "POST",
      body: JSON.stringify({ environment, dry_run: false, ...extra }),
    });
    setToast(`${action} job #${job.id} scheduled for ${service}/${environment}`);
    await pollJob(job.id, service, environment);
  } catch (error) {
    setToast(error.message);
  }
}

async function pollJob(jobId, service, environment) {
  for (let i = 0; i < 60; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, i === 0 ? 250 : 1500));
    const job = await api(`/api/jobs/${jobId}`);
    await loadAll();
    if (["success", "failed"].includes(job.status)) {
      if (state.logsDrawer && state.logsDrawer.service === service && state.logsDrawer.environment === environment) {
        await reloadLogsDrawer();
      }
      if (state.historyDrawer && state.historyDrawer.service === service && state.historyDrawer.environment === environment) {
        await reloadHistoryDrawer();
      }
      setToast(`Job #${job.id}: ${job.status}`);
      return;
    }
  }
  setToast(`Job #${jobId} is still running`);
}

async function removeService(name) {
  if (!confirm(`Remove ${name} from the catalog?`)) return;
  try {
    await api(`/api/services/${name}`, { method: "DELETE" });
    closeServiceDrawer();
    await loadAll();
    setToast(`Service ${name} removed`);
  } catch (error) {
    setToast(error.message);
  }
}

loadAll().catch((error) => {
  root.innerHTML = `<div class="empty" style="height:100%"><div style="font-weight:800">Failed to load deployer UI</div><div class="muted">${escapeHtml(error.message)}</div></div>`;
});
