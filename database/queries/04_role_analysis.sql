-- =============================================================================
-- JOB MARKET INTELLIGENCE & SKILL ANALYTICS PLATFORM
-- -----------------------------------------------------------------------------
-- File      : 04_role_analysis.sql
-- Database  : PostgreSQL 14+
-- Stage     : Phase 5 - SQL analytics
-- Target DB : job_market_intelligence
-- Requires  : database/schema.sql + database/seed.sql
--
-- WHAT THIS FILE ANSWERS
--     1.  Number of jobs by job title
--     2.  Number of jobs by industry
--     3.  Number of jobs by country
--     4.  Number of jobs by work mode
--     5.  Number of jobs by employment type
--     6.  Average experience requirement by role
--     7.  Minimum experience by role
--     8.  Maximum experience by role
--     9.  Roles with the largest number of openings
--     10. Role + skill combinations
--
-- WHY EXPERIENCE CAN BE COMPARED DIRECTLY (unlike salary)
--   experience_min / experience_max are stored in YEARS, which is a single unit
--   with no currency and no period attached, so averaging them across roles and
--   countries is legitimate. Salary figures in 02_salary_analysis.sql have no
--   such property and must stay grouped by currency and period.
--
-- HOW TO RUN
--   psql -U <user> -d job_market_intelligence -f database/queries/04_role_analysis.sql
--
-- SAFETY
--   SELECT only. No data is written and the schema is not modified.
-- =============================================================================


-- =============================================================================
-- 1. NUMBER OF JOBS BY JOB TITLE
-- -----------------------------------------------------------------------------
-- Business question: "Which roles are hiring the most?"
-- distinct_companies is included because headcount alone can be misleading: 5
-- postings from 1 company is one employer expanding, whereas 5 postings from 5
-- companies is a genuine market-wide trend.
-- =============================================================================
SELECT
    j.job_title,
    COUNT(*)                          AS jobs_posted,
    COUNT(DISTINCT c.company_id)      AS distinct_companies,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM jobs), 2) AS pct_of_all_jobs
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY j.job_title
ORDER BY jobs_posted DESC, j.job_title;


-- =============================================================================
-- 2. NUMBER OF JOBS BY INDUSTRY
-- -----------------------------------------------------------------------------
-- Business question: "Which industry sector is hiring the most tech talent?"
-- industry lives on companies, not jobs, so this query needs the JOIN to
-- companies - a frequent mistake is grouping jobs by an industry column that
-- does not exist on the fact table.
-- =============================================================================
SELECT
    c.industry,
    COUNT(*)                          AS jobs_posted,
    COUNT(DISTINCT c.company_id)      AS companies_in_industry,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM jobs), 2) AS pct_of_all_jobs
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY c.industry
ORDER BY jobs_posted DESC, c.industry;


-- =============================================================================
-- 3. NUMBER OF JOBS BY COUNTRY
-- -----------------------------------------------------------------------------
-- Business question: "Where is the demand for these roles concentrated?"
-- Country is stored on the job, not the company: the same employer hires in
-- several countries, so grouping companies by their headquarters country would
-- answer a different (and less useful) question.
-- =============================================================================
SELECT
    j.country,
    COUNT(*)                          AS jobs_posted,
    COUNT(DISTINCT c.company_id)      AS distinct_companies,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM jobs), 2) AS pct_of_all_jobs
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY j.country
ORDER BY jobs_posted DESC, j.country;


-- =============================================================================
-- 4. NUMBER OF JOBS BY WORK MODE
-- -----------------------------------------------------------------------------
-- Business question: "Is the market moving towards remote work?"
-- percentage_of_disclosed is the share of jobs in that work mode. The four
-- allowed values are fixed by chk_jobs_work_mode_valid:
-- REMOTE, HYBRID, ONSITE, UNKNOWN.
-- =============================================================================
SELECT
    j.work_mode,
    COUNT(*)                          AS jobs_posted,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM jobs), 2) AS pct_of_all_jobs,
    MIN(j.posted_date)                AS earliest_posting,
    MAX(j.posted_date)                AS latest_posting
FROM jobs j
GROUP BY j.work_mode
ORDER BY jobs_posted DESC, j.work_mode;


-- =============================================================================
-- 5. NUMBER OF JOBS BY EMPLOYMENT TYPE
-- -----------------------------------------------------------------------------
-- Business question: "Full-time or contract - what is the market split?"
-- =============================================================================
SELECT
    j.employment_type,
    COUNT(*)                          AS jobs_posted,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM jobs), 2) AS pct_of_all_jobs
FROM jobs j
GROUP BY j.employment_type
ORDER BY jobs_posted DESC, j.employment_type;


-- =============================================================================
-- 6. AVERAGE EXPERIENCE REQUIREMENT BY ROLE
-- -----------------------------------------------------------------------------
-- Business question: "How many years of experience does each role demand on
-- average?"
-- Both ends of the advertised range are averaged, and the midpoint is derived
-- from the two averages. jobs_with_experience_stated makes the sample size
-- explicit, because AVG() silently IGNORES rows where experience_min IS NULL -
-- a role where only 1 of 5 postings states experience would otherwise show a
-- confident-looking average.
-- =============================================================================
SELECT
    j.job_title,
    COUNT(*)                                     AS jobs_posted,
    COUNT(j.experience_min)                      AS jobs_with_experience_stated,
    ROUND(AVG(j.experience_min), 2)              AS avg_experience_min_years,
    ROUND(AVG(j.experience_max), 2)              AS avg_experience_max_years,
    ROUND((AVG(j.experience_min) + AVG(j.experience_max)) / 2, 2)
                                                AS avg_experience_midpoint_years
FROM jobs j
GROUP BY j.job_title
ORDER BY avg_experience_min_years DESC, j.job_title;


-- =============================================================================
-- 7. MINIMUM EXPERIENCE BY ROLE
-- -----------------------------------------------------------------------------
-- Business question: "What is the lowest entry bar for each role?"
-- MIN(experience_min) is the most junior requirement advertised for that role -
-- the true entry point. MIN() also ignores NULLs, so a role with no stated
-- experience returns NULL rather than a misleading 0.
-- =============================================================================
SELECT
    j.job_title,
    COUNT(j.experience_min)         AS jobs_with_experience_stated,
    MIN(j.experience_min)           AS min_experience_years,
    ROUND(AVG(j.experience_min), 2) AS avg_experience_min_years
FROM jobs j
GROUP BY j.job_title
ORDER BY min_experience_years, j.job_title;


-- =============================================================================
-- 8. MAXIMUM EXPERIENCE BY ROLE
-- -----------------------------------------------------------------------------
-- Business question: "How senior does the top end of each role go?"
-- MAX(experience_max) is the most senior requirement advertised - it shows the
-- ceiling of a role, which is what matters when advising someone on whether a
-- role has a progression path.
-- =============================================================================
SELECT
    j.job_title,
    COUNT(j.experience_max)         AS jobs_with_experience_stated,
    MAX(j.experience_max)           AS max_experience_years,
    ROUND(AVG(j.experience_max), 2) AS avg_experience_max_years
FROM jobs j
GROUP BY j.job_title
ORDER BY max_experience_years DESC, j.job_title;


-- =============================================================================
-- 9. ROLES WITH THE LARGEST NUMBER OF OPENINGS
-- -----------------------------------------------------------------------------
-- Business question: "Which role offers the most opportunities right now?"
-- IMPORTANT: one posting = one opening in this dataset. The schema has no
-- headcount / number-of-vacancies column, so this measures POSTINGS, not
-- people. A company advertising one senior role three times is not the same
-- as three junior roles, and the average_experience column below is the
-- cheapest way to notice that difference.
--
-- NOTE ON `/ 2.0`: experience_min / experience_max are SMALLINT, so dividing
-- by the integer literal 2 would perform INTEGER division and silently round
-- (0 + 1) / 2 down to 0. Dividing by 2.0 forces NUMERIC arithmetic and keeps
-- the .5 years.
-- =============================================================================
SELECT
    j.job_title,
    COUNT(*)                          AS job_openings,
    COUNT(DISTINCT c.company_id)      AS companies_hiring,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM jobs), 2) AS pct_of_all_openings,
    ROUND(AVG((j.experience_min + j.experience_max) / 2.0), 2)
                                        AS avg_experience_midpoint_years,
    MIN(j.posted_date)                AS first_posted,
    MAX(j.posted_date)                AS last_posted
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY j.job_title
ORDER BY job_openings DESC, j.job_title;


-- =============================================================================
-- 10. ROLE + SKILL COMBINATIONS
-- -----------------------------------------------------------------------------
-- Business question: "How often does each skill appear within each role?"
-- This is the cross-tabulation of roles against skills, and it is the single
-- most useful table in the project: it is exactly what a course curriculum, a
-- resume builder or a dashboard heatmap needs.
-- GROUP BY both job_title and skill_name, so each row is one role/skill cell.
-- One job contributes at most one row per skill (guaranteed by the composite
-- primary key on job_skills), so the counts are directly comparable.
-- Roles with many skills produce many rows; the ordering puts the strongest
-- combinations at the top.
-- =============================================================================
SELECT
    j.job_title,
    s.skill_name,
    s.skill_category,
    COUNT(DISTINCT j.job_id)          AS jobs_requiring_combination,
    COUNT(DISTINCT c.company_id)      AS companies_requiring_combination
FROM jobs j
JOIN job_skills js
    ON js.job_id = j.job_id
JOIN skills s
    ON s.skill_id = js.skill_id
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY j.job_title, s.skill_name, s.skill_category
ORDER BY jobs_requiring_combination DESC, j.job_title, s.skill_name;


-- -----------------------------------------------------------------------------
-- 10b. ROLES AND SKILLS, AS A PIVOT-FRIENDLY LIST
-- -----------------------------------------------------------------------------
-- Business question: "Which skills are unique to one role, and which are
-- shared across the whole organisation?"
-- For each role/skill cell, this shows how many roles in the market use that
-- skill at all. A cell where that number is 1 is a genuine specialisation; a
-- skill used by every role is a baseline requirement rather than a
-- differentiator. Useful when deciding what to teach and what to specialise in.
-- =============================================================================
WITH role_skill AS (
    -- One row per (job_title, skill) cell, so the rows are already unique per
    -- role/skill pair. That uniqueness is what lets the next CTE use a plain
    -- COUNT(*) OVER (...) instead of COUNT(DISTINCT ...).
    -- NOTE: PostgreSQL rejects DISTINCT inside a window function
    -- ("DISTINCT is not implemented for window functions"), so the
    -- de-duplication has to happen in the GROUP BY below, not in the window.
    SELECT
        j.job_title,
        s.skill_id,
        s.skill_name,
        s.skill_category,
        COUNT(DISTINCT j.job_id) AS jobs_requiring_combination
    FROM jobs j
    JOIN job_skills js
        ON js.job_id = j.job_id
    JOIN skills s
        ON s.skill_id = js.skill_id
    GROUP BY j.job_title, s.skill_id, s.skill_name, s.skill_category
),
role_skill_with_breadth AS (
    -- Partition by skill_id and count rows: since the CTE above is already
    -- unique per (job_title, skill_id), each row is one distinct role, so this
    -- count is exactly the number of roles that require the skill.
    SELECT
        rs.job_title,
        rs.skill_name,
        rs.skill_category,
        rs.jobs_requiring_combination,
        COUNT(*) OVER (PARTITION BY rs.skill_id) AS roles_using_this_skill
    FROM role_skill rs
)
SELECT
    job_title,
    skill_name,
    skill_category,
    jobs_requiring_combination,
    roles_using_this_skill,
    CASE
        WHEN roles_using_this_skill = 1   THEN 'ROLE-SPECIFIC'
        WHEN roles_using_this_skill <= 3  THEN 'SHARED BY A FEW ROLES'
        ELSE 'BASELINE ACROSS THE MARKET'
    END AS skill_breadth
FROM role_skill_with_breadth
ORDER BY job_title, jobs_requiring_combination DESC, skill_name;
