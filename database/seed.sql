-- =============================================================================
-- JOB MARKET INTELLIGENCE & SKILL ANALYTICS PLATFORM
-- -----------------------------------------------------------------------------
-- File      : seed.sql
-- Stage     : Development Seed Data
-- Target DB : job_market_intelligence   (development only)
-- Requires  : database/schema.sql must be applied first
--
-- ############################################################################
-- #  SYNTHETIC DEVELOPMENT DATA - NOT REAL MARKET DATA                       #
-- #                                                                          #
-- #  Every company, person-free posting, salary figure and date in this file #
-- #  was INVENTED for local development and testing only.                     #
-- #                                                                          #
-- #  * No website was scraped.                                               #
-- #  * No API was called.                                                    #
-- #  * No job-posting text was copied from any source.                       #
-- #  * No real people, names, contact details or personal data appear here.  #
-- #  * Company names are fictional and do not refer to real employers.       #
-- #                                                                          #
-- #  The rows are engineered to be ANALYTICALLY REALISTIC (so that the SQL   #
-- #  analytics, API and dashboard have meaningful patterns to work on), but  #
-- #  the numbers are not measurements of any real labour market.             #
-- #                                                                          #
-- #  Do not present any figure derived from this file as a market finding.   #
-- ############################################################################
--
-- WHAT IT INSERTS
--   companies  : 15   fictional employers across 14 industries
--   jobs       : 40   fictional postings, 12 distinct job titles
--   skills     : 32   real technology / skill names in 10 categories
--   job_skills : 242  role-appropriate skill links (4-8 per job)
--
-- ID RANGE WARNING
--   This file uses EXPLICIT primary keys (companies 1-15, jobs 1-40,
--   skills 1-32) so that the job_skills rows are readable and reviewable by
--   a human. IDs therefore collide with anything already in the tables, which
--   is exactly why the script starts by TRUNCATE-ing them (RESET IDENTITY).
--   If you ever need to keep existing rows and add seed rows on top, say so
--   and this will be rewritten to capture IDs with INSERT ... RETURNING.
--
-- SAFETY
--   * The DO block below ABORTS unless the connected database is exactly
--     'job_market_intelligence'. Run it against the wrong database and
--     nothing happens.
--   * Everything runs inside a single transaction, so the database is either
--     fully seeded or completely untouched.
--   * No DROP, TRUNCATE or DELETE outside this transaction.
--   * ON_ERROR_STOP is set by the runner command at the bottom of this file.
--
-- HOW TO APPLY
--   psql -U <user> -d job_market_intelligence -v ON_ERROR_STOP=1 -f database/seed.sql
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- =============================================================================
-- 0. SAFETY GUARD - abort unless we are on the development database
-- =============================================================================
DO $$
BEGIN
    IF current_database() <> 'job_market_intelligence' THEN
        RAISE EXCEPTION
            'SEED ABORTED: this script may only run on the development database '
            '"job_market_intelligence", but the current database is "%".',
            current_database();
    END IF;
END
$$;


-- =============================================================================
-- 0b. RESET - makes this file re-runnable and keeps explicit IDs valid
--     Order follows foreign-key dependencies (children before parents).
-- =============================================================================
TRUNCATE TABLE job_skills, jobs, skills, companies RESTART IDENTITY CASCADE;


-- =============================================================================
-- 1. companies  (15 rows)
--    Fictional employers spanning 14 industries so that "skills by industry"
--    analysis is meaningful. Company names are invented.
-- =============================================================================
INSERT INTO companies
    (company_id, company_name, industry, company_size, headquarters)
VALUES
    ( 1, 'Novabyte Technologies',       'Information Technology',     'XLARGE_501_1000',      'Bengaluru, India'),
    ( 2, 'Cobalt Financial Services',   'Finance',                   'ENTERPRISE_1000_PLUS', 'Mumbai, India'),
    ( 3, 'Meridian Health Systems',     'Healthcare',                'LARGE_201_500',        'Singapore'),
    ( 4, 'Brightcart Commerce',         'E-commerce',                'MEDIUM_51_200',        'Bengaluru, India'),
    ( 5, 'Vantage Consulting Group',    'Consulting',                'SMALL_11_50',          'Delhi, India'),
    ( 6, 'TelcoNova Networks',          'Telecommunications',        'ENTERPRISE_1000_PLUS', 'Chennai, India'),
    ( 7, 'Skyline SaaS Labs',           'Software as a Service',     'SMALL_11_50',          'Hyderabad, India'),
    ( 8, 'Ironclad Security',           'Cybersecurity',             'MICRO_1_10',           'Pune, India'),
    ( 9, 'Greenfield Logistics',        'Logistics & Supply Chain',  'LARGE_201_500',        'Nagpur, India'),
    (10, 'Aurora Retail Analytics',     'Retail',                    'MEDIUM_51_200',        'Kolkata, India'),
    (11, 'Pinnacle Capital Markets',    'Financial Services',        'XLARGE_501_1000',      'London, United Kingdom'),
    (12, 'Helix Biotech',               'Biotechnology',             'SMALL_11_50',          'Boston, United States'),
    (13, 'Quantum Leap Education',      'Education Technology',      'MICRO_1_10',           'Toronto, Canada'),
    (14, 'Orbit Media Streaming',       'Entertainment & Media',     'MEDIUM_51_200',        'Sydney, Australia'),
    (15, 'Zenith Manufacturing Systems','Manufacturing',             'LARGE_201_500',        'Stuttgart, Germany');


-- =============================================================================
-- 2. skills  (32 rows)
--    Skill names are real technologies. Categories are analytical groupings
--    used later for aggregation. Covers all categories required by the spec
--    plus "Big Data" for the ingestion/orchestration tooling.
-- =============================================================================
INSERT INTO skills
    (skill_id, skill_name, skill_category)
VALUES
    -- Programming Language -------------------------------------------------
    ( 1, 'Python',                        'Programming Language'),
    ( 2, 'Java',                          'Programming Language'),
    ( 3, 'C++',                           'Programming Language'),
    ( 4, 'SQL',                           'Programming Language'),
    -- Database -------------------------------------------------------------
    ( 5, 'PostgreSQL',                    'Database'),
    ( 6, 'MySQL',                         'Database'),
    ( 7, 'MongoDB',                       'Database'),
    -- Cloud ----------------------------------------------------------------
    ( 8, 'AWS',                           'Cloud'),
    ( 9, 'Azure',                         'Cloud'),
    -- DevOps ----------------------------------------------------------------
    (10, 'Docker',                        'DevOps'),
    (11, 'Kubernetes',                    'DevOps'),
    (13, 'Linux',                         'DevOps'),
    (23, 'Terraform',                     'DevOps'),
    (24, 'Jenkins',                       'DevOps'),
    -- Web Development ------------------------------------------------------
    (14, 'FastAPI',                       'Web Development'),
    (15, 'React',                         'Web Development'),
    -- Data Science ---------------------------------------------------------
    (16, 'Pandas',                        'Data Science'),
    (17, 'NumPy',                         'Data Science'),
    (30, 'Tableau',                       'Data Science'),
    -- Machine Learning -----------------------------------------------------
    (18, 'Scikit-learn',                  'Machine Learning'),
    (19, 'TensorFlow',                    'Machine Learning'),
    (20, 'PyTorch',                       'Machine Learning'),
    (27, 'Machine Learning',              'Machine Learning'),
    (28, 'Deep Learning',                 'Machine Learning'),
    (29, 'Natural Language Processing',   'Machine Learning'),
    -- Big Data -------------------------------------------------------------
    (21, 'Apache Spark',                  'Big Data'),
    (22, 'Apache Airflow',                'Big Data'),
    -- Tools / Observability ------------------------------------------------
    (12, 'Git',                           'Tools'),
    (25, 'Prometheus',                    'Tools'),
    (26, 'Grafana',                       'Tools'),
    -- Security -------------------------------------------------------------
    (31, 'Threat Detection',              'Security'),
    (32, 'Penetration Testing',           'Security');


-- =============================================================================
-- 3. jobs  (40 rows)
--
--    Engineered so the analytics questions are answerable:
--      * Python is the most demanded skill (31 of 40 postings)
--      * every job title appears between 2 and 5 times
--      * all 15 companies post at least one job
--      * work_mode, employment_type, experience level, currency, salary period
--        and posting date are all varied across 12 months
--      * job 24 has NO salary (companies do hide pay) so that "salary is
--        disclosed" can be measured rather than assumed to be 100%
--      * salary min <= max everywhere, experience min <= max everywhere
--      * currency always matches the country of the posting
--    Descriptions are short, original and synthetic - no posting was copied.
-- =============================================================================
INSERT INTO jobs
    (job_id, company_id, job_title, location, country, employment_type, work_mode,
     experience_min, experience_max, salary_min, salary_max, currency, salary_period,
     posted_date, description)
VALUES
-- Data Analyst (5) -----------------------------------------------------------
    ( 1,  1, 'Data Analyst',        'Bengaluru', 'IN', 'FULL_TIME', 'HYBRID',
        0,  2,  600000.00,  900000.00, 'INR', 'YEARLY', DATE '2026-08-24',
        'Synthetic sample posting. Support product and growth reporting using SQL and Python, and turn results into dashboards for non-technical stakeholders.'),
    ( 2, 10, 'Data Analyst',        'Kolkata',   'IN', 'FULL_TIME', 'ONSITE',
        1,  3,  500000.00,  800000.00, 'INR', 'YEARLY', DATE '2026-07-15',
        'Synthetic sample posting. Build daily sales and inventory reports for the retail analytics team and maintain the existing reporting layer.'),
    ( 3, 11, 'Data Analyst',        'London',    'GB', 'FULL_TIME', 'HYBRID',
        2,  5,   55000.00,   75000.00, 'GBP', 'YEARLY', DATE '2026-06-30',
        'Synthetic sample posting. Analyse risk and pricing data for a financial services client and produce recurring performance packs.'),
    ( 4,  2, 'Data Analyst',        'Mumbai',    'IN', 'CONTRACT',  'REMOTE',
        1,  4,   60000.00,   90000.00, 'INR', 'MONTHLY', DATE '2026-09-02',
        'Synthetic sample posting. Six-month engagement automating regulatory reporting for the lending business.'),
    ( 5, 13, 'Data Analyst',        'Toronto',   'CA', 'PART_TIME', 'REMOTE',
        1,  3,   45000.00,   65000.00, 'CAD', 'YEARLY', DATE '2026-05-19',
        'Synthetic sample posting. Part-time analysis support for an education platform, focused on enrolment and retention metrics.'),

-- Data Scientist (4) ---------------------------------------------------------
    ( 6,  1, 'Data Scientist',      'Bengaluru', 'IN', 'FULL_TIME', 'HYBRID',
        2,  5, 1200000.00, 2000000.00, 'INR', 'YEARLY', DATE '2026-08-11',
        'Synthetic sample posting. Develop customer segmentation models and measure their effect on retention.'),
    ( 7,  3, 'Data Scientist',      'Singapore', 'SG', 'FULL_TIME', 'HYBRID',
        3,  6,   90000.00,  140000.00, 'SGD', 'YEARLY', DATE '2026-07-28',
        'Synthetic sample posting. Model patient readmission risk using clinical and operational data, with strict governance review.'),
    ( 8, 12, 'Data Scientist',      'Boston',    'US', 'FULL_TIME', 'ONSITE',
        4,  8,  110000.00,  160000.00, 'USD', 'YEARLY', DATE '2026-06-12',
        'Synthetic sample posting. Research scientist role building image-based models for assay analysis in a biotech laboratory setting.'),
    ( 9,  6, 'Data Scientist',      'Chennai',   'IN', 'FULL_TIME', 'REMOTE',
        3,  7, 1400000.00, 2400000.00, 'INR', 'YEARLY', DATE '2026-09-05',
        'Synthetic sample posting. Analyse network telemetry to predict subscriber churn and network congestion.'),

-- Machine Learning Engineer (4) ----------------------------------------------
    (10,  7, 'Machine Learning Engineer', 'Hyderabad', 'IN', 'FULL_TIME', 'HYBRID',
        3,  6, 1800000.00, 3000000.00, 'INR', 'YEARLY', DATE '2026-08-05',
        'Synthetic sample posting. Take scoring models from notebook to production, including feature pipelines, evaluation and monitoring.'),
    (11, 11, 'Machine Learning Engineer', 'London',    'GB', 'FULL_TIME', 'HYBRID',
        4,  8,   85000.00,  125000.00, 'GBP', 'YEARLY', DATE '2026-05-28',
        'Synthetic sample posting. Build fraud detection models for payments traffic, working with the risk modelling team.'),
    (12, 14, 'Machine Learning Engineer', 'Sydney',    'AU', 'FULL_TIME', 'REMOTE',
        3,  7,  130000.00,  180000.00, 'AUD', 'YEARLY', DATE '2026-07-07',
        'Synthetic sample posting. Recommend content using ranking models across a streaming catalogue.'),
    (13, 12, 'Machine Learning Engineer', 'Boston',    'US', 'CONTRACT',  'REMOTE',
        5,  9,      80.00,     130.00, 'USD', 'HOURLY',  DATE '2026-04-21',
        'Synthetic sample posting. Nine-month contract to fine-tune language models on proprietary scientific text.'),

-- AI Engineer (3) ------------------------------------------------------------
    (14,  1, 'AI Engineer',        'Bengaluru', 'IN', 'FULL_TIME', 'HYBRID',
        3,  6, 2000000.00, 3500000.00, 'INR', 'YEARLY', DATE '2026-09-10',
        'Synthetic sample posting. Design and deploy document understanding services for internal automation.'),
    (15,  3, 'AI Engineer',        'Singapore', 'SG', 'FULL_TIME', 'ONSITE',
        4,  8,  120000.00,  175000.00, 'SGD', 'YEARLY', DATE '2026-06-05',
        'Synthetic sample posting. Apply language models to clinical documentation workflows, with human review built in.'),
    (16,  5, 'AI Engineer',        'Delhi',     'IN', 'FULL_TIME', 'REMOTE',
        2,  5, 1500000.00, 2400000.00, 'INR', 'YEARLY', DATE '2026-08-18',
        'Synthetic sample posting. Prototype machine learning solutions for client engagements in the consulting practice.'),

-- Backend Engineer (4) -------------------------------------------------------
    (17,  4, 'Backend Engineer',    'Bengaluru', 'IN', 'FULL_TIME', 'ONSITE',
        2,  5, 1200000.00, 2200000.00, 'INR', 'YEARLY', DATE '2026-07-21',
        'Synthetic sample posting. Build and maintain order and payments services for a high-traffic storefront.'),
    (18,  7, 'Backend Engineer',    'Hyderabad', 'IN', 'FULL_TIME', 'REMOTE',
        3,  6, 1600000.00, 2800000.00, 'INR', 'YEARLY', DATE '2026-08-30',
        'Synthetic sample posting. Develop multi-tenant billing APIs and event-driven integrations for a SaaS product.'),
    (19, 14, 'Backend Engineer',    'Sydney',    'AU', 'FULL_TIME', 'HYBRID',
        3,  7,  110000.00,  150000.00, 'AUD', 'YEARLY', DATE '2026-05-14',
        'Synthetic sample posting. Scale the playback API and reduce latency for streaming subscribers.'),
    (20,  6, 'Backend Engineer',    'Chennai',   'IN', 'FULL_TIME', 'ONSITE',
        1,  4,  900000.00, 1600000.00, 'INR', 'YEARLY', DATE '2026-09-12',
        'Synthetic sample posting. Maintain internal provisioning and billing services for a telecom operator.'),

-- Software Engineer (4) ------------------------------------------------------
    (21,  4, 'Software Engineer',   'Bengaluru', 'IN', 'FULL_TIME', 'HYBRID',
        1,  4, 1100000.00, 2000000.00, 'INR', 'YEARLY', DATE '2026-08-14',
        'Synthetic sample posting. Full-stack work on the seller console, spanning the interface and its supporting services.'),
    (22,  9, 'Software Engineer',   'Nagpur',    'IN', 'FULL_TIME', 'ONSITE',
        0,  3,  600000.00, 1100000.00, 'INR', 'YEARLY', DATE '2026-06-25',
        'Synthetic sample posting. Graduate role building shipment tracking features and internal tooling.'),
    (23, 15, 'Software Engineer',   'Stuttgart', 'DE', 'FULL_TIME', 'HYBRID',
        2,  5,   65000.00,   90000.00, 'EUR', 'YEARLY', DATE '2026-07-02',
        'Synthetic sample posting. Develop production software for industrial equipment monitoring.'),
    (24, 13, 'Software Engineer',   'Toronto',   'CA', 'INTERNSHIP', 'ONSITE',
        0,  1,        NULL,        NULL,  NULL,   NULL,    DATE '2026-09-01',
        'Synthetic sample posting. Six-month internship on the learning platform web team. Salary not disclosed, as is common for internships.'),

-- DevOps Engineer (3) --------------------------------------------------------
    (25,  1, 'DevOps Engineer',     'Bengaluru', 'IN', 'FULL_TIME', 'HYBRID',
        3,  6, 1600000.00, 2800000.00, 'INR', 'YEARLY', DATE '2026-08-20',
        'Synthetic sample posting. Own deployment pipelines, container platforms and infrastructure as code across teams.'),
    (26,  7, 'DevOps Engineer',     'Hyderabad', 'IN', 'FULL_TIME', 'REMOTE',
        2,  6, 1400000.00, 2500000.00, 'INR', 'YEARLY', DATE '2026-07-14',
        'Synthetic sample posting. Improve release automation and service observability for a SaaS platform.'),
    (27, 15, 'DevOps Engineer',     'Stuttgart', 'DE', 'FULL_TIME', 'ONSITE',
        3,  7,   70000.00,   95000.00, 'EUR', 'YEARLY', DATE '2026-05-06',
        'Synthetic sample posting. Manage build and release tooling for manufacturing software delivery.'),

-- Cloud Engineer (3) ---------------------------------------------------------
    (28, 11, 'Cloud Engineer',      'London',    'GB', 'FULL_TIME', 'HYBRID',
        3,  7,   75000.00,  105000.00, 'GBP', 'YEARLY', DATE '2026-06-18',
        'Synthetic sample posting. Migrate on-premise workloads to public cloud and codify infrastructure with Terraform.'),
    (29,  2, 'Cloud Engineer',      'Mumbai',    'IN', 'FULL_TIME', 'ONSITE',
        2,  5, 1400000.00, 2400000.00, 'INR', 'YEARLY', DATE '2026-09-15',
        'Synthetic sample posting. Deliver cloud landing zone controls and container platform services for a bank.'),
    (30, 12, 'Cloud Engineer',      'Boston',    'US', 'CONTRACT',  'REMOTE',
        3,  6,      85.00,     125.00, 'USD', 'HOURLY',  DATE '2026-04-08',
        'Synthetic sample posting. Short contract to harden cloud environments for a research organisation.'),

-- Site Reliability Engineer (2) ----------------------------------------------
    (31,  6, 'Site Reliability Engineer', 'Chennai', 'IN', 'FULL_TIME', 'HYBRID',
        4,  8, 1800000.00, 3000000.00, 'INR', 'YEARLY', DATE '2026-08-27',
        'Synthetic sample posting. Improve reliability of a large-scale network platform through monitoring, alerting and incident practice.'),
    (32, 14, 'Site Reliability Engineer', 'Sydney',  'AU', 'FULL_TIME', 'REMOTE',
        3,  6,  120000.00,  165000.00, 'AUD', 'YEARLY', DATE '2026-06-20',
        'Synthetic sample posting. Set and maintain service level objectives for streaming infrastructure.'),

-- Data Engineer (3) ----------------------------------------------------------
    (33,  1, 'Data Engineer',       'Bengaluru', 'IN', 'FULL_TIME', 'HYBRID',
        3,  6, 1500000.00, 2600000.00, 'INR', 'YEARLY', DATE '2026-08-02',
        'Synthetic sample posting. Design batch and streaming pipelines and keep warehouse data quality high.'),
    (34, 10, 'Data Engineer',       'Kolkata',   'IN', 'FULL_TIME', 'ONSITE',
        2,  5, 1000000.00, 1800000.00, 'INR', 'YEARLY', DATE '2026-07-08',
        'Synthetic sample posting. Build and orchestrate data pipelines feeding retail analytics dashboards.'),
    (35,  3, 'Data Engineer',       'Singapore', 'SG', 'FULL_TIME', 'ONSITE',
        4,  7,   85000.00,  120000.00, 'SGD', 'YEARLY', DATE '2026-05-11',
        'Synthetic sample posting. Build governed clinical data pipelines and integration interfaces.'),

-- Business Analyst (2) -------------------------------------------------------
    (36,  2, 'Business Analyst',    'Mumbai',    'IN', 'FULL_TIME', 'HYBRID',
        3,  6, 1300000.00, 2200000.00, 'INR', 'YEARLY', DATE '2026-09-08',
        'Synthetic sample posting. Translate business requirements into analytics specifications for the lending teams.'),
    (37,  5, 'Business Analyst',    'Delhi',     'IN', 'FULL_TIME', 'ONSITE',
        2,  5, 1100000.00, 1900000.00, 'INR', 'YEARLY', DATE '2026-06-09',
        'Synthetic sample posting. Support client engagements with requirement analysis and reporting specifications.'),

-- Cybersecurity Engineer (3) -------------------------------------------------
    (38,  8, 'Cybersecurity Engineer', 'Pune',    'IN', 'FULL_TIME', 'HYBRID',
        2,  5, 1200000.00, 2200000.00, 'INR', 'YEARLY', DATE '2026-08-16',
        'Synthetic sample posting. Monitor for security events, run authorised testing engagements and write detection logic.'),
    (39, 11, 'Cybersecurity Engineer', 'London',  'GB', 'FULL_TIME', 'ONSITE',
        4,  8,   70000.00,  100000.00, 'GBP', 'YEARLY', DATE '2026-07-30',
        'Synthetic sample posting. Lead threat detection engineering and hardening of cloud workloads.'),
    (40,  2, 'Cybersecurity Engineer', 'Mumbai',  'IN', 'FREELANCE', 'REMOTE',
        3,  7,    8000.00,   15000.00, 'INR', 'DAILY',   DATE '2026-08-09',
        'Synthetic sample posting. Freelance security review of a payments platform, engaged by the day.');


-- =============================================================================
-- 4. job_skills  (242 rows)
--
--    Skills are assigned by ROLE PROFILE, not randomly, so the resulting data
--    answers the intended questions:
--      Data Analyst          -> SQL / Python / Pandas / Tableau
--      Data Scientist        -> adds Scikit-learn, Machine Learning, NumPy
--      ML / AI Engineer      -> adds TensorFlow / PyTorch, Deep Learning, NLP
--      Backend / SW Engineer -> Java or Python, databases, Git, Docker
--      DevOps / Cloud / SRE  -> Docker, Kubernetes, Terraform, Linux, Prometheus
--      Data Engineer         -> Spark, Airflow, SQL
--      Cybersecurity Eng.    -> Threat Detection, Penetration Testing, Linux
--    Most postings also share SQL, Git or Docker, which is what makes
--    "most demanded skills" and skill co-occurrence analysis realistic.
--    No (job_id, skill_id) pair is repeated - the composite PK would reject it.
-- =============================================================================

-- Data Analyst (jobs 1-5) ----------------------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    ( 1,  4), ( 1,  5), ( 1,  1), ( 1, 16), ( 1, 30),
    ( 2,  4), ( 2,  6), ( 2, 16), ( 2, 30), ( 2,  5),
    ( 3,  4), ( 3,  5), ( 3,  1), ( 3, 16), ( 3, 30),
    ( 4,  4), ( 4,  1), ( 4, 16), ( 4, 30), ( 4,  5),
    ( 5,  4), ( 5,  1), ( 5, 16), ( 5, 17);

-- Data Scientist (jobs 6-9) ---------------------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    ( 6,  1), ( 6, 16), ( 6, 17), ( 6, 18), ( 6, 27), ( 6,  4), ( 6,  5),
    ( 7,  1), ( 7, 16), ( 7, 18), ( 7, 27), ( 7,  4), ( 7,  5), ( 7, 30),
    ( 8,  1), ( 8, 18), ( 8, 27), ( 8, 28), ( 8, 19), ( 8,  4),
    ( 9,  1), ( 9, 16), ( 9, 17), ( 9, 18), ( 9, 27), ( 9, 21);

-- Machine Learning Engineer (jobs 10-13) -------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (10,  1), (10, 18), (10, 19), (10, 27), (10, 28), (10, 10), (10,  8), (10,  4),
    (11,  1), (11, 18), (11, 20), (11, 28), (11,  8), (11,  4),
    (12,  1), (12, 20), (12, 19), (12, 28), (12, 27), (12,  8),
    (13,  1), (13, 20), (13, 28), (13, 29), (13, 27), (13, 10), (13,  8);

-- AI Engineer (jobs 14-16) ----------------------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (14,  1), (14, 20), (14, 28), (14, 29), (14, 27), (14, 10), (14,  8),
    (15,  1), (15, 19), (15, 28), (15, 29), (15, 27), (15,  9), (15, 10),
    (16,  1), (16, 19), (16, 28), (16, 27), (16,  4);

-- Backend Engineer (jobs 17-20) ----------------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (17,  2), (17,  5), (17,  6), (17, 12), (17, 13),
    (18,  1), (18, 14), (18,  5), (18,  7), (18, 12), (18, 10), (18,  8),
    (19,  1), (19, 14), (19,  5), (19, 10), (19, 11), (19,  8), (19, 12),
    (20,  2), (20,  6), (20, 12), (20, 13);

-- Software Engineer (jobs 21-24) ---------------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (21,  1), (21, 15), (21,  5), (21, 12), (21, 10), (21,  4),
    (22,  2), (22,  6), (22, 12), (22, 13), (22, 15),
    (23,  3), (23,  1), (23,  5), (23, 13), (23, 12), (23, 10),
    (24,  1), (24, 12), (24, 15), (24,  4);

-- DevOps Engineer (jobs 25-27) ------------------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (25, 10), (25, 11), (25, 23), (25, 24), (25,  8), (25, 13), (25, 12), (25, 25),
    (26, 10), (26, 11), (26, 24), (26,  9), (26, 13), (26, 26), (26, 12),
    (27, 10), (27, 11), (27, 23), (27, 24), (27, 13), (27, 25), (27, 26);

-- Cloud Engineer (jobs 28-30) -------------------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (28,  8), (28,  9), (28, 23), (28, 10), (28, 11), (28, 13), (28,  1),
    (29,  8), (29,  9), (29, 23), (29, 10), (29, 13), (29,  1), (29, 12),
    (30,  8), (30,  9), (30, 23), (30, 11), (30, 13);

-- Site Reliability Engineer (jobs 31-32) -------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (31, 13), (31, 11), (31, 25), (31, 26), (31, 10), (31,  8), (31,  1), (31, 23),
    (32, 13), (32, 11), (32, 25), (32, 26), (32,  8), (32, 10), (32,  1);

-- Data Engineer (jobs 33-35) -------------------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (33,  1), (33,  4), (33,  5), (33, 21), (33, 22), (33,  8), (33, 10),
    (34,  1), (34,  4), (34,  6), (34, 22), (34, 21), (34, 13), (34, 12),
    (35,  1), (35,  4), (35,  5), (35, 22), (35, 21), (35,  9), (35, 12);

-- Business Analyst (jobs 36-37) ----------------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (36,  4), (36,  5), (36,  1), (36, 16), (36, 30),
    (37,  4), (37,  1), (37, 16), (37, 30), (37, 12);

-- Cybersecurity Engineer (jobs 38-40) ----------------------------------------
INSERT INTO job_skills (job_id, skill_id) VALUES
    (38, 31), (38, 32), (38, 13), (38,  1), (38,  9),
    (39, 31), (39, 32), (39,  8), (39, 13), (39,  1), (39, 10),
    (40, 31), (40, 32), (40,  1), (40, 13);


-- =============================================================================
-- 5. IN-POST / TRANSACTION-SCOPE VERIFICATION
--    These run inside the same transaction: if the data is not internally
--    consistent the COMMIT is never reached and the database stays empty.
-- =============================================================================

-- Expected: 15 | 40 | 32 | 242
DO $$
DECLARE
    n_companies INTEGER;
    n_jobs      INTEGER;
    n_skills    INTEGER;
    n_links     INTEGER;
    n_bad_link  INTEGER;
    n_dupes     INTEGER;
    n_orphan    INTEGER;
    n_unlinked  INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_companies FROM companies;
    SELECT COUNT(*) INTO n_jobs      FROM jobs;
    SELECT COUNT(*) INTO n_skills    FROM skills;
    SELECT COUNT(*) INTO n_links     FROM job_skills;

    IF n_companies <> 15 OR n_jobs <> 40 OR n_skills <> 32 OR n_links <> 242 THEN
        RAISE EXCEPTION
            'SEED ABORTED: expected 15/40/32/242 but got %/%/%/%.',
            n_companies, n_jobs, n_skills, n_links;
    END IF;

    -- Every junction row must point at a real job AND a real skill.
    SELECT COUNT(*) INTO n_bad_link
    FROM job_skills js
    LEFT JOIN jobs   j ON j.job_id   = js.job_id
    LEFT JOIN skills s ON s.skill_id = js.skill_id
    WHERE j.job_id IS NULL OR s.skill_id IS NULL;

    IF n_bad_link > 0 THEN
        RAISE EXCEPTION 'SEED ABORTED: % job_skills rows point at missing parents.', n_bad_link;
    END IF;

    -- No duplicated (job_id, skill_id) combination.
    SELECT COUNT(*) INTO n_dupes
    FROM (SELECT job_id, skill_id FROM job_skills
          GROUP BY job_id, skill_id HAVING COUNT(*) > 1) d;

    IF n_dupes > 0 THEN
        RAISE EXCEPTION 'SEED ABORTED: % duplicate job/skill combinations found.', n_dupes;
    END IF;

    -- Every job must require at least one skill.
    SELECT COUNT(*) INTO n_unlinked FROM jobs j
    WHERE NOT EXISTS (SELECT 1 FROM job_skills js WHERE js.job_id = j.job_id);

    IF n_unlinked > 0 THEN
        RAISE EXCEPTION 'SEED ABORTED: % jobs have no skills assigned.', n_unlinked;
    END IF;

    -- Every job must belong to an existing company.
    SELECT COUNT(*) INTO n_orphan FROM jobs j
    LEFT JOIN companies c ON c.company_id = j.company_id
    WHERE c.company_id IS NULL;

    IF n_orphan > 0 THEN
        RAISE EXCEPTION 'SEED ABORTED: % jobs reference a missing company.', n_orphan;
    END IF;

    RAISE NOTICE 'In-transaction verification passed: 15 companies, 40 jobs, 32 skills, 242 job_skill links.';
END
$$;

COMMIT;

\echo ''
\echo '================================================================'
\echo ' Seed data committed successfully (synthetic development data).'
\echo '================================================================'
