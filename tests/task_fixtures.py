"""Factories for constructing fresh schema-first test instruments."""
from copy import deepcopy

SCHEMA = "https://cca-schema.org/schema/0.1/schema.json"


def task_spec(base=None, **options):
    result = deepcopy(base) if base else {
        "codebook": {"$schema": SCHEMA, "id": "test-instrument", "version": "1.0.0",
                     "title": "Test instrument", "description": "Test construct",
                     "task": {"instructions": "Apply categories.", "unit_of_analysis": "document",
                              "classification_mode": "single_label", "categories": []}},
        "execution_defaults": {}}
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
            result["execution_defaults"][key] = value
    return result


def legacy_jobs(**defaults):
    """Exercise resume of immediately preceding single-request snapshots."""
    import json
    from textlab.db import connect,dumps
    with connect() as db:
        for row in db.execute('SELECT id,snapshot FROM jobs').fetchall():
            snapshot=json.loads(row['snapshot'])
            snapshot['prompt_protocol']='cca-reference-v2'
            snapshot['query']['prompt_protocol']='cca-reference-v2'
            snapshot['query'].update(defaults)
            db.execute('UPDATE jobs SET snapshot=? WHERE id=?',(dumps(snapshot),row['id']))
