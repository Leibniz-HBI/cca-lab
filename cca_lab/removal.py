"""Explicit deletion with dependency previews and transactional active-job guards."""
import shutil
from pathlib import Path
from fastapi import APIRouter,HTTPException
from .db import connect,root
from .eval_api import fetch
from .evaluation import TERMINAL

router=APIRouter(prefix='/api',tags=['Removal'])


def require_finished(db,ids):
    for id in ids:
        row=db.execute('SELECT status FROM jobs WHERE id=?',(id,)).fetchone()
        if row and row['status'] not in TERMINAL:
            raise HTTPException(409,'Finish or cancel all dependent jobs and wait for in-flight requests before deleting.')


def remove_jobs(db,ids):
    require_finished(db,ids)
    for id in ids:
        db.execute('DELETE FROM results WHERE job_id=?',(id,))
        db.execute('DELETE FROM jobs WHERE id=?',(id,))


def remove_evaluation(db,id):
    fetch(db,'evaluations',id)
    jobs=[r[0] for r in db.execute('SELECT job_id FROM evaluation_runs WHERE evaluation_id=?',(id,))]
    require_finished(db,jobs)
    db.execute('DELETE FROM evaluation_runs WHERE evaluation_id=?',(id,))
    remove_jobs(db,jobs);db.execute('DELETE FROM evaluations WHERE id=?',(id,))


def remove_prediction(db,id):
    p=fetch(db,'predictions',id)
    if p['artifact_status']=='building':raise HTTPException(409,'Wait for prediction exports to finish before deleting.')
    jobs=[r[0] for r in db.execute('SELECT job_id FROM prediction_runs WHERE prediction_id=?',(id,))]
    require_finished(db,jobs)
    for path in (root()/'predictions'/id,root()/'predictions'/('.building-'+id)):
        if path.exists():shutil.rmtree(path)
    db.execute('DELETE FROM prediction_artifacts WHERE prediction_id=?',(id,))
    db.execute('DELETE FROM prediction_runs WHERE prediction_id=?',(id,))
    remove_jobs(db,jobs);db.execute('DELETE FROM predictions WHERE id=?',(id,))


def dependencies(db,id):
    return {
        'jobs':[dict(r) for r in db.execute('SELECT id,name,status FROM jobs WHERE dataset_id=?',(id,))],
        'gold_sets':[dict(r) for r in db.execute('SELECT id,spec FROM gold_sets WHERE dataset_id=?',(id,))],
        'evaluations':[dict(r) for r in db.execute('SELECT id,name FROM evaluations WHERE gold_id IN (SELECT id FROM gold_sets WHERE dataset_id=?)',(id,))],
        'predictions':[dict(r) for r in db.execute('SELECT id,name,artifact_status FROM predictions WHERE dataset_id=?',(id,))]}


@router.get('/datasets/{id}/dependencies')
def dataset_dependencies(id:str):
    with connect() as db:fetch(db,'datasets',id);return dependencies(db,id)


@router.delete('/profiles/{id}')
def delete_profile(id:str):
    with connect() as db:
        fetch(db,'profiles',id);db.execute('DELETE FROM profiles WHERE id=?',(id,))
    return {'ok':True}


@router.delete('/datasets/{id}/csv')
def delete_csv(id:str):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');d=fetch(db,'datasets',id)
        if d['status'] not in ('ready','failed'):raise HTTPException(409,'Wait for the CSV import to finish before removing the source file.')
        Path(d['path']).unlink(missing_ok=True)
    return {'ok':True,'dataset_preserved':True}


@router.delete('/evaluations/{id}')
def delete_evaluation(id:str):
    with connect() as db:db.execute('BEGIN IMMEDIATE');remove_evaluation(db,id)
    return {'ok':True}


@router.delete('/predictions/{id}')
def delete_prediction(id:str):
    with connect() as db:db.execute('BEGIN IMMEDIATE');remove_prediction(db,id)
    return {'ok':True}


@router.delete('/gold-sets/{id}')
def delete_gold(id:str,cascade:bool=False):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');fetch(db,'gold_sets',id)
        evals=[r[0] for r in db.execute('SELECT id FROM evaluations WHERE gold_id=?',(id,))]
        if evals and not cascade:raise HTTPException(409,f'This gold set is used by {len(evals)} evaluations. Explicit cascade deletion is required.')
        for eid in evals:remove_evaluation(db,eid)
        db.execute('DELETE FROM gold_rows WHERE gold_id=?',(id,));db.execute('DELETE FROM gold_sets WHERE id=?',(id,))
    return {'ok':True}


@router.delete('/datasets/{id}')
def delete_dataset(id:str,cascade:bool=False):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');d=fetch(db,'datasets',id)
        if d['status'] not in ('ready','failed'):raise HTTPException(409,'Wait for the CSV import to finish before deleting.')
        deps=dependencies(db,id)
        if any(deps.values()) and not cascade:raise HTTPException(409,'Dataset has dependent records; explicit cascade deletion is required.')
        require_finished(db,[j['id'] for j in deps['jobs']])
        if any(p['artifact_status']=='building' for p in deps['predictions']):raise HTTPException(409,'Wait for prediction exports to finish.')
        for e in deps['evaluations']:remove_evaluation(db,e['id'])
        for p in deps['predictions']:remove_prediction(db,p['id'])
        for g in deps['gold_sets']:
            db.execute('DELETE FROM gold_rows WHERE gold_id=?',(g['id'],));db.execute('DELETE FROM gold_sets WHERE id=?',(g['id'],))
        remove_jobs(db,[r[0] for r in db.execute('SELECT id FROM jobs WHERE dataset_id=?',(id,))])
        db.execute('DELETE FROM records WHERE dataset_id=?',(id,));db.execute('DELETE FROM datasets WHERE id=?',(id,))
        Path(d['path']).unlink(missing_ok=True)
    return {'ok':True}
