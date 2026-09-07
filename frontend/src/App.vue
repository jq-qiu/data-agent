<!-- 单轮问数与诊断工作台：消费 SSE 进度/终态，并安全展示结果、Evidence 与 Trace。 -->
<script setup>
import { computed, nextTick, reactive, ref } from "vue";

import {
  classifyTerminal,
  createSseParser,
  upsertProgress,
} from "./lib/sse.js";
import { buildTraceCards } from "./lib/trace.js";

const API_URL = "/api/query";
const examples = [
  "2018 年 5 月 GMV 是多少？",
  "2018 年 5 月 GMV 相比 4 月变化了多少？",
  "为什么 2018 年 5 月 GMV 下降？",
  "2018 年 5 月哪些品类和州对 GMV 下降贡献最大？",
  "2018 年 5 月流量、促销和库存分别发生了什么变化？",
  "进一步分析 2018 年 5 月圣保罗州 GMV 下降的原因。",
];

const syntheticDemos = [
  { id: "D01", label: "为什么 2018 年 5 月相比 2018 年 4 月 PR 州 GMV 下降？", title: "为什么 2018 年 5 月相比 2018 年 4 月 PR 州 GMV 下降？", cause: "合成案例 · 流量下降" },
  { id: "D03", label: "为什么 2018 年 5 月相比 2018 年 4 月 SC 州 GMV 下降？", title: "为什么 2018 年 5 月相比 2018 年 4 月 SC 州 GMV 下降？", cause: "合成案例 · 促销结束" },
  { id: "D05", label: "为什么 2018 年 5 月相比 2018 年 4 月 SP 州 GMV 下降？", title: "为什么 2018 年 5 月相比 2018 年 4 月 SP 州 GMV 下降？", cause: "合成案例 · 库存不足" },
];

const question = ref("");
const exchanges = ref([]);
const loading = ref(false);
const messagesEl = ref(null);
let activeController = null;

const canSubmit = computed(() => question.value.trim() && !loading.value);

function scrollToBottom() {
  nextTick(() => {
    const element = messagesEl.value;
    if (element) element.scrollTop = element.scrollHeight;
  });
}

function reportLines(markdown) {
  // 只识别少量 Markdown 行类型并用文本插值渲染，避免使用 v-html 注入任意 HTML。
  return String(markdown || "")
    .split(/\r?\n/)
    .map((line, index) => {
      const heading = line.match(/^#{1,6}\s+(.+)$/);
      if (heading) return { id: index, type: "heading", text: heading[1] };
      const bullet = line.match(/^[-*]\s+(.+)$/);
      if (bullet) return { id: index, type: "bullet", text: bullet[1] };
      const meta = line.match(/^\[(.+)]$/);
      if (meta) return { id: index, type: "meta", text: meta[1] };
      return { id: index, type: line.trim() ? "text" : "space", text: line };
    });
}

function statusLabel(status) {
  return {
    COMPLETE: "证据完整",
    DEGRADED: "数据受限",
    NO_DECLINE: "未确认下降",
  }[status] || "分析完成";
}

function supportLabel(level) {
  return {
    HIGH: "高",
    MEDIUM: "中",
    LOW: "低",
    UNSUPPORTED: "不支持",
  }[String(level || "").toUpperCase()] || "待确认";
}

function bindingFieldLabel(field) {
  return {
    intent: "问题类型",
    metric: "指标",
    dimension: "分析维度",
    time: "当前时间",
    baseline: "对比基期",
    scope: "分析范围",
  }[field] || String(field || "待补充信息");
}

function dimensionLabel(dimension) {
  return {
    region: "地区",
    category: "品类",
  }[dimension] || String(dimension || "维度");
}

function applySuggestedQuestion(value) {
  if (!value || loading.value) return;
  question.value = value;
  document.querySelector("#question-input")?.focus();
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function chooseExample(example) {
  question.value = example;
  document.querySelector("#question-input")?.focus();
}

function cancelRequest() {
  activeController?.abort();
}

async function runSyntheticDemo(demo) {
  if (loading.value) return;
  loading.value = true;
  // exchange 必须自身可响应，流式回调对 steps/terminal 的增量修改才能立即触发渲染。
  const exchange = reactive({
    id: crypto.randomUUID(),
    question: demo.title,
    steps: [],
    terminal: null,
    state: "running",
  });
  exchanges.value.push(exchange);
  activeController = new AbortController();
  scrollToBottom();

  try {
    const response = await fetch(`/api/demo/synthetic-diagnosis/${demo.id}`, {
      method: "POST",
      signal: activeController.signal,
    });
    if (!response.ok) throw new Error("HTTP_ERROR");
    if (!response.body) throw new Error("STREAM_UNAVAILABLE");

    const parser = createSseParser((event) => {
      if (event?.type === "progress") {
        // 进度事件可多次更新同一步骤；终态只接受第一个，避免重复结果覆盖已展示内容。
        exchange.steps = upsertProgress(exchange.steps, event);
      } else if (!exchange.terminal && classifyTerminal(event)) {
        exchange.terminal = event;
      }
      scrollToBottom();
    });
    const reader = response.body.getReader();
    // 流式解码保留跨网络分块的 UTF-8 字节，完整事件边界交给 SSE parser 处理。
    const decoder = new TextDecoder("utf-8");
    while (true) {
      // reader.read() 每次得到的是网络字节块，不假设它与 SSE 事件一一对应。
      const { value: chunk, done } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(chunk, { stream: true }));
    }
    parser.push(decoder.decode());
    // flush TextDecoder 与 SSE buffer，处理服务端正常关闭但最后没有额外分隔符的情况。
    parser.finish();
    if (!exchange.terminal) throw new Error("TERMINAL_EVENT_MISSING");
    exchange.state = classifyTerminal(exchange.terminal) === "error" ? "error" : "done";
  } catch (error) {
    if (error?.name === "AbortError") {
      // 用户主动取消与服务异常分开显示，取消不会伪造成后端错误。
      exchange.state = "cancelled";
    } else {
      exchange.state = "error";
      exchange.terminal = {
        type: "error",
        code: "FRONTEND_REQUEST_FAILED",
        message: "合成诊断请求未能完成，请确认后端服务可用后重试。",
      };
    }
  } finally {
    loading.value = false;
    activeController = null;
    scrollToBottom();
  }
}

async function sendQuestion() {
  /** 发送一个完整问题；当前页面不保存可供省略式追问使用的会话语义。 */
  const value = question.value.trim();
  if (!value || loading.value) return;

  question.value = "";
  loading.value = true;
  // 每次请求维护独立状态，历史结果不会参与下一次问题的语义解析。
  const exchange = reactive({
    id: crypto.randomUUID(),
    question: value,
    steps: [],
    terminal: null,
    state: "running",
  });
  exchanges.value.push(exchange);
  activeController = new AbortController();
  scrollToBottom();

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: value }),
      signal: activeController.signal,
    });
    if (!response.ok) throw new Error("HTTP_ERROR");
    if (!response.body) throw new Error("STREAM_UNAVAILABLE");

    const parser = createSseParser((event) => {
      if (event?.type === "progress") {
        // reactive exchange 使这次赋值立即触发进度列表重绘，无需等待整个请求结束。
        exchange.steps = upsertProgress(exchange.steps, event);
      } else if (!exchange.terminal && classifyTerminal(event)) {
        exchange.terminal = event;
      }
      scrollToBottom();
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    while (true) {
      const { value: chunk, done } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(chunk, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.finish();
    // HTTP 流正常结束但没有 result/error 仍视为协议失败，不能把半成品当最终答案。
    if (!exchange.terminal) throw new Error("TERMINAL_EVENT_MISSING");
    exchange.state = classifyTerminal(exchange.terminal) === "error" ? "error" : "done";
  } catch (error) {
    if (error?.name === "AbortError") {
      exchange.state = "cancelled";
    } else {
      exchange.state = "error";
      exchange.terminal = {
        type: "error",
        code: "FRONTEND_REQUEST_FAILED",
        message: "请求未能完成，请确认后端服务可用后重试。",
      };
    }
  } finally {
    loading.value = false;
    activeController = null;
    scrollToBottom();
  }
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" aria-label="示例问题">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">析</div>
        <div>
          <strong>经营分析助手</strong>
          <span>Data Agent · MVP V1</span>
        </div>
      </div>

      <div class="scope-card">
        <span class="eyebrow">当前能力</span>
        <p>单轮问数与 GMV 异动诊断</p>
        <div class="scope-meta"><i></i>只读数据访问</div>
      </div>

      <nav class="examples">
        <div class="section-label">试试这样问</div>
        <button
          v-for="(example, index) in examples"
          :key="example"
          type="button"
          class="example-button"
          :disabled="loading"
          @click="chooseExample(example)"
        >
          <span>{{ String(index + 1).padStart(2, "0") }}</span>
          {{ example }}
        </button>
      </nav>

      <section class="synthetic-demos" aria-label="合成诊断演示">
        <div class="section-label">合成诊断演示</div>
        <p class="demo-note">使用固定 Seed 的 Synthetic Evidence，展示完整诊断证据链。</p>
        <button
          v-for="demo in syntheticDemos"
          :key="demo.id"
          type="button"
          class="example-button synthetic-button"
          :disabled="loading"
          @click="runSyntheticDemo(demo)"
        >
          <span>SYN</span>
          <span class="demo-question">{{ demo.label }}</span>
          <small class="demo-cause">{{ demo.cause }}</small>
        </button>
      </section>

      <p class="boundary-note">结果用于关联诊断，不代表严格因果结论。</p>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <span class="eyebrow">经营数据工作台</span>
          <h1>把问题交给数据，而不是猜测</h1>
        </div>
        <div class="mode-pill"><i></i>单轮分析模式</div>
      </header>

      <section ref="messagesEl" class="conversation" aria-live="polite">
        <div v-if="!exchanges.length" class="empty-state">
          <div class="orb" aria-hidden="true"><span>↗</span></div>
          <span class="eyebrow">从一个完整问题开始</span>
          <h2>查询指标，或追查一次 GMV 变化</h2>
          <p>
            我会展示分析进度、数据结果和证据边界。诊断所需数据不足时，也会明确告诉你缺少什么。
          </p>
          <button type="button" class="primary-link" @click="chooseExample(examples[2])">
            使用推荐诊断问题 <span>→</span>
          </button>
        </div>

        <article v-for="exchange in exchanges" :key="exchange.id" class="exchange">
          <div class="question-row">
            <span class="speaker">你的问题</span>
            <p>{{ exchange.question }}</p>
          </div>

          <div class="answer-row">
            <div class="answer-heading">
              <div class="assistant-mark" aria-hidden="true">析</div>
              <div>
                <span class="speaker">分析助手</span>
                <p v-if="exchange.state === 'running'">正在组织数据证据…</p>
                <p v-else-if="exchange.state === 'cancelled'">本次分析已取消</p>
                <p v-else>本次单轮分析已结束</p>
              </div>
            </div>

            <ol v-if="exchange.steps.length" class="progress-list" aria-label="分析进度">
              <li v-for="step in exchange.steps" :key="step.text" :class="step.status">
                <span class="progress-icon" aria-hidden="true"></span>
                <span>{{ step.text }}</span>
                <small>{{ step.status === "success" ? "完成" : step.status === "error" ? "异常" : "进行中" }}</small>
              </li>
            </ol>

            <div v-if="exchange.state === 'cancelled'" class="notice cancelled-notice">
              已停止读取本次响应。你可以修改问题后重新提交。
            </div>

            <div
              v-else-if="exchange.terminal?.type === 'error'"
              class="notice error-notice"
              role="alert"
            >
              <strong>分析未完成</strong>
              <span>{{ exchange.terminal.message || "请求未能安全完成。" }}</span>
            </div>

            <template v-else-if="exchange.terminal?.type === 'result'">
              <section
                v-if="exchange.terminal.binding_status === 'CLARIFICATION_REQUIRED'"
                class="result-section clarification-section"
              >
                <div class="result-title">
                  <div>
                    <span class="eyebrow">QUESTION CLARIFICATION</span>
                    <h2>还需要补充一点信息</h2>
                  </div>
                  <span class="status-badge clarification-required">待补充</span>
                </div>

                <p class="binding-guidance">{{ exchange.terminal.answer }}</p>

                <div
                  v-if="exchange.terminal.clarification?.missing_fields?.length"
                  class="binding-group"
                >
                  <h3>缺少的信息</h3>
                  <div class="binding-chips">
                    <span
                      v-for="field in exchange.terminal.clarification.missing_fields"
                      :key="field"
                    >{{ bindingFieldLabel(field) }}</span>
                  </div>
                </div>

                <div
                  v-if="exchange.terminal.clarification?.ambiguous_fields?.length"
                  class="binding-group"
                >
                  <h3>需要明确的内容</h3>
                  <div class="binding-chips ambiguous">
                    <span
                      v-for="field in exchange.terminal.clarification.ambiguous_fields"
                      :key="field"
                    >{{ bindingFieldLabel(field) }}</span>
                  </div>
                </div>

                <div
                  v-if="exchange.terminal.clarification?.candidates?.metrics?.length
                    || exchange.terminal.clarification?.candidates?.dimensions?.length
                    || exchange.terminal.clarification?.candidates?.values?.length"
                  class="binding-group"
                >
                  <h3>识别到的候选</h3>
                  <ul class="candidate-list">
                    <li
                      v-for="metric in exchange.terminal.clarification.candidates.metrics"
                      :key="`metric-${metric}`"
                    >指标：{{ String(metric).toUpperCase() }}</li>
                    <li
                      v-for="dimension in exchange.terminal.clarification.candidates.dimensions"
                      :key="`dimension-${dimension}`"
                    >维度：{{ dimensionLabel(dimension) }}</li>
                    <li
                      v-for="item in exchange.terminal.clarification.candidates.values"
                      :key="`value-${item.dimension}-${item.value}`"
                    >{{ dimensionLabel(item.dimension) }}：{{ item.value }}</li>
                  </ul>
                </div>

                <div
                  v-if="exchange.terminal.clarification?.suggested_question"
                  class="suggestion-card"
                >
                  <span>推荐完整问法</span>
                  <p>{{ exchange.terminal.clarification.suggested_question }}</p>
                  <button
                    type="button"
                    :disabled="loading"
                    @click="applySuggestedQuestion(exchange.terminal.clarification.suggested_question)"
                  >填入输入框</button>
                </div>
              </section>

              <section
                v-else-if="exchange.terminal.binding_status === 'UNSUPPORTED'
                  || exchange.terminal.intent === 'UNSUPPORTED'"
                class="result-section unsupported-section"
              >
                <div class="result-title">
                  <div>
                    <span class="eyebrow">ABILITY BOUNDARY</span>
                    <h2>当前能力暂不支持</h2>
                  </div>
                  <span class="status-badge unsupported">不支持</span>
                </div>
                <p class="binding-guidance">{{ exchange.terminal.answer }}</p>
                <div
                  v-if="exchange.terminal.clarification?.candidates?.metrics?.length"
                  class="binding-group"
                >
                  <h3>识别到的指标候选</h3>
                  <div class="binding-chips ambiguous">
                    <span
                      v-for="metric in exchange.terminal.clarification.candidates.metrics"
                      :key="metric"
                    >{{ String(metric).toUpperCase() }}</span>
                  </div>
                </div>
              </section>

              <section v-else-if="exchange.terminal.intent === 'QUERY'" class="result-section">
                <div class="result-title">
                  <div>
                    <span class="eyebrow">QUERY RESULT</span>
                    <h2>查询结果</h2>
                  </div>
                  <span class="count-pill">{{ exchange.terminal.data?.length || 0 }} 行</span>
                </div>
                <div v-if="exchange.terminal.data?.length" class="table-shell">
                  <table>
                    <thead>
                      <tr>
                        <th v-for="column in Object.keys(exchange.terminal.data[0])" :key="column" scope="col">
                          {{ column }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, rowIndex) in exchange.terminal.data" :key="rowIndex">
                        <td v-for="column in Object.keys(exchange.terminal.data[0])" :key="column">
                          {{ displayValue(row[column]) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else class="notice">查询已完成，但没有符合条件的数据。</div>
              </section>

              <section v-else class="result-section diagnosis-section">
                <div class="result-title">
                  <div>
                    <span class="eyebrow">DIAGNOSIS REPORT</span>
                    <h2>诊断报告</h2>
                  </div>
                  <span :class="['status-badge', String(exchange.terminal.report_status || '').toLowerCase()]">
                    {{ statusLabel(exchange.terminal.report_status) }}
                  </span>
                </div>

                <div class="report-paper">
                  <template v-for="line in reportLines(exchange.terminal.answer)" :key="line.id">
                    <h3 v-if="line.type === 'heading'">{{ line.text }}</h3>
                    <div v-else-if="line.type === 'bullet'" class="report-bullet"><i></i><span>{{ line.text }}</span></div>
                    <div v-else-if="line.type === 'meta'" class="report-meta">{{ line.text }}</div>
                    <div v-else-if="line.type === 'space'" class="report-space"></div>
                    <p v-else>{{ line.text }}</p>
                  </template>
                </div>

                <div v-if="exchange.terminal.evidence?.length" class="evidence-block">
                  <div class="subsection-heading">
                    <h3>证据摘要</h3>
                    <span>{{ exchange.terminal.evidence.length }} 项已校验证据</span>
                  </div>
                  <div class="evidence-grid">
                    <article v-for="item in exchange.terminal.evidence" :key="item.evidence_id" class="evidence-card">
                      <div>
                        <span class="evidence-id">{{ item.evidence_id }}</span>
                        <span :class="['support', String(item.support_level || '').toLowerCase()]">
                          {{ supportLabel(item.support_level) }}支持
                        </span>
                      </div>
                      <strong>{{ item.claim || item.evidence_type }}</strong>
                      <small>{{ item.evidence_type }}</small>
                    </article>
                  </div>
                </div>

                <div v-if="exchange.terminal.limitations?.length" class="limitations">
                  <div class="subsection-heading"><h3>数据边界</h3></div>
                  <ul>
                    <li v-for="limitation in exchange.terminal.limitations" :key="limitation">{{ limitation }}</li>
                  </ul>
                </div>

                <details v-if="exchange.terminal.analysis_trace?.length" class="trace-panel">
                  <summary>查看分析轨迹 · {{ exchange.terminal.analysis_trace.length }} 个阶段</summary>
                  <!-- Trace 卡片只消费 trace.js 的白名单投影，不直接遍历后端原始对象。 -->
                  <div class="trace-cards">
                    <section
                      v-for="card in buildTraceCards(exchange.terminal.analysis_trace)"
                      :key="card.stage"
                      class="trace-card"
                    >
                      <div class="trace-card-heading">
                        <strong>{{ card.name }}</strong>
                        <small>{{ card.status }}</small>
                      </div>
                      <dl v-if="card.rows.length" class="trace-card-rows">
                        <template
                          v-for="(row, rowIndex) in card.rows"
                          :key="`${card.stage}-${rowIndex}`"
                        >
                          <dt>{{ row.label }}</dt>
                          <dd>{{ row.value }}</dd>
                        </template>
                      </dl>
                      <p v-else class="trace-card-empty">该阶段无额外明细</p>
                    </section>
                  </div>
                </details>
              </section>
            </template>
          </div>
        </article>
      </section>

      <form class="composer" @submit.prevent="sendQuestion">
        <div class="composer-inner">
          <label for="question-input">输入一个完整的单轮问题</label>
          <div class="input-row">
            <textarea
              id="question-input"
              v-model="question"
              rows="1"
              maxlength="2000"
              placeholder="例如：为什么 2018 年 5 月 GMV 下降？"
              :disabled="loading"
              @keydown.enter.exact.prevent="sendQuestion"
            ></textarea>
            <button v-if="loading" type="button" class="cancel-button" @click="cancelRequest">停止</button>
            <button v-else type="submit" class="send-button" :disabled="!canSubmit" aria-label="发送问题">→</button>
          </div>
          <div class="composer-meta">
            <span>Enter 发送</span>
            <span>只读查询 · 不执行经营动作</span>
          </div>
        </div>
      </form>
    </main>
  </div>
</template>


<style scoped>
.synthetic-button {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  white-space: normal;
  text-align: left;
  line-height: 1.45;
}
.demo-question {
  color: inherit;
  font-size: 12px;
  letter-spacing: 0;
}
.demo-cause {
  color: #7f9d97;
  font-size: 10px;
  letter-spacing: 0.08em;
}
</style>
