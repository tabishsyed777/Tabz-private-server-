# Tabzzat Tabish Server on Oracle Cloud

This package deploys the Tabzzat Tabish Server web interface, FastAPI service, PostgreSQL database, and host-installed Ollama to one Ubuntu server.

The Compose file publishes the web service only at `127.0.0.1:8080` on the Oracle machine. It is private by default. Ollama remains at `127.0.0.1:11434` and is reachable only by the backend container.

## Before deployment

1. Create an Oracle Cloud Always Free Ampere A1 Ubuntu instance from your Oracle account.
2. Connect by SSH and run `bootstrap-ubuntu.sh`.
3. Copy this project to the server.
4. In `infrastructure/oracle`, copy `.env.example` to `.env` and replace `POSTGRES_PASSWORD` with a long unique password.

## Start the server

From the project root on the Oracle machine:

```bash
ollama pull qwen2.5-coder:3b
docker compose --env-file infrastructure/oracle/.env -f infrastructure/oracle/docker-compose.yml up -d --build
```

## Open it privately from your Mac

Run this on your Mac, replacing `SERVER_IP` with the Oracle server’s public IP:

```bash
ssh -L 8080:127.0.0.1:8080 ubuntu@SERVER_IP
```

Keep that terminal open, then visit `http://127.0.0.1:8080` in your browser. The chat request travels through the encrypted SSH connection; Ollama runs on the Oracle machine.

## What runs where

```text
Mac browser → encrypted SSH tunnel → Tabzzat Tabish Server → Ollama on Oracle
                                   └→ PostgreSQL on Oracle
```

This does not copy personal files from your Mac. Upload, file indexing, notebook execution, and agents need their own implementation and access rules before they can be put on the server.
