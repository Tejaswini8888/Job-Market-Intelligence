-- =============================================================================
-- JOB MARKET INTELLIGENCE & SKILL ANALYTICS PLATFORM
-- -----------------------------------------------------------------------------
-- File      : 05_advanced_analysis.sql
-- Database  : PostgreSQL 14+
-- Stage     : Phase 5 - SQL analytics
-- Target DB : job_market_intelligence
-- Requires  : database/schema.sql + database/seed.sql
--
-- WHAT THIS FILE ANSWERS
--     1.  Rank the most demanded skills
--     2.  Rank companies by number of job postings
--     3.  Rank job titles within each industry
--     4.  Find skills appearing in multiple job categories
--     5.  Find jobs requiring both Python and SQL
--     6.  Find jobs requiring Python but not SQL
--     7.  Find the top skills for each job category
--     8.  Compare job-posting counts across months
--     9.  Calculate month-over-month job posting changes using LAG()
--     10. Identify companies with above-average job posting counts
--     11. Identify skills appearing in above-average numbers of jobs
--     12. Find the top 3 skills in each skill category using window functions
--
-- SQL FEATURES DEMONSTRATED (and where to find them)
--     JOIN                 every query - the three-table skill join
--     LEFT JOIN            2, 10, 12a  - keep rows with no matches
--     GROUP BY             every aggregate
--     HAVING               4, 10, 11
--     CASE                 1, 6, 13
--     Subqueries           1, 2, 5, 6, 10, 11  (scalar + IN)
--     CTEs                 every query that aggregates before ranking
--     Window functions     1, 2, 3, 7, 8, 9, 12
--     ROW_NUMBER()         7, 12   - always-unique position
--     RANK()               1, 2, 3  - ties share a rank, then it SKIPS
--     DENSE_RANK()         1, 12    - ties share a rank, NO gaps
--     LAG() / LEAD()       8, 9     - look at neighbouring rows
--
-- THE TWO RULES THAT MATTER MOST HERE
--   1. A window function RANKS rows; it does not AGGREGATE them. You must
--      GROUP BY first (usually in a CTE) and rank the resulting rows. Ranking
--      raw postings instead of aggregated skills is the classic mistake.
--   2. Salary is still grouped by currency and salary_period wherever it is
--      used, exactly as in 02_salary_analysis.sql.
--
-- HOW TO RUN
--   psql -U <user> -d job_market_intelligence -f database/queries/05_advanced_analysis.sql
--
-- SAFETY
--   SELECT only. No data is written and the schema is not modified.
-- =============================================================================


-- =============================================================================
-- 1. RANK THE MOST DEMANDED SKILLS
-- -----------------------------------------------------------------------------
-- Business question: "What is the ranked list of skills by market demand?"
-- Three ranking functions on the same data, side by side, because the
-- difference is only visible on a tie:
--   RANK()       1, 2, 2, 4  - two skills tied for 2nd place, so there is no 3rd
--   DENSE_RANK() 1, 2, 2, 3  - no gaps, useful as a "top N" cut-off
--   ROW_NUMBER() always unique, but arbitrary among ties - so the skill_name
--                 tie-breaker in the ORDER BY is what makes it reproducible
-- CASE turns the raw demand into an interpretable tier, which is what a
-- stakeholder actually reads.
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
    ROUND(100.0 * jobs_requiring_skill / (SELECT COUNT(*) FROM jobs), 2) AS pct_of_all_jobs,
    RANK()       OVER (ORDER BY jobs_requiring_skill DESC) AS demand_rank,
    DENSE_RANK() OVER (ORDER BY jobs_requiring_skill DESC) AS demand_dense_rank,
    CASE
        WHEN jobs_requiring_skill >= 20 THEN 'TIER 1 - ESSENTIAL'
        WHEN jobs_requiring_skill >= 10 THEN 'TIER 2 - FREQUENTLY REQUIRED'
        WHEN jobs_requiring_skill >=  5 THEN 'TIER 3 - OFTEN REQUESTED'
        ELSE 'TIER 4 - NICHE'
    END AS demand_tier
FROM skill_demand
ORDER BY jobs_requiring_skill DESC, skill_name;


-- =============================================================================
-- 2. RANK COMPANIES BY NUMBER OF JOB POSTINGS
-- -----------------------------------------------------------------------------
-- Business question: "Which employers are expanding the most right now?"
-- LEFT JOIN is essential here: an employer that has posted NOTHING is still a
-- company, and an inner join would drop it. COUNT(j.job_id) counts actual
-- postings (0 for a company with none) whereas COUNT(*) would return 1 and
-- silently report an inactive company as active.
-- salary columns are deliberately NOT averaged here - they are mixed
-- currencies and periods, so the count of postings is the honest comparison.
-- =============================================================================
WITH company_postings AS (
    SELECT
        c.company_id,
        c.company_name,
        c.industry,
        c.company_size,
        COUNT(j.job_id) AS job_postings
    FROM companies c
    LEFT JOIN jobs j
        ON j.company_id = c.company_id
    GROUP BY c.company_id, c.company_name, c.industry, c.company_size
)
SELECT
    company_name,
    industry,
    company_size,
    job_postings,
    RANK()       OVER (ORDER BY job_postings DESC) AS posting_rank,
    DENSE_RANK() OVER (ORDER BY job_postings DESC) AS posting_dense_rank,
    ROUND(100.0 * job_postings / NULLIF((SELECT SUM(job_postings) FROM company_postings), 0), 2)
        AS pct_of_all_postings
FROM company_postings
ORDER BY job_postings DESC, company_name;


-- =============================================================================
-- 3. RANK JOB TITLES WITHIN EACH INDUSTRY
-- -----------------------------------------------------------------------------
-- Business question: "Within each industry, which roles dominate hiring?"
-- PARTITION BY c.industry restarts the ranking for every industry - that is
-- the entire point, and the reason a plain RANK() would be wrong here (it
-- would rank all titles across all industries against each other).
-- The partitioned SUM adds context: a role can be ranked 1st in an industry
-- that is itself tiny, so industry_total_postings qualifies the result.
-- =============================================================================
WITH industry_title_counts AS (
    SELECT
        c.industry,
        j.job_title,
        COUNT(*) AS job_postings
    FROM jobs j
    JOIN companies c
        ON c.company_id = j.company_id
    GROUP BY c.industry, j.job_title
)
SELECT
    industry,
    job_title,
    job_postings,
    RANK() OVER (PARTITION BY industry ORDER BY job_postings DESC) AS rank_within_industry,
    ROW_NUMBER() OVER (PARTITION BY industry ORDER BY job_postings DESC, job_title) AS row_num_in_industry,
    SUM(job_postings) OVER (PARTITION BY industry) AS industry_total_postings,
    ROUND(
        100.0 * job_postings
        / NULLIF(SUM(job_postings) OVER (PARTITION BY industry), 0),
        2
    ) AS pct_of_industry_postings
FROM industry_title_counts
ORDER BY industry, rank_within_industry, job_title;


-- =============================================================================
-- 4. SKILLS APPEARING IN MULTIPLE JOB CATEGORIES
-- -----------------------------------------------------------------------------
-- Business question: "Which skills travel across roles rather than staying
-- inside one specialisation?"
-- Here "job category" means a distinct job_title (the categories a candidate
-- actually chooses between). A skill used by 8 different titles is a
-- transferable capability; a skill used by exactly 1 is a specialisation.
-- HAVING COUNT(DISTINCT j.job_title) > 1 filters AFTER aggregation, which
-- GROUP BY alone cannot do.
-- string_agg(DISTINCT ... ORDER BY ...) lists the categories; with DISTINCT the
-- ORDER BY must repeat the aggregated expression exactly.
-- =============================================================================
SELECT
    s.skill_name,
    s.skill_category,
    COUNT(DISTINCT j.job_title) AS job_categories_using_skill,
    COUNT(DISTINCT j.job_id)     AS jobs_requiring_skill,
    string_agg(DISTINCT j.job_title, ', ' ORDER BY j.job_title) AS job_categories
FROM skills s
JOIN job_skills js
    ON js.skill_id = s.skill_id
JOIN jobs j
    ON j.job_id = js.job_id
GROUP BY s.skill_name, s.skill_category
HAVING COUNT(DISTINCT j.job_title) > 1
ORDER BY job_categories_using_skill DESC, s.skill_name;


-- -----------------------------------------------------------------------------
-- 4b. SKILLS APPEARING IN MULTIPLE INDUSTRIES
-- -----------------------------------------------------------------------------
-- Business question: "Is this skill's demand industry-specific or broad?"
-- The same question as query 4, but across employers' industries rather than
-- roles. Both are worth running: a skill can span many roles inside a single
-- industry, or one role across several industries.
-- =============================================================================
SELECT
    s.skill_name,
    s.skill_category,
    COUNT(DISTINCT c.industry) AS industries_using_skill,
    COUNT(DISTINCT c.company_id) AS companies_requiring_skill,
    string_agg(DISTINCT c.industry, ', ' ORDER BY c.industry) AS industries
FROM skills s
JOIN job_skills js
    ON js.skill_id = s.skill_id
JOIN jobs j
    ON j.job_id = js.job_id
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY s.skill_name, s.skill_category
HAVING COUNT(DISTINCT c.industry) > 1
ORDER BY industries_using_skill DESC, s.skill_name;


-- =============================================================================
-- 5. FIND JOBS REQUIRING BOTH PYTHON AND SQL
-- -----------------------------------------------------------------------------
-- Business question: "Which postings require Python AND SQL together - the
-- two-skill combination employers ask for most often?"
-- EXISTS is used twice rather than self-joining job_skills to itself: EXISTS
-- stops at the first match, and it cannot duplicate a job (a self-join would
-- emit one row per matching skill pair). It also reads closer to the English
-- question - "there EXISTS a Python row AND there EXISTS a SQL row".
-- Skill names are matched case-insensitively, matching the case-insensitive
-- uniqueness index uq_skills_skill_name_lower declared in schema.sql.
-- =============================================================================
SELECT
    j.job_id,
    c.company_name,
    c.industry,
    j.job_title,
    j.location,
    j.country,
    j.work_mode,
    j.employment_type,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
WHERE EXISTS (
        SELECT 1
        FROM job_skills js
        JOIN skills s
            ON s.skill_id = js.skill_id
        WHERE js.job_id = j.job_id
          AND lower(btrim(s.skill_name)) = 'python'
      )
  AND EXISTS (
        SELECT 1
        FROM job_skills js
        JOIN skills s
            ON s.skill_id = js.skill_id
        WHERE js.job_id = j.job_id
          AND lower(btrim(s.skill_name)) = 'sql'
      )
ORDER BY j.posted_date DESC, j.job_id;


-- -----------------------------------------------------------------------------
-- 5b. THE SAME QUESTION, STATED WITH AN IN + GROUP BY + HAVING
-- -----------------------------------------------------------------------------
-- The IN-list form of query 5: an uncorrelated subquery with GROUP BY +
-- HAVING to keep only the jobs that have BOTH skills. Included deliberately:
-- comparing this against query 5 shows that two different-looking queries
-- answer the same question, and that HAVING is the filter that makes
-- "both" true - WHERE alone cannot express it.
-- >>> CHANGE ME: the two skill names inside the IN list. <<<
-- =============================================================================
SELECT
    j.job_id,
    c.company_name,
    j.job_title,
    j.country,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
WHERE j.job_id IN (
    SELECT js.job_id
    FROM job_skills js
    JOIN skills s
        ON s.skill_id = js.skill_id
    WHERE lower(btrim(s.skill_name)) IN ('python', 'sql')
    GROUP BY js.job_id
    HAVING COUNT(DISTINCT s.skill_name) = 2
)
ORDER BY j.posted_date DESC, j.job_id;


-- =============================================================================
-- 6. FIND JOBS REQUIRING PYTHON BUT NOT SQL
-- -----------------------------------------------------------------------------
-- Business question: "Which postings need Python but do NOT ask for SQL - i.e.
-- roles where Python is programming, not data querying?"
-- The negative half of query 5, and the more useful half for career advice: it
-- isolates the engineering roles from the analyst roles. NOT EXISTS is the
-- correct operator - NOT IN would behave incorrectly with NULLs, and
-- COUNT(...) = 1 would be harder to read.
-- =============================================================================
SELECT
    j.job_id,
    c.company_name,
    j.job_title,
    j.location,
    j.country,
    j.work_mode,
    j.posted_date
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
WHERE EXISTS (
        SELECT 1
        FROM job_skills js
        JOIN skills s
            ON s.skill_id = js.skill_id
        WHERE js.job_id = j.job_id
          AND lower(btrim(s.skill_name)) = 'python'
      )
  AND NOT EXISTS (
        SELECT 1
        FROM job_skills js
        JOIN skills s
            ON s.skill_id = js.skill_id
        WHERE js.job_id = j.job_id
          AND lower(btrim(s.skill_name)) = 'sql'
      )
ORDER BY j.posted_date DESC, j.job_id;


-- -----------------------------------------------------------------------------
-- 6b. SKILL SET SIGNATURE PER JOB (the complement of query 6)
-- -----------------------------------------------------------------------------
-- Business question: "What is the complete skill signature of every posting?"
-- string_agg turns each job's skill rows into one readable line, which is how
-- the two questions above ("which skills does this job have / not have") get
-- answered by eye afterwards. The ORDER BY inside string_agg makes the list
-- alphabetical, so the same job always prints the same signature.
-- =============================================================================
SELECT
    j.job_id,
    c.company_name,
    j.job_title,
    COUNT(s.skill_id) AS skills_required,
    string_agg(s.skill_name, ', ' ORDER BY s.skill_name) AS skill_signature
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
JOIN job_skills js
    ON js.job_id = j.job_id
JOIN skills s
    ON s.skill_id = js.skill_id
GROUP BY j.job_id, c.company_name, j.job_title
ORDER BY skills_required DESC, j.job_id;


-- =============================================================================
-- 7. FIND THE TOP SKILLS FOR EACH JOB CATEGORY
-- -----------------------------------------------------------------------------
-- Business question: "If I am hiring for this specific role, what are the
-- three skills I should put at the top of the job description?"
-- ROW_NUMBER() is the right function here, not RANK(): the output is a
-- cut-off ("give me the top 3"), and RANK() would return more than 3 rows
-- whenever there is a tie at position 3 - which would break the LIMIT-style
-- guarantee. The explicit skill_name tie-breaker makes the cut deterministic.
-- pct_of_role_jobs uses a correlated scalar subquery as the denominator.
-- =============================================================================
WITH role_skill_counts AS (
    SELECT
        j.job_title,
        s.skill_name,
        s.skill_category,
        COUNT(DISTINCT j.job_id) AS jobs_requiring_skill
    FROM jobs j
    JOIN job_skills js
        ON js.job_id = j.job_id
    JOIN skills s
        ON s.skill_id = js.skill_id
    GROUP BY j.job_title, s.skill_name, s.skill_category
),
ranked AS (
    SELECT
        rsc.job_title,
        rsc.skill_name,
        rsc.skill_category,
        rsc.jobs_requiring_skill,
        ROW_NUMBER() OVER (
            PARTITION BY rsc.job_title
            ORDER BY rsc.jobs_requiring_skill DESC, rsc.skill_name
        ) AS skill_rank_within_role
    FROM role_skill_counts rsc
)
SELECT
    r.job_title,
    r.skill_rank_within_role,
    r.skill_name,
    r.skill_category,
    r.jobs_requiring_skill,
    ROUND(
        100.0 * r.jobs_requiring_skill
        / NULLIF((SELECT COUNT(*) FROM jobs j2 WHERE j2.job_title = r.job_title), 0),
        2
    ) AS pct_of_role_jobs
FROM ranked r
WHERE r.skill_rank_within_role <= 3
ORDER BY r.job_title, r.skill_rank_within_role;


-- =============================================================================
-- 8. COMPARE JOB-POSTING COUNTS ACROSS MONTHS
-- -----------------------------------------------------------------------------
-- Business question: "Is the market growing or shrinking month on month?"
-- date_trunc('month', posted_date) collapses every date in a month to the same
-- value, which is the standard way to build a monthly time bucket. ::DATE casts
-- the timestamp result back to a clean date for display.
-- LAG() reads the PREVIOUS row of the ordered set; LEAD() reads the NEXT one.
-- Neither looks at the jobs table again - they walk the already-aggregated
-- monthly rows, so they cannot be confused with a self-join.
-- CAVEAT: a month with 0 postings produces NO row at all, so "previous month"
-- silently skips it and the change figure spans two months. With continuous
-- monthly data that is harmless; with gaps it is a real distortion.
-- =============================================================================
WITH monthly_postings AS (
    SELECT
        date_trunc('month', posted_date)::DATE AS posting_month,
        COUNT(*)                              AS jobs_posted,
        COUNT(DISTINCT company_id)            AS companies_hiring
    FROM jobs
    GROUP BY date_trunc('month', posted_date)::DATE
)
SELECT
    posting_month,
    jobs_posted,
    companies_hiring,
    LAG(jobs_posted)  OVER (ORDER BY posting_month) AS previous_month_jobs,
    LEAD(jobs_posted) OVER (ORDER BY posting_month) AS next_month_jobs,
    jobs_posted - LAG(jobs_posted) OVER (ORDER BY posting_month) AS change_vs_previous_month
FROM monthly_postings
ORDER BY posting_month;


-- =============================================================================
-- 9. MONTH-OVER-MONTH JOB POSTING CHANGES USING LAG()
-- -----------------------------------------------------------------------------
-- Business question: "By how much did postings change month on month, in
-- absolute and percentage terms?"
-- The canonical use of LAG(): compare each month with the one immediately
-- before it. Three details that make this correct rather than merely running:
--   * ORDER BY inside OVER fixes WHICH row "previous" means. Without it the
--     result is undefined.
--   * NULLIF(LAG(...), 0) prevents division by zero in a month whose predecessor
--     had no postings. LAG() returns NULL for the first row, and NULL division
--     is NULL, not an error - so the earliest month correctly has no change.
--   * 100.0 (not 100) forces NUMERIC arithmetic, so the percentage is exact
--     and ROUND(..., 2) does not hit a float artefact.
-- =============================================================================
WITH monthly_postings AS (
    SELECT
        date_trunc('month', posted_date)::DATE AS posting_month,
        COUNT(*)                              AS jobs_posted
    FROM jobs
    GROUP BY date_trunc('month', posted_date)::DATE
)
SELECT
    posting_month,
    jobs_posted,
    LAG(jobs_posted) OVER (ORDER BY posting_month) AS previous_month_jobs,
    jobs_posted - LAG(jobs_posted) OVER (ORDER BY posting_month) AS change_vs_previous_month,
    ROUND(
        100.0 * (jobs_posted - LAG(jobs_posted) OVER (ORDER BY posting_month))
        / NULLIF(LAG(jobs_posted) OVER (ORDER BY posting_month), 0),
        2
    ) AS pct_change_vs_previous_month,
    CASE
        WHEN LAG(jobs_posted) OVER (ORDER BY posting_month) IS NULL
            THEN 'FIRST MONTH IN DATA'
        WHEN jobs_posted > LAG(jobs_posted) OVER (ORDER BY posting_month)
            THEN 'INCREASE'
        WHEN jobs_posted < LAG(jobs_posted) OVER (ORDER BY posting_month)
            THEN 'DECREASE'
        ELSE 'NO CHANGE'
    END AS month_over_month_trend
FROM monthly_postings
ORDER BY posting_month;


-- -----------------------------------------------------------------------------
-- 9b. THREE-MONTH MOVING AVERAGE (a window over an aggregate, without GROUP BY)
-- -----------------------------------------------------------------------------
-- Business question: "Smoothed out, is posting volume rising?"
-- ROWS BETWEEN 2 PRECEDING AND CURRENT ROW is a moving window: the average of
-- this month and the two before it. The first two months average over fewer
-- than three rows, which is visible in the count column instead of being
-- silently wrong.
-- =============================================================================
WITH monthly_postings AS (
    SELECT
        date_trunc('month', posted_date)::DATE AS posting_month,
        COUNT(*)                              AS jobs_posted
    FROM jobs
    GROUP BY date_trunc('month', posted_date)::DATE
)
SELECT
    posting_month,
    jobs_posted,
    COUNT(*) OVER (
        ORDER BY posting_month
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS months_in_window,
    ROUND(
        AVG(jobs_posted) OVER (
            ORDER BY posting_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS moving_avg_3_months
FROM monthly_postings
ORDER BY posting_month;


-- =============================================================================
-- 10. IDENTIFY COMPANIES WITH ABOVE-AVERAGE JOB POSTING COUNTS
-- -----------------------------------------------------------------------------
-- Business question: "Which employers are hiring more than a typical employer?"
-- The average is taken over PER-COMPANY counts, not over raw postings.
-- AVG(j.job_id) over the jobs table would return the average number of jobs
-- attached to a posting, which is nonsense; the subquery first reduces to one
-- row per company, and only then averages those rows. That is why the average
-- lives in a CTE instead of being written inline.
-- The subquery is repeated in the WHERE clause on purpose - it is identical,
-- and repeating it keeps the filter and the displayed benchmark provably the
-- same number. The CTE below avoids the repetition.
-- =============================================================================
WITH company_postings AS (
    SELECT
        c.company_id,
        c.company_name,
        c.industry,
        COUNT(j.job_id) AS job_postings
    FROM companies c
    LEFT JOIN jobs j
        ON j.company_id = c.company_id
    GROUP BY c.company_id, c.company_name, c.industry
),
benchmark AS (
    -- The "typical employer" number: one average across all company rows.
    SELECT
        ROUND(AVG(job_postings), 2) AS avg_postings_per_company,
        COUNT(*)                   AS companies_compared
    FROM company_postings
)
SELECT
    cp.company_name,
    cp.industry,
    cp.job_postings,
    b.avg_postings_per_company,
    ROUND(cp.job_postings - b.avg_postings_per_company, 2) AS postings_above_average,
    b.companies_compared
FROM company_postings cp
CROSS JOIN benchmark b
WHERE cp.job_postings > b.avg_postings_per_company
ORDER BY cp.job_postings DESC, cp.company_name;


-- =============================================================================
-- 11. IDENTIFY SKILLS APPEARING IN ABOVE-AVERAGE NUMBERS OF JOBS
-- -----------------------------------------------------------------------------
-- Business question: "Which skills are genuinely over-indexed in this market,
-- rather than just popular because most postings are technical?"
-- Same shape as query 10 - reduce to one row per entity, benchmark the average
-- over those rows, then compare - but applied to skills. DENSE_RANK() is used
-- here rather than RANK() so that a run of tied skills is numbered 1, 2, 3
-- with no gap, which makes "top 3 skills" a clean cut.
-- =============================================================================
WITH skill_demand AS (
    SELECT
        s.skill_id,
        s.skill_name,
        s.skill_category,
        COUNT(DISTINCT j.job_id) AS jobs_requiring_skill
    FROM skills s
    JOIN job_skills js
        ON js.skill_id = s.skill_id
    JOIN jobs j
        ON j.job_id = js.job_id
    GROUP BY s.skill_id, s.skill_name, s.skill_category
),
benchmark AS (
    SELECT ROUND(AVG(jobs_requiring_skill), 2) AS avg_jobs_per_skill
    FROM skill_demand
)
SELECT
    sd.skill_name,
    sd.skill_category,
    sd.jobs_requiring_skill,
    b.avg_jobs_per_skill,
    ROUND(sd.jobs_requiring_skill - b.avg_jobs_per_skill, 2) AS jobs_above_average,
    DENSE_RANK() OVER (ORDER BY sd.jobs_requiring_skill DESC) AS skill_demand_dense_rank
FROM skill_demand sd
CROSS JOIN benchmark b
WHERE sd.jobs_requiring_skill > b.avg_jobs_per_skill
ORDER BY sd.jobs_requiring_skill DESC, sd.skill_name;


-- =============================================================================
-- 12. TOP 3 SKILLS IN EACH SKILL CATEGORY USING WINDOW FUNCTIONS
-- -----------------------------------------------------------------------------
-- Business question: "Within every category of skill, which three dominate?"
-- PARTITION BY s.skill_category restarts the ranking for each category, so
-- three rows come back per category rather than three rows for the market.
-- ROW_NUMBER, RANK and DENSE_RANK are all shown on the same data so the
-- effect of ties is visible: on a tie, RANK() skips a position and
-- DENSE_RANK() does not, while ROW_NUMBER() always increments. A category whose
-- 3rd and 4th skills are tied returns 4 rows with RANK() but exactly 3 with
-- ROW_NUMBER() - which is why the cut-off below uses ROW_NUMBER().
-- Only skills with real demand appear: the inner JOIN drops dictionary entries
-- no posting has ever asked for (see query 12a for that list).
-- =============================================================================
WITH skill_demand AS (
    SELECT
        s.skill_id,
        s.skill_category,
        s.skill_name,
        COUNT(DISTINCT j.job_id) AS jobs_requiring_skill
    FROM skills s
    JOIN job_skills js
        ON js.skill_id = s.skill_id
    JOIN jobs j
        ON j.job_id = js.job_id
    GROUP BY s.skill_id, s.skill_category, s.skill_name
),
ranked AS (
    SELECT
        skill_category,
        skill_name,
        jobs_requiring_skill,
        ROW_NUMBER() OVER (
            PARTITION BY skill_category
            ORDER BY jobs_requiring_skill DESC, skill_name
        ) AS row_num_in_category,
        RANK() OVER (
            PARTITION BY skill_category
            ORDER BY jobs_requiring_skill DESC
        ) AS rank_in_category,
        DENSE_RANK() OVER (
            PARTITION BY skill_category
            ORDER BY jobs_requiring_skill DESC
        ) AS dense_rank_in_category
    FROM skill_demand
)
SELECT
    skill_category,
    skill_name,
    jobs_requiring_skill,
    row_num_in_category,
    rank_in_category,
    dense_rank_in_category
FROM ranked
WHERE row_num_in_category <= 3
ORDER BY skill_category, row_num_in_category;


-- =============================================================================
-- 12a. SKILLS WITH NO DEMAND (LEFT JOIN, the honest denominator)
-- -----------------------------------------------------------------------------
-- Business question: "How many skills in our dictionary are dead weight?"
-- LEFT JOIN keeps unused skills; an inner join would drop them silently.
-- WHERE js.job_id IS NULL selects them - COUNT(js.job_id) cannot be used for
-- this test, because COUNT ignores NULLs and would return 0 for used skills
-- too. This matters because every "percentage of skills" denominator elsewhere
-- quietly assumes the dictionary contains no dead entries.
-- NOTE: on a clean dataset this returns ZERO rows, which is the correct and
-- desirable result. An empty result is information, not a failed query.
-- =============================================================================
SELECT
    s.skill_name,
    s.skill_category
FROM skills s
LEFT JOIN job_skills js
    ON js.skill_id = s.skill_id
WHERE js.job_id IS NULL
ORDER BY s.skill_category, s.skill_name;


-- -----------------------------------------------------------------------------
-- 12b. SKILL DICTIONARY COVERAGE (scalar subquery, no GROUP BY needed)
-- -----------------------------------------------------------------------------
-- Business question: "What share of the skill dictionary is actually used?"
-- The same NOT EXISTS test as 12a, reduced to a single number, so the answer
-- survives even when the row list is empty.
-- =============================================================================
SELECT
    (SELECT COUNT(*) FROM skills)                          AS skills_in_dictionary,
    (SELECT COUNT(*) FROM skills s2
      WHERE NOT EXISTS (
          SELECT 1
          FROM job_skills js2
          WHERE js2.skill_id = s2.skill_id
      ))                                                  AS skills_with_zero_demand,
    (SELECT COUNT(*) FROM job_skills)                      AS total_skill_job_links,
    ROUND(
        100.0 * (SELECT COUNT(*) FROM skills s3
                  WHERE NOT EXISTS (
                      SELECT 1
                      FROM job_skills js3
                      WHERE js3.skill_id = s3.skill_id
                  ))
        / NULLIF((SELECT COUNT(*) FROM skills), 0),
        2
    )                                                      AS pct_dictionary_unused;


-- =============================================================================
-- 13. SENIORITY PROFILE OF THE MARKET USING CASE
-- -----------------------------------------------------------------------------
-- Business question: "What is the entry-level vs senior split of the market?"
-- CASE buckets the raw experience_min into interpretable bands, then the
-- counts are aggregated over the CASE result. Grouping by the CASE expression
-- (or, more simply, by the underlying column and selecting the CASE) gives the
-- same result; here the band is grouped directly.
-- Missing experience is NOT folded into the entry-level band - it gets its own
-- 'NOT SPECIFIED' band, so undisclosed requirements can never inflate the
-- junior share.
-- =============================================================================
SELECT
    CASE
        WHEN j.experience_min IS NULL THEN 'NOT SPECIFIED'
        WHEN j.experience_min = 0      THEN 'ENTRY (0 years)'
        WHEN j.experience_min <= 2     THEN 'JUNIOR (1-2 years)'
        WHEN j.experience_min <= 5     THEN 'MID (3-5 years)'
        WHEN j.experience_min <= 8     THEN 'SENIOR (6-8 years)'
        ELSE 'STAFF / PRINCIPAL (9+ years)'
    END                                        AS seniority_band,
    COUNT(*)                                   AS jobs_posted,
    COUNT(DISTINCT c.company_id)               AS companies_hiring,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM jobs), 2) AS pct_of_all_jobs,
    ROUND(AVG((j.experience_min + j.experience_max) / 2.0), 2)
                                                AS avg_experience_midpoint_years
FROM jobs j
JOIN companies c
    ON c.company_id = j.company_id
GROUP BY
    CASE
        WHEN j.experience_min IS NULL THEN 'NOT SPECIFIED'
        WHEN j.experience_min = 0      THEN 'ENTRY (0 years)'
        WHEN j.experience_min <= 2     THEN 'JUNIOR (1-2 years)'
        WHEN j.experience_min <= 5     THEN 'MID (3-5 years)'
        WHEN j.experience_min <= 8     THEN 'SENIOR (6-8 years)'
        ELSE 'STAFF / PRINCIPAL (9+ years)'
    END
ORDER BY jobs_posted DESC;


-- =============================================================================
-- 14. MARKET SUMMARY - ONE ROW, THE EXECUTIVE VIEW
-- -----------------------------------------------------------------------------
-- Business question: "Give me the five headline numbers of this market."
-- A single row is the right shape for a dashboard KPI strip or an API
-- /summary endpoint. salary-disclosure is included because it qualifies every
-- salary number in the project (see 02_salary_analysis.sql query 9b).
-- No salary averaging happens here: currencies and periods are not
-- comparable, so the honest summary reports coverage, not amounts.
-- =============================================================================
SELECT
    (SELECT COUNT(*) FROM companies)                                    AS total_companies,
    (SELECT COUNT(*) FROM jobs)                                        AS total_jobs,
    (SELECT COUNT(*) FROM skills)                                      AS total_skills,
    (SELECT COUNT(*) FROM job_skills)                                  AS total_skill_requirements,
    (SELECT COUNT(DISTINCT j.job_title) FROM jobs)                     AS distinct_job_titles,
    (SELECT COUNT(DISTINCT j.country) FROM jobs)                       AS distinct_countries,
    (SELECT COUNT(DISTINCT j.work_mode) FROM jobs)                     AS distinct_work_modes,
    (SELECT MIN(posted_date) FROM jobs)                                AS earliest_posted_date,
    (SELECT MAX(posted_date) FROM jobs)                                AS latest_posted_date,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE j.salary_min IS NOT NULL
                                  OR j.salary_max IS NOT NULL)
        / NULLIF(COUNT(*), 0),
        2
    )                                                                  AS pct_jobs_with_salary,
    (SELECT COUNT(*) FROM (SELECT DISTINCT j.currency, j.salary_period
                           FROM jobs j
                           WHERE j.salary_min IS NOT NULL) x)         AS distinct_salary_units
FROM jobs j;
