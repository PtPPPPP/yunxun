import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import httpx

root=Path(__file__).resolve().parents[3]
work=Path(tempfile.mkdtemp(prefix='yunxun-current-audit-'))
node=os.environ.get('AUDIT_NODE') or shutil.which('node')
if not node:raise RuntimeError('Put Node.js on PATH or set AUDIT_NODE to its executable path')
for port in (8019, 5179):
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1',port))
        except OSError as error:raise RuntimeError(f'Audit requires unused local port {port}') from error
env={**os.environ,'YUNXUN_DB_PATH':str(work/'audit.db'),'YUNXUN_ENV':'test','YUNXUN_DEBUG':'false','YUNXUN_JWT_SECRET':'isolated-audit-secret-no-production-data','YUNXUN_HOST':'127.0.0.1','YUNXUN_PORT':'8019','YUNXUN_ALLOWED_ORIGINS':'http://127.0.0.1:5179','YUNXUN_REQUESTS_PER_MINUTE':'600','YUNXUN_AUTH_REQUESTS_PER_MINUTE':'2000','VITE_YUNXUN_API_BASE_URL':'http://127.0.0.1:8019','PYTHONIOENCODING':'utf-8'}
processes=[]
logs=[]
try:
    import sys
    for label,args,cwd in [('backend',[sys.executable,str(root/'backend/main.py')],root),('frontend',[str(node),str(root/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5179','--strictPort'],root/'frontend')]:
        log=(work/(label+'.log')).open('w',encoding='utf-8');logs.append(log)
        processes.append(subprocess.Popen(args,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    for url in ['http://127.0.0.1:8019/health/live','http://127.0.0.1:5179']:
        for _ in range(120):
            if any(p.poll() is not None for p in processes):raise RuntimeError('probe server exited; see '+str(work))
            try:
                if httpx.get(url,timeout=1).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.25)
        else:raise RuntimeError('server did not start: '+url)
    subprocess.run([str(node),str(Path(__file__).with_name('reproduce_browser.cjs')),str(work/'ui-results.json')],cwd=root,env=env,check=True,timeout=120)
    api='http://127.0.0.1:8019/api'
    with httpx.Client(timeout=15) as client:
        token=client.post(api+'/auth/guest').json()['token']
        payload=dict(name='lock-probe',area_mu=2,soil_type='loam',irrigation='well',crop='corn',planted_on='2026-04-01')
        start=time.monotonic();client.get('http://127.0.0.1:8019/health/live');baseline=time.monotonic()-start
        connection=sqlite3.connect(work/'audit.db',check_same_thread=False)
        connection.execute('BEGIN IMMEDIATE')
        def release():connection.rollback();connection.close()
        timer=threading.Timer(2.5,release);timer.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            write=pool.submit(client.post,api+'/plots',json=payload,headers={'Authorization':'Bearer '+token})
            time.sleep(.5)
            start=time.monotonic();health=client.get('http://127.0.0.1:8019/health/live');blocked=time.monotonic()-start
            result={'baseline_seconds':round(baseline,3),'during_write_lock_seconds':round(blocked,3),'health_status':health.status_code,'write_status':write.result().status_code,'injected_lock_seconds':2.5}
            (work/'concurrency-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print('CONCURRENCY',json.dumps(result),flush=True)
        timer.join()
    print('EVIDENCE_DIRECTORY',work,flush=True)
finally:
    for process in reversed(processes):
        process.terminate()
        try:process.wait(timeout=8)
        except subprocess.TimeoutExpired:process.kill();process.wait()
    for log in logs:log.close()
