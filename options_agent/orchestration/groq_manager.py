from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field


class AltDataAssessment(BaseModel):
    topic: str
    sentiment: float = Field(ge=-1, le=1)
    relevance: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    event_time: str
    source_ids: list[str]
    uncertainty: float = Field(ge=0, le=1)
    abstain: bool
    rationale: str


class GroqManager:
    """LLM is restricted to structured alt-data interpretation and run supervision."""

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile"
        # Wire the documented temperature knob instead of a hardcoded 0.
        self.temperature = float(os.getenv("GROQ_TEMPERATURE", "0") or 0)
        self.client: Any = None

    def connect(self) -> None:
        try:
            from groq import Groq
        except ImportError as exc:
            raise ImportError("install the optional groq dependency") from exc
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is required")
        self.client = Groq(api_key=key)

    def assess_alt_data(
        self, text: str, source_ids: list[str], asof_iso: str
    ) -> AltDataAssessment:
        if self.client is None:
            self.connect()
        schema = AltDataAssessment.model_json_schema()
        prompt = (
            "Interpret only the supplied text. Do not infer facts beyond it. "
            f"The decision as-of time is {asof_iso}. Return abstain=true if event time or provenance is unclear. "
            f"Source IDs: {source_ids}. JSON schema: {json.dumps(schema)}\nTEXT:\n{text}"
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content)
        assessment = AltDataAssessment.model_validate(parsed)
        if assessment.source_ids != source_ids:
            raise ValueError("LLM attempted to alter provenance IDs")
        return assessment
