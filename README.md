# my-automation-repo

This repository contains **two automation approaches** for fetching LinkedIn jobs and
emailing a daily digest:

| Approach | Description |
|----------|-------------|
| **A – GitHub Actions + Python** *(recommended, no extra infrastructure)* | A Python script run by a GitHub Actions cron job. Reads `resume.txt` and `inputs/sheet.csv` from the repo, scrapes LinkedIn, and sends results via SMTP. |
| **B – Self-hosted n8n** | The original n8n Docker Compose setup with Google Drive/Sheets/Gemini integration. Described in the lower section of this README. |

---

## Table of Contents
### Approach A – GitHub Actions + Python
1. [How it works](#how-it-works-approach-a)
2. [Input files](#input-files)
3. [Setting up GitHub Secrets](#setting-up-github-secrets)
4. [Supported SMTP providers](#supported-smtp-providers)
5. [Running locally](#running-locally)
6. [LinkedIn scraping notes](#linkedin-scraping-notes)

### Approach B – Self-hosted n8n
7. [What the n8n automation does](#what-the-automation-does)
8. [Prerequisites](#prerequisites)
9. [Running with Docker Compose](#running-with-docker-compose)
10. [Importing the workflow into n8n](#importing-the-workflow-into-n8n)
11. [Secrets & credentials (n8n)](#secrets--credentials)

---

## How it works (Approach A)

```
GitHub Actions (cron 05:00 UTC)
  └── scripts/fetch_jobs.py
        ├── reads  resume.txt
        ├── reads  inputs/sheet.csv   (one search per row)
        ├── builds LinkedIn guest-API search URLs
        ├── scrapes publicly available job card HTML
        └── sends HTML + plain-text digest via SMTP
```

The workflow file is at `.github/workflows/daily_job_fetch.yml`.

---

## Input files

### `resume.txt`
Plain-text copy of your résumé. The script reads it as context and includes a snippet
in the outgoing email footer. Replace the placeholder content with your actual résumé.

### `inputs/sheet.csv`
One row per job search. Supported columns:

| Column | Required | Example values |
|--------|----------|----------------|
| `keyword` | ✅ | `QA Engineer`, `SDET` |
| `location` | optional | `Ireland`, `Dublin` |
| `job_type` | optional | `full_time`, `part_time`, `contract`, `internship`, `any` |
| `remote` | optional | `any` (remote + hybrid + on-site), `true` (remote only), `hybrid`, `false` (on-site only) |

> **Note:** `experience_level` is no longer used in `sheet.csv`.  
> Seniority filtering is applied automatically at the script level (see [Filtering logic](#filtering-logic) below).

Example `inputs/sheet.csv` (current configuration — QA roles in Ireland):

```csv
keyword,location,job_type,remote
QA Engineer,Ireland,any,any
QA Automation Engineer,Ireland,any,any
SDET,Ireland,any,any
Test Engineer,Ireland,any,any
Quality Engineer,Ireland,any,any
Automation Engineer in Test,Ireland,any,any
Software Engineer in Test,Ireland,any,any
```

---

## Filtering logic

### Prioritised job titles
The CSV is pre-populated with QA-focused roles that match the target profile:

- QA Engineer / QA Automation Engineer
- SDET (Junior–Mid)
- Test Engineer (Automation)
- Quality Engineer
- Automation Engineer in Test
- Software Engineer in Test (non-senior)

### Seniority exclusion with experience override
After fetching job cards the script automatically excludes any job whose title
contains one of these seniority keywords:

> **Senior · Staff · Principal · Lead · Manager**

**Exception:** if the individual job description explicitly mentions that
**3–5 years** of experience is acceptable (e.g. *"3-5 years of experience"*,
*"3 to 5 years"*), the job is **kept** regardless of the title.

### No-jobs-found email
If zero jobs remain after filtering across **all** search rows, the script still
sends an email to the configured `EMAIL_TO` address with the subject:

> *LinkedIn Job Digest – No jobs found today*

This ensures you always receive a daily confirmation, even when LinkedIn returns
no results or rate-limits the requests.

---

## Setting up GitHub Secrets

> ⚠️ **These secrets are REQUIRED. Without them the daily workflow will fail and no email will be sent.**

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Required | Description |
|-------------|----------|-------------|
| `SMTP_HOST` | ✅ | SMTP server hostname (e.g. `smtp.mailgun.org`) |
| `SMTP_PORT` | optional | SMTP port – `587` for STARTTLS (default) |
| `SMTP_USER` | ✅ | SMTP login username |
| `SMTP_PASS` | ✅ | SMTP password or API key |
| `EMAIL_FROM` | required* | Sender address shown in From header |
| `EMAIL_TO` | ✅ | Recipient address (e.g. `akashvikram98@gmail.com`) |

**If any of `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, or `EMAIL_TO` are missing the workflow will fail with a red ✗** so you are immediately alerted that the secrets need to be added.  
**`EMAIL_FROM` is required when `SMTP_USER` is not an email address** (for example, SendGrid uses `SMTP_USER=apikey`).

> ⚠️ **Never commit real credentials.** The `.env` file is git-ignored.

---

## Supported SMTP providers

### Mailgun
1. Sign up at [mailgun.com](https://www.mailgun.com) (free tier: 1 000 emails/month).
2. Add and verify your sending domain.
3. From **Sending → Domain settings → SMTP credentials**, copy the credentials:
   - `SMTP_HOST` → `smtp.mailgun.org`
   - `SMTP_PORT` → `587`
   - `SMTP_USER` → `postmaster@mg.yourdomain.com`
   - `SMTP_PASS` → the Mailgun SMTP password

### SendGrid
1. Sign up at [sendgrid.com](https://sendgrid.com) (free tier: 100 emails/day).
2. Create an API key with **Mail Send** permission.
3. Use these settings:
   - `SMTP_HOST` → `smtp.sendgrid.net`
   - `SMTP_PORT` → `587`
   - `SMTP_USER` → `apikey`  *(literal string)*
   - `SMTP_PASS` → your SendGrid API key
   - `EMAIL_FROM` → a **verified Sender Identity** in SendGrid (must match a verified sender)

### Any other SMTP relay
Use the hostname, port, and credentials provided by your email provider.

---

## Running locally

```bash
# 1. Clone the repo
git clone https://github.com/akashRoot1/my-automation-repo.git
cd my-automation-repo

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Set SMTP environment variables (copy .env.example as a guide)
export SMTP_HOST=smtp.mailgun.org
export SMTP_PORT=587
export SMTP_USER=postmaster@mg.yourdomain.com
export SMTP_PASS=your_password
export EMAIL_FROM=jobs@yourdomain.com
export EMAIL_TO=akashvikram98@gmail.com

# 4. Edit your inputs
#    - Put your résumé text in resume.txt
#    - Edit inputs/sheet.csv with your desired job searches

# 5. Run
python scripts/fetch_jobs.py
```

### Dry-run (print jobs without sending email)

Set `DRY_RUN=1` to skip SMTP entirely and just print results to stdout:

```bash
DRY_RUN=1 python scripts/fetch_jobs.py
```

You can also trigger a dry-run from GitHub Actions:  
**Actions → Daily LinkedIn Job Fetch → Run workflow → set "dry_run" to `true`**.

---

## Troubleshooting

### "Workflow shows green ✓ but I received no email"

**Root cause:** The required GitHub Secrets are not set. The workflow ran successfully but
the script skipped sending email because `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, or
`EMAIL_TO` were empty.

**Fix:**
1. Go to **Settings → Secrets and variables → Actions** in your repository.
2. Add all four required secrets: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`.
3. See [Supported SMTP providers](#supported-smtp-providers) for recommended free services.
4. Re-run the workflow manually: **Actions → Daily LinkedIn Job Fetch → Run workflow**.

After this fix, if secrets are ever missing again the workflow will fail with a
**red ✗** (exit code 1) so you are immediately alerted.

### "The from address does not match a verified Sender Identity"

**Root cause:** SendGrid rejected the email because the `EMAIL_FROM` address is
not a verified Sender Identity.

**Fix:**
1. Go to **SendGrid → Settings → Sender Authentication**.
2. Verify a **Single Sender** or your **Domain**.
3. Set `EMAIL_FROM` to that verified address in GitHub Secrets.
4. Re-run the workflow.

### How to verify email delivery from the workflow logs

1. Go to **Actions → Daily LinkedIn Job Fetch** → click the latest run.
2. Expand the **"Fetch LinkedIn jobs and send email"** step.
3. Look for:
   - `[INFO] Email sent → akashvikram98@gmail.com` → email was dispatched successfully.
   - `[ERROR] SMTP not configured – missing secrets: …` → secrets are not set (see above).
   - `[ERROR] Failed to send email: …` → SMTP credentials are wrong or the server rejected the connection.

---

## LinkedIn scraping notes

> ⚠️ LinkedIn actively detects and rate-limits automated requests.

- The script uses LinkedIn's **public guest jobs API** (`/jobs-guest/...`) which
  does not require authentication and returns basic HTML fragments.
- A 2-second polite delay is added between search requests.
- If LinkedIn blocks the request (returns empty results or a challenge page), no
  jobs will appear for that search — the script handles this gracefully.
- Using a residential or cloud-VM IP with a fresh session improves reliability.
- This is for personal/educational use.
  Review [LinkedIn's Terms of Service](https://www.linkedin.com/legal/user-agreement)
  before running at scale.

---

---
<!-- ──────────────────────────────────────────────────────────────── -->
## Approach B – Self-hosted n8n

Self-hosted **n8n** automation suite powered by Docker Compose.  
The flagship workflow scrapes LinkedIn job postings, filters them against your criteria stored in Google Sheets, enriches each listing with Gemini AI, and delivers a curated digest to your Gmail inbox.

---

## Table of Contents (n8n)
1. [What the automation does](#what-the-automation-does)
2. [Prerequisites](#prerequisites)
3. [Running with Docker Compose](#running-with-docker-compose)
4. [Importing the workflow into n8n](#importing-the-workflow-into-n8n)
5. [Secrets & credentials](#secrets--credentials)
6. [LinkedIn scraping reliability (n8n)](#linkedin-scraping-reliability)

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
