from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi.testclient import TestClient

from app.conf.app_config import app_config
from main import app

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "data" / "reports" / "API-001_minimal_demo.json"
DEMO_QUESTIONS = (
    "2018 年 5 月 GMV 是多少？",
    "2018 年 5 月 GMV 相比 4 月变化了多少？",
    "为什么 2018 年 5 月 GMV 下降？",
    "2018 年 5 月哪些品类和州对 GMV 下降贡献最大？",
    "2018 年 5 月流量、促销和库存分别发生了什么变化？",
    "进一步分析 2018 年 5 月圣保罗州 GMV 下降的原因。",
)
_TERMINAL_TYPES = {"result", "error"}
_FORBIDDEN_TRACE_KEYS = {
    "sql",
    "parameters",
    "rows",
    "sql_fingerprint",
    "connection_string",
    "password",
    "token",
    "cookie",
    "credential",
}


def _events(response: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in response.iter_lines():
        if line.startswith("data:"):
            events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return set(value) | set().union(
            *(_nested_keys(item) for item in value.values()),
            set(),
        )
    if isinstance(value, (list, tuple)):
        return set().union(*(_nested_keys(item) for item in value), set())
    return set()


def _run_case(
    client: TestClient,
    index: int,
    question: str,
) -> dict[str, Any]:
    request_field = "query" if index == 1 else "question"
    started = perf_counter()
    with client.stream(
        "POST",
        "/api/query",
        json={request_field: question},
    ) as response:
        events = _events(response)
        status_code = response.status_code
        content_type = response.headers.get("content-type", "")
    elapsed_ms = round((perf_counter() - started) * 1000, 3)
    terminals = [event for event in events if event.get("type") in _TERMINAL_TYPES]
    terminal = terminals[-1] if terminals else {}
    trace = terminal.get("analysis_trace")
    unsafe_trace_keys = sorted(_nested_keys(trace) & _FORBIDDEN_TRACE_KEYS)
    data = terminal.get("data")
    evidence = terminal.get("evidence")
    limitations = terminal.get("limitations")
    successful = (
        status_code == 200
        and content_type.startswith("text/event-stream")
        and len(terminals) == 1
        and terminal.get("type") == "result"
        and not unsafe_trace_keys
    )
    return {
        "demo_id": f"DEMO-{index:02d}",
        "question": question,
        "request_field": request_field,
        "http_status": status_code,
        "sse_content_type": content_type.startswith("text/event-stream"),
        "intent": terminal.get("intent"),
        "terminal_type": terminal.get("type"),
        "report_status": terminal.get("report_status"),
        "answer_present": bool(terminal.get("answer")),
        "row_count": len(data) if isinstance(data, list) else 0,
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
        "limitation_count": len(limitations) if isinstance(limitations, list) else 0,
        "trace_stage_count": len(trace) if isinstance(trace, list) else 0,
        "progress_event_count": sum(
            event.get("type") == "progress" for event in events
        ),
        "unsafe_trace_keys": unsafe_trace_keys,
        "error_code": terminal.get("code") if terminal.get("type") == "error" else None,
        "elapsed_ms": elapsed_ms,
        "successful": successful,
    }


def main() -> int:
    if app_config.db_dw.database != "data_agent_v1_dw":
        raise RuntimeError("API-001 Demo requires the isolated V1 database")
    results: list[dict[str, Any]] = []
    with TestClient(app) as client:
        for index, question in enumerate(DEMO_QUESTIONS, 1):
            results.append(_run_case(client, index, question))

    elapsed = [item["elapsed_ms"] for item in results]
    successful = sum(bool(item["successful"]) for item in results)
    report: dict[str, Any] = {
        "feature": "API-001",
        "evaluation_scope": "six fixed V1 HTTP/SSE Demo questions; not production accuracy",
        "database": "data_agent_v1_dw",
        "model": app_config.llm.model,
        "endpoint": "POST /api/query",
        "summary": {
            "question_count": len(results),
            "successful_questions": successful,
            "query_intents": sum(item["intent"] == "QUERY" for item in results),
            "diagnosis_intents": sum(
                item["intent"] == "DIAGNOSIS" for item in results
            ),
            "safe_trace_questions": sum(not item["unsafe_trace_keys"] for item in results),
            "http_sse_questions": sum(
                item["http_status"] == 200 and item["sse_content_type"]
                for item in results
            ),
            "mean_elapsed_ms": round(sum(elapsed) / len(elapsed), 3),
            "max_elapsed_ms": max(elapsed),
        },
        "cases": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "feature": report["feature"],
                "question_count": len(results),
                "successful_questions": successful,
                "safe_trace_questions": report["summary"]["safe_trace_questions"],
                "http_sse_questions": report["summary"]["http_sse_questions"],
            }
        )
    )
    return 0 if successful == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
