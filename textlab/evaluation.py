from . import __version__
"""Gold-set registration and reproducible, explicitly scoped evaluation metrics."""
import json
import logging
import math
import time
import warnings
from collections import Counter

from .db import connect, dumps
from .runtime import runtime_metrics

TERMINAL = ('completed', 'completed_with_errors', 'cancelled')
POLICIES = {'valid': 'Only valid predictions per variant; the document subset may differ between variants.', 'common': 'The identical intersection of documents with valid predictions from every variant.', 'failures': 'Failed and unprocessed documents are not label predictions. Coverage is the fraction with valid predictions; accuracy_all counts failures and unprocessed documents as incorrect.', 'averages': 'Macro weights every task class equally, including classes with no gold support. Weighted uses gold support in the selected subset. Micro pools TP/FP/FN.', 'undefined': 'Precision/recall/F1 with a zero denominator = 0. Undefined kappa = null. MCC with a zero denominator = 0 (scikit-learn convention). No valid documents = null metrics.', 'multilabel': 'Accuracy is exact-match/subset accuracy. Kappa and MCC are binary per class; their macro means are not global multiclass coefficients.', 'evidence': 'Metrics score labels only. Validation errors in optional rationale/evidence fields invalidate the whole response.', 'runtime': 'Runtime covers the entire variant, independent of scoring scope. Active seconds include requests, retries and batch processing, excluding queue time and pauses. Elapsed seconds include pauses after first start. Throughput is processed documents divided by active seconds. Mean document latency includes retries and overlaps under concurrency. Legacy or interrupted timing is unknown. Model load and cache effects may affect comparisons.'}

POLICIES.update(
    valid='All assigned predictions per run, including flagged fallback labels; document subsets may differ.',
    common='Identical intersection of documents with assigned predictions (model or fallback) in every completed, non-cancelled run.',
    failures='Coverage measures valid model responses only; output_coverage also includes fallback assignments. Fallback labels are scored as assigned output. Failed counts include fallbacks; fallback_n reports that subset. Unprocessed records have no fallback.',
    repetitions='Group identical task/model/parameter configurations, varying only seed. Compute each metric per run, then mean and sample standard deviation (ddof=1). Never pool predictions. Undefined values are omitted per metric; sample_n gives its denominator. SD is null with fewer than two defined runs. Cancelled or unfinished runs are excluded from aggregates and counted explicitly. Error bars show one SD, not a confidence interval.'
)


def gold_labels(value, spec):
    value = value.strip()
    if not value:
        if spec.mode == 'multi' and spec.allow_empty:
            return []
        raise ValueError('Empty gold label')
    labels = [v.strip() for v in value.split(spec.separator)] if spec.mode == 'multi' else [value]
    if any(not label for label in labels) or len(set(labels)) != len(labels):
        raise ValueError('Empty or duplicate label component')
    return labels


def ratio(a, b):
    return a / b if b else 0.0


def binary_metrics(tp, fp, fn, tn):
    n = tp + fp + fn + tn
    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    expected_numerator = (tp + fp) * (tp + fn) + (tn + fn) * (tn + fp)
    denom = n * n - expected_numerator
    return dict(precision=precision, recall=recall, f1=ratio(2 * tp, 2 * tp + fp + fn),
                accuracy=ratio(tp + tn, n), specificity=ratio(tn, tn + fp),
                kappa=((tp + tn) * n - expected_numerator) / denom if denom else None,
                mcc=ratio(tp * tn - fp * fn, math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))),
                support=tp + fn, predicted_support=tp + fp, tp=tp, fp=fp, fn=fn, tn=tn)


def score(gold, predicted, labels, mode):
    """Matrices are restricted to the explicitly selected evaluation subset."""
    import numpy as np
    from sklearn.metrics import cohen_kappa_score, matthews_corrcoef, confusion_matrix
    n, k = len(gold), len(labels)
    summary_keys = ['accuracy', 'hamming_loss', 'label_accuracy', 'jaccard_samples']
    summary_keys += [f'{metric}_{avg}' for avg in ('macro', 'micro', 'weighted', 'samples') for metric in ('precision', 'recall', 'f1')]
    summary_keys += ['kappa', 'mcc'] if mode == 'single' else ['kappa_macro_ovr', 'mcc_macro_ovr']
    if not n:
        return {'n': 0, 'summary': {key: None for key in summary_keys}, 'per_class': [dict(label=label, **{key: None for key in ('precision','recall','f1','accuracy','specificity','kappa','mcc')}, support=0,predicted_support=0,tp=0,fp=0,fn=0,tn=0) for label in labels], 'confusion_matrix': None}
    index = {label: i for i, label in enumerate(labels)}
    y, p = np.zeros((n,k), dtype=bool), np.zeros((n,k), dtype=bool)
    for row, (truth, prediction) in enumerate(zip(gold,predicted)):
        for label in truth:
            y[row,index[label]] = True
        for label in prediction:
            p[row,index[label]] = True
    tp = np.count_nonzero(y & p, axis=0)
    fp = np.count_nonzero(~y & p, axis=0)
    fn = np.count_nonzero(y & ~p, axis=0)
    tn = n - tp - fp - fn
    per_class = [dict(label=label, **binary_metrics(int(tp[i]),int(fp[i]),int(fn[i]),int(tn[i]))) for i,label in enumerate(labels)]
    summary = {'accuracy': float(np.mean(np.all(y == p, axis=1))), 'hamming_loss': float(np.mean(y != p)), 'label_accuracy': float(np.mean(y == p))}
    support_sum = sum(c['support'] for c in per_class)
    pooled = binary_metrics(int(tp.sum()),int(fp.sum()),int(fn.sum()),int(tn.sum()))
    for metric in ('precision','recall','f1'):
        summary[metric+'_macro'] = sum(c[metric] for c in per_class) / k
        summary[metric+'_weighted'] = ratio(sum(c[metric]*c['support'] for c in per_class),support_sum)
        summary[metric+'_micro'] = pooled[metric]
    if mode == 'multi':
        intersections = np.count_nonzero(y & p,axis=1)
        true_counts, pred_counts = np.count_nonzero(y,axis=1),np.count_nonzero(p,axis=1)
        def average_divide(a,b):
            return float(np.mean(np.divide(a,b,out=np.zeros(n,dtype=float),where=b!=0)))
        summary['precision_samples'] = average_divide(intersections,pred_counts)
        summary['recall_samples'] = average_divide(intersections,true_counts)
        summary['f1_samples'] = average_divide(2*intersections,true_counts+pred_counts)
        summary['jaccard_samples'] = average_divide(intersections,true_counts+pred_counts-intersections)
        kappas = [c['kappa'] for c in per_class if c['kappa'] is not None]
        summary['kappa_macro_ovr'] = sum(kappas)/len(kappas) if kappas else None
        summary['kappa_defined_classes'] = len(kappas)
        summary['mcc_macro_ovr'] = sum(c['mcc'] for c in per_class)/k
        matrix = None
    else:
        summary['hamming_loss'] = 1.0 - summary['accuracy']
        truth, prediction = [x[0] for x in gold], [x[0] for x in predicted]
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning)
            warnings.simplefilter('ignore',UserWarning)
            kappa = float(cohen_kappa_score(truth,prediction,labels=labels))
            summary['kappa'] = kappa if math.isfinite(kappa) else None
            summary['mcc'] = float(matthews_corrcoef(truth,prediction))
        matrix = confusion_matrix(truth,prediction,labels=labels).tolist()
    return {'n':n,'summary':summary,'per_class':per_class,'confusion_matrix':matrix}


def build_report(evaluation_id):
    with connect() as db:
        evaluation = dict(db.execute('SELECT * FROM evaluations WHERE id=?',(evaluation_id,)).fetchone())
        gold_set = dict(db.execute('SELECT * FROM gold_sets WHERE id=?',(evaluation['gold_id'],)).fetchone())
        gold = {r['row_no']:json.loads(r['labels']) for r in db.execute('SELECT row_no,labels FROM gold_rows WHERE gold_id=? ORDER BY row_no',(evaluation['gold_id'],))}
        runs = [dict(r) for r in db.execute('SELECT j.*,r.name variant_name,r.ordinal FROM evaluation_runs r JOIN jobs j ON j.id=r.job_id WHERE r.evaluation_id=? ORDER BY r.ordinal',(evaluation_id,))]
    if not runs or any(r['status'] not in TERMINAL for r in runs):
        raise ValueError('Evaluation is not yet finished')
    eligible = [r for r in runs if r['status'] != 'cancelled']
    common = set(gold) if eligible else set()
    for run in eligible:
        with connect() as db:
            common.intersection_update(r[0] for r in db.execute("SELECT row_no FROM results WHERE job_id=? AND status IN ('ok','fallback')",(run['id'],)))
    task_snapshot = json.loads(evaluation['task_snapshot'])
    from .models import Task
    task = Task.model_validate(task_snapshot['task'])
    labels = [c.id for c in task.categories]
    report = {'schema_version':2,'framework_version':__version__,'evaluation_id':evaluation_id,'name':evaluation['name'],'generated':time.time(),
              'task_snapshot':task_snapshot,'gold':{'id':gold_set['id'],'total':len(gold),'spec':json.loads(gold_set['spec']),'label_counts':json.loads(gold_set['label_counts'])},
              'labels':labels,'mode':task.mode,'policies':POLICIES,'common_n':len(common),'scopes':{'valid':{'runs':[]},'common':{'runs':[]}}}
    for run in runs:
        with connect() as db:
            predictions = {r['row_no']:json.loads(r['labels']) for r in db.execute("SELECT row_no,labels FROM results WHERE job_id=? AND status IN ('ok','fallback') ORDER BY row_no",(run['id'],))}
        exact_all = sum(set(prediction)==set(gold[row]) for row,prediction in predictions.items())
        item = {'job_id':run['id'],'variant':run['variant_name'],'status':run['status'],'snapshot':json.loads(run['snapshot']),
                'gold_n':len(gold),'valid_n':len(predictions)-run['fallback_count'],'prediction_n':len(predictions),'fallback_n':run['fallback_count'],'failed_n':run['failed'],'unprocessed_n':len(gold)-run['done'],
                'coverage':(len(predictions)-run['fallback_count'])/len(gold),'output_coverage':len(predictions)/len(gold),'accuracy_all':exact_all/len(gold),
                'runtime':runtime_metrics(run),'requests':run['requests'],'prompt_tokens':run['prompt_tokens'],'completion_tokens':run['completion_tokens']}
        for scope, rows in (('valid',list(predictions)),('common',sorted(common.intersection(predictions)))):
            result = score([gold[row] for row in rows],[predictions[row] for row in rows],labels,task.mode)
            from .uncertainty import run_confidence
            report['scopes'][scope]['runs'].append({**item,**result,'confidence':run_confidence(run['id'],gold,set(rows))})
    report['policies']['confidence']='Uncalibrated self-reported probability of exact label-set agreement with gold; not codebook fit. Confidence excludes failed, fallback, missing-score and (from groups) cancelled responses. Brier and 10-bin ECE are lower-is-better; error AUROC/AP are undefined with only one outcome. Group metrics and curves average runs with sample SD; empty bins are omitted per run. Risk accepts whole confidence ties; coverage is conditional on valid scored outputs, with 20 target levels and actual mean achieved coverage plotted. No calibration model is fitted.'
    report['policies']['agreement']='Per-document seed agreement groups identical task, model and query settings except seed. Counts only successful primary label sets from completed runs. Cancelled runs and duplicate seeds are excluded; fallback and failed outputs never count as votes. Fewer than two valid distinct-seed outputs: agreement and entropy are null. All tied modal sets are retained. Frequencies are not calibrated correctness probabilities.'
    from .repetitions import aggregate_runs
    for scope in report['scopes'].values():
        scope['groups']=aggregate_runs(scope['runs'])
        from .uncertainty import group_confidence
        for group in scope['groups']:
            group['confidence']=group_confidence([r for r in scope['runs'] if r['job_id'] in group['job_ids']])
    return report


def finalize_one():
    with connect() as db:
        row = db.execute("""SELECT e.id FROM evaluations e WHERE report_json IS NULL AND report_error IS NULL
            AND EXISTS(SELECT 1 FROM evaluation_runs r WHERE r.evaluation_id=e.id)
            AND NOT EXISTS(SELECT 1 FROM evaluation_runs r JOIN jobs j ON j.id=r.job_id
                WHERE r.evaluation_id=e.id AND j.status NOT IN ('completed','completed_with_errors','cancelled'))
            ORDER BY e.created LIMIT 1""").fetchone()
    if not row:
        return False
    try:
        logging.getLogger(__name__).info("evaluation_report_started evaluation_id=%s", row[0])
        report = build_report(row[0])
        encoded = json.dumps(report,ensure_ascii=False,allow_nan=False)
        with connect() as db:
            db.execute('UPDATE evaluations SET report_json=? WHERE id=?',(encoded,row[0]))
        logging.getLogger(__name__).info("evaluation_report_completed evaluation_id=%s", row[0])
    except Exception:
        logging.getLogger(__name__).exception('Evaluation report failed: %s',row[0])
        with connect() as db:
            db.execute("UPDATE evaluations SET report_error='Report calculation failed; check server log.' WHERE id=?",(row[0],))
    return True
