"""Standalone HTML, CSV tables, matplotlib charts and a reproducible report bundle."""
import base64
import csv
import html
import io
import json
import tempfile
import threading
import zipfile
from pathlib import Path

from .db import root, dumps

PLOT_LOCK = threading.RLock()


def safe_cell(value):
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\t','\r')):
        return "'" + value
    return value


def metric_rows(report,scope,classes=False,individual=False):
    source=report['scopes'][scope]
    rows=source['runs'] if individual else source.get('groups',source['runs'])
    for run in rows:
        query=run['snapshot']['query']
        base={'variant':run['variant'],'model':query['model'],'temperature':query['temperature'],
              'seeds':json.dumps(run.get('seeds',[query.get('seed')])),'scope':scope,
              'runs':run.get('repeat_n',1),'expected_runs':run.get('expected_runs',1),'excluded_runs':run.get('excluded_runs',0)}
        def add(values,sd,counts):
            for k,v in values.items():
                base[k]=v
                if not individual and 'std' in run:
                    base[k+'_sd']=sd.get(k);base[k+'_runs']=counts.get(k)
        add({k:run.get(k) for k in ('n','gold_n','valid_n','fallback_n','failed_n','unprocessed_n','coverage','output_coverage','accuracy_all')},run.get('std',{}),run.get('sample_n',{}))
        add(run.get('runtime',{}),run.get('std',{}).get('runtime',{}),run.get('sample_n',{}).get('runtime',{}))
        if classes:
            for row in run['per_class']:
                out={**base,**{k:v for k,v in row.items() if k not in ('std','sample_n')}}
                out.update({k+'_sd':v for k,v in row.get('std',{}).items()});out.update({k+'_runs':v for k,v in row.get('sample_n',{}).items()})
                yield out
        else:
            add(run['summary'],run.get('std',{}).get('summary',{}),run.get('sample_n',{}).get('summary',{}))
            yield base


def csv_text(rows):
    rows=list(rows)
    if not rows:
        return '\ufeff'
    fields=list(dict.fromkeys(key for row in rows for key in row))
    output=io.StringIO()
    output.write('\ufeff')
    writer=csv.DictWriter(output,fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key:safe_cell(value) for key,value in row.items()})
    return output.getvalue()


def table_csv(report,scope,classes=False):
    return csv_text(metric_rows(report,scope,classes))


def render_chart(report,scope,kind='overview',metric='f1_macro',job_id=None,format='svg'):
    import numpy as np
    from matplotlib.figure import Figure
    from matplotlib import rc_context
    runs=report['scopes'][scope]['runs'] if kind=='confusion' else report['scopes'][scope].get('groups',report['scopes'][scope]['runs'])
    # Use Figure directly and serialize rendering: matplotlib is not thread-safe.
    with PLOT_LOCK, rc_context({'font.family':'DejaVu Sans','svg.fonttype':'none','font.size':10}):
        if kind=='overview':
            keys=(set().union(*(r['summary'] for r in runs)) | {'coverage','accuracy_all','active_seconds','elapsed_seconds','documents_per_second','successful_documents_per_second','mean_document_seconds','completion_tokens_per_second'}) - {'kappa_defined_classes'}
            if metric not in keys:
                raise ValueError('Unknown comparison metric')
            figure=Figure(figsize=(10,max(3,1.8+.42*len(runs))),layout='constrained')
            ax=figure.subplots()
            values=[r.get(metric,r['summary'].get(metric,r.get('runtime',{}).get(metric))) for r in runs]
            plotted=[v if v is not None else 0 for v in values]
            deviations=[r.get('std',{}).get(metric,r.get('std',{}).get('summary',{}).get(metric,r.get('std',{}).get('runtime',{}).get(metric))) for r in runs]
            errors=[v or 0 for v in deviations]
            bars=ax.barh(range(len(runs)),plotted,xerr=errors,capsize=4,color=['#007f87' if v is not None else '#bac5d1' for v in values],height=.6)
            ax.set_yticks(range(len(runs)),[r['variant'] for r in runs])
            ax.invert_yaxis()
            for bar,value in zip(bars,values):
                ax.annotate('n/a' if value is None else f'{value:.3f}',(max(bar.get_width(),0),bar.get_y()+bar.get_height()/2),xytext=(5,0),textcoords='offset points',va='center',fontsize=9)
            is_runtime=metric.endswith('_seconds') or metric.endswith('_per_second')
            ax.set_xlim(min([v-e for v,e in zip(plotted,errors)]+[0])*1.15,max([v+e for v,e in zip(plotted,errors)]+[0.01])*1.25 if is_runtime else max(1.17,max([v+e for v,e in zip(plotted,errors)]+[0])*1.15))
            ax.set_xlabel(metric)
            ax.set_title('Model configuration comparison · mean ± sample SD',loc='left',fontweight='bold')
        elif kind=='classes':
            if metric not in ('precision','recall','f1','accuracy','specificity','kappa','mcc'):
                raise ValueError('Unknown class metric')
            labels=report['labels'][:40]
            figure=Figure(figsize=(11,max(4,2+len(labels)*.6)),layout='constrained')
            ax=figure.subplots()
            for index,run in enumerate(runs):
                rows=run['per_class'][:40]
                values=np.array([r[metric] if r[metric] is not None else np.nan for r in rows])
                errors=[r.get('std',{}).get(metric) or 0 for r in rows]
                offset=(index-(len(runs)-1)/2)*.7/max(1,len(runs))
                ax.errorbar(values,np.arange(len(labels))+offset,xerr=errors,fmt='o',capsize=3,label=run['variant'],markersize=4)
            ax.set_yticks(range(len(labels)),labels);ax.invert_yaxis()
            ax.set_xlabel(metric+' · mean ± sample SD')
            ax.legend(loc='upper left',bbox_to_anchor=(1,1),fontsize=8)
            ax.set_title('Class comparison'+(' · first 40 classes' if len(report['labels'])>40 else ''),loc='left',fontweight='bold')
        elif kind=='confusion':
            run=next((r for r in runs if r['job_id']==job_id),None) if job_id else runs[0]
            if run is None:
                raise ValueError('Unknown variant')
            figure=Figure(figsize=(max(7,min(16,len(report['labels'])*.5+3)),max(5,min(16,len(report['labels'])*.5+2))),layout='constrained')
            ax=figure.subplots()
            if report['mode']=='single':
                if run['confusion_matrix'] is None:
                    ax.text(.5,.5,'No valid predictions',ha='center',va='center');ax.axis('off')
                else:
                    labels=report['labels'][:40]
                    matrix=np.array(run['confusion_matrix'])[:40,:40]
                    image=ax.imshow(matrix,cmap='Blues',aspect='auto')
                    ax.set_xticks(range(len(labels)),labels,rotation=45,ha='right');ax.set_yticks(range(len(labels)),labels)
                    ax.set_xlabel('Predicted label');ax.set_ylabel('Gold-Label')
                    if len(labels)<=15:
                        for y in range(len(labels)):
                            for x in range(len(labels)):
                                ax.text(x,y,str(matrix[y,x]),ha='center',va='center',color='white' if matrix[y,x]>matrix.max()/2 else '#182638')
                    figure.colorbar(image,ax=ax,shrink=.7)
            else:
                classes=run['per_class'][:40]
                matrix=np.array([[c[key] for key in ('tn','fp','fn','tp')] for c in classes])
                image=ax.imshow(matrix,cmap='Blues',aspect='auto')
                ax.set_xticks(range(4),['TN','FP','FN','TP']);ax.set_yticks(range(len(classes)),[c['label'] for c in classes]);figure.colorbar(image,ax=ax,shrink=.7)
            ax.set_title('Confusion · '+run['variant']+(' · Subset: first 40 classes' if len(report['labels'])>40 else ''),loc='left',fontweight='bold')
        else:
            raise ValueError('Unknown chart type')
        figure.suptitle(report['name']+'\n'+('Common assigned documents' if scope=='common' else 'Assigned documents per run'),fontsize=11)
        output=io.BytesIO()
        figure.savefig(output,format=format,dpi=140)
        figure.clear()
        return output.getvalue()


def display(value):
    if value is None:
        return 'n/a'
    return f'{value:.4f}' if isinstance(value,float) else str(value)


def html_table(rows):
    rows=list(rows)
    if not rows:
        return '<p>No results</p>'
    keys=list(dict.fromkeys(key for row in rows for key in row))
    return '<div class="table"><table><thead><tr>'+''.join('<th>'+html.escape(key)+'</th>' for key in keys)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(display(row.get(key)))+'</td>' for key in keys)+'</tr>' for row in rows)+'</tbody></table></div>'


def confidence_rows(report,scope):
    rows=[]
    for group in report['scopes'][scope].get('groups',[]):
        row={'configuration':group['variant'],'group_id':group['group_id']}
        for metric,values in group.get('confidence',{}).get('metrics',{}).items():
            for stat,value in values.items():
                row[metric+'_'+stat]=value
        rows.append(row)
    return rows


def html_report(report,scope):
    title=html.escape(report['name'])
    images=''
    for kind,metric in (('overview','f1_macro'),('overview','active_seconds'),('classes','f1')):
        svg=base64.b64encode(render_chart(report,scope,kind,metric)).decode('ascii')
        images+=f'<img alt="{kind}" src="data:image/svg+xml;base64,{svg}">'
    from .uncertainty import confidence_chart
    for kind in ('reliability','risk'):
        svg=base64.b64encode(confidence_chart(report,scope,kind)).decode('ascii')
        images+=f'<h2>Confidence: {kind}</h2><img alt="{kind}" src="data:image/svg+xml;base64,{svg}">'
    notes=''.join('<p><strong>'+html.escape(key)+':</strong> '+html.escape(value)+'</p>' for key,value in report['policies'].items())
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px/1.6 system-ui;color:#172438;max-width:1400px;margin:40px auto;padding:0 25px}}h1,h2{{line-height:1.3}}h1{{color:#007f87}}.table{{overflow:auto;margin:25px 0}}table{{border-collapse:collapse;font-size:13px}}th,td{{padding:8px 12px;border:1px solid #dce3ec;text-align:left;white-space:nowrap}}th{{background:#edf4f7}}img{{max-width:100%;height:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f7;padding:20px}}@media print{{body{{margin:0}}.table{{overflow:visible}}table{{font-size:9px}}th,td{{padding:3px}}}}</style></head><body>
<h1>{title}</h1><p>TextLab 0.9.0 · Evaluation report · {html.escape(scope)} · Gold documents: {report['gold']['total']} · Common assigned documents: {report['common_n']}</p>
<p>{html.escape(report['policies'][scope])}</p><h2>Model comparison</h2>{html_table(metric_rows(report,scope))}{images}<h2>Results by class</h2>{html_table(metric_rows(report,scope,True))}
<h2>Confidence metrics (mean and sample SD)</h2>{html_table(confidence_rows(report,scope))}<h2>Scoring conventions</h2>{notes}<h2>Configuration and reproducibility</h2><pre>{html.escape(json.dumps({k:v for k,v in report.items() if k!='scopes'},ensure_ascii=False,indent=2))}</pre>
{''.join('<h3>'+html.escape(r['variant'])+'</h3><pre>'+html.escape(json.dumps(r['snapshot'],ensure_ascii=False,indent=2))+'</pre>' for r in report['scopes'][scope]['runs'])}
</body></html>'''


PREDICTION_FIELDS=['self_reported_confidence','alternative_interpretations','candidate_interpretations','seed','fallback_used','variant','job_id','row_no','doc_id','text','gold_labels','predicted_labels','exact_match','status','error','rationale','evidence','thinking','raw','attempt_outputs','attempts','seconds']


def prediction_chunks(id,format='csv'):
    from .eval_api import prediction_rows
    output=io.StringIO()
    writer=csv.DictWriter(output,fieldnames=PREDICTION_FIELDS,extrasaction='ignore')
    if format=='csv':
        output.write('\ufeff');writer.writeheader()
    count=0
    for row in prediction_rows(id):
        if format=='jsonl':
            output.write(dumps(row)+'\n')
        else:
            writer.writerow({k:safe_cell(dumps(v) if isinstance(v,(dict,list)) else v) for k,v in row.items()})
        count+=1
        if count%500==0:
            yield output.getvalue();output.seek(0);output.truncate(0)
    if output.tell():
        yield output.getvalue()


def report_zip(report,scope):
    handle=tempfile.NamedTemporaryFile(suffix='.zip',dir=root(),delete=False)
    path=Path(handle.name);handle.close()
    try:
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('report.html',html_report(report,scope))
            archive.writestr('report.json',json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
            archive.writestr('metrics.csv',table_csv(report,scope))
            archive.writestr('individual_runs.csv',csv_text(metric_rows(report,scope,individual=True)))
            archive.writestr('per_class.csv',table_csv(report,scope,True))
            from .uncertainty import confidence_chart, agreement_chunks, experiment_runs
            archive.writestr('confidence_metrics.csv',csv_text(confidence_rows(report,scope)))
            archive.writestr('confidence.json',json.dumps([{'group_id':g['group_id'],'name':g['variant'],'confidence':g.get('confidence')} for g in report['scopes'][scope].get('groups',[])],allow_nan=False))
            for kind in ('reliability','risk'):
                for fmt in ('svg','png'):
                    archive.writestr('confidence-'+kind+'.'+fmt,confidence_chart(report,scope,kind,fmt))
            with archive.open('agreement.csv','w') as output:
                for chunk in agreement_chunks(experiment_runs('evaluations',report['evaluation_id']),'csv'):
                    output.write(chunk.encode('utf-8'))
            for kind,metric in (('overview','f1_macro'),('overview','active_seconds'),('classes','f1')):
                for format in ('svg','png'):
                    archive.writestr((kind if metric in ('f1_macro','f1') else kind+'-'+metric)+'.'+format,render_chart(report,scope,kind,metric,format=format))
            for index,run in enumerate(report['scopes'][scope]['runs'],1):
                archive.writestr(f'confusion-{index:02}.svg',render_chart(report,scope,'confusion',job_id=run['job_id']))
            with archive.open('predictions.csv','w') as output:
                for chunk in prediction_chunks(report['evaluation_id']):
                    output.write(chunk.encode('utf-8'))
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise
