# 📊 Job Market Intelligence & Skill Analytics Platform

An end-to-end data analytics, machine learning, and cloud engineering platform that explores job-market trends, analyzes in-demand technical skills, identifies skill gaps, and recommends relevant career roles. The project combines data analytics, REST API development, containerization, AWS deployment, Infrastructure as Code, CI/CD automation, and infrastructure observability.

## 🚀 Project Overview

Choosing the right technical skills and career roles can be challenging without structured insights. The Job Market Intelligence & Skill Analytics Platform brings job-market data, skill-demand analytics, personalized skill-gap analysis, and role recommendations into one interactive application.

The project demonstrates a complete engineering workflow, from relational database design and SQL analytics to machine learning, API development, automated testing, cloud infrastructure provisioning, deployment automation, and infrastructure monitoring.

## ✨ Key Features

- **Interactive Analytics Dashboard:** Explore job-market trends through Streamlit and Plotly visualizations.
- **SQL Analytics:** Analyze job postings, company activity, and relationships between jobs and technical skills using PostgreSQL.
- **Skill Gap Analysis:** Compare existing skills with the skills associated with selected career roles.
- **Machine Learning Recommendations:** Recommend relevant roles using TF-IDF vectorization and cosine similarity.
- **REST API:** Expose application functionality through FastAPI endpoints.
- **Automated Testing:** Validate application functionality using Pytest.
- **Containerization:** Package application and supporting services using Docker and Docker Compose.
- **Continuous Integration:** Automate code validation and testing using GitHub Actions.
- **Automated Deployment:** Deploy application updates to AWS EC2 through GitHub Actions and AWS Systems Manager.
- **Infrastructure as Code:** Provision cloud infrastructure using Terraform.
- **Secure AWS Authentication:** Use GitHub OIDC for role-based authentication without storing long-lived AWS access keys in repository secrets.
- **Infrastructure Monitoring:** Collect and visualize infrastructure metrics using Prometheus, Grafana, Node Exporter, and cAdvisor.
- **Container Observability:** Monitor container resource utilization alongside host-level metrics.

## 🧰 Technology Stack

| Category | Technologies |
|---|---|
| Programming Languages | Python, SQL |
| Data Processing | Pandas |
| Database | PostgreSQL |
| Analytics Dashboard | Streamlit, Plotly |
| Machine Learning | Scikit-learn, TF-IDF, Cosine Similarity |
| Backend API | FastAPI, Uvicorn |
| Testing | Pytest |
| Containerization | Docker, Docker Compose |
| Cloud Platform | AWS EC2, Amazon S3, AWS Systems Manager |
| Infrastructure as Code | Terraform |
| CI/CD | GitHub Actions |
| Cloud Authentication | GitHub OIDC, AWS IAM |
| Monitoring and Observability | Prometheus, Grafana, Node Exporter, cAdvisor |
| Version Control | Git, GitHub |

## 🏗️ System Architecture

```text
                         Users
                           |
               +-----------+-----------+
               |                       |
        Streamlit Dashboard       REST API Clients
               |                       |
               +----------+------------+
                          |
                       FastAPI
                          |
             Python / Pandas / ML
                          |
                     PostgreSQL
                          |
                  SQL Analytics Layer

                 CI/CD and Deployment
                          |
                    GitHub Actions
                          |
                     GitHub OIDC
                          |
                       AWS IAM
                          |
                 AWS Systems Manager
                          |
                       AWS EC2
                          |
                   Docker Compose
                          |
            +-------------+-------------+
            |             |             |
         FastAPI       Streamlit     PostgreSQL
            |
            +---------------------------+
                          |
                   Observability
                          |
            +-------------+-------------+
            |             |             |
        Prometheus   Node Exporter    cAdvisor
            |
          Grafana
            |
    Infrastructure Dashboard

          Terraform manages
       cloud infrastructure resources
```

## 📈 Data and Analytics

The development database contains the following sample records:

| Entity | Count |
|---|---:|
| Companies | 15 |
| Job Postings | 40 |
| Skills | 32 |
| Job-to-Skill Relationships | 242 |

**Data disclaimer:** These records are development/demo data and are not a representative sample of the real job market. Analytics and recommendations should be interpreted within the limits of this dataset.

The SQL analytics layer supports exploration of:

- Job postings and company activity
- Technical skills associated with roles
- Skill-demand patterns within the available dataset
- Relationships between companies, jobs, and skills

The Python data-processing layer uses Pandas to support data preparation and analytics workflows.

## 🤖 Machine Learning and Skill Gap Analysis

### Role Recommendation Engine

The recommendation component uses:

1. **TF-IDF vectorization** to represent candidate profile text and role-related information.
2. **Cosine similarity** to compare text representations.
3. **Similarity-based ranking** to identify potentially relevant career roles.

The resulting scores represent text similarity. They are not hiring probabilities, guarantees of employment, or calibrated measures of candidate quality.

### Skill Gap Analysis

The skill-gap component compares a candidate's existing skills with the skills associated with a selected role. It highlights missing or relevant skills that the candidate may consider learning.

## 🔌 REST API

The backend uses FastAPI to expose application functionality through HTTP endpoints.

The API can be run locally as part of the Docker Compose stack. Refer to the application source code and API documentation for the exact endpoint paths, request schemas, and response formats.

When the API is running, interactive documentation may be available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

These URLs assume the API is published on local port `8000`.

## ☁️ AWS Deployment and DevOps

The platform uses AWS EC2 to run the containerized application and monitoring services.

### Infrastructure

- **Amazon EC2:** Hosts the deployed application and observability stack.
- **Amazon VPC:** Provides the network environment for the infrastructure.
- **Amazon S3:** Stores Terraform state in a private, versioned bucket.
- **AWS Systems Manager:** Supports remote administration and secure session-based access.
- **Terraform:** Manages infrastructure provisioning.
- **Docker Compose:** Runs the application and monitoring containers.

### CI/CD Workflow

The deployment workflow uses GitHub Actions to automate validation and deployment operations.

The workflow uses GitHub OIDC to obtain AWS role-based credentials and AWS Systems Manager to execute deployment commands on the EC2 instance. This avoids storing long-lived AWS access keys in GitHub repository secrets.

The deployment process updates the application code and rebuilds the relevant Docker Compose services.

### Infrastructure Monitoring

The deployed monitoring stack includes:

| Component | Responsibility |
|---|---|
| Prometheus | Scrapes and stores time-series metrics |
| Grafana | Visualizes collected metrics in dashboards |
| Node Exporter | Exposes Linux host metrics |
| cAdvisor | Exposes container resource metrics |

Prometheus is configured to scrape the monitoring targets at 15-second intervals.

The Grafana dashboard, **JMI Infrastructure Monitoring**, includes panels for:

- CPU usage
- Memory usage
- Disk space utilization
- Network received traffic
- Container CPU usage
- Container memory utilization
- Prometheus target health
### 📊 Infrastructure Monitoring Dashboard

![JMI Infrastructure Monitoring](docs/images/jmi-infrastructure-monitoring.png)

🔗 **[View Grafana Monitoring Dashboard](https://snapshots.raintank.io/dashboard/snapshot/FyMoKbLZjuQzjnwCMUfjQLbXMCcwu0Ab?from=2026-10-10T19%3A18%3A27.419Z&to=2026-10-11T11%3A18%3A27.419Z&timezone=browser&var-DS_PROMETHEUS=dg0pkq024jif4a)**

The dashboard monitors:
- CPU and memory utilization
- Root filesystem disk usage
- Network traffic
- Container CPU and memory
- Prometheus monitoring target health

> **Note:** The Grafana link displays a read-only snapshot, not live metrics. The screenshot is available directly in this repository.

### Secure Grafana Access

Grafana can be accessed through AWS Systems Manager port forwarding instead of exposing its monitoring port publicly.

For Windows PowerShell, create a local parameter file named `ssm-grafana-parameters.json` with the following content:

```json
{
  "portNumber": ["3000"],
  "localPortNumber": ["3001"]
}
```

Start the SSM tunnel:

```powershell
aws ssm start-session `
  --region ap-south-1 `
  --target "<EC2_INSTANCE_ID>" `
  --document-name "AWS-StartPortForwardingSession" `
  --parameters "file://ssm-grafana-parameters.json"
```

Keep the session open while accessing Grafana at:

`http://localhost:3001`

Replace the instance ID placeholder with the appropriate instance ID for your deployment. Keep the parameter file free of credentials and do not commit private configuration files.

## 🧪 Testing

The previously recorded test suite completed with **215 passing tests**. This result reflects an earlier run and should be revalidated before a new release.

Run the current test suite:

```bash
pytest
```

The project also includes API tests for validating backend functionality. Run the tests in the appropriate Python environment with the required dependencies installed.

## 🐳 Run with Docker Compose

### Prerequisites

- Git
- Docker Desktop or Docker Engine with Docker Compose
- Python and the project dependencies if running tests outside containers

### 1. Clone the repository

```bash
git clone https://github.com/Tejaswini8888/Job-Market-Intelligence.git
cd Job-Market-Intelligence
```

### 2. Configure environment variables

Review the environment example and Docker Compose configuration. Create your local `.env` file using the documented variable names and provide your own database credentials.

Do not commit `.env` or other files containing secrets.

### 3. Build and start the services

```bash
docker compose up -d --build
```

### 4. Check service status

```bash
docker compose ps
```

### 5. View logs

```bash
docker compose logs -f
```

### 6. Access the local application

The following addresses assume the default local port mappings are configured:

| Service | Local URL |
|---|---|
| FastAPI | `http://localhost:8000` |
| FastAPI Swagger UI | `http://localhost:8000/docs` |
| Streamlit Dashboard | `http://localhost:8501` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |

The local Docker Desktop environment may expose different host filesystem metrics from the Linux EC2 environment. Use the AWS Grafana SSM tunnel when inspecting actual EC2 host metrics.

### 7. Stop the services

```bash
docker compose down
```

This stops and removes the Compose containers and network. Persistent data handling depends on the configured Docker volumes.

## 🔐 Security Practices

- Keep passwords, API keys, AWS credentials, and other secrets out of source control.
- Use GitHub OIDC and restricted AWS IAM roles for deployment authentication.
- Store sensitive configuration in appropriate AWS-managed secret storage.
- Keep monitoring interfaces private and avoid publicly exposing Prometheus, Grafana, Node Exporter, and cAdvisor.
- Use AWS Systems Manager for secure remote administration and Grafana port forwarding.
- Use least-privilege IAM permissions for routine AWS operations.
- Review Git changes before committing configuration files.
- Avoid including sensitive infrastructure details in public screenshots or documentation.

## 🔮 Future Improvements

- Configure automated alerts for infrastructure health and resource thresholds.
- Add more automated integration and deployment tests.
- Improve data ingestion and validation workflows.
- Expand recommendation explanations and model evaluation.
- Add more detailed API and infrastructure documentation.
- Extend observability with application-level metrics and structured logging.
- Introduce automated recovery procedures for selected service failures.

## 👩‍💻 Author

**Tejaswini Madarapu**

B.Tech — Artificial Intelligence & Machine Learning

- GitHub: https://github.com/Tejaswini8888
- LinkedIn: https://www.linkedin.com/in/tejaswini-madarapu

---

*Built to demonstrate practical skills in data analytics, machine learning, backend engineering, cloud infrastructure, CI/CD automation, and infrastructure observability.*
