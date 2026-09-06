from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.diagnosis.analyzer import DeterministicAnalyzerNode
from app.diagnosis.capability import (
    CapabilityAssessmentNode,
    CapabilityAssessor,
    DataCapabilityProfile,
)
from app.diagnosis.evidence import EvidenceCheckerNode
from app.diagnosis.planner import AnalysisPlannerNode
from app.diagnosis.query import AnalysisTaskExecutor, AnalysisTaskExecutorNode
from app.diagnosis.question import AnalysisQuestionParser, AnalysisQuestionParserNode
from app.diagnosis.report import ReportGeneratorNode


class DiagnosisGraphState(TypedDict, total=False):
    question: str
    intent: str
    parsed_question: dict[str, Any] | None
    error: dict[str, Any] | None
    capability: dict[str, Any]
    analysis_plan: dict[str, Any]
    query_results: list[dict[str, Any]]
    analysis_results: list[dict[str, Any]]
    validated_evidence: dict[str, Any]
    final_report: dict[str, Any]
    final_answer: str
    api_limitations: list[str]


Node = Callable[[Mapping[str, Any]], Any]
WrappedNode = Callable[[DiagnosisGraphState], Awaitable[dict[str, Any]]]

_STEPS = {
    "analysis_question_parser": "解析诊断问题",
    "capability_assessment": "检查数据能力",
    "analysis_planner": "生成分析计划",
    "analysis_task_executor": "执行受控分析查询",
    "deterministic_analyzer": "执行确定性分析",
    "evidence_checker": "校验证据",
    "report_generator": "生成诊断报告",
}


def build_diagnosis_graph(
    parser: AnalysisQuestionParser,
    assessor: CapabilityAssessor,
    profile: DataCapabilityProfile,
    executor: AnalysisTaskExecutor,
) -> Any:
    """Compile the accepted seven-stage bounded diagnosis graph."""

    # LangGraph's current generic overloads do not accept wrapped TypedDict
    # callables precisely, although the runtime validates this schema.
    builder: Any = StateGraph(state_schema=DiagnosisGraphState)
    builder.add_node(
        "analysis_question_parser",
        _with_progress(
            _STEPS["analysis_question_parser"],
            AnalysisQuestionParserNode(parser),
        ),
    )
    builder.add_node(
        "capability_assessment",
        _with_progress(
            _STEPS["capability_assessment"],
            CapabilityAssessmentNode(assessor, profile),
        ),
    )
    builder.add_node(
        "analysis_planner",
        _with_progress(_STEPS["analysis_planner"], AnalysisPlannerNode()),
    )
    builder.add_node(
        "analysis_task_executor",
        _with_progress(
            _STEPS["analysis_task_executor"],
            AnalysisTaskExecutorNode(executor),
        ),
    )
    builder.add_node(
        "deterministic_analyzer",
        _with_progress(
            _STEPS["deterministic_analyzer"],
            DeterministicAnalyzerNode(),
        ),
    )
    builder.add_node(
        "evidence_checker",
        _with_progress(_STEPS["evidence_checker"], EvidenceCheckerNode()),
    )
    builder.add_node(
        "report_generator",
        _with_progress(_STEPS["report_generator"], ReportGeneratorNode()),
    )
    builder.add_node("controlled_stop", _controlled_stop)

    builder.add_edge(START, "analysis_question_parser")
    builder.add_conditional_edges(
        "analysis_question_parser",
        _route_after_parser,
        {
            "capability_assessment": "capability_assessment",
            "controlled_stop": "controlled_stop",
        },
    )
    builder.add_edge("capability_assessment", "analysis_planner")
    builder.add_conditional_edges(
        "analysis_planner",
        _route_after_planner,
        {
            "analysis_task_executor": "analysis_task_executor",
            "controlled_stop": "controlled_stop",
        },
    )
    builder.add_edge("analysis_task_executor", "deterministic_analyzer")
    builder.add_edge("deterministic_analyzer", "evidence_checker")
    builder.add_edge("evidence_checker", "report_generator")
    builder.add_edge("report_generator", END)
    builder.add_edge("controlled_stop", END)
    return builder.compile()


def _with_progress(step: str, node: Node) -> WrappedNode:
    async def wrapped(state: DiagnosisGraphState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer({"type": "progress", "step": step, "status": "running"})
        try:
            result = node(state)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            writer({"type": "progress", "step": step, "status": "error"})
            raise
        writer({"type": "progress", "step": step, "status": "success"})
        return dict(result)

    return wrapped


def _route_after_parser(state: DiagnosisGraphState) -> str:
    return (
        "capability_assessment"
        if state.get("parsed_question") is not None
        else "controlled_stop"
    )


def _route_after_planner(state: DiagnosisGraphState) -> str:
    plan = state.get("analysis_plan")
    if isinstance(plan, Mapping) and plan.get("tasks"):
        return "analysis_task_executor"
    return "controlled_stop"


def _controlled_stop(state: DiagnosisGraphState) -> dict[str, Any]:
    limitations: list[str] = []
    error = state.get("error")
    if isinstance(error, Mapping):
        limitations.append(str(error.get("reason") or error.get("code") or "invalid_request"))
    plan = state.get("analysis_plan")
    if isinstance(plan, Mapping):
        if stop_reason := plan.get("stop_reason"):
            limitations.append(str(stop_reason))
        missing = plan.get("missing_evidence")
        if isinstance(missing, (list, tuple)):
            limitations.extend(str(item) for item in missing)
    return {
        "final_answer": "当前数据或请求结构不足以安全完成诊断。",
        "api_limitations": list(dict.fromkeys(limitations or ["insufficient_data"])),
    }
