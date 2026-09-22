import re
from typing import Literal, Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, PrivateAttr, ConfigDict, Field, StringConstraints, model_validator, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Category(BaseModel):
    """Read-only runtime view; authoritative values live in the CCA codebook."""
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    definition: str
    inclusion_criteria: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    coding_notes: str = ""
    aliases: list[str] = Field(default_factory=list)


ThinkingLevel = Literal["default", "off", "on", "minimal", "low", "medium", "high", "max"]


class ExecutionOptions(StrictModel):
    model_config = ConfigDict(extra="forbid")
    rationale: bool = False
    alternatives: bool = False
    confidence: bool = False
    evidence: bool = False
    thinking: ThinkingLevel = "default"
    default_label: str | None = None


class Task(StrictModel):
    """CCA is the sole coding instrument; execution options are not CCA fields."""
    codebook: dict
    _execution: ExecutionOptions = PrivateAttr(default_factory=ExecutionOptions)

    @field_validator("codebook")
    @classmethod
    def check_codebook(cls, value):
        from .cca import codebook_errors
        from pydantic_core import PydanticCustomError
        errors = codebook_errors(value)
        if errors:
            raise PydanticCustomError("cca_schema", "{message}", {
                "message": errors[0]["path"] + ": " + errors[0]["message"], "issues": errors})
        return value

    @property
    def name(self): return self.codebook["title"]
    @property
    def mode(self): return "single" if self.codebook["task"]["classification_mode"] == "single_label" else "multi"
    @property
    def instructions(self): return self.codebook["task"]["instructions"]
    @property
    def unit_of_analysis(self): return self.codebook["task"]["unit_of_analysis"]
    @property
    def context(self): return self.codebook["task"].get("context", "")
    @property
    def categories(self): return [Category(**c) for c in self.codebook["task"]["categories"]]
    @property
    def examples(self): return self.codebook.get("examples", [])
    @property
    def rationale(self): return self._execution.rationale
    @property
    def alternatives(self): return self._execution.alternatives
    @property
    def confidence(self): return self._execution.confidence
    @property
    def evidence(self): return self._execution.evidence
    @property
    def thinking(self): return self._execution.thinking
    @property
    def default_label(self): return self._execution.default_label


def validate_labels(labels, task):
    if not isinstance(labels, list) or any(not isinstance(x, str) for x in labels):
        raise ValueError("labels must be a list of strings")
    allowed = {c.id for c in task.categories}
    if any(x not in allowed for x in labels) or len(labels) != len(set(labels)):
        raise ValueError("Unknown or duplicate labels")
    if task.mode == "single" and len(labels) != 1:
        raise ValueError("Single-label tasks require exactly one label")


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
    prompt_protocol: Literal["experiment-v3"] = "experiment-v3"
    model: str = Field(min_length=1, max_length=300)
    concurrency: int = Field(default=4, ge=1, le=128)
    retries: int = Field(default=3, ge=0, le=10)
    temperature: float = Field(default=0, ge=0, le=2)
    top_p: float = Field(default=1, gt=0, le=1)
    max_tokens: int = Field(default=8192, ge=16, le=32768)
    seed: int | None = Field(default=9721, ge=-(2**63), le=2**63-1)
    structured_output: Literal["json_schema", "json_object", "none"] = "json_schema"
    extra_body: dict = Field(default_factory=dict)
    examples_per_category: int = Field(default=3, ge=0, le=100)
    max_text_chars: int = Field(default=30000, ge=1, le=1000000)
    overlong: Literal["error", "truncate"] = "error"
    rationale: bool = False
    evidence: bool = False
    alternatives: bool = False
    confidence: bool = False
    thinking: ThinkingLevel = "default"
    default_label: str | None = None
    strategy: Literal["joint", "binary"] = "joint"
    batch_size: int = Field(default=1, ge=1, le=100)
    use_context: bool = False
    max_context_chars: int = Field(default=30000, ge=1, le=1000000)
    max_batch_chars: int = Field(default=200000, ge=100, le=2000000)

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
    context_column: str | None = None
    query: Query


class GoldSet(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    dataset_id: str
    doc_id_column: str = "doc_id"
    text_column: str = "text"
    gold_column: str = "gold_label"
    context_column: str | None = None
    mode: Literal["single", "multi"] = "single"
    separator: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=16)] = "|"
    allow_empty: bool = False

    @model_validator(mode="after")
    def distinct_columns(self):
        if len({self.doc_id_column, self.text_column, self.gold_column}) != 3:
            raise ValueError("doc_id, text and gold_label must be distinct columns")
        if self.context_column and self.context_column in {self.doc_id_column,self.text_column,self.gold_column}:
            raise ValueError("Context must use a separate column")
        if self.mode == "single" and self.allow_empty:
            raise ValueError("Empty gold labels are only allowed in multi-label mode")
        return self


def parse_seeds(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = [int(x.strip()) for x in value.split(',')]
        except ValueError as exc:
            raise ValueError("Seeds must be comma-separated integers") from exc
    if not isinstance(value, list) or not 1 <= len(value) <= 100:
        raise ValueError("Supply 1 to 100 seeds")
    if any(type(x) is not int or not -(2**63) <= x < 2**63 for x in value):
        raise ValueError("Seeds must be signed 64-bit integers")
    if len(set(value)) != len(value):
        raise ValueError("Seeds must be unique")
    return value


class RepeatedRuns(StrictModel):
    seeds: list[int] | None = None
    _parse_seeds = field_validator('seeds', mode='before')(parse_seeds)


class Variant(RepeatedRuns):
    name: str = Field(min_length=1, max_length=200)
    profile_id: str
    query: Query


class NewEvaluation(RepeatedRuns):
    name: str = Field(min_length=1, max_length=200)
    gold_id: str
    task_id: str
    variants: list[Variant] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_names(self):
        if len({v.name for v in self.variants}) != len(self.variants):
            raise ValueError("Variant names must be unique")
        if sum(len(v.seeds or self.seeds or [v.query.seed]) for v in self.variants) > 500:
            raise ValueError("Maximum 500 total evaluation runs")
        return self


class NewPrediction(RepeatedRuns):
    source_evaluation_job_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    dataset_id: str
    task_ids: list[str] = Field(min_length=1, max_length=50)
    text_column: str
    context_column: str | None = None
    variants: list[Variant] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def configurations(self):
        if not self.variants and not self.source_evaluation_job_id:
            raise ValueError("Provide experiment configurations")
        return self

    @field_validator("task_ids")
    @classmethod
    def unique_tasks(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Choose each task only once")
        return values


