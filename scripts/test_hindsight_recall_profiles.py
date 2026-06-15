import os, subprocess, pathlib, json, time
root=pathlib.Path.home()/"AppData/Local/hermes/profiles"
project=pathlib.Path.home()/"AppData/Local/hermes/fanpage-agent"
profiles=sorted([p.name for p in root.iterdir() if p.is_dir()])
results=[]
for prof in profiles:
    env=os.environ.copy(); env['HERMES_HOME']=str(root/prof); env['TERM']='dumb'
    prompt="Recall Hindsight memory for fanpage-agent profile role and shared project path. If found, answer exactly RECALL_OK. If not found, answer RECALL_FAIL."
    t=time.time()
    try:
        cp=subprocess.run(['hermes','-z',prompt,'chat'], cwd=str(project), env=env, text=True, capture_output=True, timeout=180)
        out=(cp.stdout or '')+(cp.stderr or '')
        ok=cp.returncode==0 and 'RECALL_OK' in out
        results.append({'profile':prof,'ok':ok,'returncode':cp.returncode,'seconds':round(time.time()-t,1),'tail':out[-700:]})
    except subprocess.TimeoutExpired as e:
        out=((e.stdout or '') if isinstance(e.stdout,str) else '')+((e.stderr or '') if isinstance(e.stderr,str) else '')
        results.append({'profile':prof,'ok':False,'returncode':'timeout','seconds':180,'tail':out[-700:]})
outpath=project/'.agent/hindsight_recall_results.json'
outpath.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
print('RECALL_PASS', sum(r['ok'] for r in results), 'TOTAL', len(results))
for r in results:
    print(('OK' if r['ok'] else 'FAIL'), r['profile'], r['returncode'], r['seconds'])
    if not r['ok']:
        print('  tail:', r['tail'].replace('\n',' ')[:300])
