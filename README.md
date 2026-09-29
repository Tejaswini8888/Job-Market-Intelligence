# Job Market Intelligence & Skill Analytics Platform

A portfolio-grade, end-to-end data engineering and machine learning project that
stores, analyses, and serves job-market data so that job seekers, recruiters,
and analysts can make evidence-based decisions about skills, roles, and market
trends.

**Repository:** <https://github.com/Tejaswini8888/Job-Market-Intelligence>

> ### ⚠️ Data disclaimer — read this first
>
> Every company, job posting, salary figure, and date currently in the database
> is **synthetic data invented for local development and testing**. No website
> was scraped, no job API was called, and no posting text was copied from any
> source. Company names are fictional.
>
> The dataset is engineered to be *analytically realistic* — so the SQL, the
> API, and the dashboard have meaningful patterns to work with — but **no figure
> derived from it is a real labour-market measurement.** Do not present any
> number in this project as a market finding.

---

## Table of Contents

1. [Project Status](#1-project-status)
2. [Problem Statement](#2-problem-statement)
3. [Project Objective](#3-project-objective)
4. [Architecture & Project Flow](#4-architecture--project-flow)
5. [Technology Stack](#5-technology-stack)
6. [Completed Components](#6-completed-components)
7. [Getting Started](#7-getting-started)
8. [REST API Reference](#8-rest-api-reference)
9. [Automated Testing](#9-automated-testing)
10. [Continuous Integration](#10-continuous-integration-github-actions)
11. [Security](#11-security)
12. [Roadmap](#12-roadmap)
13. [Author](#13-author)

---

## 1. Project Status

| Component | Status | Where it lives |
| --- | :---: | --- |
| PostgreSQL database | ✅ | `database/schema.sql`, `database/seed.sql` |
| SQL analytics | ✅ | `database/queries/*.sql` |
| Python data layer | ✅ | `src/data/` |
| Streamlit dashboard | ✅ | `dashboard/` |
| Skill Gap Analyzer | ✅ | `dashboard/components.py` |
| ML Recommendation Engine | ✅ | `ml/recommender.py` |
| FastAPI REST API | ✅ | `backend/` |
| Docker | ✅ | `docker-compose.yml`, `backend/Dockerfile`, `dashboard/Dockerfile` |
| Automated tests | ✅ | `tests/` — **215 passing** |
| GitHub Actions CI | ✅ | `.github/workflows/ci.yml` |
| GitHub repository | ✅ | <https://github.com/Tejaswini8888/Job-Market-Intelligence> |
| AWS deployment | ⏳ Not started | planned — see [Roadmap](#12-roadmap) |
| Monitoring (Prometheus / Grafana) | ⏳ Not started | planned — see [Roadmap](#12-roadmap) |

**Verified end-to-end:** the database, the API, the dashboard, and the container
stack are running and consistent with each other. `GET /health` returns
`{"status": "ok", "database": "up", ...}` and reports the same row counts the
SQL layer returns, so a dashboard number and an API number can never disagree.

---

## 2. Problem Statement

The job market changes faster than career advice does. Students and early-career
professionals repeatedly make decisions based on outdated guides, anecdotal
advice, or intuition. At the same time:

- Job postings are scattered across many platforms and are difficult to analyse
  at scale.
- "In-demand skills" are usually described vaguely ("AI, cloud, data") instead of
  being measured with real posting data.
- Salaries, experience requirements, and tool popularity vary significantly by
  role, seniority, location, and time period, but this variation is invisible to
  most people.
- Recruiters and career coaches lack a data-driven way to see which skills are
  trending, which roles are growing, and which combinations of skills are most
  valuable together.

There is no beginner-friendly, reproducible platform that turns raw job postings
into clear, quantified, and queryable insights.

## 3. Project Objective

To build a complete, reproducible, and well-documented platform that:

1. **Collects** job posting data from one or more public / Kaggle-style sources.
2. **Cleans and normalises** the raw data into a consistent, analysable format.
3. **Stores** the data in a relational PostgreSQL database with a properly
   designed schema.
4. **Analyses** the market to answer questions such as:
   - What are the most in-demand skills right now?
   - How does the top-skills ranking change over time?
   - Which skills co-occur most often (skill combinations)?
   - What salary ranges and experience requirements are typical per role?
   - Which roles are most saturated or most promising?
5. **Models** the data with machine learning to produce reproducible predictions
   such as salary prediction or skill-demand forecasting.
6. **Serves** the results through a public REST API and an interactive dashboard.
7. **Operates** reliably using containerisation, automated tests, CI/CD, cloud
   deployment, and monitoring.

The goal is not only the final product, but a repository that demonstrates
industry-standard software engineering practice, clear documentation, and
responsible, reproducible analysis.

---

## 4. Architecture & Project Flow

A single PostgreSQL database is the one source of truth. Everything else reads
from it, so the SQL analytics, the dashboard, the ML engine, and the API can
never disagree with each other.

```text
                         ┌──────────────────────────────────────┐
                         │  PostgreSQL 18                       │
                         │  database: job_market_intelligence   │
                         │                                      │
                         │  companies ──< jobs                 │
                         │  skills ─────< job_skills >── jobs   │
                         │  (11 indexes)                        │
                         └──────────────┬───────────────────────┘
                                        │  psycopg 3, parameterised SQL
                                        ▼
                         ┌──────────────────────────────────────┐
                         │  Python data layer — src/data/       │
                         │  database.py  connection + .env      │
                         │  queries.py    16 reusable functions │
                         │                → pandas DataFrames   │
                         └──────────────┬───────────────────────┘
                          ┌─────────────┼─────────────┐
                          ▼             ▼             ▼
        ┌─────────────────────┐ ┌──────────────┐ ┌────────────────────┐
        │ Streamlit dashboard │ │ FastAPI API  │ │ ML engine          │
        │  8 interactive tabs │ │  10 endpoints│ │ ml/recommender.py  │
        │  + Skill Gap        │ │  /docs UI    │ │  TF-IDF + cosine   │
        └──────────┬──────────┘ └──────┬───────┘ └─────────┬──────────┘
                   │                   │                   │
                   └───────────────────┴───────────────────┘
                                       │
                          both reuse the same functions
```

**Data flow, end to end**

1. **Store** — `database/schema.sql` creates the four tables and 11 indexes;
   `database/seed.sql` loads the synthetic development dataset.
2. **Query** — `database/queries/01…05_*.sql` answer the market questions in
   plain SQL, for analysts who prefer the database.
3. **Read** — `src/data/queries.py` wraps the same questions as 16 reusable,
   parameterised functions that return pandas DataFrames. Nothing else in the
   project opens a database connection.
4. **Serve** — the dashboard and the API both call those functions, so identical
   inputs always produce identical numbers in both places.
5. **Advise** — the Skill Gap Analyzer (transparent rules) and the role
   recommender (TF-IDF + cosine similarity) turn a user's own skill list into
   actionable output.

### Repository structure

The structure below is the **actual** layout of this repository, not an aspirational
one. Directories that exist only as placeholders for future stages (`data/`,
`notebooks/`, `scripts/`, `docs/`, `infra/`) are noted at the end.

```text
Job-Market-Intelligence/
├── README.md
├── docker-compose.yml              # the three-service stack
├── requirements.txt                # data layer + dashboard dependencies
├── pytest.ini                      # pytest configuration
├── .env.example                    # tracked TEMPLATE — placeholders only
├── .gitignore
├── .dockerignore
│
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions: tests + Docker config check
│
├── database/
│   ├── schema.sql                  # 4 tables, 11 indexes
│   ├── seed.sql                    # synthetic development dataset
│   └── queries/
│       ├── 01_basic_analysis.sql
│       ├── 02_salary_analysis.sql
│       ├── 03_skill_demand.sql
│       ├── 04_role_analysis.sql
│       └── 05_advanced_analysis.sql
│
├── src/
│   └── data/
│       ├── database.py             # the only place that connects to PostgreSQL
│       └── queries.py              # 16 reusable, parameterised query functions
│
├── ml/
│   ├── preprocessing.py            # skill normalisation, role aggregation
│   └── recommender.py              # TF-IDF + cosine similarity recommender
│
├── backend/                        # FastAPI service
│   ├── app/
│   │   ├── main.py                 # 10 endpoints
│   │   ├── schemas.py              # Pydantic request/response models
│   │   └── services.py             # thin layer over the data layer + ML
│   ├── Dockerfile
│   └── requirements.txt
│
├── dashboard/                      # Streamlit app
│   ├── app.py                      # 8 tabs, sidebar filters
│   ├── components.py               # charts, KPIs, Skill Gap Analyzer
│   ├── styles.py                   # custom CSS
│   └── Dockerfile
│
├── tests/                          # 215 tests
│   ├── test_database.py
│   ├── test_api.py
│   ├── test_dashboard.py
│   ├── test_recommender.py
│   └── test_skill_gap.py
│
└── .streamlit/
    └── config.toml                 # dark theme (no secrets)
```

Not yet populated, reserved for future stages: `data/raw/`, `data/processed/`,
`notebooks/`, `scripts/`, `docs/`, `infra/`.

---

## 5. Technology Stack

| Layer | Technology | Status |
| --- | --- | :---: |
| Database | PostgreSQL 18 | ✅ in use |
| Querying / SQL | SQL (CTEs, window functions, aggregation, schema design) | ✅ in use |
| Data processing | Python 3.11, Pandas | ✅ in use |
| Machine learning | scikit-learn (TF-IDF, cosine similarity) | ✅ in use |
| API | FastAPI, Pydantic, Uvicorn | ✅ in use |
| Dashboard | Streamlit, Plotly | ✅ in use |
| Packaging / environment | pip, `requirements.txt`, `python-dotenv` | ✅ in use |
| Containerisation | Docker, Docker Compose | ✅ in use |
| Automation | GitHub Actions (tests + DB service + Docker config check) | ✅ in use |
| Version control | Git, GitHub | ✅ in use |
| Cloud / deployment | AWS (EC2, RDS, S3, optionally SageMaker / Elastic Beanstalk) | ⏳ planned |
| Monitoring | Prometheus, Grafana | ⏳ planned |

---

## 6. Completed Components

### 6.1 PostgreSQL database

Database `job_market_intelligence`, defined in `database/schema.sql`.

| Table | Purpose |
| --- | --- |
| `companies` | Employer dimension — one company, many jobs |
| `jobs` | Job posting fact table — one job, belongs to one company |
| `skills` | Skill dimension — one skill, required by many jobs |
| `job_skills` | Junction table resolving the jobs ↔ skills **many-to-many** relationship |

Design points: `NUMERIC(12,2)` for money (never floating point), `TIMESTAMPTZ`
for timestamps, identity columns for keys, an explicit `ON DELETE` action on
every foreign key, portable `UPPER_SNAKE_CASE` text + `CHECK` constraints
instead of enums (so the schema can be extended without `ALTER TYPE` locks), and
**11 indexes** covering the access patterns the analytics actually use.

**Current dataset (synthetic development data):**

| Table | Rows |
| --- | ---: |
| `companies` | 15 |
| `jobs` | 40 |
| `skills` | 32 |
| `job_skills` | 242 |

> This is a deliberately small dataset created so the schema, the queries, the
> API, and the tests all have something concrete to exercise. It is **not** real
> market data and is **not** a statistical sample of anything.

### 6.2 SQL analytics

Five query files in `database/queries/`, each written as a documented answer to a
market question:

| File | Focus |
| --- | --- |
| `database/queries/01_basic_analysis.sql` | Job listings, unique titles, company and country breakdowns |
| `database/queries/02_salary_analysis.sql` | Salary averages, ranges, and per-role comparisons |
| `database/queries/03_skill_demand.sql` | Most-demanded skills, top-N, demand by skill category |
| `database/queries/04_role_analysis.sql` | Job counts by title, industry, country, and work mode |
| `database/queries/05_advanced_analysis.sql` | Ranked skills, ranked companies, titles within industries |

SQL features used across the set, and implemented in the files themselves:

- `JOIN` — combining `jobs`, `companies`, `skills`, and `job_skills`
- `GROUP BY` / aggregate functions — `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `ROUND`
- `HAVING` — filtering aggregated groups (`database/queries/05_advanced_analysis.sql`)
- `CASE` — conditional bucketing of seniority, salary bands, and work mode
- Subqueries — derived counts and nested lookups
- CTEs (`WITH`) — multi-step readable analysis
- Window functions (`OVER`) — ranking skills and companies, and titles within
  each industry

### 6.3 Python data layer (`src/data/`)

| File | Responsibility |
| --- | --- |
| `src/data/database.py` | The **only** place in the project that opens a database connection |
| `src/data/queries.py` | 16 reusable query functions used by the dashboard, the API, and the tests |

How it works:

- **Environment-driven configuration** — connection settings come from `.env`
  (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) via
  `python-dotenv`. Real environment variables always win over the file, so CI
  and shell sessions can override settings without editing anything.
- **Parameterised queries** — values are bound through the driver's parameter
  mechanism (`%s` placeholders) and are never pasted into SQL text, which is
  what makes the code injection-safe.
- **Pandas DataFrames everywhere** — every query function returns a
  `pandas.DataFrame`, so callers work with DataFrames instead of raw rows.
- **Reusable, single-purpose functions** — `get_top_skills()`,
  `get_average_salary_by_role()`, `get_experience_distribution()`, and 13 more.
  The dashboard and the API call the *same* functions, which is why an API
  answer and a dashboard number can never disagree.
- **Safety by default** — sessions are opened read-only
  (`default_transaction_read_only=on`), and any message is passed through a
  scrubbing function so a driver error can never echo the password into a log.

### 6.4 Streamlit dashboard (`dashboard/`)

| File | Responsibility |
| --- | --- |
| `dashboard/app.py` | Page entry point, data loading, sidebar filters, tab layout |
| `dashboard/components.py` | Reusable chart, KPI, and analysis building blocks |
| `dashboard/styles.py` | Custom CSS on top of the dark Streamlit theme |

Eight interactive tabs, all filter-aware:

| Tab | What it shows |
| --- | --- |
| **Overview** | KPI cards, top roles, most-demanded skills, work-mode mix, latest postings |
| **Job Demand** | Demand by role, country, work mode, and industry, plus the monthly posting trend |
| **Skill Demand** | Top skills for the current selection next to the market-wide ranking, and a per-category breakdown |
| **Salary Analytics** | Salary by role and seniority, currency and pay-period aware |
| **Experience Analytics** | Experience-level distribution and how it shifts by role |
| **Recent Jobs** | The latest postings, filterable and sortable |
| **Skill Gap Analyzer** | How well a chosen role matches your own skill list |
| **Role Recommendations** | TF-IDF-ranked roles closest to your skill set |

Sidebar filters apply across the tabs, and every chart is a Plotly figure built
from the shared data-layer functions.

### 6.5 Skill Gap Analyzer

Implemented in `dashboard/components.py` and exposed through `POST /skill-gap`.

The scoring rule is published, not hidden:

```text
Skill Match %  =  matched required skills
                 ------------------------  x 100
                  total required skills
```

- **Transparent and rule-based** — the result is arithmetic over a set, so you
  can reproduce any number by hand. There is no model and no black box here.
- **Exact normalised matching** — a skill counts as matched only if it is equal
  after normalisation (trim, collapse internal whitespace, lowercase). This is
  the *only* matching that happens.
- **No fuzzy matching, deliberately** — `"Pythonn"` is **not** Python, and is
  reported as a *missing* skill rather than quietly counted as a match. Partial
  or approximate credit would make the percentage look more precise than the
  underlying string comparison actually is.
- **Unknown skills are reported separately** — anything you type that is not in
  the database comes back in an `unknown` list instead of being silently ignored
  or silently counted, so a low match percentage is always explainable.

The response returns the matched, missing, required, and unknown skill lists
alongside the percentage.

### 6.6 ML Role Recommendation Engine

Implemented in `ml/recommender.py`, with text preparation in
`ml/preprocessing.py`, and exposed through `POST /recommend`.

How it works:

1. **Role-level aggregation** — every job posting is turned into a document of
   its required skills, and postings are aggregated **by job role** into a
   single document per role (the union of the skills that role's postings ask
   for). Recommending at the role level is more useful than recommending a
   specific posting.
2. **TF-IDF vectorisation** — `sklearn.feature_extraction.text.TfidfVectorizer`
   turns each role document into a sparse, L2-normalised term-weight vector, so
   common boilerplate words carry less weight than distinctive skills.
3. **Cosine similarity** — `sklearn.metrics.pairwise.cosine_similarity` measures
   the angle between your skill vector and each role vector.
4. **Result reported as a Skill Similarity Score** — `similarity x 100`, rounded
   to one decimal.

> ### What this score is not
>
> The **Skill Similarity Score is a cosine similarity, not a probability.** It
> is **not** a chance of getting the job, **not** a confidence score, **not** a
> salary prediction, and **not** a hiring decision. It measures one thing only:
> how much your stated skill vocabulary overlaps the vocabulary that a role's
> postings ask for. Nothing here is trained on hiring outcomes, because no such
> outcome data exists in this project.

Each result also returns matched, missing, and required skills, so the ranking
is explainable rather than a bare list of scores. The current dataset is
**small and synthetic**, so the rankings are a demonstration of the method, not
a validated career tool.

### 6.7 FastAPI REST API (`backend/`)

A thin, documented layer over the existing data layer, Skill Gap Analyzer, and
recommender — see [the endpoint table](#8-rest-api-reference). Interactive docs
are served at `/docs` (Swagger UI) and `/redoc`.

### 6.8 Docker

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | Defines the three-service stack on a private network |
| `backend/Dockerfile` | Image for the FastAPI service |
| `dashboard/Dockerfile` | Image for the Streamlit service |
| `.dockerignore` | Keeps `.env`, virtualenvs, and local state out of the build context |

Three containers:

| Service | Image / build | Published port |
| --- | --- | --- |
| `postgres` | `postgres:18` | *none* — internal only, deliberately |
| `api` | `backend/Dockerfile` | `8000:8000` |
| `dashboard` | `dashboard/Dockerfile` | `8501:8501` |

The database host port is **not** published: the API and dashboard reach it over
the private compose network as `postgres:5432`, and no second PostgreSQL is
exposed to the host. The API container only starts once PostgreSQL reports
healthy, and the dashboard only starts once the API reports healthy.

### 6.9 Automated testing

**215 tests passing** across five files in `tests/`:

| File | Covers |
| --- | --- |
| `tests/test_database.py` | Connection handling, `.env` configuration, and read-only guarantees |
| `tests/test_api.py` | Every FastAPI endpoint, status codes, and response models |
| `tests/test_dashboard.py` | Dashboard components, chart builders, and rendering helpers |
| `tests/test_recommender.py` | Preprocessing, TF-IDF, cosine similarity, and role aggregation |
| `tests/test_skill_gap.py` | The Skill Match % formula and its edge cases |

The suite runs against a real PostgreSQL database, not a mock, so the tests
exercise the same connection path used in production.

### 6.10 GitHub Actions CI

See [Continuous Integration](#10-continuous-integration-github-actions).

---

## 7. Getting Started

### 7.1 Run everything with Docker (recommended)

```bash
# 1. Create your local secrets file from the template
cp .env.example .env            # Windows PowerShell:  Copy-Item .env.example .env

# 2. Set DB_PASSWORD in .env to a password of your choice.
#    On a fresh database volume the PostgreSQL container initialises itself
#    with this value automatically.
#    If you are reusing an EXISTING volume, DB_PASSWORD must match the value
#    that volume was first created with, or PostgreSQL will reject the
#    connection.

# 3. Build and start the three containers
docker compose up -d --build

# 4. Check that all three report healthy
docker compose ps
```

Then open:

| Service | URL |
| --- | --- |
| API health | <http://localhost:8000/health> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| Dashboard | <http://localhost:8501> |

To stop the stack — this **keeps** the database volume and your data:

```bash
docker compose down
```

> `docker compose down -v` additionally **deletes** the database volume, which
> discards the data and re-runs `database/schema.sql` + `database/seed.sql` on
> the next start.
> Only use it when you deliberately want to reset the database.

### 7.2 Run locally without Docker

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate            # macOS / Linux

# 2. Install dependencies
#    backend\requirements.txt is the superset and covers everything:
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 3. Create .env from the template and set DB_PASSWORD
Copy-Item .env.example .env

# 4. Create the database and load schema + seed
#    (requires a local PostgreSQL and the psql client)
psql -U postgres -c "CREATE DATABASE job_market_intelligence;"
psql -U postgres -d job_market_intelligence -f database\schema.sql
psql -U postgres -d job_market_intelligence -f database\seed.sql

# 5a. Start the dashboard
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py

# 5b. Or start the API  (docs: /docs Swagger, /redoc ReDoc)
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

`src/data/database.py` expects `DB_HOST=localhost` for local runs; inside
Docker the compose file overrides it to `postgres` automatically.

### 7.3 Inspect the data with SQL

```bash
# Open an interactive session
psql -U postgres -d job_market_intelligence

# Then run any of the analysis files
\i database/queries/03_skill_demand.sql
```

---

## 8. REST API Reference

The same analytics and machine learning the dashboard shows are also exposed as
a REST API in `backend/`, so any client (a notebook, a job board front end, a
recruiter's tool) can query the market without a browser. It is a thin layer:
it reuses the existing data-access functions in `src/data/queries.py`, the
dashboard's own rule-based Skill Gap Analyzer, and the TF-IDF role recommender
in `ml/`, so an API answer and a dashboard number can never disagree.

```bash
# Start the API  (docs: /docs Swagger, /redoc ReDoc)
python -m uvicorn backend.app.main:app --reload
```

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Service metadata and the list of available endpoints |
| `GET` | `/health` | Liveness probe, plus a cheap PostgreSQL reachability check and row counts |
| `GET` | `/jobs` | All postings, optionally filtered by `country`, `work_mode`, `employment_type`, `industry`, `job_role` |
| `GET` | `/skills` | Every skill in the database |
| `GET` | `/companies` | Every employer, with its posting count |
| `GET` | `/analytics/skills?limit=10` | Most-requested skills market-wide |
| `GET` | `/analytics/salaries` | Average salary per role, grouped by currency and period |
| `GET` | `/analytics/roles` | How much of the market each role accounts for |
| `POST` | `/skill-gap` | `{role, skills: [...]}` → match percentage, matched/missing/required/unknown skills |
| `POST` | `/recommend` | `{skills: [...], top_n}` → ranked roles by **Skill Similarity Score** (never a probability) |

Example:

```bash
curl http://localhost:8000/analytics/skills?limit=5

curl -X POST http://localhost:8000/skill-gap \
  -H "Content-Type: application/json" \
  -d '{"role": "Data Analyst", "skills": ["SQL", "Python", "Excel"]}'

curl -X POST http://localhost:8000/recommend \
  -H "Content-Type: application/json" \
  -d '{"skills": ["SQL", "Python", "Power BI"], "top_n": 5}'
```

Security notes: credentials come only from `.env` (never hardcoded), every
database error is sanitised to a generic message, and the recommender score is
documented as a cosine similarity, not a prediction.

---

## 9. Automated Testing

```bash
# Always use the virtual environment interpreter
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: **215 passed**. The suite needs a reachable PostgreSQL database
holding the schema and seed data, because it exercises the real data layer
rather than a mock.

| File | Covers |
| --- | --- |
| `tests/test_database.py` | Connection handling, `.env` configuration, and read-only session guarantees |
| `tests/test_api.py` | Every FastAPI endpoint, status codes, and response models |
| `tests/test_dashboard.py` | Dashboard components, chart builders, and rendering helpers |
| `tests/test_recommender.py` | Preprocessing, TF-IDF, cosine similarity, and role aggregation |
| `tests/test_skill_gap.py` | The Skill Match % formula and its edge cases |

---

## 10. Continuous Integration (GitHub Actions)

The project lives in one Git repository at the repository root, and every push
and pull request is verified automatically by the workflow in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

**Repository:** <https://github.com/Tejaswini8888/Job-Market-Intelligence>

### What runs on every push / pull request

| Step | What it does |
| --- | --- |
| Trigger | Runs on `push` and `pull_request` |
| Checkout | Clones the repository (the real `.env` is git-ignored and never arrives) |
| Python 3.11 | Installs the same interpreter version used locally |
| PostgreSQL 18 service | Starts an ephemeral service container for the test run |
| Wait for ready | Blocks until PostgreSQL actually accepts connections |
| Install dependencies | `backend/requirements.txt` (the superset) |
| Initialise database | Applies the unmodified `database/schema.sql` then `database/seed.sql` |
| Verify counts | Fails fast if the seed did not load (15 / 40 / 32 / 242) |
| Run tests | `python -m pytest -q` — the same command used locally |
| Docker check | `docker compose config --quiet` validates the Compose configuration |

The CI job is deliberately conservative: it builds and tests only. It does not
build, publish, or deploy any Docker image, and it does not touch any cloud
resource.

### Running the same checks locally

```bash
# Everything the CI runs:
.\.venv\Scripts\python.exe -m pytest -q
docker compose config --quiet
```

Always use the virtual environment interpreter (`.\.venv\Scripts\python.exe` on
Windows, `.venv/bin/python` elsewhere). The global `python` may not have the
project dependencies installed.

### Secret safety in CI

The workflow contains **no real credentials**. It uses a CI-only throwaway
password for an ephemeral database container that exists only for the duration
of a single run. `docker compose config --quiet` is used rather than plain
`docker compose config` on purpose: the `--quiet` form validates the file and
its variable substitution without printing the resolved configuration, so a
password can never reach the workflow log.

---

## 11. Security

This project treats credentials as a first-class concern.

| Rule | How it is enforced |
| --- | --- |
| **Secrets live in `.env`** | `DB_PASSWORD` and every other credential are read from `.env` / environment variables at runtime. |
| **`.env` is ignored by Git** | `.env` and `.env.*` are listed in `.gitignore` (with `!.env.example` re-included), so the real file can never be committed by accident. |
| **`.env` is excluded from images** | `.dockerignore` keeps `.env`, `*.pem`, `*.key`, and `secrets/` out of every Docker build context. |
| **`.env.example` holds placeholders only** | It contains values such as `DB_PASSWORD=your_password_here` and no real secret. It is tracked on purpose, as the setup template. |
| **No hardcoded passwords in config** | `docker-compose.yml` and `.github/workflows/ci.yml` use variable substitution (`${DB_PASSWORD:?...}`) and CI-only throwaway credentials. |
| **Passwords are never logged** | The data layer scrubs every message it emits, and no code path prints, returns, or logs the connection password. |
| **SQL injection defence** | Every query is parameterised; values are bound by the driver and never concatenated into SQL text. |
| **Read-only by default** | Data-layer sessions set `default_transaction_read_only=on`, so analytics code cannot modify the database. |
| **Least-privilege surface** | The PostgreSQL container publishes no host port and is reachable only on the private compose network. |

**Never commit a real database password, API key, or access token.** If a secret
is ever exposed, treat it as compromised: rotate it immediately, then remove it
from the working tree and Git history.

---

## 12. Roadmap

### How the project was built

The project was delivered in phases, each one producing something verifiable
before the next began:

| Phase | Focus | Outcome | Status |
| --- | --- | --- | :---: |
| 1 | Project initialisation | Repository, README, `.gitignore`, `.env.example` | ✅ |
| 2 | Database | PostgreSQL schema, indexes, and seed/reference data | ✅ |
| 3 | SQL analytics | Analytical queries answering the market questions | ✅ |
| 4 | Data layer | Connection handling and reusable Pandas query functions | ✅ |
| 5 | Machine learning | TF-IDF + cosine similarity role recommender | ✅ |
| 6 | Service layer | Streamlit dashboard (8 tabs) and Skill Gap Analyzer | ✅ |
| 7 | API | FastAPI service with 10 documented endpoints | ✅ |
| 8 | DevOps | Docker, Docker Compose, 215 tests, GitHub Actions CI | ✅ |
| 9 | Cloud & monitoring | AWS deployment, Prometheus metrics, Grafana dashboards | ⏳ next |

> Phase 9 is the remaining work. Everything in the earlier phases is implemented,
> tested, and running.

### Next planned stages

The following stages are **planned and not yet started**:

| Stage | Scope |
| --- | --- |
| **AWS deployment** | Deploy the stack to the cloud with environment-based configuration (e.g. EC2, RDS, S3). |
| **Cloud-hosted application** | Run the API and dashboard as managed, publicly reachable services. |
| **Real data ingestion** | Replace the synthetic seed with a reproducible ETL pipeline that loads a real, licensed dataset. |
| **Monitoring** | Prometheus metrics collection and Grafana dashboards for service and pipeline health. |
| **Further production hardening** | Rate limiting, structured logging, authentication and authorisation, HTTPS, automated backups, and a real CI/CD promotion path that builds and publishes images. |
| **Modelling extensions** | Salary regression and skill-demand forecasting, with baseline comparisons and evaluation metrics. |

---

## 13. Author

AIML student — built as a portfolio project demonstrating data engineering,
SQL, machine learning, and production-ready software engineering practice.
