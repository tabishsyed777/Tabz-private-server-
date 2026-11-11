# LocalMind phased plan

## Architecture principle

`Browser → React → FastAPI → Ollama (localhost only) → local model`

The public-facing service is the React/FastAPI application, never Ollama itself. The initial service is single-user and local-network oriented. It has no login, persistence, notebook execution, or agent permissions yet.

## Phase 0 — decisions and hardware

Develop on the current Mac first. For a dedicated Linux machine, start with Ubuntu Server LTS, a 64 GB RAM workstation, 2 TB NVMe, an 8+ core CPU, and an NVIDIA GPU with 16–24 GB VRAM if you want responsive 7B–14B-class quantized models and coding workflows. Model quantization, context length, and concurrent use change memory requirements; test your exact model before buying hardware. Add a UPS and wired Ethernet for a 24/7 host.

## Phase 1 — local chat gateway (implemented)

- React + TypeScript chat UI
- FastAPI gateway with model list, health, and streaming chat
- Local Ollama only; no third-party inference API
- Ollama remains on `127.0.0.1:11434`
- Database-owned conversation context, conservative context budgeting, keep-alive and response limits
- Partial reply checkpoints, cancellation, informative Ollama errors, and formatted code replies
- `InferenceBackend` interface, currently implemented by Ollama

The token estimate is approximate and errs on the safe side; an exact count would require a tokenizer compatible with the selected model.

## Phase 2 — persistence and identity (partially implemented)

Conversation and message persistence is implemented with SQLite by default, with PostgreSQL supported through `DATABASE_URL`. Next, add formal schema migrations, projects/workspaces, password or passkey login, server-side sessions, encrypted backups, and per-user authorization. Enable the PostgreSQL Compose profile only after replacing its placeholder password with a secret manager value.

## Phase 3 — usefulness and local tools

Before expanding tools, collect 20–30 real tasks you want this system to help with and score answers for correctness, usefulness, and time. This reveals where the installed local model is sufficient and where a different model or tool is needed. Then add local document search with source references, followed by file access limited to explicit workspaces. Add code execution only in isolated, disposable containers with resource limits. Require explicit approval before writes, shell commands, network access, or other side effects.

## Phase 4 — safe notebook service

Do not execute notebook code in FastAPI or in a privileged Docker socket. Use short-lived, unprivileged containers or a dedicated sandbox VM with: no host mounts, no Docker socket, no default network, CPU/RAM/PID/time limits, an allowlisted base image, and disposable workspace storage. JupyterLab is a UI; it is not isolation by itself.

## Phase 5 — agent orchestration

Build a job queue and explicit tool permission policy. Every agent run gets a project workspace, a bounded budget/time limit, immutable event log, and an approval gate for shell, file export, network access, or any external side effect. Connect existing agent projects one at a time as workers.

## Phase 6 — dedicated server deployment

Move the unchanged application to Ubuntu Server. Put Caddy in front of the app, expose only HTTPS or—preferably—WireGuard private access, use a firewall default-deny policy, retain Ollama on loopback, store model files on NVMe, and schedule encrypted off-host backups.

## Phase 7 — resilience and security

Test restore from backup, restart behavior, disk-full response, load/concurrency, access-control boundaries, and notebook escape attempts. Monitor hardware temperature, storage capacity, GPU/RAM, job failures, and backup freshness.
