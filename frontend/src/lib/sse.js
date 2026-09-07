/** 解析后端 SSE 字节流，并把进度与终态转换为前端可消费的稳定结构。 */

function parseBlock(block) {
  // SSE 允许一个事件包含多行 data；必须先按规范拼接，再作为完整 JSON 解码。
  const dataLines = [];
  for (const line of block.split(/\r?\n/)) {
    // 空行负责分隔事件，以冒号开头的是 SSE 心跳/注释，都不属于业务 data。
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
    // 单个畸形事件被忽略，避免解析异常中断后续仍可能到达的合法终态。
    return null;
  }
}

export function createSseParser(onEvent) {
  /**
   * 创建增量解析器。push 接受任意边界的文本块，finish 负责刷新没有尾部分隔符的事件。
   */
  let buffer = "";

  function drain(shouldFlush = false) {
    // 浏览器读到的 chunk 不保证等于一个 SSE 事件，因此只消费双换行之前的完整 block。
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
      // 未形成完整事件的尾部留在 buffer，等待下一次网络分块继续拼接。
      buffer += chunk;
      drain();
    },
    finish() {
      drain(true);
    },
  };
}

export function upsertProgress(steps, event) {
  // 返回新数组而不原地修改旧状态，便于 Vue 稳定检测每个步骤的状态变化。
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
  // 同名步骤从 running 更新为 success/error；新步骤则按到达顺序追加。
  if (index === -1) next.push(update);
  else next[index] = update;
  return next;
}

export function classifyTerminal(event) {
  /** 只识别协议定义的终态；progress 等中间事件返回 null。 */
  if (!event || typeof event !== "object") return null;
  // error 本身就是终态；result 再按意图和 binding_status 区分不同结果组件。
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
