"""Create paired old/new prompt variants from an ordinary evaluation request.

Default: print the request for review. --start submits it to a running TextLab.
"""
import argparse
import copy
import json
from pathlib import Path

import httpx

PROTOCOLS = ("evidence-first-v1", "cca-reference-v2")


def paired_request(original):
    request = copy.deepcopy(original)
    variants = []
    for variant in original["variants"]:
        for protocol in PROTOCOLS:
            v = copy.deepcopy(variant)
            v["name"] = (variant["name"][:150] + " / " + protocol)
            v.setdefault("query", {})["prompt_protocol"] = protocol
            variants.append(v)
    if not 1 <= len(variants) <= 50:
        raise ValueError("Supply 1–25 model configurations (expanded to 2–50 variants).")
    request["variants"] = variants
    request["name"] = original.get("name", "Prompt comparison")[:175] + " / prompt comparison"
    return request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Normal TextLab evaluation request JSON")
    parser.add_argument("--api", default="http://127.0.0.1:8080")
    parser.add_argument("--start", action="store_true", help="Submit and run the experiment")
    args = parser.parse_args()
    request = paired_request(json.loads(args.config.read_text()))
    if not args.start:
        print(json.dumps(request, ensure_ascii=False, indent=2))
        return
    with httpx.Client(trust_env=False, timeout=60) as client:
        response = client.post(args.api.rstrip("/") + "/api/evaluations", json=request)
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
