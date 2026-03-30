# my-automation-repo

Self-hosted **n8n** automation suite powered by Docker Compose.  
The flagship workflow scrapes LinkedIn job postings, filters them against your criteria stored in Google Sheets, enriches each listing with Gemini AI, and delivers a curated digest to your Gmail inbox.

---

## Table of Contents
1. [What the automation does](#what-the-automation-does)
2. [Prerequisites](#prerequisites)
3. [Running with Docker Compose](#running-with-docker-compose)
4. [Importing the workflow into n8n](#importing-the-workflow-into-n8n)
5. [Secrets & credentials](#secrets--credentials)
6. [LinkedIn scraping reliability](#linkedin-scraping-reliability)

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