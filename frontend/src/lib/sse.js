function parseBlock(block) {
  const dataLines = [];
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") dataLines.push(value);
  }
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
}

export function createSseParser(onEvent) {
  let buffer = "";

  function drain(shouldFlush = false) {
    const separator = /\r?\n\r?\n/;
    let match = separator.exec(buffer);
    while (match) {
      const block = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      const event = parseBlock(block);
      if (event !== null) onEvent(event);
      match = separator.exec(buffer);
    }
    if (shouldFlush && buffer.trim()) {
      const event = parseBlock(buffer);
      if (event !== null) onEvent(event);
      buffer = "";
    }
  }

  return {
    push(chunk) {
      buffer += chunk;
      drain();
    },
    finish() {
      drain(true);
    },
  };
}

export function upsertProgress(steps, event) {
  if (event?.type !== "progress" || typeof event.step !== "string") {
    return steps;
  }
  const index = steps.findIndex((step) => step.text === event.step);
  const next = steps.map((step) => ({ ...step }));
  const update = {
    text: event.step,
    status: ["running", "success", "error"].includes(event.status)
      ? event.status
      : "running",
  };
  if (index === -1) next.push(update);
  else next[index] = update;
  return next;
}

export function classifyTerminal(event) {
  if (!event || typeof event !== "object") return null;
  if (event.type === "error") return "error";
  if (event.type !== "result") return null;
  if (event.intent === "QUERY" && Array.isArray(event.data)) return "query";
  if (event.binding_status === "CLARIFICATION_REQUIRED") return "clarification";
  if (
    event.binding_status === "UNSUPPORTED" ||
    event.intent === "UNSUPPORTED"
  ) {
    return "unsupported";
  }
  return "diagnosis";
}
