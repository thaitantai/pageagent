# Headroom Proxy For Codex ChatGPT Authentication Spec

## Goal

Route Codex Desktop and CLI traffic through a local Headroom Docker proxy while preserving the existing ChatGPT subscription login. The resulting request path is:

```text
Codex -> Headroom proxy -> chatgpt.com/backend-api/codex
```

The setup must not add dependencies to the Fanpage Agent Python environment, change its LLM configuration, or route the application's runtime traffic through Headroom.

## Verified baseline

- Codex currently uses `auth_mode = "chatgpt"` and has no OpenAI API key.
- The installed Headroom image is version `0.25.0` with a loaded Rust core.
- The previous `headroom-9router-gateway` container is stopped and has restart policy `no`.
- The previous Headroom-to-9Router route fails for Codex Responses requests with HTTP 401 because 9Router rejects the forwarded Host header.
- A temporary canary using the existing Headroom image, no 9Router target, and a CLI-only `openai_base_url` override completed successfully with model `gpt-5.5`.
- Headroom reported `auth_mode=oauth`, `route=chatgpt_subscription`, `transport=websocket`, and zero failed requests during the canary.

## Selected approach

Use Codex's built-in `openai` provider and override only its base URL. This retains Codex's cached ChatGPT OAuth session and avoids a second provider identity or an API key.

The user-level Codex configuration will contain these top-level keys before any TOML tables:

```toml
model_provider = "openai"
openai_base_url = "http://127.0.0.1:8787/v1"
```

A custom `[model_providers.headroom]` block is intentionally not used. Although Codex supports custom providers with `requires_openai_auth = true`, the built-in provider override is smaller and was validated by the canary.

## Docker runtime

Create a new container named `headroom-codex-auth` rather than modifying the old 9Router container in place.

Runtime properties:

- Image: the locally verified Headroom `0.25.0` image digest.
- Published address: `127.0.0.1:8787 -> 8787/tcp` so the proxy is not exposed on external interfaces.
- Restart policy: `unless-stopped`.
- Telemetry: disabled.
- `OPENAI_TARGET_API_URL`: absent. Headroom must select the ChatGPT subscription route from the incoming OAuth headers.
- Persistent state: a named Docker volume mounted at Headroom's state directory for savings and diagnostic history.
- No source workspace mount and no modification of project `AGENTS.md`.

The stopped `headroom-9router-gateway` container remains available during validation as a rollback artifact but must not be started while the new container owns port 8787.

## Configuration safety

Before changing `~/.codex/config.toml`, create a timestamped backup. Insert or replace only the top-level `model_provider` and `openai_base_url` keys while preserving all existing marketplaces, MCP servers, trusted projects, and other settings.

No values from `~/.codex/auth.json` are copied into Docker. Codex continues to own token storage and refresh; it sends the active OAuth credentials with requests to the loopback proxy.

## Validation

Validation succeeds only when all checks pass:

1. `http://127.0.0.1:8787/health` reports healthy and `rust_core=loaded`.
2. A minimal `codex exec` request completes through the persistent proxy.
3. Headroom `/stats` records the canary with `auth_mode=oauth`, `route=chatgpt_subscription`, and no failed requests.
4. Codex still reports the expected ChatGPT account and model.
5. A new Codex Desktop thread works after the app restarts.
6. The Fanpage Agent repository has no runtime, dependency, environment, or instruction-file changes other than this design document.

The Headroom `0.25.0` model-list compatibility warning is acceptable only if Responses HTTP/WebSocket requests continue to succeed. It must be reported but must not be mistaken for a failed proxy route.

## Rollback

Rollback is deterministic:

1. Stop and remove `headroom-codex-auth`.
2. Restore the timestamped `~/.codex/config.toml` backup.
3. Restart Codex.
4. Confirm Codex uses the built-in OpenAI provider without a local base URL override.

The old 9Router-based Headroom container remains stopped; rollback does not reactivate the known-broken chain.
