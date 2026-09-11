"""Standalone import benchmark; creates a real ~500 MB / 1M-row CSV on disk."""
import json
import os
import resource
import tempfile
import time
from pathlib import Path

from textlab.db import init, connect, uid
from textlab.worker import tick

with tempfile.TemporaryDirectory(prefix='textlab-benchmark-') as directory:
    os.environ['TEXTLAB_DATA']=directory
    init()
    path=Path(directory)/'million.csv'
    started=time.monotonic()
    with path.open('w',encoding='utf-8',newline='') as f:
        f.write('id,text,source\n')
        text=('Dies ist ein synthetischer Text zur Klassifikation. '*10)[:490]
        for n in range(1,1_000_001):
            f.write(f'{n},{text},test\n')
    generation=time.monotonic()-started
    id=uid()
    with connect() as db:
        db.execute("INSERT INTO datasets(id,name,path,bytes,delimiter,encoding,status,created) VALUES(?,?,?,?,?,?,?,?)",(id,path.name,str(path),path.stat().st_size,',','utf-8','uploaded',time.time()))
    started=time.monotonic();tick();elapsed=time.monotonic()-started
    with connect() as db:
        dataset=dict(db.execute('SELECT status,total FROM datasets WHERE id=?',(id,)).fetchone())
        count=db.execute('SELECT COUNT(*) FROM records WHERE dataset_id=?',(id,)).fetchone()[0]
    assert dataset['status']=='ready' and count==1_000_000
    print(json.dumps(dict(rows=count,csv_bytes=path.stat().st_size,generation_seconds=round(generation,2),import_seconds=round(elapsed,2),peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),database_bytes=(Path(directory)/'textlab.sqlite').stat().st_size),indent=2))
