# Project notes: Tabzzat Tabish Server

## Vision

Tabzzat Tabish Server is intended to become a personal AI workspace that runs on infrastructure selected and controlled by its owner. The model engine is Ollama, the application is custom-built, and the project avoids third-party AI inference APIs.

## What Tabish built

The work began with a beginner-friendly architecture for a personal cloud that could grow from local development into a dedicated Linux server. The selected stack is React + TypeScript for the browser interface, FastAPI for the application server, Ollama for inference, and PostgreSQL for production persistence.

The first milestone became a working chat application, not a static mock-up. It connects to locally installed Ollama models, streams each reply, lists models, and stores chat history.

The second iteration improved reliability:

- The server, rather than the browser, constructs model context from stored messages.
- Prompt context is bounded to protect model quality and memory on small machines.
- Messages retain generation state: complete, streaming, interrupted, or error.
- Partial answers are checkpointed while they stream.
- The interface can stop a generation and display code more clearly.
- The model name is validated before a request is saved.

## Why deployment is separate from development

The development computer has 8 GB of RAM. A locally loaded 3B model can consume several gigabytes and make the machine less responsive. Local development remains useful, but it does not achieve the goal of a separate AI server.

The Oracle deployment package is built to run the software and Ollama on a separate Ubuntu instance. The first deployment mode binds the web service to loopback on that machine and uses an SSH tunnel from the Mac, keeping the service private while the first server is brought online.

## Honest project status

The codebase, deployment package, and documentation are complete for the implemented milestones. No Oracle virtual machine has been provisioned or deployed by this repository yet. Authentication, managed file access, notebook execution, autonomous agents, and operational monitoring are future milestones rather than claims of existing functionality.

## Next milestones

1. Provision the Oracle Ubuntu server and deploy the included package.
2. Establish scheduled backups and restore verification.
3. Add authentication before exposing any service outside the SSH tunnel.
4. Add source-cited local document search inside explicitly selected workspaces.
5. Add isolated code execution with approval controls.
6. Evaluate the local model on 20–30 real tasks before giving it broader tools.
