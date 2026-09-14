import re
from typing import Literal, Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Category(StrictModel):
    label: str = Field(min_length=1, max_length=100)
    definition: str = Field(min_length=1, max_length=10000)
    examples: list[str] = Field(default_factory=list, max_length=100)


class Example(StrictModel):
    text: str = Field(min_length=1, max_length=50000)
    labels: list[str]
    rationale: str = ""


ThinkingLevel = Literal["default", "off", "on", "minimal", "low", "medium", "high", "max"]


class Task(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    instructions: str = Field(min_length=1, max_length=30000)
    mode: Literal["single", "multi"] = "single"
    categories: list[Category] = Field(min_length=2, max_length=200)
    examples: list[Example] = Field(default_factory=list, max_length=200)
    ambiguity_rule: str = "Choose the best supported category. Do not infer unsupported claims."
    allow_empty: bool = False
    rationale: bool = False
    evidence: bool = False
    thinking: ThinkingLevel = "default"

    @model_validator(mode="after")
    def check(self):
        labels = [c.label for c in self.categories]
        if len(labels) != len(set(labels)):
            raise ValueError("Labels must be unique")
        if self.mode == "single" and self.allow_empty:
            raise ValueError("Empty labels are only allowed for multi-label tasks; otherwise define a fallback category")
        for ex in self.examples:
            validate_labels(ex.labels, self)
        return self


def validate_labels(labels, task):
    if not isinstance(labels, list) or any(not isinstance(x, str) for x in labels):
        raise ValueError("labels must be a list of strings")
    allowed = {c.label for c in task.categories}
    if any(x not in allowed for x in labels) or len(labels) != len(set(labels)):
        raise ValueError("Unknown or duplicate labels")
    if task.mode == "single" and len(labels) != 1:
        raise ValueError("Single-label tasks require exactly one label")
    if not labels and not task.allow_empty:
        raise ValueError("At least one label is required")


class Profile(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["openai", "ollama", "mock"] = "openai"
    base_url: str = "http://host.docker.internal:8000/v1"
    api_key_env: str = ""
    thinking_adapter: Literal["auto", "reasoning_effort", "chat_template"] = "auto"
    timeout: float = Field(default=120, ge=1, le=1800)

    @field_validator("base_url")
    @classmethod
    def url(cls, value):
        u = urlsplit(value)
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError("Expected an HTTP(S) base URL without credentials, query or fragment")
        return value.rstrip("/")

    @field_validator("api_key_env")
    @classmethod
    def env(cls, value):
        if value and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("Expected an environment variable name")
        return value


class Query(StrictModel):
    model: str = Field(min_length=1, max_length=300)
    concurrency: int = Field(default=4, ge=1, le=128)
    retries: int = Field(default=2, ge=0, le=10)
    temperature: float = Field(default=0, ge=0, le=2)
    top_p: float = Field(default=1, gt=0, le=1)
    max_tokens: int = Field(default=256, ge=16, le=32768)
    seed: int | None = None
    structured_output: Literal["json_schema", "json_object", "none"] = "json_schema"
    extra_body: dict = Field(default_factory=dict)
    examples_per_category: int = Field(default=3, ge=0, le=100)
    max_text_chars: int = Field(default=30000, ge=1, le=1000000)
    overlong: Literal["error", "truncate"] = "error"
    rationale: bool | None = None
    evidence: bool | None = None
    thinking: ThinkingLevel | None = None

    @field_validator("extra_body")
    @classmethod
    def extra(cls, value):
        reserved = {"messages", "model", "stream", "response_format", "format", "options", "temperature", "top_p", "max_tokens", "seed"}
        if reserved.intersection(value):
            raise ValueError("extra_body must not override controlled query fields")
        return value


class NewJob(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    task_id: str
    dataset_id: str
    profile_id: str
    text_column: str
    query: Query


class GoldSet(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    dataset_id: str
    doc_id_column: str = "doc_id"
    text_column: str = "text"
    gold_column: str = "gold_label"
    mode: Literal["single", "multi"] = "single"
    separator: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=16)] = "|"
    allow_empty: bool = False

    @model_validator(mode="after")
    def distinct_columns(self):
        if len({self.doc_id_column, self.text_column, self.gold_column}) != 3:
            raise ValueError("doc_id, text and gold_label must be distinct columns")
        if self.mode == "single" and self.allow_empty:
            raise ValueError("Empty gold labels are only allowed in multi-label mode")
        return self


class Variant(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    profile_id: str
    query: Query


class NewEvaluation(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    gold_id: str
    task_id: str
    variants: list[Variant] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_names(self):
        if len({v.name for v in self.variants}) != len(self.variants):
            raise ValueError("Variant names must be unique")
        return self


class NewPrediction(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    dataset_id: str
    task_ids: list[str] = Field(min_length=1, max_length=50)
    profile_id: str
    text_column: str
    query: Query

    @field_validator("task_ids")
    @classmethod
    def unique_tasks(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Choose each task only once")
        return values
