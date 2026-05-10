const state = {
  services: [],
  jobs: [],
  selected: null,
  activeTab: "overview",
  theme: localStorage.getItem("deployer-theme") || "light",
  toast: "",
  addOpen: false,
  addSourceType: "git",
  envName: "prod",
  busy: false,
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
  return name.split("-").map((part) => part[0]).join("").slice(0, 3);
}

function jobBadge(status) {
  const cls = status === "success" ? "success" : status === "failed" ? "failed" : status === "running" ? "running" : "queued";
  return `<span class="badge ${cls}"><span class="dot"></span>${escapeHtml(status || "unknown")}</span>`;
}

function envSummary(service, name) {
  return service.environments?.find((env) => env.name === name) || {};
}

function activeJobFor(serviceName) {
  return state.jobs.find((job) => job.service === serviceName && ["queued", "running"].includes(job.status));
}

async function loadAll({ keepSelected = true } = {}) {
  const [services, jobs] = await Promise.all([
    api("/api/services"),
    api("/api/jobs?limit=50"),
  ]);
  const details = await Promise.all(services.map((service) => api(`/api/services/${service.name}`)));
  state.services = details;
  state.jobs = jobs.jobs || [];
  if (keepSelected && state.selected) {
    state.selected = state.services.find((service) => service.name === state.selected.name) || null;
  }
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

function render() {
  root.innerHTML = `
    <div class="app-shell">
      ${renderSidebar()}
      <main class="main">
        ${renderTopbar()}
        <section class="content">
          ${renderToolbar()}
          ${state.services.length ? renderServiceGrid() : renderEmpty()}
        </section>
      </main>
      ${state.selected ? renderPanel(state.selected) : ""}
      ${state.addOpen ? renderAddPanel() : ""}
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
        <button class="nav-item active">${icon("server")} Services</button>
        <button class="nav-item" onclick="openLatestJob()">${icon("refresh")} Jobs</button>
      </div>
      <div class="nav-block service-list">
        <div class="nav-label">Services</div>
        ${state.services.map((service) => `
          <button class="nav-item ${state.selected?.name === service.name ? "active" : ""}" onclick="selectService('${escapeHtml(service.name)}')">
            <span class="dot" style="color:${serviceColor(service.name)}"></span>
            <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(service.name)}</span>
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
  const running = state.jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  return `
    <header class="topbar">
      <div>
        <h1>Services dashboard</h1>
        <div class="hint">${state.services.length} services · ${running} active jobs</div>
      </div>
      <div class="spacer"></div>
      <button class="btn secondary" onclick="refreshData()">${icon("refresh")} Refresh</button>
      <button class="btn primary" onclick="openAddService()">${icon("plus")} Add service</button>
    </header>
  `;
}

function renderToolbar() {
  const failed = state.jobs.filter((job) => job.status === "failed").length;
  const successful = state.jobs.filter((job) => job.status === "success").length;
  return `
    <div class="toolbar">
      <div>
        <div style="font-size:20px;font-weight:800;letter-spacing:-0.035em">Runtime overview</div>
        <div class="muted">Manage git/local services, environments, deployments and runtime jobs.</div>
      </div>
      <div class="row">
        <span class="badge success"><span class="dot"></span>${successful} successful</span>
        <span class="badge failed"><span class="dot"></span>${failed} failed</span>
      </div>
    </div>
  `;
}

function renderServiceGrid() {
  return `<div class="grid">${state.services.map(renderServiceCard).join("")}</div>`;
}

function renderServiceCard(service) {
  const color = serviceColor(service.name);
  const prod = envSummary(service, "prod");
  const dev = envSummary(service, "dev");
  const job = activeJobFor(service.name);
  return `
    <article class="card service-card">
      <div class="service-accent" style="background:${color}"></div>
      <div class="card-body">
        <div class="service-title">
          <div class="service-icon" style="background:${color}">${escapeHtml(serviceInitials(service.name))}</div>
          <div style="min-width:0;flex:1">
            <h2 class="service-name">${escapeHtml(service.name)}</h2>
            <div class="muted mono" style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(service.source_url || service.source_path)}</div>
          </div>
          ${job ? jobBadge(job.status) : `<span class="badge">${escapeHtml(service.source_type)}</span>`}
        </div>
        <div class="stats">
          <div class="stat"><div class="stat-value">${escapeHtml(prod.current_ref || "-")}</div><div class="stat-label">prod ref</div></div>
          <div class="stat"><div class="stat-value">${escapeHtml(dev.current_ref || "-")}</div><div class="stat-label">dev ref</div></div>
          <div class="stat"><div class="stat-value">${escapeHtml((prod.env && Object.keys(prod.env).length) || 0)}</div><div class="stat-label">env vars</div></div>
        </div>
      </div>
      <div class="card-footer">
        <button class="btn primary" onclick="deployService('${escapeHtml(service.name)}', 'prod')">${icon("play")} Deploy prod</button>
        <button class="btn secondary" onclick="selectService('${escapeHtml(service.name)}')">${icon("gear")} Details</button>
      </div>
    </article>
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

function renderPanel(service) {
  return `
    <div class="panel-backdrop" onclick="closePanel()"></div>
    <aside class="panel">
      <div class="panel-header">
        <div class="row">
          <div class="service-icon" style="background:${serviceColor(service.name)}">${escapeHtml(serviceInitials(service.name))}</div>
          <div>
            <div style="font-size:17px;font-weight:800">${escapeHtml(service.name)}</div>
            <div class="muted mono" style="font-size:12px">${escapeHtml(service.source_type)} · ${escapeHtml(service.default_branch || "no default branch")}</div>
          </div>
          <div class="spacer"></div>
          <button class="btn ghost" onclick="closePanel()">${icon("close")}</button>
        </div>
      </div>
      <div class="tabs">
        ${["overview", "env", "deployments", "logs", "settings"].map((tab) => `
          <button class="tab ${state.activeTab === tab ? "active" : ""}" onclick="setTab('${tab}')">${tab}</button>
        `).join("")}
      </div>
      <div class="panel-content">${renderActiveTab(service)}</div>
    </aside>
  `;
}

function renderActiveTab(service) {
  if (state.activeTab === "env") return renderEnvTab(service);
  if (state.activeTab === "deployments") return renderDeploymentsTab(service);
  if (state.activeTab === "logs") return renderLogsTab(service);
  if (state.activeTab === "settings") return renderSettingsTab(service);
  return renderOverviewTab(service);
}

function renderOverviewTab(service) {
  const latest = state.jobs.find((job) => job.service === service.name);
  return `
    <div class="section">
      <div class="section-title">Runtime actions</div>
      <div class="row" style="flex-wrap:wrap">
        <button class="btn primary" onclick="deployService('${escapeHtml(service.name)}', 'prod')">${icon("play")} Deploy prod</button>
        <button class="btn secondary" onclick="deployService('${escapeHtml(service.name)}', 'dev')">${icon("play")} Deploy dev</button>
        <button class="btn secondary" onclick="runtimeAction('${escapeHtml(service.name)}', 'restart', 'prod')">${icon("refresh")} Restart</button>
        <button class="btn secondary" onclick="runtimeAction('${escapeHtml(service.name)}', 'stop', 'prod')">${icon("stop")} Stop</button>
        <button class="btn danger" onclick="runtimeAction('${escapeHtml(service.name)}', 'down', 'prod')">${icon("trash")} Down</button>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Environments</div>
      <div class="table">
        <div class="table-row table-head"><div>Environment</div><div>Version</div><div>Subdomain</div><div>Env vars</div></div>
        ${service.environments.map((env) => `
          <div class="table-row">
            <div><span class="badge">${escapeHtml(env.name)}</span></div>
            <div class="mono">${escapeHtml(env.current_ref || env.current_version || "-")}<div class="subtle">${escapeHtml(env.current_commit || "")}</div></div>
            <div>${escapeHtml(env.subdomain)}</div>
            <div>${Object.keys(env.env || {}).length}</div>
          </div>
        `).join("")}
      </div>
    </div>
    <div class="section">
      <div class="section-title">Latest job</div>
      ${latest ? renderJobRow(latest) : `<div class="empty" style="min-height:120px">No jobs for this service yet.</div>`}
    </div>
  `;
}

function renderEnvTab(service) {
  const env = envSummary(service, state.envName);
  const pairs = Object.entries(env.env || {});
  return `
    <div class="section">
      <div class="row">
        <div class="section-title" style="margin:0">Environment variables</div>
        <div class="spacer"></div>
        <select class="select" style="width:130px" onchange="setEnvName(this.value)">
          <option value="prod" ${state.envName === "prod" ? "selected" : ""}>prod</option>
          <option value="dev" ${state.envName === "dev" ? "selected" : ""}>dev</option>
        </select>
      </div>
      <form onsubmit="saveEnvVar(event, '${escapeHtml(service.name)}')" style="display:grid;grid-template-columns:1fr 1fr auto;gap:8px;margin:12px 0">
        <input class="input mono" name="key" placeholder="KEY" required>
        <input class="input mono" name="value" placeholder="value" required>
        <button class="btn primary" type="submit">${icon("plus")} Set</button>
      </form>
      <div class="table">
        <div class="table-row table-head" style="grid-template-columns:180px 1fr 90px"><div>Key</div><div>Value</div><div></div></div>
        ${pairs.length ? pairs.map(([key, value]) => `
          <div class="table-row" style="grid-template-columns:180px 1fr 90px">
            <div class="mono">${escapeHtml(key)}</div>
            <div class="mono">${escapeHtml(value)}</div>
            <button class="btn ghost" onclick="unsetEnvVar('${escapeHtml(service.name)}', '${escapeHtml(key)}')">unset</button>
          </div>
        `).join("") : `<div style="padding:14px" class="muted">No variables configured for ${escapeHtml(state.envName)}.</div>`}
      </div>
    </div>
  `;
}

function renderDeploymentsTab(service) {
  const jobs = state.jobs.filter((job) => job.service === service.name);
  return `
    <div class="section-title">Recent runtime jobs</div>
    <div class="table">
      <div class="table-row table-head"><div>Action</div><div>Status</div><div>Env</div><div>Time</div></div>
      ${jobs.length ? jobs.map(renderJobRow).join("") : `<div style="padding:14px" class="muted">No jobs yet.</div>`}
    </div>
  `;
}

function renderJobRow(job) {
  return `
    <div class="table-row">
      <div class="mono">${escapeHtml(job.action)}</div>
      <div>${jobBadge(job.status)}<div class="subtle mono">${escapeHtml(job.ref || job.version || "")}</div></div>
      <div>${escapeHtml(job.environment)}</div>
      <div class="subtle">${escapeHtml(formatTime(job.finished_at || job.started_at || job.created_at))}</div>
    </div>
  `;
}

function renderLogsTab(service) {
  const latest = state.jobs.find((job) => job.service === service.name);
  return `
    <div class="row" style="margin-bottom:12px">
      <button class="btn secondary" onclick="loadRuntimeLog('${escapeHtml(service.name)}', 'prod')">Load prod logs</button>
      <button class="btn secondary" onclick="loadRuntimeLog('${escapeHtml(service.name)}', 'dev')">Load dev logs</button>
      <button class="btn secondary" onclick="loadStatus('${escapeHtml(service.name)}', 'prod')">Status</button>
    </div>
    <div class="section-title">Latest job output</div>
    <pre class="log-box">${escapeHtml(latest?.log || "No job log yet.")}</pre>
  `;
}

function renderSettingsTab(service) {
  return `
    <div class="section">
      <div class="section-title">Source</div>
      <div class="field"><label>Source type</label><input class="input" value="${escapeHtml(service.source_type)}" disabled></div>
      <div class="field"><label>Source</label><input class="input mono" value="${escapeHtml(service.source_url || service.source_path)}" disabled></div>
      <div class="field"><label>Default branch</label><input class="input mono" value="${escapeHtml(service.default_branch || "")}" disabled></div>
    </div>
    <div class="section">
      <div class="section-title">Danger zone</div>
      <button class="btn danger" onclick="removeService('${escapeHtml(service.name)}')">${icon("trash")} Remove service from catalog</button>
    </div>
  `;
}

function renderAddPanel() {
  return `
    <div class="panel-backdrop" onclick="closeAddService()"></div>
    <aside class="panel" style="max-width:540px">
      <div class="panel-header">
        <div class="row">
          <div>
            <div style="font-size:17px;font-weight:800">Add service</div>
            <div class="muted">Register git source or local debug project.</div>
          </div>
          <div class="spacer"></div>
          <button class="btn ghost" onclick="closeAddService()">${icon("close")}</button>
        </div>
      </div>
      <div class="panel-content">
        <form onsubmit="createService(event)">
          <div class="field"><label>Name</label><input class="input mono" name="name" placeholder="my-service" required></div>
          <div class="field">
            <label>Source type</label>
            <select class="select" name="source_type" onchange="setAddSourceType(this.value)">
              <option value="git" ${state.addSourceType === "git" ? "selected" : ""}>git</option>
              <option value="local" ${state.addSourceType === "local" ? "selected" : ""}>local</option>
            </select>
          </div>
          ${state.addSourceType === "git" ? `
            <div class="field"><label>Git URL</label><input class="input mono" name="git_url" placeholder="git@example.com:me/app.git" required></div>
            <div class="field"><label>Default branch</label><input class="input mono" name="default_branch" placeholder="main"></div>
          ` : `
            <div class="field"><label>Local path</label><input class="input mono" name="path" placeholder="/tmp/paas-test-app" required></div>
          `}
          <div class="row" style="justify-content:flex-end;margin-top:18px">
            <button type="button" class="btn ghost" onclick="closeAddService()">Cancel</button>
            <button class="btn primary" type="submit">${icon("plus")} Add service</button>
          </div>
        </form>
      </div>
    </aside>
  `;
}

function formatTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

async function refreshData() {
  try {
    await loadAll();
    setToast("Data refreshed");
  } catch (error) {
    setToast(error.message);
  }
}

function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  localStorage.setItem("deployer-theme", state.theme);
  document.documentElement.dataset.theme = state.theme;
  render();
}

function selectService(name) {
  state.selected = state.services.find((service) => service.name === name) || null;
  state.activeTab = "overview";
  render();
}

function closePanel() {
  state.selected = null;
  render();
}

function setTab(tab) {
  state.activeTab = tab;
  render();
}

function setEnvName(name) {
  state.envName = name;
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

function openLatestJob() {
  const job = state.jobs[0];
  if (!job) {
    setToast("No jobs yet");
    return;
  }
  selectService(job.service);
  state.activeTab = "deployments";
  render();
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
    await loadAll({ keepSelected: false });
    setToast(`Service ${payload.name} added`);
  } catch (error) {
    setToast(error.message);
  }
}

async function saveEnvVar(event, service) {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api(`/api/services/${service}/env/${state.envName}`, {
      method: "POST",
      body: JSON.stringify({ key: form.get("key"), value: form.get("value") }),
    });
    event.target.reset();
    await loadAll();
    setToast("Environment variable saved");
  } catch (error) {
    setToast(error.message);
  }
}

async function unsetEnvVar(service, key) {
  try {
    await api(`/api/services/${service}/env/${state.envName}/${encodeURIComponent(key)}`, { method: "DELETE" });
    await loadAll();
    setToast("Environment variable removed");
  } catch (error) {
    setToast(error.message);
  }
}

async function deployService(service, environment) {
  const ref = prompt(`Deploy ${service} to ${environment}. Ref/branch/tag/commit:`, environment === "prod" ? "main" : "develop");
  if (ref === null) return;
  await scheduleJob(service, "deploy", environment, { ref: ref || null });
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
    setToast(`${action} job #${job.id} scheduled`);
    await pollJob(job.id);
  } catch (error) {
    setToast(error.message);
  }
}

async function pollJob(jobId) {
  for (let i = 0; i < 60; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, i === 0 ? 250 : 1500));
    const job = await api(`/api/jobs/${jobId}`);
    await loadAll();
    if (["success", "failed"].includes(job.status)) {
      setToast(`Job #${job.id}: ${job.status}`);
      return;
    }
  }
  setToast(`Job #${jobId} is still running`);
}

async function loadRuntimeLog(service, environment) {
  try {
    const result = await api(`/api/services/${service}/logs?environment=${environment}&tail=300`);
    state.jobs.unshift({
      service,
      environment,
      action: "logs",
      status: result.status,
      log: result.log,
      created_at: new Date().toISOString(),
    });
    render();
  } catch (error) {
    setToast(error.message);
  }
}

async function loadStatus(service, environment) {
  try {
    const result = await api(`/api/services/${service}/status?environment=${environment}`);
    state.jobs.unshift({
      service,
      environment,
      action: "status",
      status: result.status,
      log: result.log,
      created_at: new Date().toISOString(),
    });
    render();
  } catch (error) {
    setToast(error.message);
  }
}

async function removeService(service) {
  if (!confirm(`Remove ${service} from deployer catalog? Containers are not stopped automatically.`)) return;
  try {
    await api(`/api/services/${service}`, { method: "DELETE" });
    state.selected = null;
    await loadAll({ keepSelected: false });
    setToast(`Service ${service} removed`);
  } catch (error) {
    setToast(error.message);
  }
}

Object.assign(window, {
  refreshData,
  toggleTheme,
  selectService,
  closePanel,
  setTab,
  setEnvName,
  openAddService,
  closeAddService,
  setAddSourceType,
  createService,
  saveEnvVar,
  unsetEnvVar,
  deployService,
  runtimeAction,
  loadRuntimeLog,
  loadStatus,
  removeService,
  openLatestJob,
});

loadAll({ keepSelected: false }).catch((error) => {
  state.toast = error.message;
  render();
});
