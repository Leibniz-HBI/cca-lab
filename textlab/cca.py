"""CCA 0.1 interchange. Validation uses the bundled schema, never remote references."""
import copy
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA=json.loads((Path(__file__).parent/'schemas/cca-schema-0.1.schema.json').read_text())
VALIDATOR=Draft202012Validator(SCHEMA,format_checker=FormatChecker())


def validate_codebook(doc):
    errors=sorted(VALIDATOR.iter_errors(doc),key=lambda e:str(list(e.absolute_path)))
    if errors:
        e=errors[0]
        raise ValueError('/'+'/'.join(map(str,e.absolute_path))+': '+e.message)
    ids=[c['id'] for c in doc['task']['categories']]
    if len(ids)!=len(set(ids)):raise ValueError('/task/categories: category IDs must be unique')
    for i,ex in enumerate(doc.get('examples',[])):
        if not set(ex['labels'])<=set(ids):raise ValueError(f'/examples/{i}/labels: unknown category ID')
    return doc


def from_codebook(doc):
    from .models import Task
    validate_codebook(doc)
    task=doc['task']
    return Task(name=doc['title'],description=doc['description'],instructions=task['instructions'],
        unit_of_analysis=task['unit_of_analysis'],context=task.get('context',''),
        mode='single' if task['classification_mode']=='single_label' else 'multi',ambiguity_rule='',
        categories=[{'label':c['id'],'display_label':c['label'],'definition':c['definition'],
                     **{k:c.get(k,[] if k!='coding_notes' else '') for k in ('inclusion_criteria','exclusion_criteria','coding_notes','aliases')}} for c in task['categories']],
        examples=[{'text':e['text'],'labels':e['labels'],'rationale':e.get('explanation',''),'context':e.get('context','')} for e in doc.get('examples',[])],
        cca_source=copy.deepcopy(doc))


def to_codebook(task,task_id,revision):
    if task.allow_empty:
        raise ValueError('CCA 0.1 does not represent empty label assignments. Disable Allow empty selection or use native Task JSON.')
    doc=copy.deepcopy(task.cca_source) if task.cca_source else {'$schema':SCHEMA['$id'],'id':'urn:textlab:task:'+task_id,'version':f'0.1.{revision-1}'}
    doc.update(title=task.name,description=task.description or task.instructions)
    instructions=task.instructions
    if task.ambiguity_rule.strip():instructions+='\n\nAmbiguity rule:\n'+task.ambiguity_rule
    old=doc.get('task',{})
    categories={c['id']:c for c in old.get('categories',[])}
    doc['task']={'instructions':instructions,'unit_of_analysis':task.unit_of_analysis,
                 'classification_mode':'single_label' if task.mode=='single' else 'multi_label','categories':[]}
    if task.context:doc['task']['context']=task.context
    for c in task.categories:
        out=copy.deepcopy(categories.get(c.label,{}))
        out.update(id=c.label,label=c.display_label or c.label,definition=c.definition)
        for key in ('inclusion_criteria','exclusion_criteria','coding_notes','aliases'):
            value=getattr(c,key)
            if value:out[key]=value
            else:out.pop(key,None)
        doc['task']['categories'].append(out)
    examples=[{'text':e.text,'labels':e.labels,**({'explanation':e.rationale} if e.rationale else {}),**({'context':e.context} if e.context else {})} for e in task.examples]
    for c in task.categories:
        examples.extend({'text':text,'labels':[c.label]} for text in c.examples)
    if examples or 'examples' in doc:doc['examples']=examples
    return validate_codebook(doc)
