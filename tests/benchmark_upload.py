"""Real HTTP upload smoke benchmark against a separately running local TextLab.
Leaves the imported dataset on that server. Use an empty test instance only.
Usage: python tests/benchmark_upload.py http://127.0.0.1:8080
"""
import json
import sys
import tempfile
import time
from pathlib import Path
import httpx

base=sys.argv[1]
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'benchmark.csv'
    with path.open('w') as f:
        f.write('id,text,source\n')
        text=('Dies ist ein synthetischer Text zur Klassifikation. '*10)[:490]
        for n in range(1,1_000_001):f.write(f'{n},{text},test\n')
    def chunks():
        with path.open('rb') as f:
            while block:=f.read(1024*1024):yield block
    with httpx.Client(base_url=base,trust_env=False,timeout=120) as client:
        started=time.monotonic()
        r=client.post('/api/datasets?filename=benchmark.csv',content=chunks(),headers={'Content-Type':'application/octet-stream'})
        r.raise_for_status(); id=r.json()['id'];upload_seconds=time.monotonic()-started
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            dataset=next(d for d in client.get('/api/datasets').json() if d['id']==id)
            if dataset['status'] in ('ready','failed'):break
            time.sleep(.5)
        assert dataset['status']=='ready' and dataset['total']==1_000_000,dataset
        print(json.dumps({'bytes':path.stat().st_size,'rows':dataset['total'],'upload_seconds':round(upload_seconds,2),'upload_and_import_seconds':round(time.monotonic()-started,2)},indent=2))
