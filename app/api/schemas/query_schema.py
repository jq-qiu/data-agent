"""定义单轮查询请求模型，并兼容规范 question 字段和旧 query 字段。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuerySchema(BaseModel):
    """Single-turn API input with a canonical field and legacy compatibility."""

    # extra=forbid 防止调用方夹带未定义控制参数，保持单轮 API 边界明确。
    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(default=None, max_length=2000)
    query: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_single_question(self) -> QuerySchema:
        provided = [value for value in (self.question, self.query) if value is not None]
        if len(provided) != 1 or not provided[0].strip():
            raise ValueError("exactly one non-empty question or query is required")
        value = provided[0].strip()
        if self.question is not None:
            self.question = value
        else:
            self.query = value
        return self

    @property
    def resolved_question(self) -> str:
        return self.question if self.question is not None else str(self.query)
