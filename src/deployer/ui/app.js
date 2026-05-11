function loadStoredJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

const state = {
  services: [],
  jobs: [],
  currentView: { name: "services" },
  theme: localStorage.getItem("deployer-theme") || "light",
  toast: "",
  addOpen: false,
  addSourceType: "git",
  deployModal: null,
  logsDrawer: null,
  historyDrawer: null,
  jobDrawer: null,
  actionMenu: null,
  expandedServices: {},
  servicesFilter: loadStoredJson("deployer-services-filter", {
    query: "",
    environment: "",
    status: "",
  }),
  jobsFilter: loadStoredJson("deployer-jobs-filter", {
    query: "",
    service: "",
    environment: "",
    status: "",
  }),
  runtimePreview: {},
  runtimeStatus: {},
  loadError: "",
};

const root = document.getElementById("deployer-root");
document.documentElement.dataset.theme = state.theme;
const ACTION_MENU_WIDTH = 180;
const ACTION_MENU_HEIGHT = 240;
const ACTION_MENU_GAP = 6;
const ACTION_MENU_VIEWPORT_PADDING = 8;

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
  gear: "M10.3 4.3c.4-1.7 2.9-1.7 3.4 0a1.7 1.7 0 002.5 1c1.5-.9 3.3.9 2.4 2.4a1.7 1.7 0 001 2.5c1.7.4 1.7 2.9 0 3.4a1.7 1.7 0 00-1 2.5c.9 1.5-.9 3.3-2.4 2.4a1.7 1.7 0 00-2.5 1c-.5 1.7-3 1.7-3.4 0a1.7 1.7 0 00-2.5-1c-1.5.9-3.3-.9-2.4-2.4a1.7 1.7 0 00-1-2.5c-1.7-.5-1.7-3 0-3.4a1.7 1.7 0 001-2.5c-.9-1.5.9-3.3 2.4-2.4a1.7 1.7 0 002.5-1zM12 9a3 3 0 100 6 3 3 0 000-6z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  history: "M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8m9-4v8l4 2",
  chevronDown: "M6 9l6 6 6-6",
  chevronRight: "M9 6l6 6-6 6",
  external: "M14 5h5v5M10 14L19 5M19 14v5H5V5h5",
  more: "M12 5h.01M12 12h.01M12 19h.01",
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

function runtimeKey(service, environment) {
  return `${service}/${environment}`;
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

function matchesQuery(parts, query) {
  if (!query) return true;
  const lowered = query.toLowerCase();
  return parts.some((part) => String(part ?? "").toLowerCase().includes(lowered));
}

function environmentLabel(name) {
  return name;
}

function envSummary(service, environment) {
  return service.environments?.find((item) => item.name === environment) || {};
}

function deployPolicyLabel(env) {
  if (!env?.deploy_mode || env.deploy_mode === "manual") return "manual";
  const source = env.deploy_source || "-";
  const pattern = env.deploy_pattern || "-";
  const patternType = env.deploy_pattern_type || "-";
  return `${env.deploy_mode} · ${source} · ${patternType} · ${pattern}`;
}

function serviceEnvironmentNames(service) {
  return (service.environments || []).map((environment) => environment.name);
}

function allEnvironmentNames() {
  return [...new Set([
    ...state.services.flatMap(serviceEnvironmentNames),
    ...state.jobs.map((job) => job.environment).filter(Boolean),
  ])].sort((a, b) => a.localeCompare(b));
}

function serviceByName(name) {
  return state.services.find((service) => service.name === name) || null;
}

function runtimeByName(serviceName, environment) {
  const service = serviceByName(serviceName);
  if (!service) return null;
  const summary = envSummary(service, environment);
  if (!summary.name) return null;
  return { service, environment: summary };
}

function runtimeUrl(serviceName, environment) {
  const runtime = runtimeByName(serviceName, environment);
  return runtime?.environment.public_url || null;
}

function latestRuntimeJob(serviceName, environment) {
  return state.jobs.find((job) => job.service === serviceName && job.environment === environment);
}

function latestVisibleFailure(serviceName, environment) {
  const job = state.jobs.find(
    (item) =>
      item.service === serviceName &&
      item.environment === environment &&
      ["success", "failed"].includes(item.status),
  );
  return job?.status === "failed" ? job : null;
}

function activeJobForRuntime(serviceName, environment) {
  return state.jobs.find(
    (job) =>
      job.service === serviceName &&
      job.environment === environment &&
      ["queued", "running"].includes(job.status),
  );
}

function upsertJob(job) {
  const index = state.jobs.findIndex((item) => item.id === job.id);
  if (index >= 0) {
    state.jobs[index] = job;
  } else {
    state.jobs = [job, ...state.jobs];
  }
  if (state.jobDrawer?.id === job.id) {
    state.jobDrawer = job;
  }
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

function parseRuntimeStatus(serviceName, environment, response) {
  const summary = response?.summary || {};
  const raw = String(response?.log || "");
  const running = Boolean(summary.running);
  const states = Array.isArray(summary.containers) ? summary.containers.map((item) => item.state) : [];
  const stopped = states.some((value) => ["exited", "stopped", "dead", "created", "removing"].includes(value));
  const health = summary.health || "unknown";
  return {
    service: serviceName,
    environment,
    loading: false,
    available: response?.status === "success",
    running,
    state: running ? "running" : stopped || response?.status === "success" ? "stopped" : "unknown",
    health,
    raw,
  };
}

function runtimeStatus(serviceName, environment) {
  return (
    state.runtimeStatus[runtimeKey(serviceName, environment)] || {
      loading: true,
      available: false,
      running: false,
      state: "unknown",
      health: "unknown",
      raw: "",
    }
  );
}

function runtimePreview(serviceName, environment) {
  return (
    state.runtimePreview[runtimeKey(serviceName, environment)] || {
      loading: true,
      valid: false,
      errors: [],
      source_path: "",
      manifest_path: "",
      compose_files: [],
      public_url: null,
      env_file_path: "",
      env_file_content: "",
      override_path: "",
      override_content: "",
    }
  );
}

function renderValidationErrors(errors) {
  if (!errors?.length) return "";
  return `
    <div class="inline-error">
      <div class="error-title">Validation errors</div>
      <div class="error-list">
        ${errors.map((item) => `<div><span class="mono">${escapeHtml(item.scope)}</span>: ${escapeHtml(item.message)}</div>`).join("")}
      </div>
    </div>
  `;
}

function renderPreviewSummary(serviceName, environment) {
  const preview = runtimePreview(serviceName, environment);
  if (preview.loading) {
    return `<span class="badge"><span class="dot"></span>checking config</span>`;
  }
  if (preview.valid) {
    return `<span class="badge success"><span class="dot"></span>config valid</span>`;
  }
  return `<span class="badge failed"><span class="dot"></span>config invalid</span>`;
}

function renderRuntimeStatus(serviceName, environment) {
  const summary = runtimeStatus(serviceName, environment);
  if (summary.loading) {
    return `<div class="status-stack"><span class="badge"><span class="dot"></span>loading</span></div>`;
  }
  const stateBadge =
    summary.state === "running"
      ? `<span class="badge success"><span class="dot"></span>running</span>`
      : summary.state === "stopped"
        ? `<span class="badge"><span class="dot"></span>stopped</span>`
        : `<span class="badge failed"><span class="dot"></span>unknown</span>`;
  const healthBadge =
    summary.health === "healthy"
      ? `<span class="badge success"><span class="dot"></span>healthy</span>`
      : summary.health === "unhealthy"
        ? `<span class="badge failed"><span class="dot"></span>unhealthy</span>`
        : summary.health === "starting"
          ? `<span class="badge running"><span class="dot"></span>starting</span>`
          : `<span class="badge"><span class="dot"></span>no health</span>`;
  return `<div class="status-stack">${stateBadge}${healthBadge}</div>`;
}

function renderVersionCell(serviceName, environment) {
  const runtime = runtimeByName(serviceName, environment);
  if (!runtime) return "-";
  const ref = runtime.environment.current_ref || runtime.environment.current_version || "-";
  const commit = shortCommit(runtime.environment.current_commit);
  return `
    <div class="version-stack">
      <div class="mono">${escapeHtml(ref)}</div>
      <div class="subtle mono">${escapeHtml(commit)}</div>
    </div>
  `;
}

async function loadAll() {
  try {
    const [services, jobs] = await Promise.all([api("/api/services"), api("/api/jobs?limit=100")]);
    const details = await Promise.all(services.map((service) => api(`/api/services/${service.name}`)));
    state.services = details;
    state.jobs = jobs.jobs || [];
    state.loadError = "";
    ensureExpandedState();
    syncCurrentView();
    render();
    if (state.currentView.name === "runtime") {
      loadRuntimePreview(state.currentView.service, state.currentView.environment, true);
    }
    refreshRuntimeStatuses();
  } catch (error) {
    state.loadError = error.message;
    render();
    throw error;
  }
}

function ensureExpandedState() {
  state.services.forEach((service) => {
    if (state.expandedServices[service.name] === undefined) {
      state.expandedServices[service.name] = false;
    }
  });
}

function syncCurrentView() {
  if (state.currentView.name === "service" && !serviceByName(state.currentView.service)) {
    state.currentView = { name: "services" };
  }
  if (state.currentView.name === "runtime" && !runtimeByName(state.currentView.service, state.currentView.environment)) {
    state.currentView = { name: "services" };
  }
  if (state.jobsFilter.service && !serviceByName(state.jobsFilter.service)) {
    state.jobsFilter.service = "";
  }
  persistJobsFilter();
}

async function refreshRuntimeStatuses() {
  const runtimes = state.services.flatMap((service) =>
    serviceEnvironmentNames(service).map((environment) => ({ service: service.name, environment })),
  );
  runtimes.forEach(({ service, environment }) => {
    state.runtimeStatus[runtimeKey(service, environment)] = {
      ...runtimeStatus(service, environment),
      loading: true,
    };
  });
  render();
  const results = await Promise.all(
    runtimes.map(async ({ service, environment }) => {
      try {
        const response = await api(`/api/services/${service}/status?environment=${environment}`);
        return parseRuntimeStatus(service, environment, response);
      } catch (error) {
        return {
          service,
          environment,
          loading: false,
          available: false,
          running: false,
          state: "unknown",
          health: "unknown",
          raw: String(error.message),
        };
      }
    }),
  );
  results.forEach((item) => {
    state.runtimeStatus[runtimeKey(item.service, item.environment)] = item;
  });
  render();
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

function persistServicesFilter() {
  localStorage.setItem("deployer-services-filter", JSON.stringify(state.servicesFilter));
}

function persistJobsFilter() {
  localStorage.setItem("deployer-jobs-filter", JSON.stringify(state.jobsFilter));
}

function render() {
  root.innerHTML = `
    <div class="app-shell">
      ${renderSidebar()}
      <main class="main">
        ${renderTopbar()}
        <section class="content">
          ${state.loadError ? renderLoadErrorBanner() : ""}
          ${renderCurrentView()}
        </section>
      </main>
      ${state.actionMenu ? renderActionMenuOverlay() : ""}
      ${state.logsDrawer ? renderLogsDrawer() : ""}
      ${state.historyDrawer ? renderHistoryDrawer() : ""}
      ${state.jobDrawer ? renderJobDrawer() : ""}
      ${state.addOpen ? renderAddPanel() : ""}
      ${state.deployModal ? renderDeployModal() : ""}
      ${state.toast ? `<div class="toast">${escapeHtml(state.toast)}</div>` : ""}
    </div>
  `;
}

function renderLoadErrorBanner() {
  return `
    <div class="inline-error banner-error">
      <div class="error-title">Failed to refresh data</div>
      <div class="error-list">
        <div>${escapeHtml(state.loadError)}</div>
      </div>
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
        <button class="nav-item ${state.currentView.name === "services" ? "active" : ""}" onclick="showServicesPage()">${icon("server")} Services</button>
        <button class="nav-item ${state.currentView.name === "jobs" ? "active" : ""}" onclick="showJobsPage()">${icon("list")} Jobs</button>
      </div>
      <div class="nav-block service-list">
        <div class="nav-label">Catalog</div>
        ${state.services.map(renderSidebarService).join("")}
      </div>
      <div class="nav-block">
        <button class="nav-item" onclick="toggleTheme()">${icon(state.theme === "dark" ? "sun" : "moon")} ${state.theme === "dark" ? "Light theme" : "Dark theme"}</button>
      </div>
    </aside>
  `;
}

function renderSidebarService(service) {
  const expanded = state.expandedServices[service.name];
  const isServicePage = state.currentView.name === "service" && state.currentView.service === service.name;
  return `
    <div class="tree-item">
      <button class="nav-item ${isServicePage ? "active" : ""}" onclick="openServicePage('${escapeHtml(service.name)}')">
        <span class="tree-chevron" onclick="event.stopPropagation();toggleServiceTree('${escapeHtml(service.name)}')">${expanded ? icon("chevronDown", 14) : icon("chevronRight", 14)}</span>
        <span class="dot" style="color:${serviceColor(service.name)}"></span>
        <span class="ellipsis">${escapeHtml(service.name)}</span>
      </button>
      ${expanded
        ? `
          <div class="tree-children">
            ${serviceEnvironmentNames(service).map((environment) => `
              <button class="nav-item child ${state.currentView.name === "runtime" && state.currentView.service === service.name && state.currentView.environment === environment ? "active" : ""}" onclick="openRuntimePage('${escapeHtml(service.name)}', '${environment}')">
                <span class="tree-indent"></span>
                <span class="mono">${escapeHtml(environment)}</span>
              </button>
            `).join("")}
          </div>
        `
        : ""}
    </div>
  `;
}

function renderTopbar() {
  const activeJobs = state.jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  const failedJobs = state.jobs.filter((job) => job.status === "failed").length;
  const title = state.currentView.name === "jobs"
    ? "Runtime jobs"
    : state.currentView.name === "service"
      ? `Service: ${state.currentView.service}`
      : state.currentView.name === "runtime"
        ? `Runtime: ${state.currentView.service}/${state.currentView.environment}`
        : "Services dashboard";
  return `
    <header class="topbar">
      <div>
        <h1>${escapeHtml(title)}</h1>
        <div class="hint">${state.services.length} services · ${activeJobs} active jobs · ${failedJobs} failed jobs</div>
      </div>
      <div class="spacer"></div>
      <button class="btn secondary" onclick="refreshData()">${icon("refresh")} Refresh</button>
      ${state.currentView.name !== "jobs" ? `<button class="btn primary" onclick="openAddService()">${icon("plus")} Add service</button>` : ""}
    </header>
  `;
}

function renderCurrentView() {
  if (state.currentView.name === "jobs") return renderJobsView();
  if (state.currentView.name === "service") return renderServicePage();
  if (state.currentView.name === "runtime") return renderRuntimePage();
  return renderServicesView();
}

function serviceFilterMatch(service, environment) {
  const filter = state.servicesFilter;
  const summary = runtimeStatus(service.name, environment);
  if (filter.environment && filter.environment !== environment) return false;
  if (
    filter.status &&
    ((filter.status === "running" && summary.state !== "running") ||
      (filter.status === "stopped" && summary.state !== "stopped") ||
      (filter.status === "problem" && !["unknown"].includes(summary.state) && summary.health !== "unhealthy"))
  ) {
    return false;
  }
  return matchesQuery(
    [
      service.name,
      environment,
      service.source_status?.current_ref,
      service.source_status?.current_commit,
      runtimeUrl(service.name, environment),
      envSummary(service, environment).current_ref,
      envSummary(service, environment).current_commit,
    ],
    filter.query,
  );
}

function clearServicesFilter() {
  state.servicesFilter = { query: "", environment: "", status: "" };
  persistServicesFilter();
  render();
}

function clearJobsFilter() {
  state.jobsFilter = { query: "", service: "", environment: "", status: "" };
  persistJobsFilter();
  render();
}

function renderFilterEmptyState(title, message, resetHandler) {
  return `
    <div class="empty compact-empty">
      <div style="font-weight:800">${escapeHtml(title)}</div>
      <div>${escapeHtml(message)}</div>
      <button class="btn secondary" onclick="${resetHandler}()">${icon("refresh")} Clear filters</button>
    </div>
  `;
}

function renderServicesView() {
  const successful = state.jobs.filter((job) => job.status === "success").length;
  const failed = state.jobs.filter((job) => job.status === "failed").length;
  const environmentNames = allEnvironmentNames();
  const rows = state.services.flatMap((service) =>
    serviceEnvironmentNames(service)
      .filter((environment) => serviceFilterMatch(service, environment))
      .map((environment) => renderServiceTableRow(service, environment)),
  );
  return `
    <div class="toolbar">
      <div>
        <div class="headline">Runtime table</div>
        <div class="muted">One row equals one runtime target: service plus environment.</div>
      </div>
      <div class="row wrap">
        <span class="badge success"><span class="dot"></span>${successful} successful</span>
        <span class="badge failed"><span class="dot"></span>${failed} failed</span>
      </div>
    </div>
    <div class="filter-bar card">
      <div class="field grow">
        <label>Search</label>
        <input class="input" value="${escapeHtml(state.servicesFilter.query)}" placeholder="service, ref, commit, url" oninput="setServicesFilter('query', this.value)">
      </div>
      <div class="field">
        <label>Environment</label>
        <select class="select" onchange="setServicesFilter('environment', this.value)">
          <option value="">all</option>
          ${environmentNames.map((environment) => `<option value="${escapeHtml(environment)}" ${state.servicesFilter.environment === environment ? "selected" : ""}>${escapeHtml(environment)}</option>`).join("")}
        </select>
      </div>
      <div class="field">
        <label>Status</label>
        <select class="select" onchange="setServicesFilter('status', this.value)">
          <option value="">all</option>
          <option value="running" ${state.servicesFilter.status === "running" ? "selected" : ""}>running</option>
          <option value="stopped" ${state.servicesFilter.status === "stopped" ? "selected" : ""}>stopped</option>
          <option value="problem" ${state.servicesFilter.status === "problem" ? "selected" : ""}>problem</option>
        </select>
      </div>
    </div>
    ${state.services.length
      ? `
        ${rows.length
          ? `
            <div class="table table-wide">
              <div class="table-row table-head services-table-head">
                <div>Service</div>
                <div>Environment</div>
                <div>Link</div>
                <div>Status</div>
                <div>Version</div>
                <div>Quick</div>
                <div>Actions</div>
              </div>
              ${rows.join("")}
            </div>
          `
          : renderFilterEmptyState("No runtimes match the current filters", "Try another search string or reset the filters.", "clearServicesFilter")}
      `
      : renderEmpty()}
  `;
}

function renderServiceTableRow(service, environment) {
  const summary = runtimeStatus(service.name, environment);
  const activeJob = activeJobForRuntime(service.name, environment);
  const visibleFailure = latestVisibleFailure(service.name, environment);
  const canOpenLink = summary.running;
  const publicUrl = runtimeUrl(service.name, environment);
  return `
    <div class="table-row services-table-row">
      <div class="service-cell">
        <div class="service-icon small" style="background:${serviceColor(service.name)}">${escapeHtml(serviceInitials(service.name))}</div>
        <div>
          <div class="service-link-button" onclick="openServicePage('${escapeHtml(service.name)}')">${escapeHtml(service.name)}</div>
          <div class="subtle mono ellipsis">${escapeHtml(shortCommit(service.source_status?.current_commit))}</div>
        </div>
      </div>
      <div><span class="badge">${escapeHtml(environment)}</span></div>
      <div>
        ${canOpenLink
          ? `<a class="table-link mono" href="${escapeHtml(publicUrl)}" target="_blank" rel="noreferrer">${escapeHtml(publicUrl)}</a>`
          : `<span class="subtle">not exposed</span>`}
      </div>
      <div>
        ${renderRuntimeStatus(service.name, environment)}
        ${activeJob ? `<div class="subtle mono top-gap">${escapeHtml(activeJob.action)}</div>` : ""}
        ${!activeJob && visibleFailure ? `<div class="failure-note top-gap">last ${escapeHtml(visibleFailure.action)} failed</div>` : ""}
      </div>
      <div>${renderVersionCell(service.name, environment)}</div>
      <div class="quick-actions">
        <button class="btn ghost" onclick="openServicePage('${escapeHtml(service.name)}')">Service</button>
        <button class="btn ghost" onclick="openLogsDrawer('${escapeHtml(service.name)}', '${environment}')">Logs</button>
        <button class="btn ghost" onclick="openRuntimePage('${escapeHtml(service.name)}', '${environment}')">Settings</button>
      </div>
      <div class="action-menu-wrap">
        <button class="btn secondary" onclick="toggleActionMenu(event, '${escapeHtml(service.name)}', '${environment}')">${icon("more")} Actions</button>
      </div>
    </div>
  `;
}

function renderActionMenuOverlay() {
  return `
    <button class="action-menu-backdrop" onclick="closeActionMenu()" aria-label="Close actions menu"></button>
    ${renderActionMenu(state.actionMenu.service, state.actionMenu.environment, state.actionMenu.top, state.actionMenu.left)}
  `;
}

function renderActionMenu(serviceName, environment, top, left) {
  return `
    <div class="action-menu action-menu-floating" style="top:${top}px;left:${left}px">
      <button class="action-item" onclick="openDeployModal('${escapeHtml(serviceName)}', '${environment}')">Deploy</button>
      <button class="action-item" onclick="runtimeAction('${escapeHtml(serviceName)}', 'restart', '${environment}')">Restart</button>
      <button class="action-item" onclick="runtimeAction('${escapeHtml(serviceName)}', 'stop', '${environment}')">Stop</button>
      <button class="action-item" onclick="runtimeAction('${escapeHtml(serviceName)}', 'down', '${environment}')">Down</button>
      <button class="action-item" onclick="openHistoryDrawer('${escapeHtml(serviceName)}', '${environment}')">History</button>
    </div>
  `;
}

function renderServicePage() {
  const service = serviceByName(state.currentView.service);
  if (!service) return renderMissing("Unknown service");
  return `
    <div class="page-stack">
      <section class="card page-card">
        <div class="page-header">
          <div class="service-title">
            <div class="service-icon" style="background:${serviceColor(service.name)}">${escapeHtml(serviceInitials(service.name))}</div>
            <div>
              <h2 class="service-name">${escapeHtml(service.name)}</h2>
              <div class="muted">Shared service definition and source settings.</div>
            </div>
          </div>
          <div class="row wrap">
            ${sourceBadge(service)}
            ${service.source_status?.current_ref ? `<span class="badge mono">${escapeHtml(service.source_status.current_ref)}</span>` : ""}
            ${service.source_status?.current_commit ? `<span class="badge mono">${escapeHtml(shortCommit(service.source_status.current_commit))}</span>` : ""}
          </div>
        </div>
        <div class="details-grid">
          <div class="field"><label>Source type</label><input class="input" value="${escapeHtml(service.source_type)}" disabled></div>
          <div class="field"><label>Default branch</label><input class="input mono" value="${escapeHtml(service.default_branch || "")}" disabled></div>
          <div class="field field-span"><label>Source</label><input class="input mono" value="${escapeHtml(formatSource(service))}" disabled></div>
          <div class="field field-span"><label>Managed checkout</label><input class="input mono" value="${escapeHtml(service.source_path)}" disabled></div>
        </div>
        ${service.source_status?.error ? `<div class="inline-error">${escapeHtml(service.source_status.error)}</div>` : ""}
      </section>
      <section class="card page-card">
        <div class="section-title">Runtime targets</div>
        <div class="runtime-mini-grid">
          ${serviceEnvironmentNames(service).map((environment) => `
            <button class="runtime-mini-card" onclick="openRuntimePage('${escapeHtml(service.name)}', '${environment}')">
              <div class="runtime-mini-head">
                <span class="badge">${escapeHtml(environment)}</span>
                ${renderRuntimeStatus(service.name, environment)}
              </div>
              <div class="muted mono">${escapeHtml(runtimeUrl(service.name, environment) || "-")}</div>
              <div class="muted mono top-gap">${escapeHtml(deployPolicyLabel(envSummary(service, environment)))}</div>
              <div class="mono top-gap">${escapeHtml(envSummary(service, environment).current_ref || "-")}</div>
            </button>
          `).join("")}
        </div>
      </section>
      <section class="card page-card danger-card">
        <div class="section-title">Danger zone</div>
        <button class="btn danger" onclick="removeService('${escapeHtml(service.name)}')">${icon("trash")} Remove service from catalog</button>
      </section>
    </div>
  `;
}

function renderRuntimePage() {
  const service = serviceByName(state.currentView.service);
  if (!service) return renderMissing("Unknown service");
  const environment = state.currentView.environment;
  const env = envSummary(service, environment);
  const envPairs = Object.entries(env.env || {});
  const summary = runtimeStatus(service.name, environment);
  const preview = runtimePreview(service.name, environment);
  const publicUrl = runtimeUrl(service.name, environment);
  const jobs = state.jobs.filter((job) => job.service === service.name && job.environment === environment);
  return `
    <div class="page-stack">
      <section class="card page-card">
        <div class="page-header">
          <div>
            <div class="headline-small">${escapeHtml(service.name)}/${escapeHtml(environment)}</div>
            <div class="muted">Runtime-specific settings and actions.</div>
          </div>
          <div class="row wrap">
            ${renderRuntimeStatus(service.name, environment)}
          </div>
        </div>
        <div class="runtime-page-grid">
          <div class="fact">
            <span class="fact-label">Public URL</span>
            <span class="fact-value">${summary.running && publicUrl ? `<a class="table-link mono" href="${escapeHtml(publicUrl)}" target="_blank" rel="noreferrer">${escapeHtml(publicUrl)}</a>` : `<span class="subtle">not exposed</span>`}</span>
          </div>
          <div class="fact">
            <span class="fact-label">Current ref</span>
            <span class="fact-value mono">${escapeHtml(env.current_ref || env.current_version || "-")}</span>
          </div>
          <div class="fact">
            <span class="fact-label">Current commit</span>
            <span class="fact-value mono">${escapeHtml(shortCommit(env.current_commit))}</span>
          </div>
          <div class="fact">
            <span class="fact-label">Last deployment</span>
            <span class="fact-value mono">${escapeHtml(env.last_deployment_id ? `#${env.last_deployment_id}` : "-")}</span>
          </div>
          <div class="fact">
            <span class="fact-label">Deploy policy</span>
            <span class="fact-value mono">${escapeHtml(deployPolicyLabel(env))}</span>
          </div>
        </div>
        <div class="runtime-button-row">
          <button class="btn primary" onclick="openDeployModal('${escapeHtml(service.name)}', '${environment}')">${icon("play")} Deploy</button>
          <button class="btn secondary" onclick="runtimeAction('${escapeHtml(service.name)}', 'restart', '${environment}')">${icon("refresh")} Restart</button>
          <button class="btn secondary" onclick="runtimeAction('${escapeHtml(service.name)}', 'stop', '${environment}')">${icon("stop")} Stop</button>
          <button class="btn danger" onclick="runtimeAction('${escapeHtml(service.name)}', 'down', '${environment}')">${icon("trash")} Down</button>
          <button class="btn secondary" onclick="openLogsDrawer('${escapeHtml(service.name)}', '${environment}')">${icon("list")} Logs</button>
          <button class="btn secondary" onclick="openHistoryDrawer('${escapeHtml(service.name)}', '${environment}')">${icon("history")} History</button>
        </div>
      </section>
      <section class="card page-card">
        <div class="page-header">
          <div>
            <div class="section-title">Rendered configuration</div>
            <div class="muted">Current managed env file and generated override for this runtime target.</div>
          </div>
          <div class="row wrap">
            ${renderPreviewSummary(service.name, environment)}
            <button class="btn secondary" onclick="loadRuntimePreview('${escapeHtml(service.name)}', '${environment}', true)">${icon("refresh")} Reload preview</button>
          </div>
        </div>
        <div class="preview-meta">
          <div class="fact">
            <span class="fact-label">Managed env file</span>
            <span class="fact-value mono">${escapeHtml(preview.env_file_path || "-")}</span>
          </div>
          <div class="fact">
            <span class="fact-label">Managed override</span>
            <span class="fact-value mono">${escapeHtml(preview.override_path || "-")}</span>
          </div>
        </div>
        ${preview.loading ? `<div class="table-empty muted">Loading preview...</div>` : ""}
        ${!preview.loading ? renderValidationErrors(preview.errors) : ""}
        ${!preview.loading
          ? `
            <div class="preview-grid">
              <div class="preview-panel">
                <div class="section-title">Env file</div>
                <pre class="log-box compact">${escapeHtml(preview.env_file_content || "# empty")}</pre>
              </div>
              <div class="preview-panel">
                <div class="section-title">Override</div>
                <pre class="log-box compact">${escapeHtml(preview.override_content || "# override preview unavailable")}</pre>
              </div>
            </div>
          `
          : ""}
      </section>
      <section class="card page-card">
        <div class="section-title">Environment variables</div>
        <form onsubmit="saveEnvVar(event, '${escapeHtml(service.name)}', '${environment}')" class="inline-form">
          <input class="input mono" name="key" placeholder="KEY" required>
          <input class="input mono" name="value" placeholder="value" required>
          <button class="btn primary" type="submit">${icon("plus")} Set</button>
        </form>
        <div class="table">
          <div class="table-row table-head env-table-head">
            <div>Key</div>
            <div>Value</div>
            <div></div>
          </div>
          ${envPairs.length
            ? envPairs.map(([key, value]) => `
              <div class="table-row env-table-row">
                <div class="mono">${escapeHtml(key)}</div>
                <div class="mono value-wrap">${escapeHtml(value)}</div>
                <button class="btn ghost" onclick="unsetEnvVar('${escapeHtml(service.name)}', '${environment}', '${escapeHtml(key)}')">unset</button>
              </div>
            `).join("")
            : `<div class="table-empty muted">No variables configured for ${escapeHtml(service.name)}/${escapeHtml(environment)}.</div>`}
        </div>
      </section>
      <section class="card page-card">
        <div class="section-title">Recent jobs</div>
        <div class="table">
          <div class="table-row table-head runtime-jobs-head">
            <div>Action</div>
            <div>Status</div>
            <div>Ref</div>
            <div>Finished</div>
            <div></div>
          </div>
          ${jobs.length
            ? jobs.slice(0, 10).map((job) => `
              <div class="table-row runtime-jobs-row">
                <div class="mono">${escapeHtml(job.action)}</div>
                <div>${jobBadge(job.status)}</div>
                <div class="mono">${escapeHtml(job.ref || job.version || "-")}</div>
                <div class="subtle">${escapeHtml(formatTime(job.finished_at || job.started_at || job.created_at))}</div>
                <div><button class="btn ghost" onclick="openJobDrawer(${job.id})">Output</button></div>
              </div>
            `).join("")
            : `<div class="table-empty muted">No jobs yet for ${escapeHtml(service.name)}/${escapeHtml(environment)}.</div>`}
        </div>
      </section>
    </div>
  `;
}

function renderJobsView() {
  const environmentNames = allEnvironmentNames();
  const filtered = state.jobs.filter((job) => {
    if (!matchesQuery([job.service, job.environment, job.action, job.ref, job.version, job.status], state.jobsFilter.query)) return false;
    if (state.jobsFilter.service && job.service !== state.jobsFilter.service) return false;
    if (state.jobsFilter.environment && job.environment !== state.jobsFilter.environment) return false;
    if (state.jobsFilter.status && job.status !== state.jobsFilter.status) return false;
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
        <label>Search</label>
        <input class="input" value="${escapeHtml(state.jobsFilter.query)}" placeholder="service, action, ref, status" oninput="setJobsFilter('query', this.value)">
      </div>
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
          ${environmentNames.map((environment) => `<option value="${escapeHtml(environment)}" ${state.jobsFilter.environment === environment ? "selected" : ""}>${escapeHtml(environment)}</option>`).join("")}
        </select>
      </div>
      <div class="field grow">
        <label>Status</label>
        <select class="select" onchange="setJobsFilter('status', this.value)">
          <option value="">all statuses</option>
          <option value="queued" ${state.jobsFilter.status === "queued" ? "selected" : ""}>queued</option>
          <option value="running" ${state.jobsFilter.status === "running" ? "selected" : ""}>running</option>
          <option value="success" ${state.jobsFilter.status === "success" ? "selected" : ""}>success</option>
          <option value="failed" ${state.jobsFilter.status === "failed" ? "selected" : ""}>failed</option>
        </select>
      </div>
    </div>
    ${filtered.length
      ? `
        <div class="table">
          <div class="table-row table-head jobs-table-head">
            <div>Service</div>
            <div>Action</div>
            <div>Status</div>
            <div>Target</div>
            <div>Ref</div>
            <div>Finished</div>
            <div></div>
          </div>
          ${filtered.map(renderGlobalJobRow).join("")}
        </div>
      `
      : renderFilterEmptyState("No jobs match the current filters", "Try another search string or reset the job filters.", "clearJobsFilter")}
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
      <div><button class="btn ghost" onclick="openJobDrawer(${job.id})">Output</button></div>
    </div>
  `;
}

function renderJobDrawer() {
  const job = state.jobDrawer;
  return `
    <div class="overlay-backdrop" onclick="closeJobDrawer()"></div>
    <aside class="drawer drawer-wide">
      <div class="drawer-header">
        <div class="row">
          <div>
            <div class="drawer-title">Job #${escapeHtml(job.id)}</div>
            <div class="muted">${escapeHtml(job.service)}/${escapeHtml(job.environment)} · ${escapeHtml(job.action)}</div>
          </div>
          <div class="spacer"></div>
          <button class="btn secondary" onclick="reloadJobDrawer()">Reload</button>
          <button class="btn ghost" onclick="closeJobDrawer()">${icon("close")}</button>
        </div>
      </div>
      <div class="drawer-body">
        <div class="section">
          <div class="row wrap">
            ${jobBadge(job.status)}
            <span class="badge mono">${escapeHtml(job.ref || job.version || "-")}</span>
            ${job.deployment_id ? `<span class="badge mono">deploy #${escapeHtml(job.deployment_id)}</span>` : ""}
          </div>
        </div>
        <div class="section">
          <div class="section-title">CLI Output</div>
          ${job.log_truncated ? `<div class="inline-error">Output is truncated. Showing the most recent part.</div>` : ""}
          <pre class="log-box">${escapeHtml(job.log || "No job output yet.")}</pre>
        </div>
      </div>
    </aside>
  `;
}

function renderMissing(title) {
  return `<div class="empty"><div style="font-weight:800">${escapeHtml(title)}</div></div>`;
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

function renderLogsDrawer() {
  const drawer = state.logsDrawer;
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
  const preview = runtimePreview(modal.service, modal.environment);
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
          <input class="input" value="${escapeHtml(service?.source_status?.available ? "source fetched" : "source unavailable")}" disabled>
        </div>
        <div class="field">
          <label>Runtime validation</label>
          <div class="row wrap">
            ${renderPreviewSummary(modal.service, modal.environment)}
          </div>
          <div class="muted top-gap">Preview reflects the current managed checkout for this runtime target.</div>
        </div>
        ${preview.loading ? `<div class="muted">Checking current configuration...</div>` : renderValidationErrors(preview.errors)}
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

function showServicesPage() {
  state.currentView = { name: "services" };
  state.actionMenu = null;
  render();
}

function showJobsPage() {
  state.currentView = { name: "jobs" };
  state.actionMenu = null;
  render();
}

function toggleServiceTree(service) {
  state.expandedServices[service] = !state.expandedServices[service];
  render();
}

function openServicePage(service) {
  state.expandedServices[service] = true;
  state.currentView = { name: "service", service };
  state.actionMenu = null;
  render();
}

function openRuntimePage(service, environment) {
  state.expandedServices[service] = true;
  state.currentView = { name: "runtime", service, environment };
  state.actionMenu = null;
  render();
  loadRuntimePreview(service, environment, false);
}

function setJobsFilter(key, value) {
  state.jobsFilter[key] = value;
  persistJobsFilter();
  render();
}

function setServicesFilter(key, value) {
  state.servicesFilter[key] = value;
  persistServicesFilter();
  render();
}

async function loadRuntimePreview(service, environment, force = false) {
  const key = runtimeKey(service, environment);
  const current = state.runtimePreview[key];
  if (!force && current && !current.loading) {
    return;
  }
  state.runtimePreview[key] = {
    ...(current || {}),
    loading: true,
    errors: current?.errors || [],
  };
  render();
  try {
    const preview = await api(`/api/services/${service}/preview?environment=${environment}`);
    state.runtimePreview[key] = {
      ...preview,
      loading: false,
    };
    render();
  } catch (error) {
    state.runtimePreview[key] = {
      loading: false,
      valid: false,
      errors: [{ scope: "api", message: error.message }],
      source_path: "",
      manifest_path: "",
      compose_files: [],
      public_url: null,
      env_file_path: "",
      env_file_content: "",
      override_path: "",
      override_content: "",
    };
    render();
  }
}

function actionMenuPosition(trigger) {
  const rect = trigger.getBoundingClientRect();
  const maxLeft = window.innerWidth - ACTION_MENU_WIDTH - ACTION_MENU_VIEWPORT_PADDING;
  const left = Math.max(ACTION_MENU_VIEWPORT_PADDING, Math.min(rect.right - ACTION_MENU_WIDTH, maxLeft));
  const openAbove = rect.bottom + ACTION_MENU_GAP + ACTION_MENU_HEIGHT > window.innerHeight - ACTION_MENU_VIEWPORT_PADDING;
  const top = openAbove
    ? Math.max(ACTION_MENU_VIEWPORT_PADDING, rect.top - ACTION_MENU_HEIGHT - ACTION_MENU_GAP)
    : Math.min(rect.bottom + ACTION_MENU_GAP, window.innerHeight - ACTION_MENU_HEIGHT - ACTION_MENU_VIEWPORT_PADDING);
  return { top, left };
}

function closeActionMenu() {
  if (!state.actionMenu) return;
  state.actionMenu = null;
  render();
}

function toggleActionMenu(event, service, environment) {
  if (state.actionMenu && state.actionMenu.service === service && state.actionMenu.environment === environment) {
    state.actionMenu = null;
  } else {
    const trigger = event?.currentTarget;
    if (!trigger) return;
    state.actionMenu = { service, environment, ...actionMenuPosition(trigger) };
  }
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

async function openJobDrawer(jobId) {
  try {
    state.jobDrawer = await api(`/api/jobs/${jobId}`);
    render();
  } catch (error) {
    setToast(error.message);
  }
}

function closeJobDrawer() {
  state.jobDrawer = null;
  render();
}

async function reloadJobDrawer() {
  if (!state.jobDrawer) return;
  await openJobDrawer(state.jobDrawer.id);
}

async function openLogsDrawer(service, environment) {
  state.logsDrawer = {
    service,
    environment,
    loading: true,
    log: "",
    statusText: "",
  };
  state.actionMenu = null;
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
  state.actionMenu = null;
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
    ref: environment === "prod" ? svc?.default_branch || "main" : envSummary(svc, "dev").current_ref || "develop",
    refs: [],
    error: "",
  };
  state.actionMenu = null;
  render();
  loadRuntimePreview(service, environment, false);
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
  state.actionMenu = null;
  if (["down", "stop"].includes(action) && !confirm(`${action} ${service}/${environment}?`)) return;
  await scheduleJob(service, action, environment);
}

async function scheduleJob(service, action, environment, extra = {}) {
  try {
    const job = await api(`/api/services/${service}/${action}`, {
      method: "POST",
      body: JSON.stringify({ environment, dry_run: false, ...extra }),
    });
    upsertJob(job);
    render();
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
    upsertJob(job);
    if (["success", "failed"].includes(job.status)) {
      await loadAll();
      if (
        state.currentView.name !== "runtime" ||
        state.currentView.service !== service ||
        state.currentView.environment !== environment
      ) {
        await loadRuntimePreview(service, environment, true);
      }
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
    state.currentView = { name: "services" };
    await loadAll();
    setToast(`Service ${name} removed`);
  } catch (error) {
    setToast(error.message);
  }
}

loadAll().catch((error) => {
  root.innerHTML = `<div class="empty" style="height:100%"><div style="font-weight:800">Failed to load deployer UI</div><div class="muted">${escapeHtml(error.message)}</div></div>`;
});
