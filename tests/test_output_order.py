from task_fixtures import runtime_task
from task_fixtures import task_spec
import itertools
import json
import pytest
from cca_lab.models import Task, Query
from cca_lab.llm import output_schema, messages, parse_result, mock_response
BASE = task_spec(**{'name': 'Task', 'instructions': 'Apply the codebook.', 'categories': [{'label': 'A', 'definition': 'Alpha', 'examples': ['Alpha Beta']}, {'label': 'B', 'definition': 'Beta'}]})

def test_fixed_order_for_all_optional_field_combinations():
    for evidence, alternatives, rationale, confidence in itertools.product((False, True), repeat=4):
        task = runtime_task(BASE, evidence=evidence, alternatives=alternatives, rationale=rationale, confidence=confidence)
        order = [name for name, enabled in [('evidence', evidence), ('candidate_interpretations', alternatives), ('rationale', rationale), ('labels', True), ('self_reported_confidence', confidence)] if enabled]
        schema = output_schema(task)
        assert list(schema['properties']) == schema['required'] == order
        msg = messages(task, Query(model='m',evidence=evidence,alternatives=alternatives,rationale=rationale,confidence=confidence), 'Alpha Beta')
        assert 'Emit only these fields, in order: ' + ' → '.join(order) in msg[0]['content']
        assert [m['role'] for m in msg] == ['system','user','assistant','user']
        parsed = parse_result(json.dumps(mock_response(task, 'Alpha Beta', ['A'], 'Demo')), task, 'Alpha Beta')
        if alternatives:
            assert parsed['alternative_interpretations'] == [] and parsed['candidate_interpretations'][0]['labels'] == ['A']
        assert list(mock_response(task, 'Alpha Beta', ['A'], 'Supplied example')) == order

def test_unselected_evidence_and_primary_candidate_derivation():
    task = runtime_task(BASE, evidence=True, alternatives=True, rationale=True, confidence=True)
    obj = mock_response(task, 'Alpha Beta', ['A'], 'The Alpha rule takes priority.')
    obj['evidence'] = [{'label': 'B', 'quote': 'Beta'}, {'label': 'A', 'quote': 'Alpha'}]
    competing = {'labels': ['B'], 'justification': 'Beta supports this reading.', 'supporting_quotes': ['Beta'], 'boundary_note': 'Alpha takes priority.'}
    obj['candidate_interpretations'].insert(0, competing)
    result = parse_result(json.dumps(obj), task, 'Alpha Beta')
    assert result['evidence'][0] == {'label': 'B', 'quote': 'Beta', 'start': 6, 'end': 10}
    assert result['alternative_interpretations'] == [competing]
    assert len(result['candidate_interpretations']) == 2
    obj['candidate_interpretations'] = obj['candidate_interpretations'][:1]
    with pytest.raises(ValueError, match='complete candidate'):
        parse_result(json.dumps(obj), task, 'Alpha Beta')

def test_unknown_evidence_and_model_supplied_alternatives_rejected():
    task = runtime_task(BASE, evidence=True, alternatives=True)
    obj = mock_response(task, 'Alpha Beta', ['A'], 'Example')
    obj['evidence'][0]['label'] = 'UNKNOWN'
    with pytest.raises(ValueError, match='unknown codebook'):
        parse_result(json.dumps(obj), task, 'Alpha Beta')
    obj = mock_response(task, 'Alpha Beta', ['A'], 'Example')
    obj['alternative_interpretations'] = []
    with pytest.raises(ValueError, match='schema'):
        parse_result(json.dumps(obj), task, 'Alpha Beta')
