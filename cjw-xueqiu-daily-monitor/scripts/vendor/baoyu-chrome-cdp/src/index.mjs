import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import process from "node:process";

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function getFreePort(fixedEnvName) {
  const fixed = fixedEnvName ? Number.parseInt(process.env[fixedEnvName] ?? "", 10) : NaN;
  if (Number.isInteger(fixed) && fixed > 0) return fixed;

  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close(() => reject(new Error("Unable to allocate a free TCP port.")));
        return;
      }
      const port = address.port;
      server.close((err) => {
        if (err) reject(err);
        else resolve(port);
      });
    });
  });
}

export function findChromeExecutable(options) {
  for (const envName of options.envNames ?? []) {
    const override = process.env[envName]?.trim();
    if (override && fs.existsSync(override)) return override;
  }

  const candidates = process.platform === "darwin"
    ? options.candidates.darwin ?? options.candidates.default
    : process.platform === "win32"
      ? options.candidates.win32 ?? options.candidates.default
      : options.candidates.default;

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }

  const commandFallbacks = ["google-chrome", "chromium", "chromium-browser"];
  for (const command of commandFallbacks) {
    try {
      const result = spawnSync("which", [command], { encoding: "utf-8", timeout: 3_000 });
      if (result.status === 0 && result.stdout.trim()) {
        return result.stdout.trim();
      }
    } catch {
      // ignore and try the next fallback
    }
  }

  return undefined;
}

function isPortListening(port, timeoutMs = 3_000) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    const timer = setTimeout(() => {
      socket.destroy();
      resolve(false);
    }, timeoutMs);
    socket.once("connect", () => {
      clearTimeout(timer);
      socket.destroy();
      resolve(true);
    });
    socket.once("error", () => {
      clearTimeout(timer);
      resolve(false);
    });
    socket.connect(port, "127.0.0.1");
  });
}

async function fetchWithTimeout(url, timeoutMs) {
  if (!timeoutMs || timeoutMs <= 0) {
    return await fetch(url, { redirect: "follow" });
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      redirect: "follow",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJson(url, timeoutMs = 5_000) {
  const response = await fetchWithTimeout(url, timeoutMs);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return await response.json();
}

async function isDebugPortReady(port, timeoutMs = 3_000) {
  try {
    const version = await fetchJson(`http://127.0.0.1:${port}/json/version`, timeoutMs);
    return !!version.webSocketDebuggerUrl;
  } catch {
    return false;
  }
}

function parseDevToolsActivePort(filePath) {
  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const lines = content.split(/\r?\n/);
    const port = Number.parseInt(lines[0]?.trim() ?? "", 10);
    const wsPath = lines[1]?.trim();
    if (port > 0 && wsPath) return { port, wsPath };
  } catch {
    // ignore
  }
  return null;
}

export async function findExistingChromeDebugPort({ profileDir, timeoutMs = 3_000 }) {
  const parsed = parseDevToolsActivePort(path.join(profileDir, "DevToolsActivePort"));
  if (parsed && parsed.port > 0 && await isDebugPortReady(parsed.port, timeoutMs)) {
    return parsed.port;
  }

  if (process.platform === "win32") return null;

  try {
    const result = spawnSync("ps", ["aux"], { encoding: "utf-8", timeout: 5_000 });
    if (result.status !== 0 || !result.stdout) return null;

    const lines = result.stdout
      .split("\n")
      .filter((line) => line.includes(profileDir) && line.includes("--remote-debugging-port="));

    for (const line of lines) {
      const match = line.match(/--remote-debugging-port=(\d+)/);
      const port = Number.parseInt(match?.[1] ?? "", 10);
      if (port > 0 && await isDebugPortReady(port, timeoutMs)) {
        return port;
      }
    }
  } catch {
    // ignore
  }

  return null;
}

export async function waitForChromeDebugPort(port, timeoutMs, options = {}) {
  const start = Date.now();
  let lastError = null;

  while (Date.now() - start < timeoutMs) {
    try {
      const version = await fetchJson(`http://127.0.0.1:${port}/json/version`, 5_000);
      if (version.webSocketDebuggerUrl) return version.webSocketDebuggerUrl;
      lastError = new Error("Missing webSocketDebuggerUrl");
    } catch (error) {
      lastError = error;
    }
    await sleep(200);
  }

  if (options.includeLastError && lastError) {
    throw new Error(
      `Chrome debug port not ready: ${lastError instanceof Error ? lastError.message : String(lastError)}`
    );
  }
  throw new Error("Chrome debug port not ready");
}

export class CdpConnection {
  constructor(ws, defaultTimeoutMs = 15_000) {
    this.ws = ws;
    this.defaultTimeoutMs = defaultTimeoutMs;
    this.nextId = 0;
    this.pending = new Map();
    this.eventHandlers = new Map();

    this.ws.addEventListener("message", (event) => {
      try {
        const data = typeof event.data === "string"
          ? event.data
          : new TextDecoder().decode(event.data);
        const message = JSON.parse(data);

        if (message.method) {
          const handlers = this.eventHandlers.get(message.method);
          if (handlers) handlers.forEach((handler) => handler(message.params));
        }

        if (message.id) {
          const pending = this.pending.get(message.id);
          if (!pending) return;
          this.pending.delete(message.id);
          if (pending.timer) clearTimeout(pending.timer);
          if (message.error?.message) pending.reject(new Error(message.error.message));
          else pending.resolve(message.result);
        }
      } catch {
        // ignore malformed frames
      }
    });

    this.ws.addEventListener("close", () => {
      for (const [id, pending] of this.pending.entries()) {
        this.pending.delete(id);
        if (pending.timer) clearTimeout(pending.timer);
        pending.reject(new Error("CDP connection closed."));
      }
    });
  }

  static async connect(url, timeoutMs, options = {}) {
    const ws = new WebSocket(url);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("CDP connection timeout.")), timeoutMs);
      ws.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      });
      ws.addEventListener("error", () => {
        clearTimeout(timer);
        reject(new Error("CDP connection failed."));
      });
    });
    return new CdpConnection(ws, options.defaultTimeoutMs ?? 15_000);
  }

  on(method, handler) {
    if (!this.eventHandlers.has(method)) this.eventHandlers.set(method, new Set());
    this.eventHandlers.get(method)?.add(handler);
  }

  off(method, handler) {
    this.eventHandlers.get(method)?.delete(handler);
  }

  async send(method, params, options = {}) {
    const id = ++this.nextId;
    const message = { id, method };
    if (params) message.params = params;
    if (options.sessionId) message.sessionId = options.sessionId;

    const timeoutMs = options.timeoutMs ?? this.defaultTimeoutMs;
    return await new Promise((resolve, reject) => {
      const timer = timeoutMs > 0
        ? setTimeout(() => {
          this.pending.delete(id);
          reject(new Error(`CDP timeout: ${method}`));
        }, timeoutMs)
        : null;
      this.pending.set(id, { resolve, reject, timer });
      this.ws.send(JSON.stringify(message));
    });
  }

  close() {
    try {
      this.ws.close();
    } catch {
      // ignore
    }
  }
}

export async function launchChrome({ chromePath, profileDir, port, url, headless = false, extraArgs = [] }) {
  await fs.promises.mkdir(profileDir, { recursive: true });
  const args = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    ...extraArgs,
  ];
  if (headless) args.push("--headless=new");
  if (url) args.push(url);
  return spawn(chromePath, args, { stdio: "ignore" });
}

export function killChrome(chrome) {
  try {
    chrome.kill("SIGTERM");
  } catch {
    // ignore
  }
  setTimeout(() => {
    if (chrome.exitCode === null && chrome.signalCode === null) {
      try {
        chrome.kill("SIGKILL");
      } catch {
        // ignore
      }
    }
  }, 2_000).unref?.();
}

export async function openPageSession({
  cdp,
  reusing,
  url,
  matchTarget,
  enablePage = true,
  enableRuntime = true,
  enableDom = false,
  enableNetwork = false,
  activateTarget = true,
}) {
  let targetId;
  let createdTarget = false;

  if (reusing) {
    const created = await cdp.send("Target.createTarget", { url });
    targetId = created.targetId;
    createdTarget = true;
  } else {
    const targets = await cdp.send("Target.getTargets");
    const existing = targets.targetInfos.find(matchTarget);
    if (existing) {
      targetId = existing.targetId;
    } else {
      const created = await cdp.send("Target.createTarget", { url });
      targetId = created.targetId;
      createdTarget = true;
    }
  }

  const attached = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const sessionId = attached.sessionId;

  if (activateTarget) await cdp.send("Target.activateTarget", { targetId });
  if (enablePage) await cdp.send("Page.enable", {}, { sessionId });
  if (enableRuntime) await cdp.send("Runtime.enable", {}, { sessionId });
  if (enableDom) await cdp.send("DOM.enable", {}, { sessionId });
  if (enableNetwork) await cdp.send("Network.enable", {}, { sessionId });

  return { sessionId, targetId, createdTarget };
}
