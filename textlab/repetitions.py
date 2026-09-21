"""Group seed repetitions without pooling predictions or changing their estimand."""
import hashlib
import json
import math
import statistics
from collections import OrderedDict

RUNTIME_FIELDS = ('active_seconds','elapsed_seconds','documents_per_second','successful_documents_per_second','mean_document_seconds','completion_tokens_per_second')
COUNT_FIELDS = ('n','gold_n','valid_n','prediction_n','fallback_n','failed_n','unprocessed_n','coverage','output_coverage','accuracy_all','requests','prompt_tokens','completion_tokens','done','failed','fallback_count','total')


def experiment_key(snapshot):
    query={k:v for k,v in snapshot['query'].items() if k!='seed'}
    identity={k:snapshot.get(k) for k in ('task_id','task_revision','task','profile','text_column','context_column','prompt_protocol')}
    identity['query']=query
    return hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()[:24]


def stats(values):
    values=[v for v in values if isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v)]
    return (statistics.mean(values) if values else None, statistics.stdev(values) if len(values)>1 else None, len(values))


def collect(rows,keys):
    triples={k:stats(r.get(k) for r in rows) for k in keys}
    return ({k:v[0] for k,v in triples.items()}, {k:v[1] for k,v in triples.items()}, {k:v[2] for k,v in triples.items()})


def aggregate_runs(runs):
    buckets=OrderedDict()
    for run in runs:
        buckets.setdefault(experiment_key(run['snapshot']),[]).append(run)
    groups=[]
    for key,members in buckets.items():
        eligible=[r for r in members if r.get('status') in ('completed','completed_with_errors')]
        first=members[0]
        snapshot=first['snapshot']
        name=snapshot.get('experiment_name') or first.get('variant') or first.get('task_name') or first.get('name')
        group={'group_id':key,'job_id':key,'variant':name,'task_name':name,'name':name,'snapshot':snapshot,
               'expected_runs':len(members),'repeat_n':len(eligible),'excluded_runs':len(members)-len(eligible),
               'job_ids':[r.get('job_id',r.get('id')) for r in members],
               'seeds':[r['snapshot']['query'].get('seed') for r in members], 'std':{},'sample_n':{}}
        for section,keys in [('summary',set().union(*(r.get('summary',{}) for r in members))),('runtime',RUNTIME_FIELDS)]:
            means,sd,counts=collect([r.get(section,{}) for r in eligible],keys)
            group[section]=means;group['std'][section]=sd;group['sample_n'][section]=counts
        means,sd,counts=collect(eligible,[k for k in COUNT_FIELDS if k in first])
        group.update(means);group['std'].update(sd);group['sample_n'].update(counts)
        group['per_class']=[]
        for c in first.get('per_class',[]):
            rows=[next(x for x in r['per_class'] if x['label']==c['label']) for r in eligible]
            means,sd,counts=collect(rows,[k for k in c if k!='label'])
            group['per_class'].append({'label':c['label'],**means,'std':sd,'sample_n':counts})
        groups.append(group)
    return groups
