# Job Market Intelligence & Skill Analytics Platform

A portfolio-grade, end-to-end data engineering and machine learning project that
collects, cleans, analyses, and serves job-market data so that job seekers,
recruiters, and analysts can make evidence-based decisions about skills, roles,
and market trends.

---

## 1. Problem Statement

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

## 2. Project Objective

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

## 3. Planned Technology Stack

| Layer | Technology |
| --- | --- |
| Database | PostgreSQL |
| Querying / SQL | SQL (CTEs, window functions, aggregation, schema design) |
| Data processing | Python, Pandas, NumPy |
| Machine learning | scikit-learn (plus optional LightGBM), Jupyter Notebook for exploration |
| API | FastAPI, Pydantic, Uvicorn |
| Dashboard | Streamlit, Plotly |
| Packaging / environment | pip, `requirements.txt`, `pyproject.toml`, `python-dotenv` |
| Containerisation | Docker, Docker Compose |
| Automation | GitHub Actions (linting, tests, ETL + DB container run) |
| Cloud / deployment | AWS (EC2, RDS, S3, optionally SageMaker / Elastic Beanstalk) |
| Monitoring | Prometheus, Grafana |
| Version control | Git, GitHub |

## 4. Planned Project Features

### Data layer
- Data ingestion from CSV / JSON job-posting datasets (later: live job APIs).
- Reusable, idempotent ETL pipeline that writes clean data into PostgreSQL.
- Reference tables for `skills`, `roles`, `locations`, `companies`, `seniority`.
- Bridge table for many-to-many skill ↔ job relationships.

### Analytics layer
- Top-N skills overall, per role, per seniority, and per time period.
- Skill co-occurrence analysis (which skills are usually combined).
- Skill trend analysis (rising vs. falling demand over time).
- Salary statistics by role, seniority, and location.
- Data quality checks (null rates, duplicate postings, outliers).

### Machine learning layer
- Salary prediction (regression) with baseline vs. improved model comparison.
- Skill-demand forecasting (time-series style regression).
- Feature engineering from the normalised skills and metadata.
- Proper evaluation metrics and a documented, reproducible notebook.

### Service layer
- **FastAPI** REST API exposing analytics endpoints
  (e.g. `/skills/top`, `/skills/trends`, `/roles/{role}/summary`).
- **Streamlit** dashboard: KPI cards, interactive filters, charts, and
  data-quality overview.
- Interactive API documentation via Swagger UI.

### Engineering / operations
- Docker and Docker Compose for the database, API, and dashboard.
- Automated tests for the ETL, API endpoints, and core analytics functions.
- CI/CD pipeline that runs lint + tests on every push and builds the Docker
  image.
- Deployment on AWS with environment-based configuration.
- Prometheus metrics collection and a Grafana dashboard for pipeline health.

## 5. Planned Development Phases

| Phase | Focus | Outcome |
| --- | --- | --- |
| **Phase 1** | Project initialisation | Repository structure, README, `.gitignore`, `.env.example` ✅ |
| **Phase 2** | Data exploration | Acquire a small job dataset; exploratory analysis in a notebook |
| **Phase 3** | Data engineering | Clean/transform pipeline in Pandas; write `jobs`, `skills`, `job_skills` tables |
| **Phase 4** | Database | PostgreSQL setup, schema, indexes, and seed/reference data |
| **Phase 5** | SQL analytics | Analytical queries answering the market questions |
| **Phase 6** | Machine learning | Feature engineering, modelling, evaluation, notebook write-up |
| **Phase 7** | API | FastAPI service exposing analytics as REST endpoints |
| **Phase 8** | Dashboard | Streamlit app for non-technical users |
| **Phase 9** | DevOps | Docker, Docker Compose, GitHub Actions CI/CD, tests, linting |
| **Phase 10** | Cloud & monitoring | AWS deployment, Prometheus metrics, Grafana dashboards, final polish |

## 6. Planned Project Structure

```text
job-market-intelligence/
├── README.md
├── .gitignore
├── .env.example
├── data/
│   ├── raw/                 # untouched source data (not tracked)
│   └── processed/           # cleaned, analysis-ready data (not tracked)
├── notebooks/               # Jupyter notebooks: EDA, modelling
├── src/
│   └── app/
│       ├── api/             # FastAPI application
│       ├── ml/              # Machine learning code
│       └── db/              # Database connection + SQL queries
├── scripts/                 # Entry-point scripts (run_etl.py, load_db.py, ...)
├── tests/                   # Automated tests
├── docs/                    # Architecture notes, ERD, data dictionary
└── infra/                   # Docker, GitHub Actions, monitoring configs
```

> The folder structure above is the **target** layout. It is created progressively
> as each phase is implemented, so the repository stays clean and honest.

## 7. Current Status

**Phase 1 complete.** The repository is initialised and documented.
No database, API, dashboard, ML code, or container configuration exists yet —
those are added in their respective phases.

## 8. How to Run (later phases)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/Scripts/activate   # Windows (PowerShell): .venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy the example environment file and fill in your own values
cp .env.example .env

# 4. Start the stack
docker compose up
```

---

## 9. FastAPI Backend API

The same analytics and machine learning the dashboard shows are also exposed as
a REST API in `backend/`, so any client (a notebook, a job board front end, a
recruiter's tool) can query the market without a browser. It is a thin layer:
it reuses the existing data-access functions in `src/data/queries.py`, the
dashboard's own rule-based Skill Gap Analyzer, and the TF-IDF role recommender
in `ml/`, so an API answer and a dashboard number can never disagree.

```bash
# 1. Install the API's dependencies (uses the same .env / DB_* settings)
python -m pip install -r backend\requirements.txt

# 2. Start the API (docs: /docs Swagger, /redoc ReDoc)
python -m uvicorn backend.app.main:app --reload
```

Example endpoints:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe, plus a cheap PostgreSQL reachability check |
| `GET` | `/jobs` | All postings, optionally filtered by `country`, `work_mode`, `employment_type`, `industry`, `job_role` |
| `GET` | `/skills` | Every skill in the database |
| `GET` | `/companies` | Every employer, with its posting count |
| `GET` | `/analytics/skills?limit=10` | Most-requested skills market-wide |
| `GET` | `/analytics/salaries` | Average salary per role, grouped by currency and period |
| `GET` | `/analytics/roles` | How much of the market each role accounts for |
| `POST` | `/skill-gap` | `{role, skills: [...]}` -> match percentage, matched/missing/required/unknown skills |
| `POST` | `/recommend` | `{skills: [...], top_n}` -> ranked roles by **Skill Similarity Score** (never a probability) |

Security notes: credentials come only from `.env` (never hardcoded), every
database error is sanitised to a generic message, and the recommender score is
documented as a cosine similarity, not a prediction.

---

## 10. Continuous Integration (GitHub Actions)

The whole project lives in one Git repository at the root of `PROJECT/`, and
every push and pull request is verified automatically by the workflow in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

### What runs on every push / pull request

| Step | What it does |
| --- | --- |
| Checkout | Clones the repository (the real `.env` is git-ignored and never arrives) |
| Python 3.11 | Installs the same interpreter version used locally |
| PostgreSQL 18 | Starts an ephemeral service container for the test run |
| Wait for ready | Blocks until PostgreSQL actually accepts connections |
| Initialise database | Applies `database/schema.sql` then `database/seed.sql` |
| Verify counts | Fails fast if the seed did not load (15 / 40 / 32 / 242) |
| Run tests | `python -m pytest -q` — the same command used locally |
| Docker check | `docker compose config --quiet` validates the Compose file |

### Running the same checks locally

```bash
# Everything the CI runs, using the project virtual environment:
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

## 11. Author

AIML student — built as a portfolio project demonstrating data engineering,
SQL, machine learning, and production-ready software engineering practice.
