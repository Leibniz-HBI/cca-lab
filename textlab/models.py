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


class Task(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    instructions: str = Field(min_length=1, max_length=30000)
    mode: Literal["single", "multi"] = "single"
    categories: list[Category] = Field(min_length=2, max_length=200)
    examples: list[Example] = Field(default_factory=list, max_length=200)
    ambiguity_rule: str = "Wähle die am besten belegte Kategorie. Leite keine nicht belegten Aussagen ab."
    allow_empty: bool = False
    rationale: bool = False
    evidence: bool = False

    @model_validator(mode="after")
    def check(self):
        labels = [c.label for c in self.categories]
        if len(labels) != len(set(labels)):
            raise ValueError("Labels müssen eindeutig sein")
        if self.mode == "single" and self.allow_empty:
            raise ValueError("Leere Labels sind nur bei Multi-Label erlaubt; sonst Restkategorie definieren")
        for ex in self.examples:
            validate_labels(ex.labels, self)
        return self


def validate_labels(labels, task):
    if not isinstance(labels, list) or any(not isinstance(x, str) for x in labels):
        raise ValueError("labels muss eine Liste von Strings sein")
    allowed = {c.label for c in task.categories}
    if any(x not in allowed for x in labels) or len(labels) != len(set(labels)):
        raise ValueError("Unbekannte oder doppelte Labels")
    if task.mode == "single" and len(labels) != 1:
        raise ValueError("Single-Label erwartet genau ein Label")
    if not labels and not task.allow_empty:
        raise ValueError("Mindestens ein Label erwartet")


class Profile(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["openai", "ollama", "mock"] = "openai"
    base_url: str = "http://host.docker.internal:8000/v1"
    api_key_env: str = ""
    timeout: float = Field(default=120, ge=1, le=1800)

    @field_validator("base_url")
    @classmethod
    def url(cls, value):
        u = urlsplit(value)
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError("HTTP(S)-Basis-URL ohne Zugangsdaten, Query oder Fragment erwartet")
        return value.rstrip("/")

    @field_validator("api_key_env")
    @classmethod
    def env(cls, value):
        if value and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("Name einer Umgebungsvariable erwartet")
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

    @field_validator("extra_body")
    @classmethod
    def extra(cls, value):
        reserved = {"messages", "model", "stream", "response_format", "format", "options", "temperature", "top_p", "max_tokens", "seed"}
        if reserved.intersection(value):
            raise ValueError("extra_body darf kontrollierte Query-Felder nicht überschreiben")
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
            raise ValueError("doc_id, text und gold_label müssen verschiedene Spalten sein")
        if self.mode == "single" and self.allow_empty:
            raise ValueError("Leere Gold-Labels sind nur bei Multi-Label zulässig")
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
            raise ValueError("Varianten benötigen eindeutige Namen")
        return self
