import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyTerminal,
  createSseParser,
  upsertProgress,
} from "../src/lib/sse.js";

test("reconstructs events split across arbitrary chunks", () => {
  const events = [];
  const parser = createSseParser((event) => events.push(event));

  parser.push('data: {"type":"pro');
  parser.push('gress","step":"检查数据","status":"running"}\r\n\r');
  parser.push('\ndata: {"type":"result","intent":"QUERY","data":[]}\n\n');
  parser.finish();

  assert.deepEqual(events, [
    { type: "progress", step: "检查数据", status: "running" },
    { type: "result", intent: "QUERY", data: [] },
  ]);
});

test("joins multiple data lines and flushes a final unterminated event", () => {
  const events = [];
  const parser = createSseParser((event) => events.push(event));

  parser.push(': keepalive\ndata: {"type":"result",\ndata: "intent":"DIAGNOSIS"}');
  parser.finish();

  assert.deepEqual(events, [{ type: "result", intent: "DIAGNOSIS" }]);
});

test("ignores comments and malformed JSON", () => {
  const events = [];
  const parser = createSseParser((event) => events.push(event));

  parser.push(': heartbeat\n\ndata: not-json\n\ndata: {"type":"error"}\n\n');
  parser.finish();

  assert.deepEqual(events, [{ type: "error" }]);
});

test("updates a named progress step without mutating prior state", () => {
  const original = [{ text: "识别请求意图", status: "running" }];
  const updated = upsertProgress(original, {
    type: "progress",
    step: "识别请求意图",
    status: "success",
  });
  const appended = upsertProgress(updated, {
    type: "progress",
    step: "生成诊断报告",
    status: "running",
  });

  assert.equal(original[0].status, "running");
  assert.equal(updated[0].status, "success");
  assert.equal(appended.length, 2);
});

test("classifies query, diagnosis, error, and non-terminal events", () => {
  assert.equal(
    classifyTerminal({ type: "result", intent: "QUERY", data: [] }),
    "query",
  );
  assert.equal(
    classifyTerminal({ type: "result", intent: "DIAGNOSIS", answer: "ok" }),
    "diagnosis",
  );
  assert.equal(classifyTerminal({ type: "error", message: "no" }), "error");
  assert.equal(classifyTerminal({ type: "progress" }), null);
});
