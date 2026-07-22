# Cultural Hegemony Annotation Portal

A Flask-based web application for studying **cultural hegemony in LLM outputs**.  
Annotators submit prompts, view responses from multiple LLMs, and tag each response for the presence and impact of cultural hegemony across six axes. The portal supports multi-state annotation campaigns, expert review workflows, and inter-annotator agreement (IAA) reviews.

---

## Table of Contents

- [What This Project Does](#what-this-project-does)
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Set Up Credentials](#2-set-up-credentials)
  - [3. Configure the Application](#3-configure-the-application)
  - [4. Run the Application](#4-run-the-application)
- [Adapting for Your Own Study](#adapting-for-your-own-study)
  - [Change Geographical Region / State Map](#change-geographical-region--state-map)
  - [Change LLM Models](#change-llm-models)
  - [Change Hegemony Axes](#change-hegemony-axes)
  - [Change Onboarded Annotators](#change-onboarded-annotators)
  - [Change Inter-Annotator Review Config](#change-inter-annotator-review-config)
  - [Change Prompt Similarity Thresholds](#change-prompt-similarity-thresholds)
  - [Change Styling / Templates](#change-styling--templates)
- [User Roles & Workflow](#user-roles--workflow)
- [Data Storage](#data-storage)
- [API Endpoints](#api-endpoints)
- [Common Tasks](#common-tasks)
  - [Admin Access](#admin-access)
  - [Export Data](#export-data)
  - [Delete Records](#delete-records)
  - [Inter-Annotator Review via SQLite](#inter-annotator-review-via-sqlite)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## What This Project Does

This portal enables a structured annotation workflow:

1. **Annotators** write two prompt variants: a *base* (neutral) prompt and an *identity-primed* prompt (e.g. "as a person from community X").
2. The portal calls **4 LLMs** to generate responses for each prompt variant (8 total outputs per annotation).
3. Annotators **tag each output** for the presence of cultural hegemony across 6 axes (social, economic, religious, gender, linguistic, colorism) and write a free-text **impact description**.
4. Annotators provide a **ground truth** assessment and optional **references**.
5. An **admin/expert reviewer** validates annotations, marking them as accepted, rejected, or needing restructuring.
6. **Peer reviewers** (inter-annotator agreement) score each other's annotations on prompt quality, model output quality, and overall assessment.

All data is synced to **Google Sheets** (for collaborative access) and a **local JSONL file** (as fallback).

---

## Architecture Overview

```
annotation_app/
├── app.py               → Flask application (~1850 lines), all routes & business logic
├── auth.py              → Blueprint: signup (access-code-gated), login, logout
├── config.py            → Constants: state/region map, LLM model config, annotator lists, hegemony axes
├── storage.py           → JSONL read/write, record builder, Google-Sheets flattening
├── sheets.py            → Google Sheets integration (primary + backup worksheets)
├── llm.py               → LLM API calls (OpenRouter for Gemini / DeepSeek / GPT-OSS, OpenAI for GPT)
├── prompt_similarity.py → Embedding-based prompt deduplication (OpenRouter embeddings)
├── notes_store.py       → Per-user SQLite database for saved prompt notes
├── iaa_store.py         → SQLite database for inter-annotator agreement reviews
├── draft_store.py       → JSON-file draft persistence per session
├── requirements.txt     → Python package dependencies
├── accounts/            → (gitignored) Contains credential JSON files
├── static/
│   ├── annotations.jsonl         → Local JSONL data store
│   └── Inter-Annotator-Review-Guidelines.pdf
├── templates/           → 13 Jinja2 HTML templates
├── data/drafts/         → Per-session draft JSON files (gitignored)
└── annotators.json      → Registered annotator credentials (gitignored)
```

---

## Prerequisites

- **Python 3.10+**
- A **Google Cloud service account** with the Google Sheets & Google Drive APIs enabled
- API keys for at least one of the supported LLM providers:
  - **OpenAI** (for GPT-5.2)
  - **OpenRouter** (for Gemini 3 Flash, DeepSeek V3.2, GPT-OSS-120B)
- (Optional) Your own LLM API keys for other models

---

## Setup

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd <your-project-directory>
```

### 2. Set Up Credentials

Create the following files inside `annotation_app/accounts/`. This directory is gitignored, so your secrets stay local.

#### `accounts/google_creds.json`

A Google Cloud service-account JSON key with access to Google Sheets & Google Drive APIs.  
[Create one here](https://console.cloud.google.com/apis/credentials).

```json
{
  "type": "service_account",
  "project_id": "your-project",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "...@your-project.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  ...
}
```

#### `accounts/apikeys.json`

```json
{
  "FLASK_SECRET_KEY": "generate-a-random-secret-key",
  "ANNOTATOR_PASSWORD_HASH": "bcrypt-hash-of-access-code",
  "ADMIN_USERNAME": "admin",
  "ADMIN_PASSWORD_HASH": "bcrypt-hash-of-admin-password",
  "GPT_API_KEY": "sk-proj-...",
  "OPENAI_API_KEY": "sk-or-...",
  "GEMINI_API_KEY": "AIza...",
  "DEEPSEEK_API_KEY": "sk-..."
}
```

| Key | Purpose |
|---|---|
| `FLASK_SECRET_KEY` | Flask session signing — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ANNOTATOR_PASSWORD_HASH` | Werkzeug hash of the signup access code — generate with `python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-code'))"` |
| `ADMIN_PASSWORD_HASH` | Werkzeug hash of the admin login password |
| `GPT_API_KEY` | OpenAI API key (for GPT-5.2 calls) |
| `OPENAI_API_KEY` | OpenRouter API key (for Gemini / DeepSeek / GPT-OSS calls via OpenRouter) |
| `GEMINI_API_KEY` | (Currently unused — the code routes Gemini through OpenRouter) |
| `DEEPSEEK_API_KEY` | (Currently unused — the code routes DeepSeek through OpenRouter) |

### 3. Configure the Application

Open **`config.py`** and adjust these key sections:

#### Region → State Map

```python
REGION_STATE_MAP = {
    "East": ["West Bengal", "Arunachal Pradesh", ...],
    "North": ["Uttar Pradesh", "Bihar", ...],
    "Central": ["Madhya Pradesh", "Chhattisgarh"],
    "South": ["Andhra Pradesh", ...],
    "West": ["Maharashtra", ...],
}
```

#### Google Sheet

```python
SHEET_NAME = "json-to-sheets-hegemony"   # Change to your Google Sheet name
```

#### Hegemony Axes

```python
HEGEMONY_AXES = [
    "social",
    "economic",
    "religious",
    "gender",
    "linguistic",
    "colorism",
]
```

#### Headers

If you change the axes or models, update the `HEADERS` list in `config.py` to match your new column layout. Each model variant (8 total: 4 models × base + identity) generates columns for: text, hallucination, and for each axis: `{axis}` and `{axis}_impact`.

#### Onboarded Annotators

```python
ONBOARDED_ANNOTATOR_USERNAMES = [
    "admin",
    "Arnab6203",
    ...
]
ONBOARDED_ANNOTATOR_USERNAMES_STATES = {
    "admin": "Uttar Pradesh",
    "Arnab6203": "West Bengal",
    ...
}
```

### 4. Run the Application

```bash
cd annotation_app
pip install -r requirements.txt
python app.py
```

The app starts at `http://127.0.0.1:5000`.

**First-time setup:**
1. Visit `/access-code` and enter the code you hashed as `ANNOTATOR_PASSWORD_HASH`.
2. Register your first annotator account.
3. Log in via `/login` as `admin` with your admin password.

---

## Adapting for Your Own Study

This section tells you **exactly what to change** if you're forking this project for a different geography, set of models, or research question.

### Change Geographical Region / State Map

The entire region/state hierarchy lives in **`config.py`**:

```python
REGION_STATE_MAP = {
    "North": ["State A", "State B"],
    "South": ["State C", "State D"],
    ...
}
```

The **templates** also reference this map — if your states differ, the signup dropdown and admin filters will auto-populate from this dict. No template changes needed.

If you change the study location, update the **IAA config** in `app.py`:

```python
STATE_REVIEW_ASSIGNMENT_CONFIGS = {
    "your state": {
        "seed": "iaa-my-state-v1",
        "annotators": ["Annotator1", "Annotator2"],
        "per_annotator_quota": {"Annotator1": 10, "Annotator2": 10},
    },
}
```

### Change LLM Models

Edit **`config.py`** — the `HEADERS` list has 8 model-variant blocks (gemini_base, gemini_identity, gpt_base, gpt_identity, llama_base, llama_identity, deepseek_base, deepseek_identity).

To change which models are called, edit **`llm.py`**:

- Each `generate_*_output(prompt)` function makes an API call.
- Replace the model string, API endpoint, and authentication.
- Currently all models except GPT go through **OpenRouter**. GPT goes through **OpenAI** directly.
- To add/remove a model, you must also update:
  - `config.py` → `HEADERS` list
  - `storage.py` → `build_record()` and `json_to_row()` functions
  - `sheets.py` → `load_records_from_sheet()` and `_row_map_to_record()`
  - `app.py` → the `/generate/<model>` routes and `MODEL_REVIEW_FIELD_PREFIXES`
  - `templates/annotate.html` → the model output sections (search for the model name)

**Known mislabel:** The code calls the model "llama" but it actually queries `openai/gpt-oss-120b` via OpenRouter. Update the label everywhere if this matters for your study.

### Change Hegemony Axes

Edit the `HEGEMONY_AXES` list in **`config.py`**. This automatically propagates to:
- The annotation form (it iterates over axes in `templates/annotate.html`)
- The record builder (`storage.py`)
- The sheet flattening/loading (`storage.py`, `sheets.py`)
- The admin review templates
- The CSV export

No code changes beyond `config.py` are needed to add/remove axes.

### Change Onboarded Annotators

Edit in **`config.py`**:
- `ONBOARDED_ANNOTATOR_USERNAMES` — list of usernames
- `ONBOARDED_ANNOTATOR_USERNAMES_STATES` — mapping of username → state

These control:
- Which users see the "Timesheet" link
- Which annotations are eligible for IAA review
- Which users can access the IAA review module

### Change Inter-Annotator Review Config

Edit `STATE_REVIEW_ASSIGNMENT_CONFIGS` in **`app.py`**:

```python
STATE_REVIEW_ASSIGNMENT_CONFIGS = {
    "state name": {
        "seed": "unique-seed-string",            # Used for deterministic random sampling
        "annotators": ["User1", "User2"],         # Annotators in this state
        "per_annotator_quota": {"User1": 10, ...}, # How many of each annotator's records to review
    },
}
```

Each annotator reviews the other annotator(s)' records from the same state. With 2 annotators, each reviews the other's work. With 3+, records are split evenly.

The temporary access overrides in `app.py` (`TEMP_INTER_ANNOTATOR_REVIEW_ACCESS` and `TEMP_INTER_ANNOTATOR_REVIEW_USER_ALIAS`) let you grant IAA access to test users or alias one user to another's assignment.

### Change Prompt Similarity Thresholds

Edit in **`prompt_similarity.py`**:

```python
PROMPT_SIM_THRESHOLD = 0.65         # Minimum similarity to show a match
PROMPT_SIM_NEAR_DUP_THRESHOLD = 0.9 # Above this, flag as near-duplicate
PROMPT_SIM_MIN_CHARS = 40           # Minimum prompt length to check
PROMPT_SIM_TOP_K = 5                # Max matches to return
```

### Change Styling / Templates

All UI is in **`templates/`** (Jinja2 HTML). A shared layout is in `templates/layout/base.html`. Styling uses inline CSS in `<style>` blocks within each template — there is no external CSS file.

Key templates:
| Template | Purpose |
|---|---|
| `annotate.html` | Main annotation form (415 lines) |
| `review.html` | Review & expert review page (438 lines) |
| `admin.html` | Admin record browser (966 lines) |
| `review_annotation.html` | IAA review scoring form |
| `review_list.html` | IAA review queue |
| `signup.html` / `login.html` / `access_code.html` | Auth pages |
| `examples.html` | Public examples page |

---

## User Roles & Workflow

### Roles

| Role | Privileges |
|---|---|
| **Annotator** | Create/edit own annotations, save notes, perform IAA peer reviews for their state |
| **Admin** | View/edit all annotations, validate/accept/reject, export CSV, view IAA stats |

### Full Workflow

```
   ┌─────────────────────┐
   │ Annotator registers  │  (access-code gated, selects state)
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │  Creates annotation  │  Enters base + identity prompt
   │  → 4 LLMs generate   │  Clicks "Generate" per model
   │  → Tags hegemony     │  yes/no per axis + impact text
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │  Confirm & Save      │  → JSONL + Google Sheets
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │  Admin Expert Review  │  Accept / Needs restructuring / Reject
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │  IAA Peer Review     │  Same-state annotators rate each other's
   │  (if approved)       │  annotations on 1–5 Likert scales
   └─────────────────────┘
```

---

## Data Storage

| Layer | Technology | Location | Purpose |
|---|---|---|---|
| **Primary** | Google Sheets | `testing` + `testing2` worksheets | Collaborative access & backup |
| **Local** | JSONL | `static/annotations.jsonl` | Local fallback / offline resilience |
| **IAA Reviews** | SQLite | `data/iaa_reviews.db` | Structured peer-review data |
| **Notes** | SQLite (per user) | `data/drafts/{user}_notes.db` | Annotator's saved prompts |
| **Drafts** | JSON files | `data/drafts/{uuid}.json` | In-progress annotation drafts |
| **Prompt Embeddings** | JSON | `data/prompt_embeddings.json` | Similarity index for dedup |

**All `data/` content and `annotators.json` are gitignored.**

---

## API Endpoints

### Core Annotation

| Method | Route | Description |
|---|---|---|
| GET/POST | `/` | Annotation form + draft loading |
| POST | `/save-annotation-draft` | AJAX save annotation to JSONL + Sheets |
| POST | `/confirm` | Finalize annotation from draft |
| GET | `/freshannotate` | Clear draft and start fresh |
| GET/POST | `/load-annotation` | Load & edit existing annotations |
| GET | `/examples` | Public sample annotations |

### LLM Generation

| Method | Route | Model |
|---|---|---|
| POST | `/generate/gemini` | Gemini 3 Flash (via OpenRouter) |
| POST | `/generate/gpt` | GPT-5.2 (via OpenAI) |
| POST | `/generate/llama` | GPT-OSS-120B (via OpenRouter) |
| POST | `/generate/deepseek` | DeepSeek V3.2 (via OpenRouter) |

### Admin

| Method | Route | Description |
|---|---|---|
| GET | `/admin` | Filterable, sortable record table |
| GET | `/admin/dashboard-stats` | JSON dashboard statistics |
| GET | `/admin/inter-annotator-review-stats` | JSON IAA completion stats |
| GET/POST | `/admin/load/<id>` | Admin expert review panel |
| POST | `/admin/delete` | Bulk delete records |
| GET | `/admin/annotations.csv` | Full CSV export |
| GET | `/admin/iaa-reviews.csv` | IAA reviews CSV export |
| GET | `/records` | Full records list (admin only) |

### Inter-Annotator Review

| Method | Route | Description |
|---|---|---|
| GET | `/promptreview` | IAA review queue |
| GET | `/review/<annotation_id>` | IAA review form |
| POST | `/submit_review` | Submit IAA review |
| GET | `/inter-annotator-review-guidelines.pdf` | Download guidelines PDF |

### Notes & Similarity

| Method | Route | Description |
|---|---|---|
| GET/POST | `/notes` | Save/delete/display prompt notes |
| POST | `/check-prompt-similarity` | Check prompt against existing embeddings |

---

## Common Tasks

### Admin Access

1. Log in at `/login` with your admin username and password (set in `accounts/apikeys.json`).
2. Default credentials: `admin` / `icml@2026` (change in production).

### Export Data

- **Filtered CSV:** Go to `/admin`, apply filters, click "Download CSV".
- **Full annotations CSV:** `/admin/annotations.csv`
- **IAA reviews CSV:** `/admin/iaa-reviews.csv`

### Delete Records

1. Go to `/admin`.
2. Find records and check the delete checkboxes.
3. Click "Delete Selected". This removes from both JSONL and Google Sheets.

### Inter-Annotator Review via SQLite

```bash
sqlite3 annotation_app/data/iaa_reviews.db
SELECT * FROM iaa_reviews WHERE reviewer_name = 'someuser';
DELETE FROM iaa_reviews WHERE reviewer_name = 'someuser';
```

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `Google Sheets not found` | `SHEET_NAME` in config.py doesn't match your sheet | Create the sheet or update the name |
| `403 Forbidden` on admin routes | Not logged in as admin | Check `ADMIN_USERNAME` in apikeys.json |
| LLM calls fail | API key expired or missing from apikeys.json | Check the key; verify quota |
| "Llama" model shows unexpected results | It's actually GPT-OSS-120B, not Llama | Update the label in `config.py` HEADERS |
| IAA review says "not eligible" | User's state doesn't match the annotation's state | Check `ONBOARDED_ANNOTATOR_USERNAMES_STATES` |
| Access-code page loops | Password hash in apikeys.json is wrong | Regenerate with `generate_password_hash()` |
| Annotation not saving to Sheets | Google service account lacks edit access | Share the sheet with the service account email |

---

## License

This project is provided for academic and research use.  
If you use or adapt this tool for a publication, please cite the original study.

---

## Contact

For questions or collaboration, refer to the original research team.
