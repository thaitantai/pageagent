#!/usr/bin/env python3
"""
Run installed Hermes registry workflows against local Hermes agent profiles.

Default mode is --dry-run. Use --execute to run real profile calls.

Examples:
  python scripts/run_registry_workflow.py bug-fix --goal "Fix duplicate Facebook publishing"
  python scripts/run_registry_workflow.py security-audit --goal "Audit token handling" --execute
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HERMES_ROOT = Path.home() / "AppData" / "Local" / "hermes"
PROFILES_ROOT = HERMES_ROOT / "profiles"
DEFAULT_WORKFLOWS_DIR = PROFILES_ROOT / "pagent" / "workflows"
AGENT_DIR = PROJECT_ROOT / ".agent"
TASKS_DIR = AGENT_DIR / "tasks"
HANDOFFS_DIR = AGENT_DIR / "handoffs"
RUNS_DIR = AGENT_DIR / "runs"

EXACT_PROFILE_ALIASES = {
    "architect": "architect",
    "api-designer": "api-designer",
    "api_designer": "api-designer",
    "backend-engineer": "backend-engineer",
    "backend_engineer": "backend-engineer",
    "backend": "backend-engineer",
    "developer": "backend-engineer",
    "engineer": "backend-engineer",
    "frontend-engineer": "frontend-engineer",
    "frontend_engineer": "frontend-engineer",
    "frontend": "frontend-engineer",
    "test-writer": "test-writer",
    "test_writer": "test-writer",
    "tester": "test-writer",
    "qa": "test-writer",
    "debugger": "debugger",
    "security-auditor": "security-auditor",
    "security_auditor": "security-auditor",
    "security": "security-auditor",
    "performance-optimizer": "performance-optimizer",
    "performance_optimizer": "performance-optimizer",
    "performance": "performance-optimizer",
    "code-reviewer": "code-reviewer",
    "code_reviewer": "code-reviewer",
    "reviewer": "code-reviewer",
    "review": "code-reviewer",
    "refactorer": "refactorer",
    "refactor": "refactorer",
    "devops-engineer": "devops-engineer",
    "devops_engineer": "devops-engineer",
    "devops": "devops-engineer",
    "doc-writer": "doc-writer",
    "doc_writer": "doc-writer",
    "docs": "doc-writer",
    "writer": "doc-writer",
    "prompt-engineer": "prompt-engineer",
    "prompt_engineer": "prompt-engineer",
    "prompt": "prompt-engineer",
    "data-analyst": "data-analyst",
    "data_analyst": "data-analyst",
    "analyst": "data-analyst",
    "researcher": "data-analyst",
    "sql-expert": "sql-expert",
    "sql_expert": "sql-expert",
    "sql": "sql-expert",
    "pagent": "pagent",
    "orchestrator": "pagent",
}

FALLBACK_BY_WORKFLOW_STEP = [
    (re.compile(r"security|secret|token|auth|vulnerab", re.I), "security-auditor"),
    (re.compile(r"test|coverage|pytest|regression|qa", re.I), "test-writer"),
    (re.compile(r"review|pr|diff|quality", re.I), "code-reviewer"),
    (re.compile(r"debug|reproduce|root cause|diagnos", re.I), "debugger"),
    (re.compile(r"refactor|cleanup|simpl", re.I), "refactorer"),
    (re.compile(r"deploy|docker|dependency|upgrade|release", re.I), "devops-engineer"),
    (re.compile(r"doc|changelog|notes|readme", re.I), "doc-writer"),
    (re.compile(r"research|triage|analy", re.I), "data-analyst"),
    (re.compile(r"design|architect|plan", re.I), "architect"),
    (re.compile(r"api|contract|schema|interface", re.I), "api-designer"),
]


def slugify(value: str, max_len: int = 60) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-._")
    return (value or "workflow")[:max_len]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_steps(workflow: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = workflow.get("steps") or workflow.get("tasks") or []
    if not isinstance(raw, list):
        raise ValueError("workflow steps/tasks must be a list")
    steps: List[Dict[str, Any]] = []
    for i, item in enumerate(raw, start=1):
        if isinstance(item, str):
            step = {"id": f"step-{i}", "description": item}
        elif isinstance(item, dict):
            step = dict(item)
        else:
            raise ValueError(f"unsupported step type at index {i}: {type(item)!r}")
        step.setdefault("id", f"step-{i}")
        step.setdefault("description", step.get("name") or step.get("title") or "")
        steps.append(step)
    return steps


def resolve_profile(step: Dict[str, Any], workflow_name: str) -> str:
    raw_agent = (
        step.get("agent")
        or step.get("profile")
        or step.get("role")
        or step.get("assignee")
        or ""
    )
    key = slugify(str(raw_agent).replace("_", "-"), 80)
    key_underscore = str(raw_agent).strip().lower().replace("-", "_")
    if key in EXACT_PROFILE_ALIASES:
        return EXACT_PROFILE_ALIASES[key]
    if key_underscore in EXACT_PROFILE_ALIASES:
        return EXACT_PROFILE_ALIASES[key_underscore]

    text = " ".join(str(x) for x in [raw_agent, step.get("id", ""), step.get("name", ""), step.get("description", ""), workflow_name])
    for pattern, profile in FALLBACK_BY_WORKFLOW_STEP:
        if pattern.search(text):
            return profile
    return "backend-engineer"


def ensure_dirs() -> None:
    for d in [TASKS_DIR, HANDOFFS_DIR, RUNS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def task_markdown(
    *,
    workflow_name: str,
    run_id: str,
    index: int,
    total: int,
    step: Dict[str, Any],
    profile: str,
    goal: str,
    handoff_path: Path,
    previous_handoff: Optional[Path],
    all_previous_handoffs: List[Path],
    extra_context: str,
) -> str:
    step_id = str(step.get("id") or f"step-{index}")
    description = str(step.get("description") or step.get("name") or "")
    raw_agent = str(step.get("agent") or step.get("profile") or step.get("role") or "")
    prev = str(previous_handoff.relative_to(PROJECT_ROOT)) if previous_handoff else "None"
    prev_all = "\n".join(f"- {p.relative_to(PROJECT_ROOT)}" for p in all_previous_handoffs) or "- None"
    return f"""# Workflow task: {workflow_name} / {step_id}

## Run ID
{run_id}

## Step
{index}/{total}: {step_id}

## Assigned profile
{profile}

## Registry agent field
{raw_agent or 'not specified'}

## User goal
{goal}

## Step description
{description}

## Project
{PROJECT_ROOT}

## Previous handoff
{prev}

## All previous handoffs
{prev_all}

## Extra context
{extra_context or 'None'}

## Operating rules
- Work inside project path above.
- Use profile-local memory/Hindsight if available.
- Do not print or store secrets, API keys, tokens, passwords, or connection strings.
- Prefer targeted edits and tests.
- Do not use `hermes profile use`.
- Path B AgentBus is active; path A agent.py legacy may still exist.
- If uncertain, document risk in handoff instead of inventing facts.

## Required output
Create handoff file exactly here:

```text
{handoff_path.relative_to(PROJECT_ROOT)}
```

Handoff must include:

```md
# Handoff: {run_id} / {step_id} / {profile}

## Summary

## Files changed

## Commands run

## Results

## Risks

## Next step
```

## Done criteria
- Step goal addressed.
- Handoff file exists at required path.
- Any code changes are described with tests or reason tests not run.
"""


def build_prompt(task_path: Path, handoff_path: Path) -> str:
    task_rel = task_path.relative_to(PROJECT_ROOT)
    handoff_rel = handoff_path.relative_to(PROJECT_ROOT)
    return (
        f"Read task file {task_rel}. Complete exactly that workflow step inside project "
        f"{PROJECT_ROOT}. Write required handoff to {handoff_rel}. "
        "Do not reveal secrets. Keep final answer short and mention handoff path."
    )


def run_profile(profile: str, prompt: str, timeout: int) -> Tuple[int, str, str]:
    profile_dir = PROFILES_ROOT / profile
    env = os.environ.copy()
    env["HERMES_HOME"] = str(profile_dir)
    env["TERM"] = "dumb"
    cmd = ["hermes", "-z", prompt, "chat"]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description="Run installed Hermes registry workflow via local profiles")
    parser.add_argument("workflow", help="Workflow folder name, e.g. bug-fix")
    parser.add_argument("--goal", required=True, help="User goal for this workflow run")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan only; default")
    mode.add_argument("--execute", action="store_true", help="Run Hermes profiles for real")
    parser.add_argument("--workflows-dir", default=str(DEFAULT_WORKFLOWS_DIR), help="Installed workflows directory")
    parser.add_argument("--timeout", type=int, default=900, help="Per-step timeout seconds")
    parser.add_argument("--run-id", default=None, help="Override run id")
    parser.add_argument("--extra-context", default="", help="Extra context added to every task")
    parser.add_argument("--continue-on-missing-handoff", action="store_true", help="Do not fail when handoff missing")
    args = parser.parse_args()

    execute = bool(args.execute)
    workflow_slug = slugify(args.workflow)
    workflows_dir = Path(args.workflows_dir)
    workflow_dir = workflows_dir / workflow_slug
    workflow_path = workflow_dir / "workflow.json"
    manifest_path = workflow_dir / "manifest.json"

    if not workflow_path.exists():
        print(f"ERROR: workflow not found: {workflow_path}", file=sys.stderr)
        return 2

    ensure_dirs()
    workflow = load_json(workflow_path)
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    steps = normalize_steps(workflow)
    if not steps:
        print(f"ERROR: workflow has no steps: {workflow_path}", file=sys.stderr)
        return 2

    run_id = args.run_id or f"{workflow_slug}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = RUNS_DIR / run_id
    run_tasks_dir = run_dir / "tasks"
    run_handoffs_dir = run_dir / "handoffs"
    run_logs_dir = run_dir / "logs"
    for d in [run_dir, run_tasks_dir, run_handoffs_dir, run_logs_dir]:
        d.mkdir(parents=True, exist_ok=True)

    run_record: Dict[str, Any] = {
        "run_id": run_id,
        "workflow": workflow_slug,
        "goal": args.goal,
        "mode": "execute" if execute else "dry-run",
        "project_root": str(PROJECT_ROOT),
        "workflows_dir": str(workflows_dir),
        "workflow_path": str(workflow_path),
        "manifest": manifest,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "steps": [],
    }

    print(f"RUN_ID {run_id}")
    print(f"WORKFLOW {workflow_slug}")
    print(f"MODE {'EXECUTE' if execute else 'DRY_RUN'}")
    print(f"STEPS {len(steps)}")

    previous_handoff: Optional[Path] = None
    previous_handoffs: List[Path] = []
    status = "completed"

    for idx, step in enumerate(steps, start=1):
        step_id = slugify(str(step.get("id") or f"step-{idx}"), 50)
        profile = resolve_profile(step, workflow_slug)
        profile_dir = PROFILES_ROOT / profile
        task_name = f"{run_id}-{idx:02d}-{step_id}-{profile}.md"
        handoff_name = f"{run_id}-{idx:02d}-{step_id}-{profile}.md"
        task_path = TASKS_DIR / task_name
        handoff_path = HANDOFFS_DIR / handoff_name
        run_task_copy = run_tasks_dir / task_name
        run_handoff_copy = run_handoffs_dir / handoff_name
        prompt = build_prompt(task_path, handoff_path)

        task_text = task_markdown(
            workflow_name=workflow_slug,
            run_id=run_id,
            index=idx,
            total=len(steps),
            step=step,
            profile=profile,
            goal=args.goal,
            handoff_path=handoff_path,
            previous_handoff=previous_handoff,
            all_previous_handoffs=previous_handoffs,
            extra_context=args.extra_context,
        )
        task_path.write_text(task_text, encoding="utf-8")
        run_task_copy.write_text(task_text, encoding="utf-8")

        step_record: Dict[str, Any] = {
            "index": idx,
            "step_id": step_id,
            "raw_step": step,
            "profile": profile,
            "profile_dir": str(profile_dir),
            "task_path": str(task_path),
            "handoff_path": str(handoff_path),
            "prompt": prompt,
            "status": "planned",
        }

        print(f"\nSTEP {idx}/{len(steps)} {step_id}")
        print(f"PROFILE {profile}")
        print(f"TASK {task_path.relative_to(PROJECT_ROOT)}")
        print(f"HANDOFF {handoff_path.relative_to(PROJECT_ROOT)}")

        if not profile_dir.exists():
            step_record["status"] = "failed"
            step_record["error"] = f"profile not found: {profile_dir}"
            run_record["steps"].append(step_record)
            status = "failed"
            print(f"FAIL profile not found: {profile_dir}")
            break

        if not execute:
            step_record["status"] = "dry-run"
            print("COMMAND HERMES_HOME='%s' TERM=dumb hermes -z %r chat" % (profile_dir, prompt))
            previous_handoff = handoff_path
            previous_handoffs.append(handoff_path)
            run_record["steps"].append(step_record)
            continue

        try:
            rc, stdout, stderr = run_profile(profile, prompt, args.timeout)
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            rc = 124
            step_record["timeout"] = True

        (run_logs_dir / f"{idx:02d}-{step_id}-{profile}.stdout.log").write_text(stdout or "", encoding="utf-8", errors="replace")
        (run_logs_dir / f"{idx:02d}-{step_id}-{profile}.stderr.log").write_text(stderr or "", encoding="utf-8", errors="replace")
        step_record["returncode"] = rc
        step_record["stdout_log"] = str(run_logs_dir / f"{idx:02d}-{step_id}-{profile}.stdout.log")
        step_record["stderr_log"] = str(run_logs_dir / f"{idx:02d}-{step_id}-{profile}.stderr.log")

        handoff_exists = handoff_path.exists()
        step_record["handoff_exists"] = handoff_exists
        if handoff_exists:
            shutil.copy2(handoff_path, run_handoff_copy)
            step_record["run_handoff_copy"] = str(run_handoff_copy)

        if rc != 0:
            step_record["status"] = "failed"
            step_record["error"] = f"Hermes returned {rc}"
            status = "failed"
            print(f"FAIL returncode {rc}")
            print((stderr or stdout or "")[-1200:])
            run_record["steps"].append(step_record)
            break

        if not handoff_exists and not args.continue_on_missing_handoff:
            step_record["status"] = "failed"
            step_record["error"] = "missing required handoff"
            status = "failed"
            print(f"FAIL missing handoff: {handoff_path.relative_to(PROJECT_ROOT)}")
            run_record["steps"].append(step_record)
            break

        step_record["status"] = "completed" if handoff_exists else "completed-no-handoff"
        print(f"OK handoff={'yes' if handoff_exists else 'no'}")
        previous_handoff = handoff_path
        previous_handoffs.append(handoff_path)
        run_record["steps"].append(step_record)

    run_record["status"] = status
    run_record["finished_at"] = datetime.now().isoformat(timespec="seconds")
    run_json = run_dir / "run.json"
    run_json.write_text(json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        f"# Workflow run: {run_id}",
        "",
        f"- workflow: `{workflow_slug}`",
        f"- mode: `{run_record['mode']}`",
        f"- status: `{status}`",
        f"- goal: {args.goal}",
        "",
        "## Steps",
        "",
    ]
    for s in run_record["steps"]:
        summary.append(f"- {s['index']:02d} `{s['step_id']}` -> `{s['profile']}`: `{s['status']}`")
        summary.append(f"  - task: `{Path(s['task_path']).relative_to(PROJECT_ROOT)}`")
        summary.append(f"  - handoff: `{Path(s['handoff_path']).relative_to(PROJECT_ROOT)}`")
    (run_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"\nSTATUS {status.upper()}")
    print(f"RUN_JSON {run_json}")
    print(f"SUMMARY {run_dir / 'summary.md'}")
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
