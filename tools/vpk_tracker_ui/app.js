/* Deadlock VPK Tracker UI.
 * No framework, no build step. Snapshot data and diffs come from the local
 * Python server; this file only chooses, filters and draws them.
 */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const number = new Intl.NumberFormat('en-US');

const state = {
  snapshots: [],
  latest: null,
  previous: null,
  from: '',
  to: '',
  vpk: 'all',
  kind: 'all',
  q: '',
  offset: 0,
  limit: 200,
  sort: 'path',
  data: null,
  selected: null,
  loading: false,
};

const live = { data: null, lastCapture: '', polling: false, toastTimer: null };
const history = { open: false, snapshots: [], builds: [], login: null, buildError: '', compare: null, loading: false };

function fmtBytes(value) {
  const n = Number(value || 0);
  const abs = Math.abs(n);
  if (abs < 1024) return `${n} B`;
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  let size = abs / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${n < 0 ? '-' : ''}${size.toFixed(size >= 100 ? 0 : 1)} ${units[unit]}`;
}

function fmtDelta(value) {
  const n = Number(value || 0);
  if (!n) return '—';
  return `${n > 0 ? '+' : '-'}${fmtBytes(Math.abs(n))}`;
}

function fmtCrc(value) {
  if (value === null || value === undefined) return '—';
  return `0x${Number(value).toString(16).padStart(8, '0')}`;
}

function fmtDate(value, withTime = false) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, withTime
    ? { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { month: 'short', day: 'numeric', year: 'numeric' });
}

function sourceLabel(row) {
  const source = row && row.source ? row.source : {};
  return source.kind === 'manifest' ? 'Steam' : 'Local';
}

function snapshotLabel(row) {
  if (!row) return 'Baseline';
  const build = row.build || row.label || 'Snapshot';
  return `${build} · ${sourceLabel(row)}`;
}

function fmtClock(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function snapshotOptionLabel(row) {
  const time = fmtClock(row.created_at);
  return `${snapshotLabel(row)}${time ? ` · ${time}` : ''}`;
}

/* ---- popit shape fallback ------------------------------------------------ */

const popitShape = { active: false, observer: null };

function popitPolygon(width, height) {
  // A rounded rectangle with superellipse corners, matching the LBP3 Popit.
  const radius = Math.min(52, Math.max(24, Math.min(width, height) * 0.075));
  const exponent = 0.5;
  const steps = 24;
  const points = [];
  const add = (x, y) => points.push(`${x.toFixed(2)}px ${y.toFixed(2)}px`);
  const curve = (point) => {
    for (let index = 0; index <= steps; index += 1) {
      add(...point((index / steps) * (Math.PI / 2)));
    }
  };
  curve((angle) => [
    radius - radius * Math.pow(Math.cos(angle), exponent),
    radius - radius * Math.pow(Math.sin(angle), exponent),
  ]);
  curve((angle) => [
    width - radius + radius * Math.pow(Math.sin(angle), exponent),
    radius - radius * Math.pow(Math.cos(angle), exponent),
  ]);
  curve((angle) => [
    width - radius + radius * Math.pow(Math.cos(angle), exponent),
    height - radius + radius * Math.pow(Math.sin(angle), exponent),
  ]);
  curve((angle) => [
    radius - radius * Math.pow(Math.sin(angle), exponent),
    height - radius + radius * Math.pow(Math.cos(angle), exponent),
  ]);
  return `polygon(${points.join(',')})`;
}

function shapePopitPanel(panel) {
  if (!panel || panel.hidden || !popitShape.active) return;
  const width = panel.offsetWidth;
  const height = panel.offsetHeight;
  if (width < 2 || height < 2) return;
  panel.style.clipPath = popitPolygon(width, height);
  panel.classList.add('popit-shaped');
}

function initPopitShapes() {
  if (typeof CSS === 'undefined' || !CSS.supports) return;
  if (CSS.supports('corner-shape', 'squircle')) return;
  if (!CSS.supports('clip-path', 'polygon(0px 0px, 1px 0px, 1px 1px)')) return;
  popitShape.active = true;
  const panels = [$('#launcher-panel'), $('#history-panel')].filter(Boolean);
  panels.forEach(shapePopitPanel);
  if ('ResizeObserver' in window) {
    popitShape.observer = new ResizeObserver((entries) => {
      entries.forEach((entry) => shapePopitPanel(entry.target));
    });
    panels.forEach((panel) => popitShape.observer.observe(panel));
  }
}

/* ---- launcher ------------------------------------------------------------ */

const launcher = { open: false, info: null, job: null, polling: false, showLog: false, loginPending: false, loginTimer: null };

function launcherChip(label, value, ok) {
  const chip = document.createElement('span');
  chip.className = 'launcher-chip';
  chip.dataset.ok = String(!!ok);
  const key = document.createElement('b');
  key.textContent = label;
  const val = document.createElement('span');
  val.textContent = value;
  chip.append(key, val);
  return chip;
}

function showLauncherError(error) {
  const box = $('#launcher-error');
  box.textContent = errorText(error);
  box.hidden = false;
}

function renderLauncher() {
  const info = launcher.info;
  const status = $('#launcher-status');
  status.replaceChildren();
  if (info) {
    status.append(
      launcherChip('Viewer', info.s2v ? 'ready' : 'missing', !!info.s2v),
      launcherChip('Steam tools', info.sfd ? 'ready' : 'missing', !!info.sfd),
      launcherChip('Snapshots', number.format(info.snapshots || 0), (info.snapshots || 0) > 0),
    );
  }

  const job = launcher.job || (info && info.job);
  const running = !!(job && job.status === 'running');
  const loginReady = !!(info && info.login_window && info.sfd);
  $('#launcher-snapshot').disabled = running || !!(info && !info.s2v);
  const canFetch = !!(info && info.sfd && info.logged_in);
  $('#launcher-fetch').disabled = running || !canFetch;
  $('#launcher-fetch').title = info && !info.logged_in ? 'Sign in to Steam first.' : '';
  $('#launcher-login').disabled = !loginReady;
  $('#launcher-login-note').textContent = info && info.logged_in
    ? 'Signed in.'
    : info && !info.login_window
      ? 'Steam sign-in is only available on Windows.'
      : info && !info.sfd
        ? 'Steam tools are missing.'
        : launcher.loginPending
          ? 'Waiting for Steam sign-in…'
          : 'Sign in once to fetch old builds.';

  const block = $('#launcher-job');
  if (job && job.status !== 'idle') {
    if (job.id !== launcher.jobId) {
      launcher.jobId = job.id;
      launcher.showLog = false;
    }
    block.hidden = false;
    const action = job.action === 'manifest' ? 'Fetching build' : 'Snapshotting game';
    $('#launcher-job-label').textContent = job.status === 'running'
      ? `${action}…`
      : job.status === 'done'
        ? (job.action === 'manifest' ? 'Build saved.' : 'Snapshot saved.')
        : 'Job failed.';
    const hasLog = !!(job.log_tail || '').trim();
    $('#launcher-log-toggle').hidden = !hasLog;
    $('#launcher-log-toggle').textContent = launcher.showLog ? 'Hide' : 'Details';
    const log = $('#launcher-log');
    log.hidden = !launcher.showLog;
    log.textContent = hasLog ? job.log_tail : '';
    if (launcher.showLog) log.scrollTop = log.scrollHeight;
    if (job.status === 'failed') {
      showLauncherError(new Error('Job failed. Open Details.'));
    }
  } else {
    block.hidden = true;
    $('#launcher-log').textContent = '';
  }
  $('#launcher-foot').textContent = info
    ? `${number.format(info.snapshots || 0)} snapshots · ${info.logged_in ? 'Steam signed in' : 'Steam signed out'}`
    : 'Checking…';
}

async function reloadLatestSnapshot({ follow = true, reset = false } = {}) {
  const body = await api('/api/snapshots');
  state.snapshots = body.snapshots || [];
  state.latest = body.latest;
  state.previous = body.previous;
  if (!state.snapshots.length) return;
  if (follow) {
    state.to = body.latest;
    state.from = body.previous && body.previous !== body.latest ? body.previous : '';
    state.offset = 0;
    if (reset) {
      state.kind = 'all';
      state.vpk = 'all';
      state.q = '';
      $('#search').value = '';
    }
  }
  populateSelects();
  await load();
  if (launcher.info) launcher.info.snapshots = state.snapshots.length;
  renderLauncher();
  if (history.open) await refreshHistory();
}

async function refreshLauncher({ refreshLogin = false } = {}) {
  const before = launcher.job;
  const info = await api(`/api/launcher${refreshLogin ? '?login=refresh' : ''}`);
  launcher.info = info;
  launcher.job = info.job;
  if (info.logged_in) {
    launcher.loginPending = false;
    clearTimeout(launcher.loginTimer);
  }
  renderLauncher();
  if (before && before.status === 'running' && info.job.status === 'done') {
    $('#launcher-error').hidden = true;
    await reloadLatestSnapshot({ follow: true, reset: true });
  }
}

async function openLauncherPanel() {
  if (history.open) closeHistoryPanel();
  launcher.open = true;
  $('#launcher-panel').hidden = false;
  $('#launcher-backdrop').hidden = false;
  $('#launcher-toggle').setAttribute('aria-expanded', 'true');
  shapePopitPanel($('#launcher-panel'));
  try {
    await refreshLauncher();
  } catch (error) {
    showLauncherError(error);
  }
}

function closeLauncherPanel() {
  launcher.open = false;
  $('#launcher-panel').hidden = true;
  $('#launcher-backdrop').hidden = true;
  $('#launcher-toggle').setAttribute('aria-expanded', 'false');
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `${response.status} ${response.statusText}`);
  return body;
}

async function startLauncherJob(action, payload = {}) {
  $('#launcher-error').hidden = true;
  launcher.showLog = false;
  const body = await postJson('/api/jobs', { action, ...payload });
  launcher.job = body.job;
  launcher.jobId = body.job.id;
  launcher.open = true;
  renderLauncher();
}

async function startLauncherLogin() {
  $('#launcher-error').hidden = true;
  await postJson('/api/login', {});
  launcher.loginPending = true;
  clearTimeout(launcher.loginTimer);
  launcher.loginTimer = setTimeout(() => {
    launcher.loginPending = false;
    renderLauncher();
  }, 120000);
  renderLauncher();
  setTimeout(() => refreshLauncher({ refreshLogin: true }).catch(() => {}), 2500);
}

async function fetchLauncherBuild() {
  const value = $('#launcher-manifest').value.trim();
  if (!value) {
    showLauncherError('Enter a build number.');
    return;
  }
  if (/^\d+$/.test(value)) {
    const feed = await api('/api/builds');
    const row = (feed.builds || []).find((item) => item.build === value);
    if (!row) {
      showLauncherError('Build not found.');
      return;
    }
    if (row.snapshot_id) {
      showLauncherError('That build is already captured.');
      return;
    }
    await startLauncherJob('manifest', { sha: row.sha });
    return;
  }
  await startLauncherJob('manifest', { manifest: value });
}

async function pollLauncher() {
  if (launcher.polling) return;
  if (!launcher.open && !(launcher.job && launcher.job.status === 'running')) return;
  launcher.polling = true;
  try {
    await refreshLauncher();
  } catch (error) {
    if (launcher.open) showLauncherError(error);
  } finally {
    launcher.polling = false;
  }
}

/* ---- live watch --------------------------------------------------------- */

function showLiveToast(text) {
  const toast = $('#live-toast');
  $('#live-toast-text').textContent = text;
  toast.hidden = false;
  clearTimeout(live.toastTimer);
  live.toastTimer = setTimeout(() => { toast.hidden = true; }, 8000);
}

function renderLive() {
  const data = live.data;
  const chip = $('#live-chip');
  const label = $('#live-label');
  if (!data) {
    label.textContent = 'Checking game…';
    chip.dataset.state = 'starting';
    return;
  }
  chip.dataset.state = data.state || 'watching';
  chip.title = data.last_error || data.message || '';
  if (data.state === 'unavailable') label.textContent = data.message || 'Game not found';
  else if (data.state === 'error') label.textContent = data.last_error ? 'Patch watch error' : 'Patch error';
  else if (data.state === 'needs-first') label.textContent = 'Snapshot the game once';
  else if (data.state === 'settling') label.textContent = `Patch detected · ${data.build || 'checking'}…`;
  else if (data.state === 'capturing') label.textContent = `Capturing ${data.build || 'build'}…`;
  else if (data.state === 'waiting') label.textContent = 'Waiting for job';
  else {
    const recent = data.last_capture_at && Date.now() - new Date(data.last_capture_at).getTime() < 120000;
    label.textContent = recent && data.last_capture_status === 'done'
      ? `Build ${data.last_capture_build || data.build || '?'} captured`
      : `Live · ${data.build || 'checking'}`;
  }
}

async function pollLive() {
  if (live.polling) return;
  live.polling = true;
  try {
    const data = await api('/api/live');
    const before = live.data;
    const previousCapture = live.lastCapture;
    const previousStatus = live.captureStatus;
    const first = !before;
    live.data = data;
    live.captureStatus = data.last_capture_status || '';
    const finished = data.last_capture
      && data.last_capture_status === 'done'
      && (previousCapture !== data.last_capture || previousStatus === 'running');
    if (finished && !first) {
      await refreshSnapshots({ follow: true, reset: true });
      await load();
      const summary = state.data && state.data.summary;
      const changed = summary ? summary.added + summary.modified + summary.removed : 0;
      const buildOnly = summary && summary.build_changed && !changed;
      showLiveToast(`Build ${data.last_capture_build || data.build || '?'} captured · ${buildOnly ? 'build only' : `${number.format(changed)} changed`}`);
      if (history.open) await refreshHistory();
    }
    live.lastCapture = data.last_capture || live.lastCapture;
    renderLive();
  } catch (error) {
    const chip = $('#live-chip');
    chip.dataset.state = 'error';
    $('#live-label').textContent = 'Patch watch offline';
    chip.title = errorText(error);
  } finally {
    live.polling = false;
  }
}

/* ---- history ------------------------------------------------------------ */

function historyStatRow(stats) {
  const host = document.createElement('div');
  host.className = 'history-stats';
  if (!stats) {
    const quiet = document.createElement('span');
    quiet.className = 'quiet';
    quiet.textContent = 'first';
    host.append(quiet);
    return host;
  }
  if (!stats.added && !stats.modified && !stats.removed) {
    const quiet = document.createElement('span');
    quiet.className = stats.build_changed ? 'build-only' : 'quiet';
    quiet.textContent = stats.build_changed ? 'build only' : 'same';
    host.append(quiet);
    return host;
  }
  for (const [kind, value, mark] of [['add', stats.added, '+'], ['mod', stats.modified, '~'], ['del', stats.removed, '-']]) {
    const span = document.createElement('span');
    span.className = kind;
    span.textContent = `${mark}${number.format(value || 0)}`;
    host.append(span);
  }
  return host;
}

function renderHistory() {
  const snapCount = $('#history-snapshot-count');
  const buildStatus = $('#history-build-status');
  const login = history.login;
  snapCount.textContent = `${history.snapshots.length} version${history.snapshots.length === 1 ? '' : 's'}`;
  buildStatus.textContent = login
    ? (login.logged_in ? 'Signed in' : (login.known === false ? 'Steam unavailable' : 'Signed out'))
    : '—';
  $('#history-signin').hidden = !(login && login.known !== false && !login.logged_in);

  const snapshotHost = $('#history-snapshots');
  snapshotHost.replaceChildren();
  if (!history.snapshots.length) {
    const empty = document.createElement('div');
    empty.className = 'history-empty';
    empty.textContent = 'No snapshots yet.';
    snapshotHost.append(empty);
  } else {
    for (const row of [...history.snapshots].reverse()) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'history-row';
      button.dataset.snapId = row.id;
      button.dataset.base = String(row.id === state.from);
      button.dataset.head = String(row.id === state.to);
      const main = document.createElement('div');
      main.className = 'history-row-main';
      const build = document.createElement('span');
      build.className = 'history-build';
      build.textContent = row.build || row.label || 'Snapshot';
      const meta = document.createElement('span');
      meta.className = 'history-meta';
      const digest = String(row.digest || '').replace('blake3:', '').slice(0, 7);
      meta.textContent = `${digest ? `${digest} · ` : ''}${sourceLabel(row)} · ${fmtDate(row.created_at, true)}`;
      main.append(build, meta);
      button.append(main, historyStatRow(row.stats));
      button.title = `${snapshotLabel(row)} · click to compare · shift-click for base`;
      snapshotHost.append(button);
    }
  }

  const buildHost = $('#history-builds');
  buildHost.replaceChildren();
  if (history.buildError) {
    const empty = document.createElement('div');
    empty.className = 'history-empty';
    empty.textContent = history.buildError;
    buildHost.append(empty);
  } else if (!history.builds.length) {
    const empty = document.createElement('div');
    empty.className = 'history-empty';
    empty.textContent = 'No Steam builds.';
    buildHost.append(empty);
  } else {
    for (const row of history.builds) {
      const item = document.createElement('div');
      item.className = 'history-row history-build-row';
      const main = document.createElement('div');
      const top = document.createElement('div');
      top.className = 'history-row-main';
      const build = document.createElement('span');
      build.className = 'history-build';
      build.textContent = row.build;
      const when = document.createElement('span');
      when.className = 'history-meta';
      when.textContent = fmtDate(row.date);
      top.append(build, when);
      const meta = document.createElement('div');
      meta.className = 'history-meta';
      meta.textContent = `${row.short_sha || 'commit'} · ${number.format(row.files_changed)} files`;
      meta.title = (row.changed || []).slice(0, 12).map((change) => change.path).join('\n');
      main.append(top, meta);
      const actions = document.createElement('div');
      actions.className = 'history-build-actions';
      if (row.snapshot_id) {
        const open = document.createElement('button');
        open.type = 'button';
        open.className = 'history-mini';
        open.dataset.openSnapshot = row.snapshot_id;
        open.textContent = 'Open';
        actions.append(open);
      } else if (login && login.logged_in) {
        const fetch = document.createElement('button');
        fetch.type = 'button';
        fetch.className = 'history-mini';
        fetch.dataset.fetchSha = row.sha;
        fetch.dataset.build = row.build;
        fetch.textContent = 'Fetch';
        actions.append(fetch);
      }
      item.append(main, actions);
      buildHost.append(item);
    }
  }
  renderHistoryCompare();
}

function renderHistoryCompare() {
  const to = state.snapshots.find((row) => row.id === state.to);
  if (!to) {
    $('#history-compare').textContent = 'Select a version.';
    $('#history-show').disabled = true;
    return;
  }
  const from = state.snapshots.find((row) => row.id === state.from);
  let text = `${from ? snapshotLabel(from) : 'Baseline'} → ${snapshotLabel(to)}`;
  const data = state.data;
  if (data && data.to && data.to.id === state.to && (data.from ? data.from.id === state.from : !state.from) && !data.baseline) {
    const s = data.summary;
    const buildOnly = data.build && data.build.changed && !s.added && !s.modified && !s.removed;
    text += buildOnly
      ? ' · build only'
      : !s.added && !s.modified && !s.removed
        ? ' · same'
        : ` · +${number.format(s.added)} ~${number.format(s.modified)} -${number.format(s.removed)}`;
  }
  $('#history-compare').textContent = text;
  $('#history-show').disabled = false;
}

async function refreshHistory() {
  if (history.loading) return;
  history.loading = true;
  history.buildError = '';
  try {
    let login = null;
    try {
      login = await api('/api/login/status');
    } catch (error) {
      login = null;
    }
    const body = await api('/api/history');
    history.snapshots = body.snapshots || [];
    history.login = login || body.login || history.login;
    try {
      const feed = await api('/api/builds');
      history.builds = feed.builds || [];
      history.login = login || feed.login || history.login;
    } catch (error) {
      history.builds = [];
      history.buildError = errorText(error);
    }
    if (!state.to && history.snapshots.length) state.to = history.snapshots[history.snapshots.length - 1].id;
    renderHistory();
  } catch (error) {
    history.snapshots = [];
    history.builds = [];
    history.buildError = errorText(error);
    renderHistory();
  } finally {
    history.loading = false;
  }
}

function openHistoryPanel() {
  if (launcher.open) closeLauncherPanel();
  history.open = true;
  $('#history-panel').hidden = false;
  $('#history-backdrop').hidden = false;
  $('#history-toggle').setAttribute('aria-expanded', 'true');
  shapePopitPanel($('#history-panel'));
  renderHistory();
  refreshHistory().catch((error) => {
    history.buildError = errorText(error);
    renderHistory();
  });
}

function closeHistoryPanel() {
  history.open = false;
  $('#history-panel').hidden = true;
  $('#history-backdrop').hidden = true;
  $('#history-toggle').setAttribute('aria-expanded', 'false');
}

function previousBefore(id) {
  const index = state.snapshots.findIndex((row) => row.id === id);
  return index > 0 ? state.snapshots[index - 1] : null;
}

function errorText(error) {
  const raw = error && error.message ? error.message : String(error);
  if (raw.startsWith('steam-login-required')) return 'Sign in to Steam first.';
  if (raw.startsWith('steam-no-access')) return 'Steam denied access. Sign in and try again.';
  if (raw.startsWith('steam-rate-limited')) return 'Steam is rate limiting. Wait a few minutes.';
  if (raw === 'job-already-running') return 'Wait for the current job to finish.';
  if (raw === 'manifest-target-wants-depot:manifest') return 'Enter a build or depot:manifest.';
  if (raw === 'build-list-unavailable' || raw === 'build-list-unreadable') return 'Build list unavailable.';
  if (raw === 'build-sha-invalid') return 'That build could not be resolved.';
  if (raw.startsWith('manifest-vpk-missing')) return 'That build has no directory VPKs.';
  if (raw === 'game-changed-during-snapshot') return 'The game changed while reading. Retrying.';
  if (raw.startsWith('game-not-stable')) return 'The game is still changing. Try again in a moment.';
  if (raw === 'deadlock-missing') return 'Game not found.';
  if (raw === 'source-2-viewer-missing' || raw === 'steam-file-downloader-missing') return 'A tool is missing.';
  return raw.replace(/^[a-z0-9.-]+:/, '').replace(/[-_]/g, ' ').slice(0, 180);
}

async function api(path) {
  const response = await fetch(path, { cache: 'no-store' });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `${response.status} ${response.statusText}`);
  return body;
}

/* ---- selects and timeline ------------------------------------------------ */

function populateSelects() {
  const from = $('#from-select');
  const to = $('#to-select');
  from.replaceChildren();
  to.replaceChildren();

  const baseline = document.createElement('option');
  baseline.value = '';
  baseline.textContent = 'Baseline';
  from.append(baseline);

  for (const row of state.snapshots) {
    const option = document.createElement('option');
    option.value = row.id;
    option.textContent = snapshotOptionLabel(row);
    from.append(option);

    const target = option.cloneNode(true);
    to.append(target);
  }
  from.value = state.from;
  to.value = state.to;
}

function renderTimeline() {
  const track = $('#timeline');
  track.replaceChildren();
  for (const row of state.snapshots) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'snap-tick';
    button.dataset.id = row.id;
    button.dataset.to = String(row.id === state.to);
    button.dataset.from = String(row.id === state.from);
    button.title = `${snapshotLabel(row)} · click to compare · shift-click for base`;
    const build = document.createElement('span');
    build.className = 'b';
    build.textContent = `${row.build || row.label || 'Snapshot'} · ${sourceLabel(row)}`;
    const when = document.createElement('span');
    when.className = 't';
    when.textContent = fmtDate(row.created_at, true);
    button.append(build, when);
    track.append(button);
  }
  const meta = $('#tl-meta');
  if (state.data) {
    meta.textContent = `${state.snapshots.length} snapshot${state.snapshots.length === 1 ? '' : 's'} · ${number.format(state.data.to.summary.entries)} files`;
  } else {
    meta.textContent = `${state.snapshots.length} snapshots`;
  }
}

function renderHeader() {
  const data = state.data;
  if (!data) return;
  const from = data.from;
  const to = data.to;
  const noEntryChanges = !data.baseline
    && !data.summary.added && !data.summary.modified && !data.summary.removed;
  const buildOnly = noEntryChanges && data.build && data.build.changed;
  $('#build-chip').textContent = `${to.build || '—'} · ${sourceLabel(to)}`;
  $('#stage-title').textContent = data.baseline ? 'Snapshot' : buildOnly ? 'Build update' : 'Changes';
  $('#stage-sub').textContent = data.baseline
    ? `${number.format(to.summary.entries)} files · ${fmtDate(to.created_at)}`
    : `${from ? snapshotLabel(from) : 'Baseline'} → ${snapshotLabel(to)}${buildOnly ? ' · no VPK entry changes' : ''}`;
  $('#digest-chip').textContent = `${to.digest.replace('blake3:', '').slice(0, 12)}…`;
  $('#digest-chip').title = to.digest;
  $('#insp-sub').textContent = data.baseline ? 'Snapshot' : 'Select a row';
  $('#kind-seg').querySelectorAll('button').forEach((button) => {
    const disabled = data.baseline && button.dataset.kind !== 'all';
    button.disabled = disabled;
    button.setAttribute('aria-pressed', String(button.dataset.kind === state.kind));
  });
}

/* ---- rail ---------------------------------------------------------------- */

function renderRail() {
  const data = state.data;
  const host = $('#vpk-list');
  host.replaceChildren();
  if (!data) return;

  const all = document.createElement('button');
  all.type = 'button';
  all.className = 'vpk-item';
  all.dataset.vpk = 'all';
  all.setAttribute('aria-pressed', String(state.vpk === 'all'));
  const allName = document.createElement('span');
  allName.className = 'vpk-name';
  allName.textContent = 'All VPKs';
  const allCount = document.createElement('span');
  allCount.className = 'vpk-count';
  allCount.textContent = data.baseline
    ? number.format(data.to.summary.entries)
    : number.format(data.summary.added + data.summary.removed + data.summary.modified);
  all.append(allName, allCount);
  host.append(all);

  const max = Math.max(1, ...data.vpks.map((vpk) => data.baseline
    ? vpk.entries_after
    : vpk.added + vpk.removed + vpk.modified));

  for (const vpk of data.vpks) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'vpk-item';
    button.dataset.vpk = vpk.name;
    button.setAttribute('aria-pressed', String(state.vpk === vpk.name));
    const name = document.createElement('span');
    name.className = 'vpk-name';
    name.textContent = vpk.name;
    const count = document.createElement('span');
    count.className = 'vpk-count';
    count.textContent = data.baseline
      ? number.format(vpk.entries_after)
      : `${vpk.added ? `+${vpk.added}` : ''}${vpk.added && (vpk.modified || vpk.removed) ? ' ' : ''}${vpk.modified ? `~${vpk.modified}` : ''}${vpk.modified && vpk.removed ? ' ' : ''}${vpk.removed ? `-${vpk.removed}` : ''}` || '0';
    const bar = document.createElement('span');
    bar.className = 'vpk-bar';
    if (data.baseline) {
      const fill = document.createElement('i');
      fill.style.width = '100%';
      fill.style.background = 'var(--teal)';
      bar.append(fill);
    } else {
      const total = vpk.added + vpk.modified + vpk.removed;
      for (const [kind, countValue] of [['added', vpk.added], ['modified', vpk.modified], ['removed', vpk.removed]]) {
        if (!countValue) continue;
        const fill = document.createElement('i');
        fill.className = kind;
        fill.style.width = `${(countValue / Math.max(1, total)) * (total / max) * 100}%`;
        bar.append(fill);
      }
      if (!total) bar.style.background = 'rgba(255,255,255,0.04)';
    }
    button.append(name, count, bar);
    host.append(button);
  }

  const summary = data.baseline ? data.to.summary : data.summary;
  $('#rail-foot').textContent = `${number.format(summary.entries || data.to.summary.entries)} files · ${number.format(data.to.summary.chunks)} chunks`;
}

/* ---- stats and table ----------------------------------------------------- */

function statCard(label, value, sub, className = '') {
  const card = document.createElement('div');
  card.className = `stat ${className}`;
  const k = document.createElement('div');
  k.className = 'k';
  k.textContent = label;
  const v = document.createElement('div');
  v.className = 'v';
  v.textContent = value;
  const s = document.createElement('div');
  s.className = 's';
  s.textContent = sub || '';
  card.append(k, v, s);
  return card;
}

function renderStats() {
  const data = state.data;
  const host = $('#stats');
  host.replaceChildren();
  if (!data) return;
  if (data.baseline) {
    const summary = data.to.summary;
    host.append(
      statCard('Files', number.format(summary.entries), `${data.to.vpks.length} VPKs`),
      statCard('Chunks', number.format(summary.chunks), 'archive parts'),
      statCard('Size', fmtBytes(summary.dir_bytes), 'on disk'),
      statCard('Digest', data.to.digest.slice(7, 19), 'BLAKE3', 'bytes'),
    );
    return;
  }
  const summary = data.summary;
  host.append(
    statCard('Added', number.format(summary.added), `${fmtBytes(summary.bytes_added)}`, 'added'),
    statCard('Removed', number.format(summary.removed), `${fmtBytes(summary.bytes_removed)}`, 'removed'),
    statCard('Modified', number.format(summary.modified), `${number.format(summary.repacked)} repacked`, 'modified'),
    statCard('Chunks', number.format(summary.new_chunks), `${number.format(summary.changed_chunks)} changed`, 'bytes'),
  );
}

function renderTable() {
  const data = state.data;
  const body = $('#rows');
  body.replaceChildren();
  if (!data) return;

  const rows = data.rows;
  rows.forEach((row, index) => {
    const tr = document.createElement('tr');
    tr.dataset.index = String(index);
    tr.setAttribute('aria-selected', String(state.selected === index));
    tr.title = row.path;

    const kind = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = `kind ${row.kind}`;
    badge.textContent = row.kind;
    kind.append(badge);

    const path = document.createElement('td');
    path.className = 'path';
    path.textContent = row.path;

    const vpk = document.createElement('td');
    vpk.className = 'vpk';
    vpk.textContent = row.vpk;

    const oldSize = document.createElement('td');
    oldSize.className = 'num';
    oldSize.textContent = row.old_size === null ? '—' : fmtBytes(row.old_size);

    const newSize = document.createElement('td');
    newSize.className = 'num';
    newSize.textContent = row.new_size === null ? '—' : fmtBytes(row.new_size);

    const delta = document.createElement('td');
    delta.className = `num delta ${row.delta > 0 ? 'plus' : row.delta < 0 ? 'minus' : ''}`;
    delta.textContent = row.kind === 'baseline' ? '—' : fmtDelta(row.delta);

    tr.append(kind, path, vpk, oldSize, newSize, delta);
    tr.addEventListener('click', () => {
      state.selected = index;
      $$('#rows tr').forEach((node) => node.setAttribute('aria-selected', String(node === tr)));
      renderInspector();
    });
    body.append(tr);
  });

  const empty = $('#empty');
  const start = data.filtered ? data.offset + 1 : 0;
  const end = Math.min(data.offset + rows.length, data.filtered);
  if (!rows.length) {
    const build = data.build || {};
    const buildOnly = !data.baseline && build.changed
      && !data.summary.added && !data.summary.modified && !data.summary.removed;
    empty.hidden = false;
    if (state.q) {
      $('#empty-title').textContent = 'No matches';
      $('#empty-body').textContent = `Nothing matches “${state.q}”.`;
    } else if (data.baseline) {
      $('#empty-title').textContent = 'No files';
      $('#empty-body').textContent = 'This snapshot has no files.';
    } else if (buildOnly) {
      $('#empty-title').textContent = 'Build updated';
      $('#empty-body').textContent = `Build ${build.before || 'previous'} → ${build.after || 'current'}. No VPK directory entries changed.`;
    } else {
      $('#empty-title').textContent = 'No changes';
      $('#empty-body').textContent = 'This pair is identical.';
    }
  } else {
    empty.hidden = true;
  }
  $('#page-label').textContent = data.filtered
    ? `${number.format(start)}–${number.format(end)} of ${number.format(data.filtered)}`
    : '0 files';
  $('#prev').disabled = data.offset <= 0;
  $('#next').disabled = data.offset + rows.length >= data.filtered;
  $('#limit').value = String(state.limit);
}

/* ---- inspector and chunks ------------------------------------------------ */

function detailRow(label, value, className = '') {
  const key = document.createElement('div');
  key.className = 'k';
  key.textContent = label;
  const val = document.createElement('div');
  val.className = `v ${className}`;
  val.textContent = value;
  return [key, val];
}

function renderInspector() {
  const data = state.data;
  const host = $('#entry-detail');
  host.replaceChildren();
  if (!data) return;
  const row = state.selected === null ? null : data.rows[state.selected];
  if (!row) {
    const note = document.createElement('div');
    note.className = 'detail-note';
    note.textContent = data.baseline ? 'Select a file.' : 'Select a change.';
    host.append(note);
    $('#insp-sub').textContent = data.baseline ? 'Snapshot' : 'Select a row';
    renderChunks();
    return;
  }
  $('#insp-sub').textContent = `${row.kind} · ${row.vpk}`;
  const path = document.createElement('div');
  path.className = 'detail-path';
  path.textContent = row.path;
  host.append(path);
  const grid = document.createElement('div');
  grid.className = 'detail-grid';
  grid.append(
    ...detailRow('Change', row.kind, row.kind),
    ...detailRow('VPK', row.vpk),
    ...detailRow('Snapshot', snapshotLabel(data.to)),
    ...detailRow('CRC before', fmtCrc(row.old_crc)),
    ...detailRow('CRC after', fmtCrc(row.new_crc)),
    ...detailRow('Size before', row.old_size === null ? '—' : `${number.format(row.old_size)} B`),
    ...detailRow('Size after', row.new_size === null ? '—' : `${number.format(row.new_size)} B`),
    ...detailRow('Delta', row.kind === 'baseline' ? '—' : fmtDelta(row.delta), row.delta > 0 ? 'added' : row.delta < 0 ? 'removed' : ''),
    ...detailRow('Archive', `chunk #${row.fnum} · 0x${Number(row.offset).toString(16)}`),
    ...detailRow('Folder', row.path.includes('/') ? row.path.split('/')[0] : '(root)'),
  );
  host.append(grid);
  renderChunks();
}

function renderChunks() {
  const data = state.data;
  const host = $('#chunk-list');
  host.replaceChildren();
  if (!data) return;
  const title = document.querySelector('.chunk-block .slab-sub');
  const chunks = data.new_chunks.length ? data.new_chunks : data.changed_chunks;
  title.textContent = data.new_chunks.length
    ? `New chunks · ${data.new_chunks.length}`
    : data.changed_chunks.length
      ? `Changed chunks · ${data.changed_chunks.length}`
      : 'Chunks';
  if (!chunks.length) {
    const note = document.createElement('div');
    note.className = 'chunk-empty';
    note.textContent = data.baseline
      ? `${number.format(data.to.summary.chunks)} chunks in this snapshot.`
      : 'No changed chunks.';
    host.append(note);
    return;
  }
  chunks.slice(0, 12).forEach((chunk) => {
    const item = document.createElement('div');
    item.className = 'chunk';
    const name = document.createElement('span');
    name.className = 'n';
    name.textContent = chunk.name;
    const size = document.createElement('span');
    size.className = 's';
    size.textContent = fmtBytes(chunk.size);
    const date = document.createElement('span');
    date.className = 'd';
    const stamp = chunk.mtime_ns
      ? new Date(chunk.mtime_ns / 1e6).toLocaleString()
      : `sha1 ${String(chunk.sha1 || '').slice(0, 12)}`;
    date.textContent = `${chunk.vpk || ''}${chunk.vpk ? ' · ' : ''}${stamp}`;
    item.append(name, size, date);
    host.append(item);
  });
}

/* ---- loading ------------------------------------------------------------- */

function showError(error) {
  const empty = $('#empty');
  empty.hidden = false;
  $('#empty-title').textContent = 'Could not load';
  $('#empty-body').textContent = errorText(error);
  $('#stage-sub').textContent = 'Try Refresh.';
  console.error(error);
}

async function refreshSnapshots({ follow = false, reset = false } = {}) {
  const body = await api('/api/snapshots');
  state.snapshots = body.snapshots || [];
  state.latest = body.latest;
  state.previous = body.previous;
  if (!state.snapshots.length) {
    $('#stage-sub').textContent = 'No snapshots';
    $('#empty').hidden = false;
    $('#empty-title').textContent = 'No snapshots yet';
    $('#empty-body').textContent = 'Use Launcher to snapshot the game.';
    return false;
  }
  if (follow) {
    state.to = body.latest;
    state.from = body.previous && body.previous !== body.latest ? body.previous : '';
    state.offset = 0;
    if (reset) {
      state.kind = 'all';
      state.vpk = 'all';
      state.q = '';
      $('#search').value = '';
    }
  } else {
    const ids = new Set(state.snapshots.map((row) => row.id));
    if (!ids.has(state.to)) state.to = state.latest;
    if (!ids.has(state.from) || state.from === state.to) {
      state.from = state.previous && state.previous !== state.to ? state.previous : '';
    }
  }
  populateSelects();
  return true;
}

async function load() {
  if (!state.snapshots.length) return;
  if (state.from === state.to) {
    const previous = previousBefore(state.to);
    state.from = previous ? previous.id : '';
  }
  state.loading = true;
  $('#stage-sub').textContent = 'Loading…';
  document.body.classList.add('loading');
  const params = new URLSearchParams({
    to: state.to,
    from: state.from,
    vpk: state.vpk,
    kind: state.kind,
    q: state.q,
    offset: String(state.offset),
    limit: String(state.limit),
    sort: state.sort,
  });
  try {
    const data = await api(`/api/diff?${params.toString()}`);
    state.data = data;
    if (data.baseline) state.kind = 'all';
    state.selected = null;
    renderHeader();
    renderStats();
    renderRail();
    renderTable();
    renderInspector();
    renderTimeline();
    if (history.open) renderHistory();
    $('#kind-seg').querySelectorAll('button').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.kind === state.kind));
    });
  } catch (error) {
    state.data = null;
    showError(error);
  } finally {
    state.loading = false;
    document.body.classList.remove('loading');
  }
}

/* ---- events -------------------------------------------------------------- */

function bind() {
  $('#from-select').addEventListener('change', (event) => {
    state.from = event.target.value;
    state.offset = 0;
    load();
  });
  $('#to-select').addEventListener('change', (event) => {
    state.to = event.target.value;
    const previous = previousBefore(state.to);
    state.from = previous ? previous.id : '';
    state.offset = 0;
    populateSelects();
    load();
  });
  $('#kind-seg').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-kind]');
    if (!button || button.disabled) return;
    state.kind = button.dataset.kind;
    state.offset = 0;
    load();
  });
  let searchTimer;
  $('#search').addEventListener('input', (event) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.q = event.target.value.trim();
      state.offset = 0;
      load();
    }, 240);
  });
  $('#limit').addEventListener('change', (event) => {
    state.limit = Number(event.target.value) || 200;
    state.offset = 0;
    load();
  });
  $('#prev').addEventListener('click', () => {
    state.offset = Math.max(0, state.offset - state.limit);
    load();
  });
  $('#next').addEventListener('click', () => {
    state.offset += state.limit;
    load();
  });
  $('#refresh').addEventListener('click', async () => {
    try {
      if (await refreshSnapshots()) await load();
    } catch (error) {
      showError(error);
    }
  });
  $('#launcher-toggle').addEventListener('click', () => {
    if (launcher.open) closeLauncherPanel();
    else openLauncherPanel();
  });
  $('#launcher-close').addEventListener('click', closeLauncherPanel);
  $('#launcher-backdrop').addEventListener('click', closeLauncherPanel);
  $('#launcher-snapshot').addEventListener('click', () => {
    startLauncherJob('snapshot').catch(showLauncherError);
  });
  $('#launcher-fetch').addEventListener('click', () => {
    fetchLauncherBuild().catch(showLauncherError);
  });
  $('#launcher-manifest').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      $('#launcher-fetch').click();
    }
  });
  $('#launcher-login').addEventListener('click', () => {
    startLauncherLogin().catch(showLauncherError);
  });
  $('#launcher-log-toggle').addEventListener('click', () => {
    launcher.showLog = !launcher.showLog;
    renderLauncher();
  });
  $('#history-toggle').addEventListener('click', () => {
    if (history.open) closeHistoryPanel();
    else openHistoryPanel();
  });
  $('#history-close').addEventListener('click', closeHistoryPanel);
  $('#history-backdrop').addEventListener('click', closeHistoryPanel);
  $('#history-show').addEventListener('click', () => {
    closeHistoryPanel();
    populateSelects();
    load();
  });
  $('#history-clear').addEventListener('click', () => {
    state.to = state.latest || '';
    const previous = previousBefore(state.to);
    state.from = previous ? previous.id : '';
    state.offset = 0;
    populateSelects();
    load();
  });
  $('#history-snapshots').addEventListener('click', (event) => {
    const button = event.target.closest('[data-snap-id]');
    if (!button) return;
    if (event.shiftKey) {
      state.from = button.dataset.snapId === state.to ? '' : button.dataset.snapId;
    } else {
      state.to = button.dataset.snapId;
      const previous = previousBefore(state.to);
      state.from = previous ? previous.id : '';
    }
    state.offset = 0;
    populateSelects();
    load();
  });
  $('#history-signin').addEventListener('click', () => {
    closeHistoryPanel();
    openLauncherPanel().catch(showLauncherError);
  });
  $('#history-builds').addEventListener('click', (event) => {
    const open = event.target.closest('[data-open-snapshot]');
    if (open) {
      state.to = open.dataset.openSnapshot;
      const previous = previousBefore(state.to);
      state.from = previous ? previous.id : '';
      state.offset = 0;
      closeHistoryPanel();
      populateSelects();
      load();
      return;
    }
    const fetch = event.target.closest('[data-fetch-sha]');
    if (fetch) {
      closeHistoryPanel();
      openLauncherPanel()
        .then(() => startLauncherJob('manifest', { sha: fetch.dataset.fetchSha }))
        .catch(showLauncherError);
    }
  });
  $('#live-toast-close').addEventListener('click', () => {
    $('#live-toast').hidden = true;
  });
  $('#vpk-list').addEventListener('click', (event) => {
    const button = event.target.closest('[data-vpk]');
    if (!button) return;
    state.vpk = button.dataset.vpk;
    state.offset = 0;
    load();
  });
  $('#timeline').addEventListener('click', (event) => {
    const button = event.target.closest('[data-id]');
    if (!button) return;
    if (event.shiftKey) {
      state.from = button.dataset.id === state.to ? '' : button.dataset.id;
    } else {
      state.to = button.dataset.id;
      const previous = previousBefore(state.to);
      state.from = previous ? previous.id : '';
    }
    state.offset = 0;
    populateSelects();
    load();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === '/' && document.activeElement !== $('#search')) {
      event.preventDefault();
      $('#search').focus();
    }
    if (event.key === 'Escape' && document.activeElement === $('#search')) {
      $('#search').value = '';
      $('#search').blur();
      state.q = '';
      state.offset = 0;
      load();
    }
    if (event.key === 'Escape' && document.activeElement !== $('#search')) {
      if (launcher.open) closeLauncherPanel();
      else if (history.open) closeHistoryPanel();
    }
  });
}

async function boot() {
  bind();
  initPopitShapes();
  setInterval(pollLauncher, 1200);
  setInterval(pollLive, 1600);
  try {
    if (await refreshSnapshots()) await load();
    await pollLive();
  } catch (error) {
    showError(error);
  }
}

boot();
