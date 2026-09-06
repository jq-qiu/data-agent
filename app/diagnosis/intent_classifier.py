from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.diagnosis.intent import IntentSignals, SemanticIntentDecision
from app.prompt.prompt_loader import load_prompt


class LangChainIntentClassifier:
    """Structured semantic classifier used only after deterministic ambiguity."""

    def __init__(self, model: BaseChatModel) -> None:
        self._classifier = model.with_structured_output(SemanticIntentDecision)
        self._system_prompt = load_prompt("classify_intent")

    async def classify(
        self,
        question: str,
        signals: IntentSignals,
    ) -> SemanticIntentDecision:
        result: Any = await self._classifier.ainvoke(
            [
                SystemMessage(content=self._system_prompt),
                HumanMessage(
                    content=(
                        "安全信号："
                        + json.dumps(signals.model_dump(), ensure_ascii=False)
                        + "\n当前单轮问题："
                        + question
                    )
                ),
            ]
        )
        return SemanticIntentDecision.model_validate(result)
