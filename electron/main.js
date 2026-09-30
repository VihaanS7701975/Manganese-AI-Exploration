// Manganese AI desktop shell (Electron).
//
// Launches the existing FastAPI backend as a hidden child process, waits
// for its health endpoint, then loads the existing production Vite build
// (../frontend/dist) in an app window. No dev terminal is shown; the
// backend is killed when the app quits.
//
// Backend resolution order (first hit wins):
//   1. Bundled PyInstaller exe: <resources>/backend/manganese-backend.exe
//      (build via electron/backend-pyinstaller.spec -- full offline bundle).
//   2. First Python with the backend stack: %MANGANESE_PYTHON% (process),
//      User-registry MANGANESE_PYTHON (current even without relogin),
//      per-user %LOCALAPPDATA% Python installs, else `python` on PATH.
//      Set MANGANESE_PYTHON persistently (setx) on the demo machine.
//
// The frontend's API config already defaults to http://localhost:8000, so
// the desktop backend intentionally binds that same fixed port -- no
// frontend change needed. Localhost dev workflow (`npm run dev` + uvicorn
// manually) is untouched by this file.

const { app, BrowserWindow, dialog } = require('electron');
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const BACKEND_PORT = 8000;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/`;
// Project root in dev (electron/ sibling of frontend/ + backend/); in a
// packaged app, project files live under resources/.
const PROJECT_ROOT = app.isPackaged
  ? path.join(process.resourcesPath, 'project')
  : path.join(__dirname, '..');

let backendProc = null;
let mainWindow = null;

function bundledBackendExe() {
  const candidate = path.join(
    process.resourcesPath, 'backend', 'manganese-backend.exe');
  return fs.existsSync(candidate) ? candidate : null;
}

// Backend resolution: bundled exe first, else the first Python with the
// backend stack. Process env alone is unreliable on Windows (stale
// Explorer/shell blocks miss setx values until relogin), so resolve in
// this order: %MANGANESE_PYTHON% (process) -> User-registry
// MANGANESE_PYTHON (via reg.exe, always current) -> per-user Python
// installs under %LOCALAPPDATA%\Programs\Python probed for
// (pandas, fastapi, uvicorn) -> `python` last resort (health check +
// dialog below handle a miss). All probes are synchronous with hard
// timeouts, so resolution always settles quickly.
function regQueryUserEnv(name) {
  try {
    const out = execFileSync(
      'reg', ['query', 'HKCU\\Environment', '/v', name],
      { windowsHide: true, timeout: 15000, encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'ignore'] });
    const line = String(out).split('\n').find((l) => l.includes(name));
    const m = line && line.match(/REG_\w+\s+(.*?)\s*$/);
    return m ? m[1] : null;
  } catch {
    return null;
  }
}

function hasBackendStack(py) {
  try {
    execFileSync(py, ['-c', 'import pandas, fastapi, uvicorn'],
      { windowsHide: true, timeout: 30000,
        stdio: ['ignore', 'ignore', 'ignore'] });
    return true;
  } catch {
    return false;
  }
}

function scanLocalPythons() {
  const base = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python');
  let dirs = [];
  try {
    dirs = fs.readdirSync(base).filter((d) => /^python/i.test(d));
  } catch {
    return [];
  }
  return dirs
    .map((d) => path.join(base, d, 'python.exe'))
    .filter((p) => {
      try {
        return fs.existsSync(p);
      } catch {
        return false;
      }
    });
}

function resolvePython() {
  const seen = [];
  const push = (p) => {
    if (p && !seen.includes(p)) seen.push(p);
  };
  push(process.env.MANGANESE_PYTHON);
  push(regQueryUserEnv('MANGANESE_PYTHON'));
  for (const p of scanLocalPythons()) push(p);
  for (const p of seen) {
    if (hasBackendStack(p)) return p;
  }
  return 'python';
}

function startBackend() {
  return new Promise((resolve, reject) => {
    const exe = bundledBackendExe();
    let cmd;
    let args;
    let cwd;
    if (exe) {
      cmd = exe;
      args = ['--port', String(BACKEND_PORT)];
      cwd = path.dirname(exe);
    } else {
      cmd = resolvePython();
      args = ['-m', 'uvicorn', 'backend.main:app',
        '--host', '127.0.0.1', '--port', String(BACKEND_PORT)];
      cwd = PROJECT_ROOT;
    }
    // windowsHide: no visible terminal for the backend.
    backendProc = spawn(cmd, args, { cwd, windowsHide: true, shell: false });
    backendProc.on('error', (err) => reject(
      new Error(`Could not start backend (${cmd}): ${err.message}. ` +
        'Install the Python environment (requirements.txt) or set MANGANESE_PYTHON ' +
        'to the Python that has it.')));
    backendProc.stdout?.on('data', () => {});
    backendProc.stderr?.on('data', () => {});
    pollHealth(resolve, reject, Date.now());
  });
}

function pollHealth(resolve, reject, startedAt) {
  const timeoutMs = 90000;
  const tick = async () => {
    if (Date.now() - startedAt > timeoutMs) {
      reject(new Error(`Backend did not answer ${HEALTH_URL} within 90 s.`));
      return;
    }
    try {
      const res = await fetch(HEALTH_URL);
      if (res.ok) {
        resolve();
        return;
      }
    } catch {
      // Not up yet -- keep polling.
    }
    setTimeout(tick, 1000);
  };
  tick();
}

function stopBackend() {
  if (backendProc && !backendProc.killed) {
    try {
      backendProc.kill();
    } catch {
      // Already gone -- nothing to clean up.
    }
    backendProc = null;
  }
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    backgroundColor: '#020617',
    title: 'GeoManganese AI — Team RIZZLERS (SIH26009)',
    autoHideMenuBar: true,
  });
  const entry = path.join(PROJECT_ROOT, 'frontend', 'dist', 'index.html');
  if (!fs.existsSync(entry)) {
    dialog.showErrorBox('Build missing',
      `Frontend production build not found:\n${entry}\nRun "npm run build" in frontend/ first.`);
  } else {
    await mainWindow.loadFile(entry);
  }
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  try {
    await startBackend();
  } catch (err) {
    dialog.showErrorBox('Backend failed to start', String(err));
    app.quit();
    return;
  }
  await createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', stopBackend);
