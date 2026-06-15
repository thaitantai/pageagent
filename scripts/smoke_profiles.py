import os, subprocess, pathlib, json, time, sys
root=pathlib.Path.home()/"AppData/Local/hermes/profiles"
profiles=sorted([p.name for p in root.iterdir() if p.is_dir()])
results=[]
for prof in profiles:
    env=os.environ.copy()
    env['HERMES_HOME']=str(root/prof)
    env['TERM']='dumb'
    prompt=f"Say ONLY OK_PROFILE_TEST_{prof.replace('-', '_').upper()}"
    cmd=['hermes','-z',prompt,'chat']
    t=time.time()
    try:
        cp=subprocess.run(cmd, cwd=str(pathlib.Path.home()/"AppData/Local/hermes/fanpage-agent"), env=env, text=True, capture_output=True, timeout=180)
        out=(cp.stdout or '')+(cp.stderr or '')
        expected=f"OK_PROFILE_TEST_{prof.replace('-', '_').upper()}"
        ok=cp.returncode==0 and expected in out
        results.append({'profile':prof,'ok':ok,'returncode':cp.returncode,'seconds':round(time.time()-t,1),'expected':expected,'output_tail':out[-500:]})
    except subprocess.TimeoutExpired as e:
        out=((e.stdout or '') if isinstance(e.stdout,str) else '') + ((e.stderr or '') if isinstance(e.stderr,str) else '')
        results.append({'profile':prof,'ok':False,'returncode':'timeout','seconds':180,'expected':prompt,'output_tail':out[-500:]})
path=pathlib.Path('C:/Users/thait/AppData/Local/hermes/fanpage-agent/.agent/profile_smoke_results.json')
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
print('PASS', sum(r['ok'] for r in results), 'TOTAL', len(results))
for r in results:
    print(('OK' if r['ok'] else 'FAIL'), r['profile'], r['returncode'], r['seconds'])
    if not r['ok']:
        tail=r['output_tail'].replace('\n',' ')[:300]
        print('  tail:', tail)
