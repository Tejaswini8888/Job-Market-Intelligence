-- =============================================================================
-- JOB MARKET INTELLIGENCE & SKILL ANALYTICS PLATFORM
-- -----------------------------------------------------------------------------
-- File      : 03_skill_demand.sql
-- Database  : PostgreSQL 14+
-- Stage     : Phase 5 - SQL analytics
-- Target DB : job_market_intelligence
-- Requires  : database/schema.sql + database/seed.sql
--
-- WHAT THIS FILE ANSWERS
--     1.  Most demanded skills
--     2.  Top 10 skills by number of jobs
--     3.  Skill demand by skill category
--     4.  Skills required by AI/ML roles
--     5.  Skills required by Data Analyst roles
--     6.  Skills required by Data Engineer roles
--     7.  Skills required by DevOps/SRE roles
--     8.  Number of jobs requiring each skill
--     9.  Percentage of jobs requiring each skill
--     10. Companies requiring each skill
--
-- THE MANY-TO-MANY JOIN (the core pattern of this file)
--   skills --< job_skills >-- jobs
--   job_skills is the junction table: one row means "this job requires this
--   skill". Reaching a skill's demand therefore needs THREE joins:
--       skills JOIN job_skills JOIN jobs
--   Skipping the middle table is the single most common mistake in this schema.
--
--   Counting rule used throughout: COUNT(DISTINCT j.job_id), not COUNT(*).
--   A plain COUNT(*) would still be correct for THIS dataset (the composite
--   primary key on job_skills prevents a duplicate job/skill pair), but
--   DISTINCT states the intent - "how many different jobs" - and stays correct
--   if the junction table ever gains an extra column such as a proficiency
--   level or a mention count.
--
-- HOW TO RUN
--   psql -U <user> -d job_market_intelligence -f database/queries/03_skill_demand.sql
--
-- SAFETY
--   SELECT only. No data is written and the schema is not modified.
-- =============================================================================


-- =============================================================================
-- 1. MOST DEMANDED SKILLS
-- -----------------------------------------------------------------------------
-- Business question: "What does the market actually ask for?"
-- Every skill, ranked by how many distinct postings require it. This is the
-- headline ranking of the whole project. Ties are broken alphabetically by
-- skill_name so the output order is reproducible.
-- =============================================================================
SELECT
    s.skill_name,
    s.skill_category,
    COUNT(DISTINCT j.job_id) AS jobs_requiring_skill
FROM skills s
JOIN job_skills js
    ON js.skill_id = s.skill_id
JOIN jobs j
    ON j.job_id = js.job_id
GROUP BY s.skill_name, s.skill_category
ORDER BY jobs_requiring_skill DESC, s.skill_name;


-- =============================================================================
-- 2. TOP 10 SKILLS BY NUMBER OF JOBS
-- -----------------------------------------------------------------------------
-- Business question: "What are the ten skills a candidate should prioritise?"
-- The same aggregation as query 1 with LIMIT 10. Note this counts JOBS, not
-- total mentions: a skill listed twice in one posting is still one requirement.
-- =============================================================================
SELECT
    s.skill_name,
    s.skill_category,
    COUNT(DISTINCT j.job_id) AS jobs_requiring_skill
FROM skills s
JOIN job_skills js
    ON js.skill_id = s.skill_id
JOIN jobs j
    ON j.job_id = js.job_id
GROUP BY s.skill_name, s.skill_category
ORDER BY jobs_requiring_skill DESC, s.skill_name
LIMIT 10;


-- =============================================================================
-- 3. SKILL DEMAND BY SKILL CATEGORY
-- -----------------------------------------------------------------------------
-- Business question: "Which families of skills carry the most market weight?"
-- Three different measures, because they answer different questions:
--   skills_in_category  - how wide is the category (breadth of vocabulary)
--   total_skill_job_links - SUM of demand = the CATEGORY's total weight
--   jobs_touching_category - DISTINCT jobs using at least one skill from it.
--   The last two differ on purpose: a single job using four Big Data skills
--   contributes 4 links but only 1 job. Use links to size the category and
--   jobs to judge how many postings it actually affects.
-- =============================================================================
SELECT
    s.skill_category,
    COUNT(DISTINCT s.skill_id) AS skills_in_category,
    COUNT(js.job_id)           AS total_skill_job_links,
    COUNT(DISTINCT js.job_id)  AS jobs_touching_category,
    ROUND(
        100.0 * COUNT(DISTINCT js.job_id) / (SELECT COUNT(*) FROM jobs),
        2
    )                          AS pct_of_all_jobs
FROM skills s
JOIN job_skills js
    ON js.skill_id = s.skill_id
GROUP BY s.skill_category
ORDER BY total_skill_job_links DESC, s.skill_category;


-- =============================================================================
-- 4. SKILLS REQUIRED BY AI/ML ROLES
-- -----------------------------------------------------------------------------
-- Business question: "What is the actual technical stack of an AI/ML job?"
-- The role scope is declared ONCE, in a CTE, and the comment above it lists
-- the titles that are in scope. Change the list there to redefine the cohort -
-- there is no need to hunt through the query body.
-- -----------------------------------------------------------------------
-- NOTE ON ROLE COHORTS
--   These queries match job_title EXACTLY. A cohort is only as good as its
--   title list, so the list is written out in the comment above each query and
--   kept in one place. Adding a title here silently changes the cohort size,
--   which is why the result also reports how many roles and jobs matched.
-- =============================================================================
WITH role_scope AS (
    -- Titles in scope: the two AI/ML engineering roles.
    -- Add 'Data Scientist' here to widen the cohort to data-science roles too.
    SELECT j.job_id, j.job_title
    FROM jobs j
    WHERE j.job_title IN ('AI Engineer', 'Machine Learning Engineer')
),
skill_demand AS (
    SELECT
        s.skill_name,
        s.skill_category,
        COUNT(DISTINCT r.job_id) AS jobs_requiring_skill
    FROM role_scope r
    JOIN job_skills js
        ON js.job_id = r.job_id
    JOIN skills s
        ON s.skill_id = js.skill_id
    GROUP BY s.skill_name, s.skill_category
)
SELECT
    d.skill_name,
    d.skill_category,
    d.jobs_requiring_skill,
    (SELECT COUNT(*) FROM role_scope)                        AS jobs_in_cohort,
    (SELECT COUNT(DISTINCT job_title) FROM role_scope)       AS roles_in_cohort,
    ROUND(
        100.0 * d.jobs_requiring_skill / NULLIF((SELECT COUNT(*) FROM role_scope), 0),
        2
    )                                                         AS pct_of_cohort_jobs
FROM skill_demand d
ORDER BY d.jobs_requiring_skill DESC, d.skill_name;


-- =============================================================================
-- 5. SKILLS REQUIRED BY DATA ANALYST ROLES
-- -----------------------------------------------------------------------------
-- Business question: "What must I learn to qualify as a Data Analyst?"
-- Titles in scope: 'Data Analyst'
-- =============================================================================
WITH role_scope AS (
    SELECT j.job_id, j.job_title
    FROM jobs j
    WHERE j.job_title IN ('Data Analyst')
),
skill_demand AS (
    SELECT
        s.skill_name,
        s.skill_category,
        COUNT(DISTINCT r.job_id) AS jobs_requiring_skill
    FROM role_scope r
    JOIN job_skills js
        ON js.job_id = r.job_id
    JOIN skills s
        ON s.skill_id = js.skill_id
    GROUP BY s.skill_name, s.skill_category
)
SELECT
    d.skill_name,
    d.skill_category,
    d.jobs_requiring_skill,
    (SELECT COUNT(*) FROM role_scope) AS jobs_in_cohort,
    ROUND(
        100.0 * d.jobs_requiring_skill / NULLIF((SELECT COUNT(*) FROM role_scope), 0),
        2
    )                                AS pct_of_cohort_jobs
FROM skill_demand d
ORDER BY d.jobs_requiring_skill DESC, d.skill_name;


-- =============================================================================
-- 6. SKILLS REQUIRED BY DATA ENGINEER ROLES
-- -----------------------------------------------------------------------------
-- Business question: "What distinguishes a Data Engineer from a Data Analyst?"
-- Titles in scope: 'Data Engineer'
-- Comparing this result against query 5 isolates exactly the skills that
-- separate the two roles (Spark / Airflow style tooling rather than BI tools).
-- =============================================================================
WITH role_scope AS (
    SELECT j.job_id, j.job_title
    FROM jobs j
    WHERE j.job_title IN ('Data Engineer')
),
skill_demand AS (
    SELECT
        s.skill_name,
        s.skill_category,
        COUNT(DISTINCT r.job_id) AS jobs_requiring_skill
    FROM role_scope r
    JOIN job_skills js
        ON js.job_id = r.job_id
    JOIN skills s
        ON s.skill_id = js.skill_id
    GROUP BY s.skill_name, s.skill_category
)
SELECT
    d.skill_name,
    d.skill_category,
    d.jobs_requiring_skill,
    (SELECT COUNT(*) FROM role_scope) AS jobs_in_cohort,
    ROUND(
        100.0 * d.jobs_requiring_skill / NULLIF((SELECT COUNT(*) FROM role_scope), 0),
        2
    )                                AS pct_of_cohort_jobs
FROM skill_demand d
ORDER BY d.jobs_requiring_skill DESC, d.skill_name;


-- =============================================================================
-- 7. SKILLS REQUIRED BY DEVOPS / SRE ROLES
-- -----------------------------------------------------------------------------
-- Business question: "What is the shared infrastructure stack across DevOps
-- and reliability roles?"
-- Titles in scope: 'DevOps Engineer', 'Site Reliability Engineer'
-- Add 'Cloud Engineer' to include the cloud-engineering cohort.
-- =============================================================================
WITH role_scope AS (
    SELECT j.job_id, j.job_title
    FROM jobs j
    WHERE j.job_title IN ('DevOps Engineer', 'Site Reliability Engineer')
),
skill_demand AS (
    SELECT
        s.skill_name,
        s.skill_category,
        COUNT(DISTINCT r.job_id) AS jobs_requiring_skill
    FROM role_scope r
    JOIN job_skills js
        ON js.job_id = r.job_id
    JOIN skills s
        ON s.skill_id = js.skill_id
    GROUP BY s.skill_name, s.skill_category
)
SELECT
    d.skill_name,
    d.skill_category,
    d.jobs_requiring_skill,
    (SELECT COUNT(*) FROM role_scope)                  AS jobs_in_cohort,
    (SELECT COUNT(DISTINCT job_title) FROM role_scope) AS roles_in_cohort,
    ROUND(
        100.0 * d.jobs_requiring_skill / NULLIF((SELECT COUNT(*) FROM role_scope), 0),
        2
    )                                                  AS pct_of_cohort_jobs
FROM skill_demand d
ORDER BY d.jobs_requiring_skill DESC, d.skill_name;


-- -----------------------------------------------------------------------------
-- 7b. SKILL COVERAGE PER ROLE (one row per role, for comparison)
-- -----------------------------------------------------------------------------
-- Business question: "How many distinct skills does each role demand?"
-- Aggregate over the already-aggregated role/skill counts, so it reuses the
-- same many-to-many join instead of re-deriving it.
-- =============================================================================
SELECT
    j.job_title,
    COUNT(DISTINCT s.skill_id) AS distinct_skills_required,
    COUNT(js.job_id)           AS total_skill_requirements,
    COUNT(DISTINCT j.job_id)   AS jobs_in_role
FROM jobs j
JOIN job_skills js
    ON js.job_id = j.job_id
JOIN skills s
    ON s.skill_id = js.skill_id
GROUP BY j.job_title
ORDER BY distinct_skills_required DESC, j.job_title;


-- =============================================================================
-- 8. NUMBER OF JOBS REQUIRING EACH SKILL
-- -----------------------------------------------------------------------------
-- Business question: "For each skill, how many postings list it?"
-- The core counting query, kept as its own numbered query because it is the
-- building block for the rankings in 05_advanced_analysis.sql.
-- =============================================================================
SELECT
    s.skill_name,
    s.skill_category,
    COUNT(DISTINCT j.job_id)  AS jobs_requiring_skill,
    COUNT(DISTINCT c.company_id) AS companies_requiring_skill
FROM skills s
JOIN job_skills js
    ON js.skill_id = s.skill_id
JOIN jobs j
    ON j.job_id = js.job_id
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY s.skill_name, s.skill_category
ORDER BY jobs_requiring_skill DESC, s.skill_name;


-- =============================================================================
-- 9. PERCENTAGE OF JOBS REQUIRING EACH SKILL
-- -----------------------------------------------------------------------------
-- Business question: "How widespread is this skill across the whole market?"
-- A percentage states coverage far better than a raw count: "31 of 40" means
-- something very different out of 40 postings than it would out of 4,000.
-- The denominator is a scalar subquery over the whole jobs table. NULLIF
-- guards the divide-by-zero for the (theoretical) case of an empty database.
-- =============================================================================
SELECT
    s.skill_name,
    s.skill_category,
    COUNT(DISTINCT j.job_id)                                   AS jobs_requiring_skill,
    (SELECT COUNT(*) FROM jobs)                                 AS total_jobs,
    ROUND(
        100.0 * COUNT(DISTINCT j.job_id) / NULLIF((SELECT COUNT(*) FROM jobs), 0),
        2
    )                                                           AS pct_of_all_jobs
FROM skills s
JOIN job_skills js
    ON js.skill_id = s.skill_id
JOIN jobs j
    ON j.job_id = js.job_id
GROUP BY s.skill_name, s.skill_category
ORDER BY jobs_requiring_skill DESC, s.skill_name;


-- =============================================================================
-- 10. COMPANIES REQUIRING EACH SKILL
-- -----------------------------------------------------------------------------
-- Business question: "How many different employers want this skill, and which
-- ones?" - i.e. is demand concentrated in one employer or spread across the
-- market? A skill wanted by 1 company is far riskier than one wanted by 10.
-- COUNT(DISTINCT c.company_id) gives the number of employers;
-- string_agg(DISTINCT ... ORDER BY ...) lists them alphabetically. With
-- DISTINCT, the ORDER BY expression must be the same column being aggregated -
-- which is why the ORDER BY repeats j->c.company_name exactly.
-- =============================================================================
SELECT
    s.skill_name,
    s.skill_category,
    COUNT(DISTINCT c.company_id) AS companies_requiring_skill,
    COUNT(DISTINCT j.job_id)     AS jobs_requiring_skill,
    string_agg(DISTINCT c.company_name, ', ' ORDER BY c.company_name) AS companies
FROM skills s
JOIN job_skills js
    ON js.skill_id = s.skill_id
JOIN jobs j
    ON j.job_id = js.job_id
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY s.skill_name, s.skill_category
ORDER BY companies_requiring_skill DESC, jobs_requiring_skill DESC, s.skill_name;


-- =============================================================================
-- 11. SKILL DEMAND RANKED WITH A WINDOW FUNCTION
-- -----------------------------------------------------------------------------
-- Business question: "What is the exact rank of every skill?"
-- RANK() gives tied skills the same number and then SKIPS the next value
-- (1, 2, 2, 4) - which is the honest way to show a tie: the second place is
-- genuinely shared. DENSE_RANK() renumbers without gaps (1, 2, 2, 3) and is
-- better when the goal is a position index rather than a competition result.
-- Both are shown so the difference is visible on real data.
-- The demand counts are computed once in a CTE, then ranked - a window
-- function ranks rows, it does not aggregate them, so the aggregation has to
-- happen first.
-- =============================================================================
WITH skill_demand AS (
    SELECT
        s.skill_name,
        s.skill_category,
        COUNT(DISTINCT j.job_id) AS jobs_requiring_skill
    FROM skills s
    JOIN job_skills js
        ON js.skill_id = s.skill_id
    JOIN jobs j
        ON j.job_id = js.job_id
    GROUP BY s.skill_name, s.skill_category
)
SELECT
    skill_name,
    skill_category,
    jobs_requiring_skill,
    RANK()       OVER (ORDER BY jobs_requiring_skill DESC) AS demand_rank,
    DENSE_RANK() OVER (ORDER BY jobs_requiring_skill DESC) AS demand_dense_rank,
    ROW_NUMBER() OVER (ORDER BY jobs_requiring_skill DESC, skill_name) AS row_num
FROM skill_demand
ORDER BY jobs_requiring_skill DESC, skill_name;


-- =============================================================================
-- 12. SKILLS WITH ZERO DEMAND (data-quality check, LEFT JOIN)
-- -----------------------------------------------------------------------------
-- Business question: "Is my skill dictionary polluted with skills no posting
-- ever asks for?"
-- LEFT JOIN keeps skills that have NO rows in job_skills - an inner join would
-- silently drop them, and a dictionary full of unused skills quietly inflates
-- every "percentage of skills" denominator. IS NULL is the correct test here:
-- COUNT(js.job_id) cannot be used, because COUNT of a column ignores NULLs and
-- would return 0 for used skills too.
-- =============================================================================
SELECT
    s.skill_name,
    s.skill_category
FROM skills s
LEFT JOIN job_skills js
    ON js.skill_id = s.skill_id
WHERE js.job_id IS NULL
ORDER BY s.skill_category, s.skill_name;
