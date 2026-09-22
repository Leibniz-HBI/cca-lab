"""Factories for constructing fresh schema-first test instruments."""
from copy import deepcopy

SCHEMA = "https://cca-schema.org/schema/0.1/schema.json"


def task_spec(base=None, **options):
    result = deepcopy(base) if base else {
        "codebook": {"$schema": SCHEMA, "id": "test-instrument", "version": "1.0.0",
                     "title": "Test instrument", "description": "Test construct",
                     "task": {"instructions": "Apply categories.", "unit_of_analysis": "document",
                              "classification_mode": "single_label", "categories": []}}}
    codebook = result["codebook"]
    for key, value in options.items():
        if key == "name":
            codebook["title"] = value
        elif key in {"description", "examples"}:
            codebook[key] = value
        elif key == "mode":
            codebook["task"]["classification_mode"] = {"single": "single_label", "multi": "multi_label"}[value]
        elif key == "instructions":
            codebook["task"]["instructions"] = value
        elif key == "categories":
            codebook["task"]["categories"] = []
            for category in value:
                c = deepcopy(category)
                examples = c.pop("examples", [])
                c.setdefault("id", c["label"])
                codebook["task"]["categories"].append(c)
                if examples:
                    codebook.setdefault("examples", []).extend({"text": text, "labels": [c["id"]]} for text in examples)
        else:
            pass  # Execution choices belong to queries, not task payloads.
    return result



def runtime_task(base=None, **options):
    from cca_lab.models import Task, Query, ExecutionOptions
    from cca_lab.jobs import resolved_task
    return resolved_task(Task(**task_spec(base,**options)), Query(model='test',**{k:v for k,v in options.items() if k in ExecutionOptions.model_fields}))
