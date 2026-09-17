"""CCA 0.1 reference validation and lossless interchange."""
import copy
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = json.loads((Path(__file__).parent / "schemas/cca-schema-0.1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def pointer(parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def codebook_errors(doc):
    errors = []
    for error in sorted(VALIDATOR.iter_errors(doc), key=lambda e: str(list(e.absolute_path))):
        parts = list(error.absolute_path)
        if error.validator == "required":
            parts += [next(k for k in error.validator_value if k not in error.instance)]
        errors.append({"path": pointer(parts), "message": error.message})
    if errors:
        return errors[:100]
    seen = set()
    for i, category in enumerate(doc["task"]["categories"]):
        if category["id"] in seen:
            errors.append({"path": f"/task/categories/{i}/id", "message": "Category IDs must be unique."})
        seen.add(category["id"])
    for i, example in enumerate(doc.get("examples", [])):
        if not set(example["labels"]) <= seen:
            errors.append({"path": f"/examples/{i}/labels", "message": "Unknown category ID."})
    return errors[:100]


def validate_codebook(doc):
    errors = codebook_errors(doc)
    if errors:
        raise ValueError(errors[0]["path"] + ": " + errors[0]["message"])
    return doc


def from_codebook(doc):
    from .models import Task
    return Task(codebook=copy.deepcopy(validate_codebook(doc)))


def to_codebook(task):
    # Version and identity belong to the researcher, not the database revision.
    return copy.deepcopy(validate_codebook(task.codebook))
