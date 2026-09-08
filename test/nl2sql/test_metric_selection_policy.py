from app.agent.nodes.filter_metric import apply_metric_selection_policy
from app.agent.state import MetricInfoState


def _metric(metric_id: str, name: str) -> MetricInfoState:
    return MetricInfoState(
        id=metric_id,
        name=name,
        description=name,
        formula="",
        base_grain="",
        time_column="",
        status_filters={},
        allowed_dimensions=[],
        component_metrics=[],
        relevant_columns=[],
        alias=[],
    )


def test_detail_row_count_does_not_select_registered_item_count() -> None:
    metrics = [_metric("item_count", "Item Count")]

    selected = apply_metric_selection_policy(
        "订单商品明细一共有多少件",
        metrics,
        {"Item Count"},
    )

    assert selected == []


def test_status_sliced_count_does_not_select_overall_dws_order_count() -> None:
    metrics = [_metric("order_count", "Order Count")]

    selected = apply_metric_selection_policy(
        "对比已送达与已取消订单的数量",
        metrics,
        {"Order Count"},
        {"fact_order.status"},
    )

    assert selected == []


def test_metric_selection_keeps_supported_aggregate_metric() -> None:
    metrics = [_metric("order_count", "Order Count")]

    selected = apply_metric_selection_policy(
        "2018年5月整体订单数是多少",
        metrics,
        {"Order Count"},
    )

    assert selected == metrics
