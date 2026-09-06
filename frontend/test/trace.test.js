import assert from "node:assert/strict";
import test from "node:test";

import { buildTraceCards, traceStageName } from "../src/lib/trace.js";

function fullTrace() {
  return [
    {
      stage: "intent_router",
      status: "success",
      intent: "DIAGNOSIS",
      confidence: 0.95,
      reason: "gmv_diagnosis_request",
    },
    {
      stage: "semantic_grounding",
      status: "success",
      binding_status: "READY",
      reason: null,
      missing_fields: [],
      ambiguous_fields: [],
    },
    {
      stage: "analysis_question_parser",
      status: "success",
      parsed_question: {
        target_metric: "gmv",
        current_period: { start: "2018-05-01", end: "2018-05-31" },
        baseline_period: { start: "2018-04-01", end: "2018-04-30" },
        scope: { region: "PR", category: null },
        requested_dimensions: ["region", "category"],
        requested_factors: ["traffic", "promotion", "inventory"],
      },
    },
    {
      stage: "capability_assessment",
      status: "success",
      capability: {
        level: "ASSOCIATION_DIAGNOSIS",
        supported_methods: [
          "period_comparison",
          "metric_decomposition",
          "dimension_contribution",
          "traffic_validation",
        ],
        available_dimensions: ["region", "category"],
        missing_evidence: ["promoted_sku_count"],
        data_quality_status: "PASS",
      },
    },
    {
      stage: "analysis_planner",
      status: "success",
      plan: {
        plan_version: "analysis-plan-v1",
        tasks: [
          { task_id: "T1", method: "period_comparison", dimensions: [], factors: [] },
          { task_id: "T2", method: "metric_decomposition", dimensions: [], factors: [] },
          {
            task_id: "T3",
            method: "dimension_contribution",
            dimensions: ["region"],
            factors: [],
          },
        ],
        stop_reason: null,
        missing_evidence: [],
      },
    },
    {
      stage: "analysis_task_executor",
      status: "success",
      queries: [
        { query_id: "Q001", method: "period_comparison", query_role: "baseline" },
      ],
    },
    {
      stage: "deterministic_analyzer",
      status: "success",
      results: [
        {
          analysis_result_id: "A001",
          method: "period_comparison",
          reconciliation: { status: "PASS" },
        },
      ],
    },
    {
      stage: "evidence_checker",
      status: "success",
      evidence: [
        {
          evidence_id: "E001",
          evidence_type: "period_comparison",
          support_level: "HIGH",
        },
      ],
    },
    { stage: "report_generator", status: "success", report_status: "DEGRADED" },
  ];
}

test("maps known trace stages to Chinese names", () => {
  assert.equal(traceStageName("analysis_planner"), "分析计划");
  assert.equal(traceStageName("unknown_stage"), "处理步骤");
});

test("builds labelled cards for every safe diagnosis stage", () => {
  const cards = buildTraceCards(fullTrace());

  assert.equal(cards.length, 9);
  assert.equal(cards[0].name, "意图识别");
  assert.equal(cards[0].status, "已完成");
  assert.deepEqual(cards[0].rows, [
    { label: "意图", value: "DIAGNOSIS" },
    { label: "置信度", value: "0.95" },
    { label: "路由原因", value: "gmv_diagnosis_request" },
  ]);
});

test("extracts canonical question, capability and plan details", () => {
  const cards = buildTraceCards(fullTrace());
  const parsed = cards[2];
  const capability = cards[3];
  const plan = cards[4];

  assert.deepEqual(parsed.rows, [
    { label: "指标", value: "GMV" },
    { label: "当前期", value: "2018-05-01 ~ 2018-05-31" },
    { label: "对比基期", value: "2018-04-01 ~ 2018-04-30" },
    { label: "分析范围", value: "地区：PR" },
    { label: "请求维度", value: "地区、品类" },
    { label: "请求因素", value: "流量、促销、库存" },
  ]);
  assert.deepEqual(capability.rows[1], {
    label: "支持方法",
    value: "期间对比、指标拆解、维度贡献、流量验证",
  });
  assert.deepEqual(plan.rows, [
    { label: "任务 T1", value: "期间对比" },
    { label: "任务 T2", value: "指标拆解" },
    { label: "任务 T3", value: "维度贡献 · 地区" },
  ]);
});

test("extracts query, analysis, evidence and report summaries", () => {
  const cards = buildTraceCards(fullTrace());
  const queries = cards[5];
  const analyses = cards[6];
  const evidence = cards[7];
  const report = cards[8];

  assert.deepEqual(queries.rows, [
    { label: "查询 Q001", value: "期间对比 · baseline" },
  ]);
  assert.deepEqual(analyses.rows, [
    { label: "A001", value: "期间对比 · 对账 PASS" },
  ]);
  assert.deepEqual(evidence.rows, [
    { label: "E001", value: "period_comparison · HIGH" },
  ]);
  assert.deepEqual(report.rows, [{ label: "报告状态", value: "DEGRADED" }]);
});

test("unknown stages render only a status and never dump raw objects", () => {
  const cards = buildTraceCards([
    { stage: "mystery", status: "running", nested: { token: "secret" } },
    null,
    { type: "not-a-stage" },
  ]);

  assert.equal(cards.length, 1);
  assert.equal(cards[0].name, "处理步骤");
  assert.equal(cards[0].status, "进行中");
  assert.deepEqual(cards[0].rows, []);
});

test("clarification trace does not leak retrieval details", () => {
  const cards = buildTraceCards([
    {
      stage: "semantic_grounding",
      status: "success",
      binding_status: "CLARIFICATION_REQUIRED",
      reason: "missing_current_period",
      missing_fields: ["time"],
      ambiguous_fields: [],
      score: 0.97,
      retrieval_used: true,
    },
  ]);

  assert.deepEqual(cards[0].rows, [
    { label: "绑定状态", value: "CLARIFICATION_REQUIRED" },
    { label: "状态原因", value: "missing_current_period" },
    { label: "缺失信息", value: "time" },
  ]);
});
