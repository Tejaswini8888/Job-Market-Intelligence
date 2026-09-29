-- =============================================================================
-- JOB MARKET INTELLIGENCE & SKILL ANALYTICS PLATFORM
-- -----------------------------------------------------------------------------
-- File      : 01_basic_analysis.sql
-- Database  : PostgreSQL 14+
-- Stage     : Phase 5 - SQL analytics
-- Target DB : job_market_intelligence
-- Requires  : database/schema.sql + database/seed.sql
--
-- WHAT THIS FILE ANSWERS
--   The "table of contents" questions. Before any analysis, confirm what is
--   actually stored, and confirm the filters used later really have data.
--
--     1.  Display all jobs
--     2.  Display the first 10 jobs
--     3.  List unique job titles
--     4.  List unique countries
--     5.  List unique work modes
--     6.  Count total jobs
--     7.  Count total companies
--     8.  Count total skills
--     9.  Find jobs posted most recently
--     10. Find jobs by employment type
--     11. Find jobs by work mode
--     12. Find jobs by country
--
-- CONVENTIONS USED THROUGHOUT
--   * Every job query joins companies so the employer is always visible; a
--     posting without its company name is not interpretable.
--   * Results are ordered by a deterministic key (posted_date + job_id) so the
--     same query returns the same rows every time.
--   * Parameters (queries 10-12) live in a single one-line CTE named `params`,
--     so there is exactly one place to change the filter value.
--   * Values inside those CTEs must match the CHECK constraints declared in
--     schema.sql (employment_type, work_mode, country, ...).
--
-- HOW TO RUN
--   psql -U <user> -d job_market_intelligence -f database/queries/01_basic_analysis.sql
--
-- SAFETY
--   SELECT only. This file contains no INSERT / UPDATE / DELETE / DDL, so it
--   cannot change the database.
-- =============================================================================


-- =============================================================================
-- 1. DISPLAY ALL JOBS
-- -----------------------------------------------------------------------------
-- Business question: "Show me every posting in the database."
-- This is the raw fact table joined to its employer, ordered oldest-posting-last
-- so the list reads chronologically.
-- =============================================================================
SELECT
    j.job_id,
    c.company_name,
    j.job_title,
    j.location,
    j.country,
    j.employment_type,
    j.work_mode,
    j.experience_min,
    j.experience_max,
    j.salary_min,
    j.salary_max,
    j.currency,
    j.salary_period,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
ORDER BY j.posted_date, j.job_id;


-- =============================================================================
-- 2. DISPLAY THE FIRST 10 JOBS
-- -----------------------------------------------------------------------------
-- Business question: "What does a posting look like?"
-- The first 10 rows as stored (lowest job_id). Change the ORDER BY to
-- `j.posted_date DESC` if you would rather see the 10 newest postings
-- (that view is query 9 in this file).
-- =============================================================================
SELECT
    j.job_id,
    c.company_name,
    j.job_title,
    j.location,
    j.country,
    j.employment_type,
    j.work_mode,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
ORDER BY j.job_id
LIMIT 10;


-- =============================================================================
-- 3. UNIQUE JOB TITLES
-- -----------------------------------------------------------------------------
-- Business question: "What distinct roles exist in this market?"
-- COUNT(*) alongside each title is a free quality check: a role appearing once
-- is too small to draw conclusions from.
-- =============================================================================
SELECT
    j.job_title,
    COUNT(*) AS jobs_posted
FROM jobs j
GROUP BY j.job_title
ORDER BY j.job_title;


-- =============================================================================
-- 4. UNIQUE COUNTRIES
-- -----------------------------------------------------------------------------
-- Business question: "Which countries are covered, and how many postings come
-- from each?" Required before any location-based conclusion can be trusted.
-- COUNT(DISTINCT c.company_id) also shows how many distinct employers are
-- hiring in each country (a country with 6 jobs from 1 company is a single
-- employer, not a national trend).
-- =============================================================================
SELECT
    j.country,
    COUNT(*) AS jobs_posted,
    COUNT(DISTINCT c.company_id) AS distinct_companies_hiring
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY j.country
ORDER BY jobs_posted DESC, j.country;


-- =============================================================================
-- 5. UNIQUE WORK MODES
-- -----------------------------------------------------------------------------
-- Business question: "What work arrangements appear in the data?"
-- Allowed values are fixed by chk_jobs_work_mode_valid:
-- REMOTE, HYBRID, ONSITE, UNKNOWN.
-- =============================================================================
SELECT
    j.work_mode,
    COUNT(*) AS jobs_posted,
    ROUND(
        100.0 * COUNT(*) / (SELECT COUNT(*) FROM jobs),
        2
    ) AS pct_of_all_jobs
FROM jobs j
GROUP BY j.work_mode
ORDER BY jobs_posted DESC, j.work_mode;


-- -----------------------------------------------------------------------------
-- 5b. ALLOWED EMPLOYMENT TYPES (the controlled vocabulary)
-- -----------------------------------------------------------------------------
-- Business question: "Which employment types could a filter legitimately use?"
-- The allowed values are listed in chk_jobs_employment_type_valid in
-- schema.sql. UNKNOWN exists so that missing source data is recorded honestly
-- rather than guessed; a high UNKNOWN count is a data-quality warning, which is
-- exactly why it is surfaced here.
-- =============================================================================
SELECT
    v.employment_type,
    COALESCE(COUNT(j.job_id), 0) AS jobs_posted
FROM (VALUES ('FULL_TIME'),
             ('PART_TIME'),
             ('CONTRACT'),
             ('INTERNSHIP'),
             ('TEMPORARY'),
             ('FREELANCE'),
             ('OTHER'),
             ('UNKNOWN')) AS v(employment_type)
LEFT JOIN jobs j
    ON j.employment_type = v.employment_type
GROUP BY v.employment_type
ORDER BY jobs_posted DESC, v.employment_type;


-- =============================================================================
-- 6. COUNT TOTAL JOBS
-- -----------------------------------------------------------------------------
-- Business question: "How large is the job dataset?"
-- COUNT(*) is exact and fast. COUNT(j.job_id) would give the same answer
-- because job_id is the primary key (never NULL).
-- =============================================================================
SELECT COUNT(*) AS total_jobs
FROM jobs;


-- =============================================================================
-- 7. COUNT TOTAL COMPANIES
-- -----------------------------------------------------------------------------
-- Business question: "How many distinct employers are represented?"
-- This counts companies, NOT postings. Compare with total_jobs to see how many
-- postings the average employer contributes.
-- =============================================================================
SELECT COUNT(*) AS total_companies
FROM companies;


-- =============================================================================
-- 8. COUNT TOTAL SKILLS
-- -----------------------------------------------------------------------------
-- Business question: "How large is the skill vocabulary?"
-- This counts every skill in the dictionary, including any skill not yet
-- required by any posting. To count only skills actually demanded, see
-- 03_skill_demand.sql query 12 (skills with zero demand).
-- =============================================================================
SELECT COUNT(*) AS total_skills
FROM skills;


-- -----------------------------------------------------------------------------
-- 8b. DATASET SNAPSHOT (row counts across all four tables)
-- -----------------------------------------------------------------------------
-- Business question: "Is the database in the state I expect before I trust
-- any analysis?" One screen that answers "is anything missing?".
-- =============================================================================
SELECT 'companies'  AS table_name, COUNT(*) AS row_count FROM companies
UNION ALL
SELECT 'jobs'       AS table_name, COUNT(*) AS row_count FROM jobs
UNION ALL
SELECT 'skills'     AS table_name, COUNT(*) AS row_count FROM skills
UNION ALL
SELECT 'job_skills' AS table_name, COUNT(*) AS row_count FROM job_skills
ORDER BY table_name;


-- =============================================================================
-- 9. JOBS POSTED MOST RECENTLY
-- -----------------------------------------------------------------------------
-- Business question: "What is happening in the market right now?"
-- The newest postings first. posted_date is a plain DATE, so ORDER BY ... DESC
-- sorts newest-first without needing a timestamp expression.
-- =============================================================================
SELECT
    j.job_id,
    c.company_name,
    j.job_title,
    j.location,
    j.country,
    j.work_mode,
    j.employment_type,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
ORDER BY j.posted_date DESC, j.job_id DESC
LIMIT 10;


-- =============================================================================
-- 10. FIND JOBS BY EMPLOYMENT TYPE
-- -----------------------------------------------------------------------------
-- Business question: "How many full-time versus contract roles are there?"
-- >>> CHANGE ME: edit the value inside the `params` CTE. <<<
--   Valid values (chk_jobs_employment_type_valid):
--   FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP, TEMPORARY, FREELANCE,
--   OTHER, UNKNOWN
-- The filter value is a parameter, not a hard-coded WHERE, so this query
-- documents itself: one obvious line to change, and the query cannot be broken
-- by editing a WHERE clause far from the top of the statement.
-- =============================================================================
WITH params AS (
    SELECT 'FULL_TIME'::TEXT AS employment_type
)
SELECT
    p.employment_type                       AS filter_employment_type,
    j.job_id,
    c.company_name,
    j.job_title,
    j.location,
    j.country,
    j.work_mode,
    j.salary_min,
    j.salary_max,
    j.currency,
    j.salary_period,
    j.posted_date
FROM params p
JOIN jobs j
    ON j.employment_type = p.employment_type
JOIN companies c
    ON c.company_id = j.company_id
ORDER BY j.posted_date DESC, j.job_id;


-- =============================================================================
-- 11. FIND JOBS BY WORK MODE
-- -----------------------------------------------------------------------------
-- Business question: "Which postings are remote?"
-- >>> CHANGE ME: edit the value inside the `params` CTE. <<<
--   Valid values (chk_jobs_work_mode_valid): REMOTE, HYBRID, ONSITE, UNKNOWN
-- =============================================================================
WITH params AS (
    SELECT 'REMOTE'::TEXT AS work_mode
)
SELECT
    p.work_mode                              AS filter_work_mode,
    j.job_id,
    c.company_name,
    j.job_title,
    j.location,
    j.country,
    j.employment_type,
    j.posted_date
FROM params p
JOIN jobs j
    ON j.work_mode = p.work_mode
JOIN companies c
    ON c.company_id = j.company_id
ORDER BY j.posted_date DESC, j.job_id;


-- =============================================================================
-- 12. FIND JOBS BY COUNTRY
-- -----------------------------------------------------------------------------
-- Business question: "What is the hiring picture in one country?"
-- >>> CHANGE ME: edit the value inside the `params` CTE. <<<
--   Values present in this database are ISO 3166-1 alpha-2 codes such as
--   IN, GB, US, CA, AU, DE, SG. To list them all, run query 4 in this file.
-- =============================================================================
WITH params AS (
    SELECT 'IN'::TEXT AS country
)
SELECT
    p.country                                AS filter_country,
    j.job_id,
    c.company_name,
    c.industry,
    j.job_title,
    j.location,
    j.employment_type,
    j.work_mode,
    j.posted_date
FROM params p
JOIN jobs j
    ON j.country = p.country
JOIN companies c
    ON c.company_id = j.company_id
ORDER BY j.posted_date DESC, j.job_id;
