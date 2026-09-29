-- =============================================================================
-- JOB MARKET INTELLIGENCE & SKILL ANALYTICS PLATFORM
-- -----------------------------------------------------------------------------
-- File      : 02_salary_analysis.sql
-- Database  : PostgreSQL 14+
-- Stage     : Phase 5 - SQL analytics
-- Target DB : job_market_intelligence
-- Requires  : database/schema.sql + database/seed.sql
--
-- ############################################################################
-- #  THE MOST IMPORTANT RULE IN THIS FILE                                          #
-- #                                                                                 #
-- #  A salary figure is ONLY meaningful together with its `currency` and its        #
-- #  `salary_period`. The schema enforces this (chk_jobs_salary_requires_currency,   #
-- #  chk_jobs_salary_requires_period) precisely so this mistake cannot be made.      #
-- #                                                                                 #
-- #  * 600000 INR/YEARLY  and  60000 INR/MONTHLY  are different magnitudes.           #
-- #  * 600000 INR/YEARLY  and    80 USD/HOURLY  are different currencies AND         #
-- #    different periods. Adding or averaging them produces a number with no         #
-- #    meaning whatsoever.                                                           #
-- #                                                                                 #
-- #  THEREFORE: every aggregation in this file groups by `currency` AND              #
-- #  `salary_period` (or is explicitly restricted to a single currency/period).      #
-- #  A single "average salary for the whole market" figure is NOT produced,         #
-- #  because it would be an arithmetic average of incommensurable numbers.           #
-- #                                                                                 #
-- #  There is no FX rate table in this database, so cross-currency comparison       #
-- #  is impossible by design. That is an honest limitation, not an oversight.       #
-- ############################################################################
--
-- WHAT THIS FILE ANSWERS
--     1.  Average minimum salary
--     2.  Average maximum salary
--     3.  Minimum advertised salary
--     4.  Maximum advertised salary
--     5.  Average salary by job title
--     6.  Average salary by country
--     7.  Average salary by work mode
--     8.  Jobs with the highest salary ranges
--     9.  Jobs with salary information available
--     10. Jobs where salary_min AND salary_max are both available
--
-- HOW TO RUN
--   psql -U <user> -d job_market_intelligence -f database/queries/02_salary_analysis.sql
--
-- SAFETY
--   SELECT only. No data is inserted, updated or deleted, and the schema is
--   not modified.
-- =============================================================================


-- =============================================================================
-- 1. AVERAGE MINIMUM SALARY
-- -----------------------------------------------------------------------------
-- Business question: "What is the typical lower bound employers advertise?"
-- GROUPED BY CURRENCY AND SALARY PERIOD - see the warning at the top of this
-- file. Each row is an average within one comparable group, so the numbers
-- across rows are never added together.
-- jobs_in_group is shown next to the average so the sample size is never
-- hidden: an average over 1 posting is not a market signal.
-- =============================================================================
SELECT
    j.currency,
    j.salary_period,
    COUNT(*)                                   AS jobs_in_group,
    ROUND(AVG(j.salary_min), 2)                AS avg_salary_min,
    ROUND(MIN(j.salary_min), 2)                AS lowest_salary_min,
    ROUND(MAX(j.salary_min), 2)                AS highest_salary_min
FROM jobs j
WHERE j.salary_min IS NOT NULL
GROUP BY j.currency, j.salary_period
ORDER BY j.currency, j.salary_period;


-- =============================================================================
-- 2. AVERAGE MAXIMUM SALARY
-- -----------------------------------------------------------------------------
-- Business question: "What is the typical upper bound employers advertise?"
-- Again grouped by currency and period, never merged into a single figure.
-- =============================================================================
SELECT
    j.currency,
    j.salary_period,
    COUNT(*)                                   AS jobs_in_group,
    ROUND(AVG(j.salary_max), 2)                AS avg_salary_max,
    ROUND(MIN(j.salary_max), 2)                AS lowest_salary_max,
    ROUND(MAX(j.salary_max), 2)                AS highest_salary_max
FROM jobs j
WHERE j.salary_max IS NOT NULL
GROUP BY j.currency, j.salary_period
ORDER BY j.currency, j.salary_period;


-- -----------------------------------------------------------------------------
-- 2b. AVERAGE OF THE ADVERTISED RANGE (midpoint)
-- -----------------------------------------------------------------------------
-- Business question: "What single figure best represents a posting's pay?"
-- The midpoint (min + max) / 2 summarises the range. AVG() is computed over
-- rows where BOTH ends exist, otherwise the midpoint would be half of a range
-- whose other half is unknown. ROUND(..., 2) keeps NUMERIC arithmetic
-- readable - NUMERIC is exact, so this rounding is presentation only.
-- =============================================================================
SELECT
    j.currency,
    j.salary_period,
    COUNT(*)                                           AS jobs_in_group,
    ROUND(AVG((j.salary_min + j.salary_max) / 2), 2) AS avg_salary_midpoint
FROM jobs j
WHERE j.salary_min IS NOT NULL
  AND j.salary_max IS NOT NULL
GROUP BY j.currency, j.salary_period
ORDER BY j.currency, j.salary_period;


-- =============================================================================
-- 3. MINIMUM ADVERTISED SALARY
-- -----------------------------------------------------------------------------
-- Business question: "What is the lowest pay on offer anywhere in the data?"
-- Grouped by currency and period: the lowest yearly INR figure and the lowest
-- hourly USD figure are different questions with different answers.
-- =============================================================================
SELECT
    j.currency,
    j.salary_period,
    COUNT(*)                            AS jobs_in_group,
    ROUND(MIN(j.salary_min), 2)         AS min_salary_advertised,
    ROUND(MIN(j.salary_max), 2)         AS min_of_upper_bounds
FROM jobs j
WHERE j.salary_min IS NOT NULL
GROUP BY j.currency, j.salary_period
ORDER BY j.currency, j.salary_period;


-- =============================================================================
-- 4. MAXIMUM ADVERTISED SALARY
-- -----------------------------------------------------------------------------
-- Business question: "What is the highest pay on offer anywhere in the data?"
-- Grouped by currency and period, for the same reason as query 3.
-- =============================================================================
SELECT
    j.currency,
    j.salary_period,
    COUNT(*)                            AS jobs_in_group,
    ROUND(MAX(j.salary_min), 2)         AS max_salary_advertised,
    ROUND(MAX(j.salary_max), 2)         AS max_salary_upper_bound
FROM jobs j
WHERE j.salary_max IS NOT NULL
GROUP BY j.currency, j.salary_period
ORDER BY j.currency, j.salary_period;


-- =============================================================================
-- 5. AVERAGE SALARY BY JOB TITLE
-- -----------------------------------------------------------------------------
-- Business question: "How much does a Data Analyst earn versus a Data
-- Engineer, for the same currency and pay period?"
-- currency + salary_period are part of the grouping, so each row compares
-- like with like. Two rows for the same job_title mean the title appears in
-- two different pay contexts (e.g. an annual role in India and an hourly
-- contract in the US) - that is correct behaviour, not a duplicate.
-- =============================================================================
SELECT
    j.job_title,
    j.currency,
    j.salary_period,
    COUNT(*)                                           AS jobs_posted,
    ROUND(AVG(j.salary_min), 2)                        AS avg_salary_min,
    ROUND(AVG(j.salary_max), 2)                        AS avg_salary_max,
    ROUND(AVG((j.salary_min + j.salary_max) / 2), 2)   AS avg_salary_midpoint
FROM jobs j
WHERE j.salary_min IS NOT NULL
  AND j.salary_max IS NOT NULL
GROUP BY j.job_title, j.currency, j.salary_period
ORDER BY j.job_title, j.currency, j.salary_period;


-- -----------------------------------------------------------------------------
-- 5b. THE SAME COMPARISON, RESTRICTED TO ONE COMPARABLE GROUP
-- -----------------------------------------------------------------------------
-- Business question: "Within one single currency and pay period, how do roles
-- compare on pay?"
-- >>> CHANGE ME: the WHERE clause pins ONE currency + ONE period. <<<
-- This is the only way to rank roles against each other fairly without an FX
-- table. Both values must match chk_jobs_currency_iso4217 ('^[A-Z]{3}$') and
-- chk_jobs_salary_period_valid (YEARLY, MONTHLY, WEEKLY, DAILY, HOURLY).
-- Note the guard `AND j.salary_period = 'YEARLY'` - a YEARLY-only view would
-- silently include HOURLY rows if the period were not also pinned.
-- =============================================================================
SELECT
    j.job_title,
    j.currency,
    j.salary_period,
    COUNT(*)                                           AS jobs_posted,
    ROUND(AVG(j.salary_min), 2)                        AS avg_salary_min,
    ROUND(AVG(j.salary_max), 2)                        AS avg_salary_max,
    ROUND(AVG((j.salary_min + j.salary_max) / 2), 2)   AS avg_salary_midpoint,
    ROUND(AVG((j.salary_max - j.salary_min)), 2)       AS avg_range_width
FROM jobs j
WHERE j.salary_min IS NOT NULL
  AND j.salary_max IS NOT NULL
  AND j.currency      = 'INR'
  AND j.salary_period = 'YEARLY'
GROUP BY j.job_title, j.currency, j.salary_period
ORDER BY avg_salary_midpoint DESC, j.job_title;


-- =============================================================================
-- 6. AVERAGE SALARY BY COUNTRY
-- -----------------------------------------------------------------------------
-- Business question: "Which countries pay the most for this kind of work?"
-- IMPORTANT: this does NOT mean the highest number is the best-paying country.
-- It identifies the highest number within each currency, and those rows
-- deliberately sit under different currency labels. A genuine cross-country
-- ranking requires converting to one currency, which this database cannot do.
-- country_code joins the human-readable country from the posting, so the same
-- country always carries one currency in this dataset.
-- =============================================================================
SELECT
    j.country,
    j.currency,
    j.salary_period,
    COUNT(DISTINCT c.company_id)                       AS companies_hiring,
    COUNT(*)                                           AS jobs_posted,
    ROUND(AVG(j.salary_min), 2)                        AS avg_salary_min,
    ROUND(AVG(j.salary_max), 2)                        AS avg_salary_max,
    ROUND(AVG((j.salary_min + j.salary_max) / 2), 2)   AS avg_salary_midpoint
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
WHERE j.salary_min IS NOT NULL
  AND j.salary_max IS NOT NULL
GROUP BY j.country, j.currency, j.salary_period
ORDER BY j.country;


-- =============================================================================
-- 7. AVERAGE SALARY BY WORK MODE
-- -----------------------------------------------------------------------------
-- Business question: "Do employers pay differently for remote vs on-site?"
-- Grouped by currency and period, because a HYBRID row in INR and a REMOTE
-- row in USD are not comparable.
-- =============================================================================
SELECT
    j.work_mode,
    j.currency,
    j.salary_period,
    COUNT(*)                                           AS jobs_posted,
    ROUND(AVG(j.salary_min), 2)                        AS avg_salary_min,
    ROUND(AVG(j.salary_max), 2)                        AS avg_salary_max,
    ROUND(AVG((j.salary_min + j.salary_max) / 2), 2)   AS avg_salary_midpoint
FROM jobs j
WHERE j.salary_min IS NOT NULL
  AND j.salary_max IS NOT NULL
GROUP BY j.work_mode, j.currency, j.salary_period
ORDER BY j.work_mode, j.currency, j.salary_period;


-- =============================================================================
-- 8. JOBS WITH THE HIGHEST SALARY RANGES
-- -----------------------------------------------------------------------------
-- Business question: "Which postings advertise the widest / most generous
-- salary range?"
-- A global "top 10 highest salaries" across the whole table would be wrong: the
-- top of the list would simply be the currency with the largest nominal
-- numbers, which says nothing about generosity. Instead the ranking is
-- PARTITIONED BY currency and period, so only comparable rows compete.
--   * DENSE_RANK() ranks the range WIDTH (salary_max - salary_min) - how much
--     room the employer left open. Ties share a rank and the next rank is not
--     skipped, which is why DENSE_RANK is a better fit than RANK here.
--   * salary_max and the midpoint are shown for context, and so the same
--     window-function pattern can be reused to rank by top-of-range pay.
-- Requires BOTH ends of the range, since the width cannot be computed otherwise.
-- =============================================================================
SELECT
    j.currency,
    j.salary_period,
    DENSE_RANK() OVER (
        PARTITION BY j.currency, j.salary_period
        ORDER BY (j.salary_max - j.salary_min) DESC
    )                                               AS range_width_rank,
    j.job_id,
    c.company_name,
    j.job_title,
    j.country,
    j.location,
    ROUND(j.salary_min, 2)                          AS salary_min,
    ROUND(j.salary_max, 2)                          AS salary_max,
    ROUND((j.salary_max - j.salary_min), 2)         AS salary_range_width,
    ROUND((j.salary_min + j.salary_max) / 2, 2)     AS salary_midpoint,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
WHERE j.salary_min IS NOT NULL
  AND j.salary_max IS NOT NULL
ORDER BY j.currency, j.salary_period, range_width_rank, j.job_id;


-- -----------------------------------------------------------------------------
-- 8b. HIGHEST TOP-OF-RANGE PAY, WITHIN EACH COMPARABLE GROUP
-- -----------------------------------------------------------------------------
-- Business question: "Which single posting pays the most, among postings that
-- are actually comparable?"
-- Same partitioning logic as query 8, but ranked by salary_max instead of by
-- range width.
-- =============================================================================
SELECT
    j.currency,
    j.salary_period,
    RANK() OVER (
        PARTITION BY j.currency, j.salary_period
        ORDER BY j.salary_max DESC
    )                                       AS max_salary_rank,
    j.job_id,
    c.company_name,
    j.job_title,
    j.country,
    ROUND(j.salary_max, 2)                  AS salary_max,
    ROUND(j.salary_min, 2)                  AS salary_min,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
WHERE j.salary_max IS NOT NULL
ORDER BY j.currency, j.salary_period, max_salary_rank, j.job_id;


-- =============================================================================
-- 9. JOBS WITH SALARY INFORMATION AVAILABLE
-- -----------------------------------------------------------------------------
-- Business question: "How many postings actually disclose pay?"
-- AT LEAST ONE bound is present: salary_min OR salary_max. OR (not AND) is
-- deliberate - a posting that reveals only a minimum has still disclosed
-- something. The currency and salary_period columns are printed on every row so
-- no figure can be read out of context.
-- =============================================================================
SELECT
    j.job_id,
    c.company_name,
    j.job_title,
    j.country,
    j.salary_min,
    j.salary_max,
    j.currency,
    j.salary_period,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
WHERE j.salary_min IS NOT NULL
   OR j.salary_max IS NOT NULL
ORDER BY j.posted_date DESC, j.job_id;


-- -----------------------------------------------------------------------------
-- 9b. SALARY DISCLOSURE RATE (data quality)
-- -----------------------------------------------------------------------------
-- Business question: "Can I trust salary analysis on this dataset?"
-- If disclosure is well below 100%, any average is computed on a biased subset
-- - undisclosed roles are often the lower-paid ones, so the figures are
-- optimistic by an unknown amount. Measure that before analysing, not after.
-- =============================================================================
SELECT
    COUNT(*)                                                     AS total_jobs,
    COUNT(*) FILTER (WHERE j.salary_min IS NOT NULL
                       OR j.salary_max IS NOT NULL)              AS jobs_with_any_salary,
    COUNT(*) FILTER (WHERE j.salary_min IS NOT NULL
                       AND j.salary_max IS NOT NULL)              AS jobs_with_full_range,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE j.salary_min IS NOT NULL
                                  OR j.salary_max IS NOT NULL)
        / NULLIF(COUNT(*), 0),
        2
    )                                                             AS pct_with_any_salary,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE j.salary_min IS NOT NULL
                                  AND j.salary_max IS NOT NULL)
        / NULLIF(COUNT(*), 0),
        2
    )                                                             AS pct_with_full_range
FROM jobs j;


-- =============================================================================
-- 10. JOBS WHERE salary_min AND salary_max ARE BOTH AVAILABLE
-- -----------------------------------------------------------------------------
-- Business question: "Which postings give me a complete range to work with?"
-- This is the strict subset needed for midpoint, range-width and
-- min-vs-max comparisons. Everything else in this file is a superset.
-- =============================================================================
SELECT
    j.job_id,
    c.company_name,
    j.job_title,
    j.country,
    j.location,
    j.salary_min,
    j.salary_max,
    (j.salary_max - j.salary_min)                        AS salary_range_width,
    ROUND((j.salary_min + j.salary_max) / 2, 2)          AS salary_midpoint,
    j.currency,
    j.salary_period,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
WHERE j.salary_min IS NOT NULL
  AND j.salary_max IS NOT NULL
ORDER BY j.salary_min, j.job_id;


-- -----------------------------------------------------------------------------
-- 10b. WHICH CURRENCY AND PERIOD GROUPS EXIST, AND HOW BIG IS EACH?
-- -----------------------------------------------------------------------------
-- Business question: "Where is the sample too thin to draw conclusions?"
-- Any group with a small jobs_in_group produces an average that is really just
-- one or two postings. Listing group sizes next to the averages is the cheapest
-- guard against over-interpreting them.
-- =============================================================================
SELECT
    j.currency,
    j.salary_period,
    COUNT(*)                                   AS jobs_in_group,
    ROUND(AVG((j.salary_min + j.salary_max) / 2), 2) AS avg_salary_midpoint,
    CASE
        WHEN COUNT(*) >= 5  THEN 'REASONABLE SAMPLE'
        WHEN COUNT(*) >= 2  THEN 'THIN - TREAT WITH CAUTION'
        ELSE 'SINGLE POSTING - NOT A TREND'
    END                                         AS sample_quality
FROM jobs j
WHERE j.salary_min IS NOT NULL
  AND j.salary_max IS NOT NULL
GROUP BY j.currency, j.salary_period
ORDER BY jobs_in_group DESC, j.currency, j.salary_period;
