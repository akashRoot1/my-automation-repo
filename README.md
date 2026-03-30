# my-automation-repo

Self-hosted **n8n** automation suite powered by Docker Compose.  
The flagship workflow scrapes LinkedIn job postings, filters them against your criteria stored in Google Sheets, enriches each listing with Gemini AI, and delivers a curated digest to your Gmail inbox.

---

## Table of Contents
1. [How this repository was built — process summary](#how-this-repository-was-built--process-summary)
2. [What the automation does](#what-the-automation-does)
3. [Prerequisites](#prerequisites)
4. [Running with Docker Compose](#running-with-docker-compose)
5. [Importing the workflow into n8n](#importing-the-workflow-into-n8n)
6. [Secrets & credentials](#secrets--credentials)
7. [LinkedIn scraping reliability](#linkedin-scraping-reliability)

---

## How this repository was built — process summary

### 1. Initial request
The user shared a screenshot of an n8n workflow and asked for it to be added to their GitHub repository (`akashRoot1/my-automation-repo`).  Because a screenshot alone cannot capture node parameters, expressions, or credential IDs, two clarifying questions were raised before any files were written:

- **Which repository?** — the exact `owner/repo` slug.
- **Which integration format?** — three options were offered (see below).
- **Actual workflow data?** — the user was asked to export the workflow from n8n (**Workflow → … → Download / Export → JSON**) and share the JSON.

### 2. Format clarification — why Option B (n8n self-host) instead of Option C (GitHub Actions)

Three implementation options were presented:

| Option | Description | When it makes sense |
|--------|-------------|---------------------|
| **A — n8n export only** | Drop the workflow JSON + README into the repo (no runtime). | You already have a running n8n instance elsewhere. |
| **B — Self-host n8n** ✅ | Docker Compose (`docker-compose.yml`) + PostgreSQL + `.env.example` + workflow JSON. | You want to spin up a production-grade n8n server with one command. |
| **C — GitHub Actions** | Rebuild the automation as a `.github/workflows/` YAML file. | The workflow is a CI/CD task that fits the GitHub runner model (short-lived, triggered by repo events). |

**Option B was chosen** for the following reasons:

- The workflow uses long-running nodes (HTTP requests with polite 2-second waits between iterations, loop batching) that exceed GitHub Actions' typical job boundaries.
- It requires **persistent credential storage** (Google OAuth tokens, Gemini API key) that GitHub Actions secrets do not natively support for n8n's encrypted credential model.
- It has a **Schedule Trigger** node designed to run on a recurring basis inside n8n — replicating this in GitHub Actions would require a `cron:` schedule that restarts a full runner on every run, with no shared state.
- n8n's visual editor makes it easy for the user to adjust filters, reconnect credentials, and extend nodes without touching YAML or code.

### 3. Workflow export and data handoff

The user exported the workflow from their n8n instance (**Workflow → … → Download / Export → JSON**).  
The exported file (`job-search-ultimate.json`) was placed at `n8n/workflows/job-search-ultimate.json`.

> **Credential IDs are stripped on import.** The JSON contains credential *references* (names such as `"Google Drive account"`) but the actual OAuth tokens never leave the original n8n instance. After importing into a fresh instance, each credential-bearing node will show a warning until you reconnect or recreate the credential — this is the expected and secure behaviour.

### 4. GitHub Actions / permissions dialogue

No GitHub Actions workflow files were created for this project.  The only GitHub Actions involvement was the automated pull-request that added the files to this repository.  Repository permissions required were:

- **Contents: write** — to create and push the new files (`docker-compose.yml`, `.env.example`, `n8n/workflows/job-search-ultimate.json`, `README.md`, `.gitignore`).
- No workflow-dispatch, no `GITHUB_TOKEN` secrets, and no Actions runner invocations were needed for the n8n stack itself.

### 5. Files added and their purpose

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Defines two services: **postgres** (PostgreSQL 16) and **n8n** (latest). Postgres data and n8n data are each stored in a named Docker volume. The n8n service waits for Postgres to pass its health check before starting. All secrets are read from environment variables — never hard-coded. |
| `.env.example` | Template for the required environment variables. Copy to `.env`, fill in real values, and **never commit `.env`**. |
| `n8n/workflows/job-search-ultimate.json` | The exported n8n workflow. Import this file into n8n via **Workflows → Import from file…** and then reconnect credentials. |
| `README.md` | This file — setup instructions, environment-variable reference, import guide, and process narrative. |
| `.gitignore` | Prevents `.env`, `n8n_data/`, and `postgres_data/` from being accidentally committed. |

### 6. Credentials handling

- **Postgres password** (`POSTGRES_PASSWORD`) and **n8n encryption key** (`N8N_ENCRYPTION_KEY`) are injected via `.env` at runtime — they are never stored in the repository.
- Google OAuth tokens (Drive, Sheets, Gmail) are generated interactively through n8n's credential UI and stored **encrypted inside the `n8n_data` Docker volume**, protected by `N8N_ENCRYPTION_KEY`.
- The Gemini API key is likewise stored as an n8n credential, not in any file tracked by Git.
- `.gitignore` explicitly excludes `.env`, `n8n_data/`, and `postgres_data/` as a defence-in-depth measure.

### 7. What you will have once the PR is merged

After merging this PR and following the setup steps you will have:

- A **one-command Docker Compose stack** (`docker compose up -d`) that launches a production-ready n8n instance backed by a PostgreSQL database, with data persisted across restarts.
- A **self-hosted n8n editor** reachable at `http://localhost:5678` (or your custom domain) where you can manage, schedule, and monitor all your automations.
- The **LinkedIn job-search workflow** pre-imported and ready to connect to your Google credentials and Gemini API key.
- A clear, auditable Git history showing every file that was added and why — with no secrets committed.

---

## What the automation does

| Step | Node | Description |
|------|------|-------------|
| 1 | Google Drive | Downloads your résumé PDF from Drive |
| 2 | Extract from File | Parses the PDF text |
| 3 | Google Sheets | Reads filter criteria (keywords, location, experience level, remote preference) |
| 4 | Code (JS) | Builds a LinkedIn job-search URL from the filter values |
| 5 | HTTP Request | Fetches the LinkedIn search results page |
| 6 | HTML parser | Extracts individual job-posting URLs |
| 7 | Loop + Wait | Iterates over each job URL with a polite 2-second delay |
| 8 | HTTP Request | Fetches each individual job page |
| 9 | HTML parser | Extracts title, company, location, description, and job ID |
| 10 | Set / Edit Fields | Normalises the description text |

> The workflow JSON also contains credential references for **Google Sheets OAuth**, **Google Drive OAuth**, and **Gemini API** nodes. You will need to reconnect these credentials after import (see below).

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| [Docker](https://docs.docker.com/get-docker/) ≥ 24 | Includes Docker Compose v2 |
| Google Cloud project | OAuth 2.0 credentials for Drive, Sheets, and Gmail |
| Gemini API key | [Google AI Studio](https://aistudio.google.com/app/apikey) |

---

## Running with Docker Compose

```bash
# 1. Clone the repository
git clone https://github.com/akashRoot1/my-automation-repo.git
cd my-automation-repo

# 2. Create your environment file
cp .env.example .env
# Open .env and fill in every placeholder value

# 3. Start the stack (detached)
docker compose up -d

# 4. Open the n8n editor
open http://localhost:5678
```

To stop the stack:

```bash
docker compose down
```

To stop and wipe all data (volumes):

```bash
docker compose down -v
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | ✅ | Password for the n8n Postgres user |
| `N8N_ENCRYPTION_KEY` | ✅ | 32-character random key for encrypting stored credentials. Generate with `openssl rand -hex 16` |
| `N8N_PROTOCOL` | optional | `http` (default) or `https` |
| `N8N_HOST` | optional | Hostname / IP where n8n is reachable (default `localhost`) |
| `WEBHOOK_URL` | optional | Full base URL for webhook nodes |
| `N8N_EDITOR_BASE_URL` | optional | Full base URL for the editor UI |
| `TZ` | optional | IANA timezone (default `UTC`) |

---

## Importing the workflow into n8n

1. Open the n8n editor at `http://localhost:5678`.
2. Create an account (first launch only).
3. Click the **≡ menu** (top-left) → **Workflows** → **Import from file…**
4. Select `n8n/workflows/job-search-ultimate.json` from this repository.
5. The workflow will appear with credential warnings — click each node that has a warning and connect (or create) the appropriate credential:
   - **Google Drive** → `googleDriveOAuth2Api`
   - **Google Sheets** → `googleSheetsOAuth2Api`
   - **Gmail** → `gmailOAuth2` *(if present)*
   - **Gemini** → API key credential
6. Update the **Google Sheets** node with your own spreadsheet ID and sheet name.
7. Update the **Google Drive** node with the file ID or URL of your résumé.
8. Save and activate the workflow with the toggle in the top-right corner.

---

## Secrets & credentials

- **Never commit your `.env` file** — it is listed in `.gitignore`.
- Google OAuth tokens are stored encrypted inside the `n8n_data` Docker volume, protected by `N8N_ENCRYPTION_KEY`.
- Rotate `N8N_ENCRYPTION_KEY` carefully: changing it without re-entering credentials will break existing stored credentials.

---

## LinkedIn scraping reliability

> ⚠️ LinkedIn actively detects and blocks automated requests.

- The workflow adds a 2-second wait between individual job-page requests to reduce rate-limiting.
- LinkedIn may return empty results or a CAPTCHA challenge if your IP is flagged.
- Using a residential proxy or a cloud VM with a clean IP improves reliability.
- LinkedIn's HTML structure changes periodically — the CSS selectors in the HTML nodes may need updating if the workflow stops extracting data correctly.
- This workflow is for personal/educational use. Review [LinkedIn's Terms of Service](https://www.linkedin.com/legal/user-agreement) before running it at scale.