# Ksylian

Ksylian is a self-hosted Minecraft server panel. It is being built as a friendly admin UI for creating, running, monitoring and maintaining Minecraft servers from one place.

The project started as a personal home-server tool, so the first priority is a simple setup for one Linux host: a web panel, a backend API and a local host agent that manages Minecraft server processes.

## Features

- First-run admin account setup
- User login and temporary invite links
- Per-user themes: pink, black, white and Minecraft-style green
- Server list with status, type, Minecraft version and quick actions
- Managed server creation for supported server types
- Server logs with auto-refresh
- Host monitoring: CPU, RAM, disks, services and top processes
- Minecraft server config editing
- Backup and self-update foundations
- CurseForge integration placeholder, ready for API-key based catalog work

## Current Status

Ksylian is early-stage software. It is already useful for local experiments, but some parts are still evolving:

- Real server management depends on the host agent.
- CurseForge installation is not fully enabled yet.
- Multi-host support is not implemented yet.
- Public releases and automatic updates are still being shaped.

## Tech Stack

- Frontend: Vue 3, Vue Router, Vite, SCSS
- Backend: FastAPI
- Host agent: FastAPI + systemd
- Runtime: Docker Compose for the panel, systemd for the agent

## Project Structure

```text
frontend/   Vue admin panel
backend/    Backend API, auth, settings and integrations
agent/      Host agent that manages Minecraft servers on the machine
deploy/     Docker Compose and environment examples
```

## Configuration

Do not commit real `.env` files. The repository intentionally tracks only example files.

Create production config from the example:

```bash
cp deploy/.env.example deploy/.env
```

At minimum, set these values:

```bash
KSYLIAN_AGENT_TOKEN=replace-with-a-long-random-token
KSYLIAN_AUTH_SECRET=replace-with-a-long-random-secret
```

Optional values:

```bash
CURSEFORGE_API_KEY=optional-curseforge-api-key
KSYLIAN_GITHUB_TOKEN=optional-github-token-for-private-repos-or-release-checks
```

For the host agent, use:

```bash
cp agent/.env.example agent/.env
```

The agent token must match `KSYLIAN_AGENT_TOKEN` from `deploy/.env`.

## Local Development

Start the backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL and create the first admin account when prompted.

## Docker Deployment

Prepare environment:

```bash
cp deploy/.env.example deploy/.env
```

Start the panel:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build
```

By default:

- Frontend: `http://SERVER_IP:8088`
- Backend: `http://SERVER_IP:8090`
- Agent: `http://SERVER_IP:8765`

## Host Agent

The backend can show demo data when the agent is unavailable, but real server control requires the agent.

Install the agent on the host:

```bash
cd agent
KSYLIAN_AGENT_TOKEN=replace-with-the-same-token ./install-agent.sh
```

The agent runs as a systemd service and is responsible for:

- creating managed server folders
- starting, stopping and restarting Minecraft servers
- reading logs
- reading and saving `server.properties`
- collecting host metrics
- creating backups
- running the app update command

## Open Source Safety

Before making the repository public, keep these out of Git:

- `deploy/.env`
- `agent/.env`
- CurseForge API keys
- GitHub tokens
- agent tokens
- auth/session secrets
- real user data files
- Minecraft worlds and backups

The current `.gitignore` excludes `.env` and `.env.*` while allowing `.env.example`.

## License

No license has been selected yet. Add a `LICENSE` file before advertising the project as open source.
