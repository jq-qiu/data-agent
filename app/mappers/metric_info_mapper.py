"""在指标 ORM 模型、领域实体与检索文档之间进行显式转换。"""

from dataclasses import asdict

from app.entities.metric_info import MetricInfo
from app.models.metric_info_mysql import MetricInfoMySQL


def _required_text(value: str | None, field: str) -> str:
    if value is None:
        raise ValueError(f"{field} must not be null")
    return value


def _string_list(value: dict | list | None, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a list")
    return [str(item) for item in value]


class MetricInfoMapper:
    @staticmethod
    def to_entity(model: MetricInfoMySQL) -> MetricInfo:
        return MetricInfo(
            id=model.id,
            name=_required_text(model.name, "metric_info.name"),
            description=_required_text(model.description, "metric_info.description"),
            relevant_columns=_string_list(
                model.relevant_columns, "metric_info.relevant_columns"
            ),
            alias=_string_list(model.alias, "metric_info.alias"),
        )

    @staticmethod
    def to_model(entity: MetricInfo):
        data = asdict(entity)
        legacy_fields = ("id", "name", "description", "relevant_columns", "alias")
        return MetricInfoMySQL(**{key: data[key] for key in legacy_fields})
