import {
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
  renameSync,
  openSync,
  closeSync,
  writeSync,
  readSync,
  fsyncSync,
} from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

// Append-only raw packets are the source of truth. Metadata can be rebuilt.
export class RecordingStore {
  constructor(directory) {
    this.directory = directory;
    this.sessions = new Map();
    mkdirSync(directory, { recursive: true });
    for (const name of readdirSync(directory).filter((n) =>
      /^[0-9a-f-]{36}\.json$/.test(n),
    )) {
      const meta = JSON.parse(readFileSync(join(directory, name), "utf8"));
      const session = { meta, offsets: [], fd: null, bytes: 0 };
      const path = this.path(meta.id);
      // Index in bounded chunks; a power loss can leave only the final line incomplete.
      const fd = openSync(path, "r");
      try {
        const buffer = Buffer.alloc(65536);
        let position = 0;
        let lineStart = 0;
        let size;
        while ((size = readSync(fd, buffer, 0, buffer.length, position))) {
          for (let i = 0; i < size; i++)
            if (buffer[i] === 10) {
              session.offsets.push([lineStart, position + i + 1 - lineStart]);
              lineStart = position + i + 1;
            }
          position += size;
        }
        session.bytes = position;
        meta.incompleteTailBytes = position - lineStart;
      } finally {
        closeSync(fd);
      }
      meta.events = session.offsets.length;
      if (meta.status === "recording") meta.status = "interrupted";
      this.sessions.set(meta.id, session);
      const last = this.events(meta.id, Math.max(0, meta.events - 1), 1)[0];
      meta.durationMs = last?.offsetMs ?? 0;
      this.persist(session);
    }
  }
  path(id) {
    return join(this.directory, `${id}.ndjson`);
  }
  get(id) {
    const session = this.sessions.get(id);
    if (!session)
      throw Object.assign(new Error("Opname niet gevonden"), { status: 404 });
    return session;
  }
  persist(session) {
    const destination = join(this.directory, `${session.meta.id}.json`);
    writeFileSync(`${destination}.tmp`, JSON.stringify(session.meta, null, 2));
    renameSync(`${destination}.tmp`, destination);
  }
  create(source, name) {
    const id = randomUUID();
    const meta = {
      schemaVersion: 1,
      id,
      name: name || `APEX ${new Date().toLocaleString("nl-BE")}`,
      source,
      startedAt: new Date().toISOString(),
      status: "recording",
      events: 0,
      durationMs: 0,
    };
    const session = {
      meta,
      fd: openSync(this.path(id), "wx"),
      offsets: [],
      bytes: 0,
    };
    this.sessions.set(id, session);
    this.persist(session);
    return meta;
  }
  append(id, event) {
    const s = this.get(id);
    if (s.fd === null) throw new Error("Opname is gesloten");
    const record = { ...event, seq: s.offsets.length };
    const data = Buffer.from(JSON.stringify(record) + "\n");
    let written = 0;
    while (written < data.length)
      written += writeSync(s.fd, data, written, data.length - written);
    s.offsets.push([s.bytes, data.length]);
    s.bytes += data.length;
    s.meta.events++;
    s.meta.durationMs = record.offsetMs;
    return record;
  }
  flush(id) {
    const s = this.get(id);
    if (s.fd !== null) fsyncSync(s.fd);
  }
  finish(id, status = "completed") {
    const s = this.get(id);
    if (s.fd !== null) {
      fsyncSync(s.fd);
      closeSync(s.fd);
      s.fd = null;
    }
    s.meta.status = status;
    s.meta.endedAt = new Date().toISOString();
    this.persist(s);
  }
  list() {
    return [...this.sessions.values()]
      .map((s) => ({ ...s.meta }))
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt));
  }
  events(id, after = 0, limit = 250) {
    const s = this.get(id);
    const entries = s.offsets.slice(after, after + limit);
    if (!entries.length) return [];
    const fd = openSync(this.path(id), "r");
    try {
      return entries.map(([offset, size]) => {
        const buffer = Buffer.alloc(size);
        let read = 0;
        while (read < size) {
          const n = readSync(fd, buffer, read, size - read, offset + read);
          if (!n) throw new Error("Onvolledig opnamebestand");
          read += n;
        }
        return JSON.parse(buffer.toString("utf8"));
      });
    } finally {
      closeSync(fd);
    }
  }
}
