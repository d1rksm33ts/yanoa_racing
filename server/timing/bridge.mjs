// Transport and raw recording only. All session/reference/feedback logic is server-side Python.
import { writeSync } from 'node:fs';
import { resolve } from 'node:path';
import { Recorder } from './recorder.js';
import { RecordingStore } from './store.js';

class BridgeStore extends RecordingStore {
  append(id, event) {
    const saved = super.append(id, event);
    writeSync(1, JSON.stringify({recordingId: id, packet: saved}) + '\n');
    return saved;
  }
}
const store = new BridgeStore(resolve(process.env.DATA_DIR));
const recorder = new Recorder(store);
recorder.start(process.env.RECORDING_NAME || 'Live Coach', process.env.SOURCE_ID);
const timer = setInterval(() => {
  const status = recorder.status();
  writeSync(1, JSON.stringify({status: {connection: status.connection, lastError: status.lastError}}) + '\n');
  if (!status.recording) process.exitCode = 1;
  if (!status.recording) clearInterval(timer);
}, 10000);
function stop() {
  clearInterval(timer);
  recorder.stop();
}
process.once('SIGTERM', stop);
process.once('SIGINT', stop);
