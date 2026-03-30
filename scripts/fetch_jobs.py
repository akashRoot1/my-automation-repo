#!/usr/bin/env python3
"""
LinkedIn Job Fetcher
--------------------
Reads job-search criteria from inputs/sheet.csv, scrapes publicly available
LinkedIn job listings, and emails the results via SMTP.

Usage (local):
    export SMTP_HOST=smtp.mailgun.org
    export SMTP_PORT=587
    export SMTP_USER=postmaster@mg.yourdomain.com
    export SMTP_PASS=your_mailgun_smtp_password
    export EMAIL_FROM=jobs@yourdomain.com
    export EMAIL_TO=your-email@example.com
    python scripts/fetch_jobs.py

If SMTP_HOST / SMTP_USER / SMTP_PASS / EMAIL_TO are not set the script exits
with code 1 so that GitHub Actions shows a red ✗ (alerting you to add the
missing secrets).  Set DRY_RUN=1 to skip the email check entirely, e.g.:

    DRY_RUN=1 python scripts/fetch_jobs.py

Filtering logic:
    - Job titles containing 'Senior', 'Staff', 'Principal', 'Lead', or 'Manager'
      are excluded unless the job description explicitly mentions 3–5 years of
      experience as acceptable.
    - If no jobs are found across all searches, a "no jobs found" email is sent.
"""

import csv
import os
import re
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
RESUME_PATH = REPO_ROOT / "resume.txt"
SHEET_PATH = REPO_ROOT / "inputs" / "sheet.csv"

# ── LinkedIn ───────────────────────────────────────────────────────────────────
_LINKEDIN_GUEST_API = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)
_LINKEDIN_JOB_BASE = "https://www.linkedin.com/jobs/view"

# LinkedIn filter codes
JOB_TYPE_MAP: dict[str, str] = {
    "full_time": "F",
    "part_time": "P",
    "contract": "C",
    "temporary": "T",
    "internship": "I",
    "volunteer": "V",
    "other": "O",
}

EXPERIENCE_MAP: dict[str, str] = {
    "internship": "1",
    "entry_level": "2",
    "associate": "3",
    "mid_senior_level": "4",
    "director": "5",
    "executive": "6",
}

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MAX_JOBS_PER_SEARCH = 15
REQUEST_DELAY_SECONDS = 2

# ── Title / experience filters ─────────────────────────────────────────────────

# Titles containing any of these words are excluded unless the job description
# explicitly mentions that 3–5 years of experience is acceptable.
EXCLUDED_TITLE_KEYWORDS: frozenset[str] = frozenset(
    {"senior", "staff", "principal", "lead", "manager"}
)

# Matches "3-5 years", "3–5 years", "3 to 5 years", "three to five years", etc.
_EXPERIENCE_RANGE_RE = re.compile(
    r"\b(3|three)\s*[-–—to]+\s*(5|five)\s*years?\b",
    re.IGNORECASE,
)


# ── URL builder ────────────────────────────────────────────────────────────────

def build_search_url(row: dict[str, str]) -> str:
    """Build a LinkedIn guest-API search URL from a CSV row."""
    params: dict[str, Any] = {"start": 0}

    keyword = row.get("keyword", "").strip()
    if keyword:
        params["keywords"] = keyword

    location = row.get("location", "").strip()
    if location:
        params["location"] = location

    job_type = row.get("job_type", "").strip().lower()
    # 'any' means no job-type filter
    if job_type and job_type != "any" and job_type in JOB_TYPE_MAP:
        params["f_JT"] = JOB_TYPE_MAP[job_type]

    exp_level = row.get("experience_level", "").strip().lower()
    if exp_level and exp_level in EXPERIENCE_MAP:
        params["f_E"] = EXPERIENCE_MAP[exp_level]

    remote_val = row.get("remote", "").strip().lower()
    if remote_val == "any":
        # No f_WT filter → LinkedIn returns remote, hybrid, and on-site results
        pass
    elif remote_val in ("true", "yes", "1", "remote"):
        params["f_WT"] = "2"  # remote only
    elif remote_val == "hybrid":
        params["f_WT"] = "3"  # hybrid only
    elif remote_val in ("false", "no", "0", "onsite") and location:
        params["f_WT"] = "1"  # on-site only

    return f"{_LINKEDIN_GUEST_API}?{urlencode(params)}"


# ── Title / experience helpers ─────────────────────────────────────────────────

def _has_excluded_keyword(title: str) -> bool:
    """Return True if the job title contains a seniority/exclusion keyword."""
    title_lower = title.lower()
    # Use word-boundary matching to avoid false positives (e.g. "leadership")
    for kw in EXCLUDED_TITLE_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", title_lower):
            return True
    return False


def _fetch_description(job_url: str) -> str:
    """Fetch the plain-text job description from an individual LinkedIn job page.

    Returns an empty string on any error.
    """
    try:
        resp = requests.get(job_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # LinkedIn renders description inside one of these containers
        desc_tag = soup.find(
            "div", class_="show-more-less-html__markup"
        ) or soup.find("div", class_="description__text")
        if desc_tag:
            return desc_tag.get_text(" ", strip=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not fetch description for {job_url!r}: {exc}", file=sys.stderr)
    return ""


def _description_allows_experience_range(job_url: str) -> bool:
    """Return True if the job description mentions 3–5 years as acceptable."""
    description = _fetch_description(job_url)
    return bool(_EXPERIENCE_RANGE_RE.search(description))


# ── Scraper ────────────────────────────────────────────────────────────────────

def fetch_jobs(url: str, max_jobs: int = MAX_JOBS_PER_SEARCH) -> list[dict[str, str]]:
    """Fetch job listings from a LinkedIn guest-API URL.

    Returns a list of dicts with keys: title, company, location, url.

    Post-processing rules:
    - Jobs whose titles contain 'Senior', 'Staff', 'Principal', 'Lead', or
      'Manager' are excluded, unless the individual job description explicitly
      mentions that 3–5 years of experience is acceptable.

    Returns an empty list on network / parsing errors.
    """
    raw_jobs: list[dict[str, str]] = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[WARN] Request failed for {url!r}: {exc}", file=sys.stderr)
        return raw_jobs

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.find_all("div", class_="base-card")[:max_jobs]

    for card in cards:
        try:
            title_tag = card.find("h3", class_="base-search-card__title")
            company_tag = card.find("h4", class_="base-search-card__subtitle")
            location_tag = card.find("span", class_="job-search-card__location")
            link_tag = card.find("a", class_="base-card__full-link")

            title = title_tag.get_text(strip=True) if title_tag else "N/A"
            company = company_tag.get_text(strip=True) if company_tag else "N/A"
            location = location_tag.get_text(strip=True) if location_tag else "N/A"
            link = link_tag["href"].split("?")[0] if link_tag else ""

            if link:
                raw_jobs.append(
                    {"title": title, "company": company, "location": location, "url": link}
                )
        except (AttributeError, KeyError, TypeError) as exc:
            print(f"[WARN] Could not parse job card: {exc}", file=sys.stderr)

    # ── Apply seniority filter ─────────────────────────────────────────────────
    jobs: list[dict[str, str]] = []
    for job in raw_jobs:
        if not _has_excluded_keyword(job["title"]):
            jobs.append(job)
        else:
            # Give the job a second chance: check whether the description
            # explicitly states 3–5 years is acceptable.
            time.sleep(REQUEST_DELAY_SECONDS)
            if _description_allows_experience_range(job["url"]):
                print(
                    f"[INFO]   Keeping '{job['title']}' – description allows 3–5 yrs",
                    file=sys.stderr,
                )
                jobs.append(job)
            else:
                print(
                    f"[INFO]   Excluded '{job['title']}' (seniority keyword; "
                    "no 3–5 yr override found)",
                    file=sys.stderr,
                )

    return jobs


# ── Email builder ──────────────────────────────────────────────────────────────

def build_email_body(
    all_jobs: dict[str, list[dict[str, str]]],
    resume_snippet: str,
) -> tuple[str, str]:
    """Return (plain_text, html) email bodies."""
    total = sum(len(v) for v in all_jobs.values())

    # ---- plain text ----
    lines = [
        "LinkedIn Job Digest",
        "=" * 50,
        f"Total jobs found: {total}",
        "",
    ]

    if total == 0:
        lines += [
            "No jobs were found for any of your searches today.",
            "This may be due to LinkedIn rate-limiting or a genuine lack of",
            "new postings matching your criteria. Try again tomorrow.",
            "",
        ]
    else:
        for label, jobs in all_jobs.items():
            lines.append(f"Search: {label}")
            lines.append("-" * 40)
            if jobs:
                for j in jobs:
                    lines.append(f"  {j['title']} @ {j['company']}  ({j['location']})")
                    lines.append(f"  {j['url']}")
                    lines.append("")
            else:
                lines.append("  No results found.\n")
            lines.append("")

    lines += [
        "=" * 50,
        "Resume on file (first 300 characters):",
        resume_snippet[:300].replace("\n", " ") + " …",
    ]
    plain = "\n".join(lines)

    # ---- HTML ----
    if total == 0:
        body_html = (
            "<p style='color:#c00;font-size:1.1em'>"
            "⚠️ No jobs were found for any of your searches today."
            "</p>"
            "<p>This may be due to LinkedIn rate-limiting or a genuine lack of "
            "new postings matching your criteria. Try again tomorrow.</p>"
        )
    else:
        html_rows = []
        for label, jobs in all_jobs.items():
            html_rows.append(f"<h3 style='color:#0a66c2'>🔍 {label}</h3>")
            if jobs:
                html_rows.append("<ul>")
                for j in jobs:
                    html_rows.append(
                        f'<li style="margin-bottom:6px">'
                        f'<a href="{j["url"]}" style="font-weight:bold">{j["title"]}</a>'
                        f" &mdash; {j['company']}, <em>{j['location']}</em>"
                        f"</li>"
                    )
                html_rows.append("</ul>")
            else:
                html_rows.append("<p><em>No results found.</em></p>")
        body_html = "".join(html_rows)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:16px">
  <h2 style="color:#0a66c2">LinkedIn Job Digest</h2>
  <p style="color:#555">Total jobs found: <strong>{total}</strong></p>
  {body_html}
  <hr>
  <p style="font-size:12px;color:#888">
    Generated by the LinkedIn Job Fetcher GitHub Action.<br>
    Resume on file (snippet): {resume_snippet[:200].replace('\n', ' ')} &hellip;
  </p>
</body>
</html>"""

    return plain, html


# ── Email sender ───────────────────────────────────────────────────────────────

def send_email(subject: str, plain: str, html: str) -> None:
    """Send an email via SMTP with STARTTLS.

    Reads configuration from environment variables:
      SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS,
      EMAIL_FROM (defaults to SMTP_USER when SMTP_USER is an email), EMAIL_TO
    """
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    email_from = os.environ.get("EMAIL_FROM")
    if not email_from:
        if "@" in smtp_user:
            email_from = smtp_user
        else:
            raise ValueError(
                "EMAIL_FROM is required when SMTP_USER is not an email address "
                "(for SendGrid, set EMAIL_FROM to a verified Sender Identity)."
            )
    email_to = os.environ["EMAIL_TO"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    def format_smtp_response(message: object) -> str:
        if message is None:
            return ""
        if isinstance(message, bytes):
            return message.decode("utf-8", "replace").strip()
        return str(message).strip()

    print(f"[INFO] SMTP server: {smtp_host}:{smtp_port}")
    print(f"[INFO] SMTP envelope from: {email_from}")
    print(f"[INFO] SMTP envelope to: {email_to}")

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        ehlo_code, ehlo_msg = server.ehlo()
        print(f"[INFO] SMTP EHLO: {ehlo_code} {format_smtp_response(ehlo_msg)}")
        starttls_code, starttls_msg = server.starttls()
        print(f"[INFO] SMTP STARTTLS: {starttls_code} {format_smtp_response(starttls_msg)}")
        ehlo_code, ehlo_msg = server.ehlo()
        print(f"[INFO] SMTP EHLO (post-TLS): {ehlo_code} {format_smtp_response(ehlo_msg)}")
        server.login(smtp_user, smtp_pass)
        payload = msg.as_string()
        print(f"[INFO] SMTP message size: {len(payload)} bytes")
        rejected = server.sendmail(email_from, [email_to], payload)
        if rejected:
            raise RuntimeError(f"SMTP rejected recipient(s): {rejected}")

    print(f"[INFO] Email sent → {email_to}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Read resume
    if not RESUME_PATH.exists():
        print(f"[ERROR] Resume not found at {RESUME_PATH}", file=sys.stderr)
        sys.exit(1)
    resume_text = RESUME_PATH.read_text(encoding="utf-8").strip()
    print(f"[INFO] Loaded resume ({len(resume_text)} chars)")

    # 2. Read search options
    if not SHEET_PATH.exists():
        print(f"[ERROR] Search sheet not found at {SHEET_PATH}", file=sys.stderr)
        sys.exit(1)

    with SHEET_PATH.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [r for r in reader if any(v.strip() for v in r.values())]

    if not rows:
        print("[ERROR] No search rows found in sheet.csv", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Loaded {len(rows)} search row(s) from sheet.csv")

    # 3. Scrape each search
    all_jobs: dict[str, list[dict[str, str]]] = {}

    for idx, row in enumerate(rows):
        keyword = row.get("keyword", "").strip() or "(no keyword)"
        location = row.get("location", "").strip() or "any location"
        label = f"{keyword} in {location}"

        url = build_search_url(row)
        print(f"[INFO] [{idx + 1}/{len(rows)}] Searching: {label}")
        print(f"[INFO]   URL: {url}")

        jobs = fetch_jobs(url)
        all_jobs[label] = jobs
        print(f"[INFO]   Found {len(jobs)} job(s)")

        if idx < len(rows) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    # 4. Build email content
    total_jobs = sum(len(v) for v in all_jobs.values())
    if total_jobs == 0:
        subject = "LinkedIn Job Digest – No jobs found today"
    else:
        subject = f"LinkedIn Job Digest – {total_jobs} job(s) found"
    plain, html = build_email_body(all_jobs, resume_text)

    # 5. Print summary
    print("\n" + plain)

    # 6. Send email (if SMTP is configured)
    required_env = ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "EMAIL_TO")
    missing = [k for k in required_env if not os.environ.get(k)]
    smtp_user = os.environ.get("SMTP_USER", "")
    email_from = os.environ.get("EMAIL_FROM", "")
    if smtp_user and "@" not in smtp_user and not email_from:
        missing.append("EMAIL_FROM")

    if not missing:
        try:
            send_email(subject, plain, html)
        except Exception as exc:
            print(f"[ERROR] Failed to send email: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        # DRY_RUN must be explicitly set to a truthy value ("1", "true", "yes").
        # Any other value – including the string "false" – is treated as disabled.
        dry_run = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
        if dry_run:
            print(
                f"[INFO] DRY_RUN mode: SMTP not configured "
                f"(missing: {', '.join(missing)}) – skipping email send."
            )
        else:
            print(
                f"[ERROR] SMTP not configured – missing secrets: {', '.join(missing)}.\n"
                "Add these as GitHub Actions secrets:\n"
                "  Settings → Secrets and variables → Actions → New repository secret\n"
                "Required: SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_TO\n"
                "EMAIL_FROM is required when SMTP_USER is not an email address.\n"
                "To skip email sending intentionally, set the DRY_RUN=1 environment variable.",
                file=sys.stderr,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
