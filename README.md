# 📊 Job Market Intelligence & Skill Analytics Platform

An end-to-end data analytics and machine learning platform that explores job-market trends, analyzes in-demand skills, identifies skill gaps, and recommends relevant career roles. The project combines data analytics, REST APIs, containerization, cloud deployment, CI/CD, and infrastructure monitoring.

## 🚀 Project Overview

Choosing which technical skills to learn and which roles to target can be difficult without structured insights. This platform brings job-market data, skill-demand analytics, and role recommendations into one interactive application.

It demonstrates an end-to-end workflow from relational data storage and SQL analytics to machine learning, API development, cloud deployment, and monitoring.

## ✨ Key Features

- **Interactive Analytics Dashboard:** Explore job-market data using Streamlit and Plotly visualizations.
- **SQL Analytics:** Analyze companies, job postings, and skill relationships using PostgreSQL.
- **Skill Gap Analysis:** Compare a candidate's skills against skills associated with relevant roles.
- **Role Recommendations:** Use TF-IDF vectorization and cosine similarity to identify relevant roles.
- **REST API:** Serve application functionality through FastAPI.
- **Automated Testing:** Validate application functionality with a Python test suite.
- **Containerization:** Package application services using Docker and Docker Compose.
- **Continuous Integration and Deployment:** Use GitHub Actions to automate validation and deployment workflows.
- **AWS Deployment:** Provision and manage cloud infrastructure using Terraform and AWS services.
- **Infrastructure Monitoring:** Use Prometheus, Grafana, Node Exporter, and cAdvisor to visualize host and container resource usage.

## 🧰 Technology Stack

| Category | Technologies |
|---|---|
| Programming | Python, SQL |
| Data Processing | Pandas |
| Database | PostgreSQL |
| Analytics UI | Streamlit, Plotly |
| Machine Learning | Scikit-learn, TF-IDF, Cosine Similarity |
| API | FastAPI |
| Containers | Docker, Docker Compose |
| Cloud | AWS EC2, AWS Systems Manager, Amazon S3 |
| Infrastructure as Code | Terraform |
| CI/CD | GitHub Actions, GitHub OIDC |
| Monitoring | Prometheus, Grafana, Node Exporter, cAdvisor |
| Testing | Pytest |

## 🏗️ System Architecture

```text
                 User
                  |
          Streamlit Dashboard
                  |
             FastAPI
                  |
       Python / Pandas / ML
                  |
              PostgreSQL
                  |
          SQL Analytics Layer

       Deployment & Operations
                  |
          GitHub Actions CI/CD
                  |
          GitHub OIDC + AWS
                  |
          Terraform / EC2
                  |
            Docker Compose
                  |
       Prometheus + Node Exporter
                  + cAdvisor
                  |
                Grafana
```

## 📈 Data and Analytics

The development database contains:

- 15 companies
- 40 job postings
- 32 skills
- 242 job-to-skill relationships

These records are development/demo data and should not be interpreted as a representative sample of the real job market.

The SQL analytics layer includes queries for exploring job postings, company activity, and skill relationships.

## 🤖 Machine Learning Approach

The role-recommendation component uses TF-IDF to represent text and cosine similarity to compare candidate skills or profile text with role-related information.

The resulting scores indicate text similarity, not the probability of getting hired or a calibrated measure of candidate quality.

The skill-gap component helps identify relevant skills to consider learning for a selected role.

## ☁️ Cloud Deployment and DevOps

The application is deployed on AWS EC2 using Docker Compose. Terraform manages the cloud infrastructure, while GitHub Actions automates the deployment workflow.

The deployment workflow uses GitHub OIDC for AWS authentication and AWS Systems Manager for remote deployment operations, avoiding the need to store long-lived AWS access keys in GitHub repository secrets.

Infrastructure monitoring is provided through Prometheus and Grafana. Node Exporter collects host-level metrics, while cAdvisor exposes container metrics.

Grafana provides visualizations for CPU, memory, disk utilization, network traffic, and container resource usage.

## 🧪 Testing

The previously recorded test suite completed with 215 passing tests, including API and application tests. Run the current test suite before relying on this result for a new release.

```bash
pytest
```

## 🐳 Run with Docker Compose

Clone the repository:

```bash
git clone https://github.com/Tejaswini8888/Job-Market-Intelligence.git
cd Job-Market-Intelligence
```

Review the environment example and Docker Compose configuration. Create your local environment file using the documented variable names, and provide your own database credentials.

Start the application stack:

```bash
docker compose up -d --build
```

Inspect running services:

```bash
docker compose ps
```

View service logs:

```bash
docker compose logs -f
```

Stop the services when finished:

```bash
docker compose down
```

Refer to the repository's configuration files for the exact application ports and required environment variables.

## 🔐 Security Practices

- Keep `.env` files and credentials out of version control.
- Use GitHub OIDC instead of long-lived AWS access keys for deployment authentication.
- Store sensitive deployment configuration in appropriate AWS-managed secret storage.
- Restrict access to infrastructure monitoring interfaces.
- Use AWS Systems Manager port forwarding for private Grafana access.

## 🔮 Future Improvements

- Add automated alerts for infrastructure health and resource thresholds.
- Improve data ingestion and validation workflows.
- Add more robust model evaluation and recommendation explanations.
- Expand integration and deployment testing.
- Add further operational documentation and architecture diagrams.

## 👩‍💻 Author

**Tejaswini Madarapu**

B.Tech — Artificial Intelligence & Machine Learning

- GitHub: https://github.com/Tejaswini8888
- LinkedIn: https://www.linkedin.com/in/tejaswini-madarapu

---

*Built to demonstrate practical skills in data analytics, machine learning, backend development, cloud infrastructure, CI/CD, and monitoring.*
