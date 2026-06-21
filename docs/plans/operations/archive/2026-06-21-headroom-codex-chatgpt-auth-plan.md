# Headroom Codex ChatGPT Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a persistent loopback-only Headroom Docker proxy for Codex while retaining the existing ChatGPT subscription authentication and leaving the Fanpage Agent runtime untouched.

**Architecture:** Codex keeps the built-in `openai` provider and cached ChatGPT OAuth session, but its user-level `openai_base_url` points to Headroom on `127.0.0.1:8787`. Headroom detects the OAuth headers and forwards Responses HTTP/WebSocket traffic directly to `chatgpt.com/backend-api/codex`; 9Router is not in the request path.

**Tech Stack:** Docker Desktop, Headroom 0.25.0 image digest, Codex `config.toml`, PowerShell, Codex CLI Responses/WebSocket transport.

---

## File and state map

- Modify: `C:\Users\thait\.codex\config.toml` — select the built-in OpenAI provider and route it through the local proxy.
- Create: `C:\Users\thait\.codex\backups\config.toml.headroom-codex-auth-$stamp.bak` — exact pre-change rollback snapshot, where `$stamp` is generated as `yyyyMMdd-HHmmss` in Task 1.
- Create: `C:\Users\thait\.codex\backups\headroom-codex-auth.latest` — pointer to the rollback snapshot used by this deployment.
- Create Docker container: `headroom-codex-auth` — persistent proxy bound to loopback port 8787.
- Create Docker volume: `headroom-codex-state` — persistent Headroom savings and diagnostic state mounted at `/root/.headroom`.
- Preserve stopped container: `headroom-9router-gateway` — rollback evidence only; never start it while port 8787 belongs to the new proxy.
- Do not modify: project `pyproject.toml`, `.env`, `Dockerfile`, `docker-compose.yml`, or `AGENTS.md`.

### Task 1: Preflight invariants and Codex configuration backup

**Files:**
- Read: `C:\Users\thait\.codex\auth.json`
- Read: `C:\Users\thait\.codex\config.toml`
- Create: `C:\Users\thait\.codex\backups\config.toml.headroom-codex-auth-$stamp.bak`
- Create: `C:\Users\thait\.codex\backups\headroom-codex-auth.latest`

- [ ] **Step 1: Verify Docker, port ownership, container state, and ChatGPT auth**

Run:

```powershell
docker info --format 'server={{.ServerVersion}}'
docker ps --format '{{.Names}} {{.Ports}}'
docker ps -a --filter name=headroom-9router-gateway --format 'old={{.Names}} status={{.Status}}'

$authPath = Join-Path $HOME '.codex\auth.json'
$auth = Get-Content -LiteralPath $authPath -Raw | ConvertFrom-Json
if ($auth.auth_mode -ne 'chatgpt') { throw "Expected ChatGPT auth, got: $($auth.auth_mode)" }
if (Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8787 is already in use'
}
```

Expected: Docker reports a server version, `headroom-9router-gateway` is stopped, port 8787 is free, and no exception is raised for `auth_mode`.

- [ ] **Step 2: Create an exact timestamped backup and pointer file**

Run:

```powershell
$configPath = Join-Path $HOME '.codex\config.toml'
$backupRoot = Join-Path $HOME '.codex\backups'
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupPath = Join-Path $backupRoot "config.toml.headroom-codex-auth-$stamp.bak"
Copy-Item -LiteralPath $configPath -Destination $backupPath
[System.IO.File]::WriteAllText(
    (Join-Path $backupRoot 'headroom-codex-auth.latest'),
    $backupPath,
    (New-Object System.Text.UTF8Encoding($false))
)
if ((Get-FileHash -LiteralPath $configPath).Hash -ne (Get-FileHash -LiteralPath $backupPath).Hash) {
    throw 'Codex config backup hash mismatch'
}
$backupPath
```

Expected: the command prints the timestamped backup path and both hashes match.

- [ ] **Step 3: Checkpoint machine state**

Run:

```powershell
git status --short --branch
```

Expected: no application-runtime files are modified. No Git commit is made because this task changes only user-level backup state.

### Task 2: Create the persistent Headroom proxy

**State:**
- Create Docker volume: `headroom-codex-state`
- Create Docker container: `headroom-codex-auth`

- [ ] **Step 1: Create the persistent state volume**

Run:

```powershell
docker volume create headroom-codex-state
```

Expected: output is `headroom-codex-state`.

- [ ] **Step 2: Start the pinned, loopback-only proxy**

Run:

```powershell
$image = 'sha256:d4f1d0f8c249e6b8c025ab83ccb84209563e1b0c6a8b20e5b248a7aa2904adc2'
docker run -d `
  --name headroom-codex-auth `
  --restart unless-stopped `
  -p 127.0.0.1:8787:8787 `
  --env HEADROOM_TELEMETRY=off `
  --volume headroom-codex-state:/root/.headroom `
  $image `
  --host 0.0.0.0 `
  --port 8787 `
  --no-telemetry
```

Expected: Docker prints a new container ID. The command intentionally omits `OPENAI_TARGET_API_URL`.

- [ ] **Step 3: Wait for health using a condition, not a fixed sleep**

Run:

```powershell
$health = $null
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/health' -TimeoutSec 3
        if ($health.ready -eq $true) { break }
    } catch {}
    Start-Sleep -Milliseconds 500
}
if (-not $health -or $health.ready -ne $true) {
    docker logs --tail 200 headroom-codex-auth
    throw 'Headroom did not become ready'
}
if ($health.rust_core -ne 'loaded') { throw "Rust core is $($health.rust_core)" }
$health | Select-Object status, ready, version, rust_core
```

Expected: `status=healthy`, `ready=True`, `version=0.25.0`, and `rust_core=loaded`.

- [ ] **Step 4: Assert isolation and restart behavior**

Run:

```powershell
$container = docker inspect headroom-codex-auth | ConvertFrom-Json
$container = $container[0]
if ($container.HostConfig.RestartPolicy.Name -ne 'unless-stopped') { throw 'Wrong restart policy' }
$binding = $container.HostConfig.PortBindings.'8787/tcp'[0]
if ($binding.HostIp -ne '127.0.0.1' -or $binding.HostPort -ne '8787') { throw 'Proxy is not loopback-only' }
if (($container.Config.Env -join "`n") -match '(?m)^OPENAI_TARGET_API_URL=') { throw '9Router/OpenAI target override leaked into proxy' }
if (-not ($container.Mounts | Where-Object Destination -eq '/root/.headroom')) { throw 'State volume is missing' }
'Docker isolation checks passed'
```

Expected: `Docker isolation checks passed`.

### Task 3: Route the built-in Codex OpenAI provider through Headroom

**Files:**
- Modify: `C:\Users\thait\.codex\config.toml`

- [ ] **Step 1: Update only top-level provider keys**

Run:

```powershell
$path = Join-Path $HOME '.codex\config.toml'
$content = [System.IO.File]::ReadAllText($path)
$firstTable = [regex]::Match($content, '(?m)^[ \t]*\[')
if ($firstTable.Success) {
    $root = $content.Substring(0, $firstTable.Index)
    $tables = $content.Substring($firstTable.Index)
} else {
    $root = $content
    $tables = ''
}

function Set-RootTomlString([string]$text, [string]$key, [string]$value) {
    $pattern = '(?m)^[ \t]*' + [regex]::Escape($key) + '[ \t]*=[^\r\n]*(?:\r?\n|$)'
    $replacement = "$key = `"$value`"`r`n"
    $regex = [regex]::new($pattern)
    if ($regex.IsMatch($text)) { return $regex.Replace($text, $replacement, 1) }
    return $replacement + $text
}

$root = Set-RootTomlString $root 'openai_base_url' 'http://127.0.0.1:8787/v1'
$root = Set-RootTomlString $root 'model_provider' 'openai'
$updated = $root.TrimEnd() + "`r`n`r`n" + $tables.TrimStart()
[System.IO.File]::WriteAllText($path, $updated, (New-Object System.Text.UTF8Encoding($false)))
```

Expected: command exits without output and does not touch `auth.json`.

- [ ] **Step 2: Verify the two root keys and preservation of existing tables**

Run:

```powershell
$path = Join-Path $HOME '.codex\config.toml'
$content = [System.IO.File]::ReadAllText($path)
if ($content -notmatch '(?m)^model_provider = "openai"$') { throw 'model_provider not configured' }
if ($content -notmatch '(?m)^openai_base_url = "http://127\.0\.0\.1:8787/v1"$') { throw 'openai_base_url not configured' }
foreach ($required in @('[marketplaces.openai-bundled]', '[mcp_servers.agentmemory]', '[mcp_servers.codegraph]')) {
    if (-not $content.Contains($required)) { throw "Existing config table lost: $required" }
}
'Codex config preservation checks passed'
```

Expected: `Codex config preservation checks passed`.

- [ ] **Step 3: Ask Codex to parse the updated configuration strictly**

Run:

```powershell
codex --strict-config features list
if ($LASTEXITCODE -ne 0) { throw 'Codex rejected config.toml' }
```

Expected: Codex lists feature flags and exits 0. A model-list warning is not a TOML parse failure.

### Task 4: End-to-end OAuth and WebSocket verification

**State:**
- Read Headroom endpoints: `/health`, `/stats`
- Exercise Codex CLI with the persistent user configuration

- [ ] **Step 1: Run a minimal real Codex request through the persistent proxy**

Run from `C:\tmp`:

```powershell
codex -m gpt-5.5 -s read-only exec --skip-git-repo-check 'Reply exactly OK. Do not call tools.'
```

Expected: output contains `provider: openai` and ends with `OK`. The known Headroom 0.25.0 model-list shape warning may appear but must not stop the request.

- [ ] **Step 2: Prove Headroom selected ChatGPT subscription routing**

Run:

```powershell
$stats = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/stats' -TimeoutSec 10
$oauth = @($stats.recent_requests | Where-Object {
    $_.tags.auth_mode -eq 'oauth' -and
    $_.tags.route -eq 'chatgpt_subscription' -and
    $_.tags.transport -eq 'websocket'
})
if ($oauth.Count -eq 0) { throw 'No verified ChatGPT OAuth WebSocket request found in Headroom stats' }
if ($stats.requests.failed -ne 0) { throw "Headroom reports $($stats.requests.failed) failed requests" }
$oauth | Select-Object -Last 1 request_id, model, tokens_saved, savings_percent
```

Expected: one recent `gpt-5.5` request is printed and failed requests equal zero.

- [ ] **Step 3: Verify container persistence settings after traffic**

Run:

```powershell
docker ps --filter name=headroom-codex-auth --format 'name={{.Names}} status={{.Status}} ports={{.Ports}}'
docker inspect headroom-codex-auth --format 'restart={{.HostConfig.RestartPolicy.Name}} image={{.Image}}'
```

Expected: container is healthy/up, port is bound to `127.0.0.1:8787`, and restart policy is `unless-stopped`.

- [ ] **Step 4: Verify project isolation**

Run:

```powershell
git status --short
git diff -- pyproject.toml .env Dockerfile docker-compose.yml AGENTS.md
```

Expected: no runtime or instruction-file changes. Only previously approved Superpowers documentation commits may differ from the remote branch.

- [ ] **Step 5: Desktop handoff checkpoint**

Close and restart Codex Desktop, then start a new thread and send a short prompt. Re-run:

```powershell
$stats = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/stats' -TimeoutSec 10
$stats.recent_requests | Select-Object -Last 3 timestamp, model, tokens_saved, tags
```

Expected: a new request appears with `route=chatgpt_subscription`. The active thread that existed before the configuration change is not used as proof.

### Task 5: Failure rollback procedure

**Files:**
- Restore: `C:\Users\thait\.codex\config.toml`
- Read: `C:\Users\thait\.codex\backups\headroom-codex-auth.latest`

- [ ] **Step 1: Execute rollback only if Tasks 2-4 fail**

Run:

```powershell
docker rm -f headroom-codex-auth 2>$null
$backupRoot = Join-Path $HOME '.codex\backups'
$backupPath = [System.IO.File]::ReadAllText((Join-Path $backupRoot 'headroom-codex-auth.latest')).Trim()
if (-not (Test-Path -LiteralPath $backupPath)) { throw "Rollback backup missing: $backupPath" }
Copy-Item -LiteralPath $backupPath -Destination (Join-Path $HOME '.codex\config.toml') -Force
'Rollback restored Codex config; restart Codex Desktop'
```

Expected: the new container is absent and the exact pre-change config is restored. Preserve `headroom-codex-state` for diagnostics unless the user explicitly requests deletion.

- [ ] **Step 2: Verify rollback when invoked**

Run:

```powershell
if (docker ps -a --format '{{.Names}}' | Select-String -SimpleMatch 'headroom-codex-auth') {
    throw 'Headroom Codex container still exists after rollback'
}
codex --strict-config features list
```

Expected: no new container exists and Codex parses the restored config successfully.
