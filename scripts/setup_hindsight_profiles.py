import os, subprocess, pathlib, json, time, sys
root=pathlib.Path.home()/"AppData/Local/hermes/profiles"
project=pathlib.Path.home()/"AppData/Local/hermes/fanpage-agent"
profiles=sorted([p.name for p in root.iterdir() if p.is_dir()])
roles={
 'api-designer':'API contract specialist for fanpage-agent AgentBus events, adapters, CLI contracts, and integration boundaries.',
 'architect':'Architecture specialist for fanpage-agent. Focus on path B AgentBus, path A legacy compatibility, module boundaries, and long-term design decisions.',
 'backend-engineer':'Backend implementation specialist for fanpage-agent Python services, agents, adapters, config, scheduler, and persistence.',
 'code-reviewer':'Code review specialist for fanpage-agent. Focus on correctness, maintainability, hidden regressions, and diff review.',
 'data-analyst':'Data/analytics specialist for fanpage-agent metrics, post performance analysis, trends, and reporting logic.',
 'debugger':'Debugging specialist for fanpage-agent failures, stack traces, flaky tests, runtime issues, and reproduction steps.',
 'devops-engineer':'DevOps specialist for fanpage-agent Docker, docker-compose, scheduler runtime, env handling, logging, and deployment safety.',
 'doc-writer':'Documentation specialist for fanpage-agent README, developer docs, handoffs, decisions, and user-facing explanations.',
 'frontend-engineer':'Frontend/UI specialist for any fanpage-agent UI, dashboards, templates, visual workflows, and content presentation code.',
 'pagent':'Primary orchestrator for fanpage-agent. Owns memory, context assembly, task routing, verification, and final decisions.',
 'performance-optimizer':'Performance specialist for fanpage-agent runtime, LLM cost/latency, caching, scheduling efficiency, and bottleneck removal.',
 'prompt-engineer':'Prompt specialist for fanpage-agent LLM prompts, agent instructions, structured outputs, and safe fallback templates.',
 'refactorer':'Refactoring specialist for fanpage-agent. Improve structure without behavior change; preserve tests and contracts.',
 'security-auditor':'Security specialist for fanpage-agent env secrets, Facebook publishing risks, prompt injection, unsafe IO, Docker exposure, and auth boundaries.',
 'sql-expert':'SQL/data persistence specialist for fanpage-agent DB schema, queries, migrations, and analytics storage if database is used.',
 'test-writer':'Testing specialist for fanpage-agent pytest coverage, fixtures, integration smoke tests, regression tests, and CI-ready commands.',
}
common=("Project fanpage-agent path is C:/Users/thait/AppData/Local/hermes/fanpage-agent/. "
"Profiles collaborate through shared repo plus .agent/tasks/*.md and .agent/handoffs/*.md. "
"Use HERMES_HOME=<profile-dir> to run profile-isolated Hermes; HERMES_PROFILE does not work. "
"Do not use 'hermes profile use' for automation because it switches global active profile. "
"pagent is orchestrator: it creates tasks, specialist profiles read repo/task, modify code/tests/docs, write handoffs, then pagent verifies diff/tests. "
"Current architecture: path B AgentBus is active; path A agent.py legacy remains for old scheduler compatibility. "
"Hindsight service runs in Docker at http://127.0.0.1:8888, mode local_external. "
"Headroom/9router model proxy is separate from Hindsight memory service. "
"Never store real API keys or secrets in memory. Store paths, decisions, conventions, and safe operational facts only.")
results=[]
for prof in profiles:
    env=os.environ.copy(); env['HERMES_HOME']=str(root/prof); env['TERM']='dumb'
    role=roles.get(prof, f"Specialist Hermes profile named {prof} for fanpage-agent work.")
    prompt=("Store this durable Hindsight memory, then answer exactly SEEDED_OK.\n\n"
            f"Role for this profile: {role}\n"
            f"Shared project facts: {common}\n"
            f"Memory bank id for this profile is agent-{prof}. Default tags include hermes, agent, {prof}, fanpage-agent.")
    t=time.time()
    try:
        cp=subprocess.run(['hermes','-z',prompt,'chat'], cwd=str(project), env=env, text=True, capture_output=True, timeout=240)
        out=(cp.stdout or '')+(cp.stderr or '')
        ok=cp.returncode==0 and 'SEEDED_OK' in out
        results.append({'profile':prof,'ok':ok,'returncode':cp.returncode,'seconds':round(time.time()-t,1),'tail':out[-700:]})
    except subprocess.TimeoutExpired as e:
        out=((e.stdout or '') if isinstance(e.stdout,str) else '')+((e.stderr or '') if isinstance(e.stderr,str) else '')
        results.append({'profile':prof,'ok':False,'returncode':'timeout','seconds':240,'tail':out[-700:]})
outpath=project/'.agent/hindsight_seed_results.json'
outpath.parent.mkdir(parents=True, exist_ok=True)
outpath.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
print('SEEDED_PASS', sum(r['ok'] for r in results), 'TOTAL', len(results))
for r in results:
    print(('OK' if r['ok'] else 'FAIL'), r['profile'], r['returncode'], r['seconds'])
    if not r['ok']:
        print('  tail:', r['tail'].replace('\n',' ')[:300])
