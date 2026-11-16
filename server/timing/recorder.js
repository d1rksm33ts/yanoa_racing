import { performance } from "node:perf_hooks";
export const SOURCES = Object.freeze({
  agadir: { name: "Maroc Racing Kart Agadir", url: "wss://live-data.apex-timing.com:8023" },
  campillos: { name: "Karting Campillos", url: "wss://live-data.apex-timing.com:9373" },
  spa: { name: "Spa-Francorchamps Karting", url: "wss://live-data.apex-timing.com:9723" },
  goodwill: { name: "Goodwill Karting", url: "wss://live-data.apex-timing.com:9573" },
});
export const DEFAULT_SOURCE = SOURCES.campillos.url;
export class Recorder {
  constructor(
    store,
    {
      socketFactory = (url) => new WebSocket(url),
      retryMs = 1000,
      connectTimeoutMs = 15000,
    } = {},
  ) {
    this.store = store;
    this.socketFactory = socketFactory;
    this.retryMs = retryMs;
    this.connectTimeoutMs = connectTimeoutMs;
    this.active = null;
    this.connection = "idle";
    this.lastError = null;
    this.socket = null;
  }
  status() {
    return {
      recording: this.active
        ? {
            ...this.store.get(this.active).meta,
            durationMs: Math.round(performance.now() - this.started),
          }
        : null,
      connection: this.connection,
      lastError: this.lastError,
    };
  }
  start(name, sourceId = "campillos") {
    if (this.active)
      throw Object.assign(new Error("Er loopt al een opname"), { status: 409 });
    const source = SOURCES[sourceId];
    if (!Object.hasOwn(SOURCES, sourceId))
      throw Object.assign(new Error("Onbekende opnamebron"), { status: 400 });
    this.source = source.url;
    const meta = this.store.create(
      this.source,
      String(name || "").slice(0, 120),
    );
    this.active = meta.id;
    this.started = performance.now();
    this.lastOffset = 0;
    this.attempt = 0;
    this.lastError = null;
    this.flushTimer = setInterval(() => {
      try {
        this.store.flush(this.active);
      } catch (e) {
        this.fail(e);
      }
    }, 1000);
    this.connect();
    return meta;
  }
  record(type, fields = {}) {
    if (!this.active) return;
    const offsetMs = Math.max(
      this.lastOffset,
      Math.round(performance.now() - this.started),
    );
    this.lastOffset = offsetMs;
    return this.store.append(this.active, {
      type,
      offsetMs,
      receivedAt: new Date().toISOString(),
      ...fields,
    });
  }
  fail(error) {
    this.lastError = error.message;
    this.connection = "error";
    const id = this.active;
    this.active = null;
    clearTimeout(this.retryTimer);
    clearTimeout(this.connectTimer);
    clearInterval(this.flushTimer);
    this.socket?.close();
    if (id) {
      try {
        this.store.finish(id, "failed");
      } catch {
        /* Preserve the raw file on disk failure. */
      }
    }
    console.error("Recorder stopped:", error.message);
  }
  connect() {
    if (!this.active) return;
    this.connection = this.attempt ? "reconnecting" : "connecting";
    let ws;
    try {
      ws = this.socketFactory(this.source);
    } catch (e) {
      this.fail(e);
      return;
    }
    this.socket = ws;
    ws.binaryType = "arraybuffer";
    let ended = false;
    const guarded =
      (fn) =>
      (...args) => {
        if (this.socket !== ws || !this.active || ended) return;
        try {
          fn(...args);
        } catch (e) {
          this.fail(e);
        }
      };
    const disconnected = guarded((code, reason) => {
      ended = true;
      clearTimeout(this.connectTimer);
      this.connection = "reconnecting";
      this.record("connection", { state: "disconnected", code, reason });
      this.retryTimer = setTimeout(
        () => this.connect(),
        Math.min(this.retryMs * 2 ** Math.min(this.attempt++, 5), 30000),
      );
    });
    this.connectTimer = setTimeout(() => {
      disconnected(0, "Verbindingstimeout");
      ws.close();
    }, this.connectTimeoutMs);
    ws.addEventListener(
      "open",
      guarded(() => {
        clearTimeout(this.connectTimer);
        this.attempt = 0;
        this.connection = "connected";
        this.lastError = null;
        this.record("connection", { state: "connected" });
      }),
    );
    ws.addEventListener(
      "message",
      guarded((event) => {
        const text = typeof event.data === "string";
        this.record("packet", {
          encoding: text ? "utf8" : "base64",
          payload: text
            ? event.data
            : Buffer.from(event.data).toString("base64"),
        });
      }),
    );
    ws.addEventListener(
      "error",
      guarded((event) => {
        this.lastError = event.message || "WebSocket-fout";
        disconnected(0, this.lastError);
        ws.close();
      }),
    );
    ws.addEventListener("close", (event) =>
      disconnected(event.code, event.reason),
    );
  }
  stop() {
    if (!this.active) return;
    this.record("connection", { state: "stopped" });
    const id = this.active;
    this.active = null;
    clearTimeout(this.retryTimer);
    clearTimeout(this.connectTimer);
    clearInterval(this.flushTimer);
    this.socket?.close();
    this.socket = null;
    this.store.finish(id);
    this.connection = "idle";
  }
}
