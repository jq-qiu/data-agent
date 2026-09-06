const STAGE_NAMES = {
  intent_router: "意图识别",
  semantic_grounding: "语义绑定",
  analysis_question_parser: "问题解析",
  capability_assessment: "数据能力检查",
  analysis_planner: "分析计划",
  analysis_task_executor: "受控查询",
  deterministic_analyzer: "确定性计算",
  evidence_checker: "证据校验",
  report_generator: "报告生成",
  query_execution: "问数执行",
};

const METHOD_NAMES = {
  period_comparison: "期间对比",
  metric_decomposition: "指标拆解",
  dimension_contribution: "维度贡献",
  candidate_validation: "候选因素验证",
  traffic_validation: "流量验证",
  promotion_validation: "促销验证",
  inventory_validation: "库存验证",
};

const DIMENSION_NAMES = {
  region: "地区",
  category: "品类",
};

const FACTOR_NAMES = {
  traffic: "流量",
  promotion: "促销",
  inventory: "库存",
};

function empty() {
  return "—";
}

function joinNames(values, names) {
  if (!Array.isArray(values) || values.length === 0) return empty();
  return values
    .map((value) => names[value] || String(value))
    .join("、");
}

function periodText(period) {
  if (!period || typeof period !== "object") return empty();
  const start = period.start;
  const end = period.end;
  if (start == null || end == null) return empty();
  return `${start} ~ ${end}`;
}

function scopeText(scope) {
  if (!scope || typeof scope !== "object") return empty();
  const parts = [];
  if (scope.region) parts.push(`地区：${scope.region}`);
  if (scope.category) parts.push(`品类：${scope.category}`);
  return parts.length ? parts.join("；") : "整体";
}

function statusText(status) {
  if (status === "success") return "已完成";
  if (status === "error") return "失败";
  if (status === "running") return "进行中";
  return status || "未知";
}

function intentRows(item) {
  const rows = [];
  if (item.intent != null) rows.push({ label: "意图", value: String(item.intent) });
  if (item.confidence != null) {
    rows.push({ label: "置信度", value: String(item.confidence) });
  }
  if (item.reason != null) rows.push({ label: "路由原因", value: String(item.reason) });
  return rows;
}

function groundingRows(item) {
  const rows = [];
  if (item.binding_status != null) {
    rows.push({ label: "绑定状态", value: String(item.binding_status) });
  }
  if (item.reason != null) rows.push({ label: "状态原因", value: String(item.reason) });
  if (Array.isArray(item.missing_fields) && item.missing_fields.length) {
    rows.push({ label: "缺失信息", value: item.missing_fields.join("、") });
  }
  if (Array.isArray(item.ambiguous_fields) && item.ambiguous_fields.length) {
    rows.push({ label: "待明确信息", value: item.ambiguous_fields.join("、") });
  }
  return rows;
}

function parsedQuestionRows(item) {
  const parsed = item.parsed_question;
  if (!parsed || typeof parsed !== "object") return [];
  const rows = [];
  if (parsed.target_metric != null) {
    rows.push({ label: "指标", value: String(parsed.target_metric).toUpperCase() });
  }
  rows.push({ label: "当前期", value: periodText(parsed.current_period) });
  rows.push({ label: "对比基期", value: periodText(parsed.baseline_period) });
  rows.push({ label: "分析范围", value: scopeText(parsed.scope) });
  const dimensions = joinNames(parsed.requested_dimensions, DIMENSION_NAMES);
  const factors = joinNames(parsed.requested_factors, FACTOR_NAMES);
  rows.push({ label: "请求维度", value: dimensions });
  rows.push({ label: "请求因素", value: factors });
  return rows;
}

function capabilityRows(item) {
  const capability = item.capability;
  if (!capability || typeof capability !== "object") return [];
  const rows = [];
  if (capability.level != null) {
    rows.push({ label: "能力级别", value: String(capability.level) });
  }
  rows.push({
    label: "支持方法",
    value: joinNames(capability.supported_methods, METHOD_NAMES),
  });
  rows.push({
    label: "可用维度",
    value: joinNames(capability.available_dimensions, DIMENSION_NAMES),
  });
  rows.push({
    label: "缺失证据",
    value: Array.isArray(capability.missing_evidence)
      ? capability.missing_evidence.join("、")
      : empty(),
  });
  if (capability.data_quality_status != null) {
    rows.push({
      label: "数据质量",
      value: String(capability.data_quality_status),
    });
  }
  return rows;
}

function taskValue(task) {
  if (!task || typeof task !== "object") return empty();
  const parts = [METHOD_NAMES[task.method] || String(task.method || "")];
  const dimensions = joinNames(task.dimensions, DIMENSION_NAMES);
  const factors = joinNames(task.factors, FACTOR_NAMES);
  if (dimensions !== empty()) parts.push(dimensions);
  if (factors !== empty()) parts.push(factors);
  return parts.filter((part) => part && part !== empty()).join(" · ");
}

function planRows(item) {
  const plan = item.plan;
  if (!plan || typeof plan !== "object") return [];
  const rows = [];
  if (Array.isArray(plan.tasks) && plan.tasks.length) {
    for (const task of plan.tasks) {
      rows.push({
        label: `任务 ${task.task_id || ""}`,
        value: taskValue(task),
      });
    }
  }
  if (plan.stop_reason != null) {
    rows.push({ label: "停止原因", value: String(plan.stop_reason) });
  }
  if (Array.isArray(plan.missing_evidence) && plan.missing_evidence.length) {
    rows.push({ label: "缺失证据", value: plan.missing_evidence.join("、") });
  }
  return rows;
}

function queriesRows(item) {
  const queries = item.queries;
  if (!Array.isArray(queries)) return [];
  const rows = [];
  for (const query of queries) {
    if (!query || typeof query !== "object") continue;
    const parts = [METHOD_NAMES[query.method] || ""];
    if (query.query_role) parts.push(String(query.query_role));
    rows.push({
      label: `查询 ${query.query_id || ""}`,
      value: parts.filter(Boolean).join(" · ") || empty(),
    });
  }
  return rows;
}

function analysisRows(item) {
  const results = item.results;
  if (!Array.isArray(results)) return [];
  const rows = [];
  for (const result of results) {
    if (!result || typeof result !== "object") continue;
    const parts = [METHOD_NAMES[result.method] || ""];
    const reconciliation = result.reconciliation;
    if (reconciliation && reconciliation.status) {
      parts.push(`对账 ${reconciliation.status}`);
    }
    rows.push({
      label: result.analysis_result_id || "分析结果",
      value: parts.filter(Boolean).join(" · ") || empty(),
    });
  }
  return rows;
}

function evidenceRows(item) {
  const evidence = item.evidence;
  if (!Array.isArray(evidence)) return [];
  const rows = [];
  for (const entry of evidence) {
    if (!entry || typeof entry !== "object") continue;
    const parts = [entry.evidence_type || "", entry.support_level || ""];
    rows.push({
      label: entry.evidence_id || "证据",
      value: parts.filter(Boolean).join(" · ") || empty(),
    });
  }
  return rows;
}

function reportRows(item) {
  const rows = [];
  if (item.report_status != null) {
    rows.push({ label: "报告状态", value: String(item.report_status) });
  }
  return rows;
}

function rowsForStage(stage, item) {
  switch (stage) {
    case "intent_router":
      return intentRows(item);
    case "semantic_grounding":
      return groundingRows(item);
    case "analysis_question_parser":
      return parsedQuestionRows(item);
    case "capability_assessment":
      return capabilityRows(item);
    case "analysis_planner":
      return planRows(item);
    case "analysis_task_executor":
      return queriesRows(item);
    case "deterministic_analyzer":
      return analysisRows(item);
    case "evidence_checker":
      return evidenceRows(item);
    case "report_generator":
      return reportRows(item);
    default:
      return [];
  }
}

export function traceStageName(stage) {
  return STAGE_NAMES[stage] || "处理步骤";
}

export function buildTraceCards(trace) {
  if (!Array.isArray(trace)) return [];
  return trace
    .filter(
      (item) => item && typeof item === "object" && typeof item.stage === "string",
    )
    .map((item) => ({
      stage: item.stage,
      name: traceStageName(item.stage),
      status: statusText(item.status),
      rows: rowsForStage(item.stage, item),
    }));
}
