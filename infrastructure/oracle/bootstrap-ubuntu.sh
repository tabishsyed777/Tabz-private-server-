#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y ca-certificates curl docker.io docker-compose-plugin
sudo systemctl enable --now docker

# Install Ollama directly on the Oracle machine. It remains bound to loopback.
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama

echo "Bootstrap complete. Copy the Tabzzat Tabish Server folder to this machine, create infrastructure/oracle/.env from .env.example, then run Docker Compose."
