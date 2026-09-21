"""Uncalibrated confidence diagnostics and bounded-memory document agreement."""
import csv
import io
import json
import math
from collections import Counter, defaultdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response
from .db import connect, dumps
from .repetitions import experiment_key, stats

router = APIRouter(prefix='/api')


def confidence_metrics(pairs):
    """Pairs are (self-reported probability of exact correctness, exact correctness)."""
    from sklearn.metrics import roc_auc_score, average_precision_score
    pairs = list(pairs)
    if not pairs:
        return {'n': 0, 'brier': None, 'ece': None, 'error_auroc': None, 'error_ap': None,
                'bins': [], 'risk': []}
    bins = []
    for i in range(10):
        rows = [(p,y) for p,y in pairs if min(9,int(p*10)) == i]
        bins.append({'bin': i, 'n': len(rows), 'confidence': stats(p for p,y in rows)[0],
                     'accuracy': stats(y for p,y in rows)[0]})
    # Include entire confidence ties; do not manufacture an ordering within a tie.
    counts = defaultdict(lambda: [0,0])
    for p,y in pairs:
        counts[p][0] += 1; counts[p][1] += int(not y)
    risk=[]; accepted=errors=0
    for p,(n,e) in sorted(counts.items(),reverse=True):
        accepted+=n;errors+=e
        risk.append({'threshold':p,'coverage':accepted/len(pairs),'risk':errors/accepted})
    # Keep report size bounded while retaining endpoints.
    if len(risk)>101:
        risk=[risk[round(i*(len(risk)-1)/100)] for i in range(101)]
    outcomes=[int(not y) for p,y in pairs]; scores=[1-p for p,y in pairs]
    both=len(set(outcomes))==2
    return {'n':len(pairs), 'brier':sum((p-y)**2 for p,y in pairs)/len(pairs),
            'ece':sum(b['n']*abs(b['confidence']-b['accuracy']) for b in bins if b['n'])/len(pairs),
            'error_auroc':float(roc_auc_score(outcomes,scores)) if both else None,
            'error_ap':float(average_precision_score(outcomes,scores)) if both else None,
            'bins':bins,'risk':risk}


def run_confidence(job_id,gold,selected):
    with connect() as db:
        rows=db.execute("SELECT row_no,labels,self_reported_confidence FROM results WHERE job_id=? AND status='ok' AND self_reported_confidence IS NOT NULL",(job_id,)).fetchall()
    return confidence_metrics((r['self_reported_confidence'],int(set(json.loads(r['labels']))==set(gold[r['row_no']]))) for r in rows if r['row_no'] in selected)


def group_confidence(members):
    members=[r['confidence'] for r in members if r['status'] in ('completed','completed_with_errors') and r.get('confidence',{}).get('n')]
    out={'runs':len(members),'metrics':{}}
    for metric in ('n','brier','ece','error_auroc','error_ap'):
        mean,sd,n=stats(r[metric] for r in members)
        out['metrics'][metric]={'mean':mean,'sd':sd,'n':n}
    out['bins']=[]
    for i in range(10):
        bins=[r['bins'][i] for r in members if r['bins'][i]['n']]
        c,_,_=stats(b['confidence'] for b in bins);a,sd,n=stats(b['accuracy'] for b in bins)
        out['bins'].append({'confidence':c,'accuracy':a,'sd':sd,'runs':n})
    out['risk']=[]
    for i in range(1,21):
        coverage=i/20
        # Whole-tie acceptance at or above each target coverage, independently per run.
        points=[next(p for p in r['risk'] if p['coverage']>=coverage) for r in members]
        mean,sd,n=stats(p['risk'] for p in points)
        actual,_,_=stats(p['coverage'] for p in points)
        out['risk'].append({'coverage':coverage,'actual_coverage':actual,'risk':mean,'sd':sd,'runs':n})
    return out


def agreement_summary(outputs,labels,expected):
    valid=[r for r in outputs if r['status']=='ok']
    counts=Counter(tuple(sorted(json.loads(r['labels']))) for r in valid)
    n=len(valid)
    winners=[list(k) for k,v in counts.items() if v==max(counts.values(),default=0)]
    return {'expected_runs':expected,'valid_runs':n,'excluded_runs':expected-n,
            'fallback_runs':sum(r['status']=='fallback' for r in outputs),
            'failed_runs':sum(r['status'] not in ('ok','fallback') for r in outputs),
            'unprocessed_runs':expected-len(outputs),
            'agreement_available':n>=2,
            'modal_label_sets':winners,
            'modal_vote_share':max(counts.values())/n if n>=2 else None,
            'label_set_entropy_bits':-sum((v/n)*math.log2(v/n) for v in counts.values()) if n>=2 else None,
            'label_set_counts':[{'labels':list(k),'count':v} for k,v in sorted(counts.items())],
            'per_label_frequency':{label:sum(count for key,count in counts.items() if label in key)/n if n else None for label in labels}}


def experiment_runs(kind,id):
    table='evaluations' if kind=='evaluations' else 'predictions'
    join='evaluation_runs' if kind=='evaluations' else 'prediction_runs'
    key='evaluation_id' if kind=='evaluations' else 'prediction_id'
    with connect() as db:
        parent=db.execute(f'SELECT * FROM {table} WHERE id=?',(id,)).fetchone()
        if not parent:raise HTTPException(404,'Experiment not found')
        runs=[dict(r) for r in db.execute(f'SELECT j.* FROM {join} p JOIN jobs j ON j.id=p.job_id WHERE p.{key}=? ORDER BY p.ordinal',(id,))]
    if any(r['status'] not in ('completed','completed_with_errors','cancelled') for r in runs):
        raise HTTPException(409,'Agreement becomes available after all runs finish or are cancelled')
    return runs


def agreement_rows(runs,after=0,limit=None):
    groups=defaultdict(list)
    for run in runs:
        run['snapshot']=json.loads(run['snapshot']) if isinstance(run['snapshot'],str) else run['snapshot']
        groups[experiment_key(run['snapshot'])].append(run)
    for key,members in groups.items():
        # Cancelled runs are excluded as whole runs to avoid selective partial sampling.
        eligible=[r for r in members if r['status'] in ('completed','completed_with_errors')]
        distinct={}
        for run in eligible:
            distinct.setdefault(run['snapshot']['query'].get('seed'),run)
        duplicates=len(eligible)-len(distinct); cancelled=len(members)-len(eligible)
        eligible=list(distinct.values())
        first=members[0]; s=first['snapshot']; cursor=after; emitted=0
        while limit is None or emitted<limit:
            size=min(100,limit-emitted) if limit else 100
            with connect() as db:
                records=db.execute('SELECT row_no FROM records WHERE dataset_id=? AND row_no>? ORDER BY row_no LIMIT ?', (first['dataset_id'],cursor,size)).fetchall()
                if not records:break
                by_row=defaultdict(list)
                for run in eligible:
                    for r in db.execute('SELECT row_no,labels,status FROM results WHERE job_id=? AND row_no>? AND row_no<=?',(run['id'],cursor,records[-1]['row_no'])):
                        by_row[r['row_no']].append(dict(r))
            for record in records:
                yield {'group_id':key,'task_id':s['task_id'],'task_name':s['task']['codebook']['title'],
                       'configuration':s.get('experiment_name',s['task']['codebook']['title']),'temperature':s['query']['temperature'],
                       'model':s['query']['model'],'dataset_id':first['dataset_id'],'row_no':record['row_no'],
                       'seeds':[r['snapshot']['query'].get('seed') for r in eligible],
                       'cancelled_runs':cancelled,'duplicate_seed_runs':duplicates,
                       **agreement_summary(by_row[record['row_no']],[c['id'] for c in s['task']['codebook']['task']['categories']],len(eligible))}
                emitted+=1
            cursor=records[-1]['row_no']


def agreement_chunks(runs,format):
    from .reports import safe_cell
    buffer=io.StringIO();writer=None
    for row in agreement_rows(runs):
        if format=='jsonl':yield dumps(row)+'\n'
        else:
            if writer is None:
                writer=csv.DictWriter(buffer,fieldnames=list(row));writer.writeheader()
            writer.writerow({k:safe_cell(dumps(v) if isinstance(v,(list,dict)) else v) for k,v in row.items()})
            yield buffer.getvalue();buffer.seek(0);buffer.truncate(0)


@router.get('/{kind}/{id}/agreement')
def agreement(kind:str,id:str,after:int=0,limit:int=50,format:str='json'):
    if kind not in ('evaluations','predictions'):raise HTTPException(404,'Unknown experiment type')
    if after<0 or not 1<=limit<=200 or format not in ('json','csv','jsonl'):raise HTTPException(422,'Invalid pagination or format')
    runs=experiment_runs(kind,id)
    if format=='json':return list(agreement_rows(runs,after,limit))
    return StreamingResponse(agreement_chunks(runs,format),media_type='text/csv' if format=='csv' else 'application/x-ndjson',headers={'Content-Disposition':f'attachment; filename="{kind}-{id}-agreement.{format}"'})


def confidence_chart(report,scope,kind,format='svg',category=None):
    from matplotlib.figure import Figure
    from .reports import PLOT_LOCK
    with PLOT_LOCK:
        fig=Figure(figsize=(9,5),layout='constrained');ax=fig.subplots();any_data=False; low=0; high=1
        for group in report['scopes'][scope].get('groups',[]):
            c=group.get('binary_confidence',{}).get(category,{}) if category else group.get('confidence',{})
            points=[p for p in c.get('bins' if kind=='reliability' else 'risk',[]) if p.get('accuracy' if kind=='reliability' else 'risk') is not None]
            if not points:continue
            any_data=True
            x='confidence' if kind=='reliability' else 'actual_coverage';y='accuracy' if kind=='reliability' else 'risk'
            low=min(low,min(p[y]-(p['sd'] or 0) for p in points)); high=max(high,max(p[y]+(p['sd'] or 0) for p in points))
            ax.errorbar([p[x] for p in points],[p[y] for p in points],yerr=[p['sd'] or 0 for p in points] if group.get('expected_runs',1)>1 else None,marker='o',capsize=3,label=group['variant'])
        if kind=='reliability':ax.plot([0,1],[0,1],'--',color='gray')
        ax.set(xlabel='Self-reported confidence' if kind=='reliability' else 'Accepted fraction among valid scored predictions',ylabel='Exact-match accuracy' if kind=='reliability' else 'Error rate among accepted predictions',xlim=(0,1),ylim=(low-.02,high+.02),title='Reliability (10 fixed bins)' if kind=='reliability' else 'Risk–coverage (whole confidence ties)')
        ax.grid(alpha=.2)
        if any_data:ax.legend(fontsize=8)
        else:ax.text(.5,.5,'No valid self-reported confidence scores',ha='center',wrap=True)
        out=io.BytesIO();fig.savefig(out,format=format);return out.getvalue()


@router.get('/evaluations/{id}/confidence-chart')
def chart(id:str,scope:str='common',kind:str='reliability',format:str='svg',category:str|None=None):
    from .eval_api import ready_report
    if scope not in ('common','valid') or kind not in ('reliability','risk') or format not in ('svg','png'):raise HTTPException(422,'Invalid chart options')
    return Response(confidence_chart(ready_report(id),scope,kind,format,category),media_type='image/svg+xml' if format=='svg' else 'image/png')


def binary_confidence(job_id,gold,selected):
    values=defaultdict(list)
    with connect() as db:
        rows=db.execute("SELECT c.row_no,c.category,c.result FROM components c JOIN results r ON r.job_id=c.job_id AND r.row_no=c.row_no WHERE c.job_id=? AND c.category!='' AND c.status='ok' AND r.status='ok'",(job_id,)).fetchall()
    for row in rows:
        result=json.loads(row['result']);score=result.get('self_reported_confidence')
        if row['row_no'] in selected and score is not None:
            correct=(row['category'] in result['labels'])==(row['category'] in gold[row['row_no']])
            values[row['category']].append((score,int(correct)))
    return {category:confidence_metrics(pairs) for category,pairs in values.items()}
