# Infrastructure as Code - AWS EC2 + Docker Compose

Terraform for the Job Market Intelligence & Skill Analytics Platform.

It provisions **one EC2 instance** that installs Docker, clones this
repository and runs the existing `docker-compose.yml` stack. It does not
deploy application logic: the same `backend/Dockerfile`,
`dashboard/Dockerfile`, `docker-compose.yml`, `database/schema.sql` and
`database/seed.sql` that run on your laptop run unchanged in AWS.

> **Nothing here has been applied.** These files were generated and
> validated locally only. No AWS resources have been created, and
> `terraform apply` has deliberately not been run.

---

## What gets created

| Resource | Purpose |
| --- | --- |
| `aws_vpc`, `aws_internet_gateway` | Isolated network for the demo |
| `aws_subnet.public` / `aws_subnet.private` (per AZ) | Host for EC2 / reserved for a future RDS |
| `aws_route_table` + associations | Public routing only, **no NAT Gateway** |
| `aws_security_group.app` | Inbound: API, dashboard, optional SSH. Outbound: all |
| `aws_iam_role` + instance profile | Reads exactly one SSM Secret |
| `aws_ssm_parameter.db_password` | `SecureString`, written by Terraform |
| `aws_key_pair.app` | Imports your **public** SSH key |
| `aws_instance.app` | Ubuntu 24.04 LTS, `t3.small`, gp3 30 GiB, IMDSv2 |
| `aws_eip` (optional) | Stable public IP, free while attached |

Services on the host, matching the verified local stack:

| Service | Port | Published to the internet? |
| --- | --- | --- |
| `api` (FastAPI) | 8000 | Yes - security-group controlled |
| `dashboard` (Streamlit) | 8501 | Yes - security-group controlled |
| `postgres` | 5432 | **No** - internal to the Compose network only |

### PostgreSQL is not publicly exposed

`docker-compose.yml` never publishes `5432`; the API and dashboard reach
the database over the private Compose network as `postgres:5432`. Because
nothing is bound on the host interface, there is nothing for a security
group to expose - and no `5432` rule exists in `security_groups.tf`.
Do not add one.

---

## Prerequisites

1. **Terraform >= 1.5.0** - <https://developer.hashicorp.com/terraform/downloads>
2. **AWS CLI v2** with a configured identity (profile, SSO, or
   environment variables). Terraform uses the standard credential chain;
   **no keys are stored in this directory**.
   ```powershell
   aws sts get-caller-identity
   ```
3. **An SSH key pair** on the machine running Terraform. Only the public
   half is ever read by Terraform:
   ```powershell
   ssh-keygen -t ed25519 -C "jmi-demo"
   ```
4. **The repository reachable over HTTPS without credentials.** A public
   GitHub repository is the intended setup; update `repo_url` in
   `terraform.tfvars`.
5. Optionally an S3 bucket (versioned, encrypted) for remote state -
   see [State handling](#state-handling).

---

## Secrets

`db_password` is a `sensitive` Terraform variable with **no default**, so
a missing value is a hard error instead of a guessable password. It is
never hardcoded in any `.tf` file, and it is never written into
`user_data.tftpl`.

Flow:

```
TF_VAR_db_password  ->  aws_ssm_parameter.db_password (SecureString)
                     ->  EC2 instance role: ssm:GetParameter on that one ARN
                     ->  user-data writes /opt/job-market-intelligence/.env (mode 600)
                     ->  docker-compose.yml substitutes DB_PASSWORD
```

Consequences worth being explicit about:

* The password never appears in cloud-init user-data, in
  `aws ec2 describe-instance-attribute --user-data`, or in this Git repo.
* `terraform plan` and `terraform apply` print `(sensitive value)`.
* **The value is stored in Terraform state.** Encrypt the state bucket,
  enable versioning, lock it down, and never commit it. Rotating the
  password means updating the variable and re-applying.
* On the instance the password lives only in the root-owned `.env`, and
  containers read it from their environment.

Generate a password:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## State handling

`versions.tf` declares an **empty** `backend "s3" {}` on purpose: no
bucket is hardcoded and no state can be created by accident. For local
validation always initialise with `-backend=false`.

For a real deployment use an encrypted, versioned S3 backend, either by
editing the block or with a separate file:

```hcl
# backend.hcl - keep this local, do not commit real bucket names if private
bucket         = "my-terraform-state"
key            = "job-market-intelligence/ec2/terraform.tfstate"
region         = "ap-south-1"
encrypt        = true
use_lockfile   = true   # S3-native locking, Terraform >= 1.10
```

```powershell
terraform init -backend-config=backend.hcl
```

Add `terraform.tfstate`, `terraform.tfstate.backup`, `.terraform/` and
`*.tfvars` to `.gitignore` if they are not already - this repository's
`.gitignore` already excludes all four.

One exception worth knowing: that same `.gitignore` also excludes
`.terraform.lock.hcl`. HashiCorp's guidance is to **commit** the lock
file, because it pins the provider version so every machine and CI run
resolves the same AWS provider. If you want that guarantee, remove that
one line from the root `.gitignore` and commit the lock file produced by
`terraform init`. It contains no secrets.

---

## Usage

All commands run from `infra/terraform/`.

### 1. Configure values

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars   # then edit it
```

### 2. `terraform init`

```powershell
terraform init -backend=false
```

Downloads the AWS provider and **does not touch any backend**. Safe.

### 3. `terraform validate`

```powershell
terraform fmt -check -recursive
terraform validate
```

Checks syntax, provider schema and internal consistency. Still no AWS
calls that change anything.

### 4. `terraform plan`

```powershell
$env:TF_VAR_db_password = "<generated password>"   # PowerShell
terraform plan -out=tfplan
```

Read the plan before continuing: it lists the VPC, subnets, security
group, IAM role, SSM parameter and the EC2 instance.

### 5. `terraform apply` - not run yet

```powershell
terraform apply tfplan
```

**Do not run this as part of code generation.** When you are ready, this
is the step that creates billable AWS resources. The first boot takes a
few minutes: cloud-init installs Docker, clones the repo, builds two
images and waits for `GET /health`.

### 6. Verify

```powershell
terraform output                       # URLs and the ssh command
curl http://<public-ip>:8000/health    # expect 200 and "database": "up"
```

Or connect and check Compose directly:

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@<public-ip>
cd /opt/job-market-intelligence
docker compose ps
docker compose logs -f api
tail -f /var/log/jmi-bootstrap.log
```

### 7. Tear down

```bash
terraform destroy
```

This removes the EC2 instance **and its EBS volume**, so the PostgreSQL
data is deleted with it. Take a `docker compose exec postgres pg_dumpall`
first if you want to keep the demo data.

---

## Operational notes

* **Reboots and restarts are safe.** `docker compose` is not run by
  systemd, but every service sets `restart: unless-stopped`, so Docker
  brings the stack back automatically. Re-run
  `/opt/jmi/bootstrap.sh` (as root) to redeploy a new commit.
* **Redeploying code does not require Terraform.** `user-data` only runs
  at first boot; edit, commit, then on the host:
  `git pull && docker compose up -d --build`.
* **Updating user-data** sets `user_data_replace_on_change = true`, so a
  template edit triggers an instance replacement (a new instance and a new
  ephemeral address unless an Elastic IP is attached). Plan deliberately.
* **Database persistence** relies on the root EBS volume plus the
  `postgres_data` named volume. `docker compose down -v` or
  `terraform destroy` deletes it.
* **Password rotation:** update `db_password` (env var or tfvars), re-run
  `terraform apply`, then on the host rebuild the API and dashboard
  containers so they pick up the new `.env`. The database role itself
  still holds the old password, so also run
  `docker compose exec postgres psql -c "ALTER USER ... WITH PASSWORD '...'"`
  to keep the two in step.
* **Session Manager** works with no SSH rule at all: `enable_ssh = false`
  plus `aws ssm start-session --target <instance-id>`.

## Cost

Deliberately cheap, in line with a portfolio project:

* No NAT Gateway (the single biggest fixed cost, ~USD 32/month).
* No RDS, no Load Balancer, no CloudFront, no ACM certificates.
* No detailed CloudWatch monitoring.
* One `t3.small` (~USD 17/month) plus a 30 GiB gp3 volume (~$2.40/month).
* An attached Elastic IP is free.

Total is roughly USD 20/month while running. AWS Free Tier, when
available, covers part of this. Always stop the instance when it is not
being demonstrated.

## Deliberate trade-offs

| Decision | Why |
| --- | --- |
| EC2 in a public subnet | Avoids a NAT Gateway. Access is restricted by the security group instead. Production would use private subnets + NAT. |
| Private subnets created but unrouted | Ready for a future RDS instance without renumbering. |
| Password in Terraform state | Simplest correct mechanism. A KMS-encrypted external secret store would remove it. |
| Single instance, no Auto Scaling | One demo stack does not need two tiers. |
| SSH open to `0.0.0.0/0` by default | Convenience for a demo. Set `ssh_allowed_cidrs` to your own IP. |

## Files

| File | Contents |
| --- | --- |
| `versions.tf` | Terraform / provider constraints, empty S3 backend stub |
| `provider.tf` | Region and default tags (no credentials) |
| `variables.tf` | Every input, documented |
| `locals.tf` | Naming, tags, AZ selection, key and secret lookups |
| `vpc.tf` | VPC, IGW, public and private subnets, routing |
| `security_groups.tf` | API, dashboard, optional SSH; no 5432 |
| `iam.tf` | EC2 role, SSM read policy, instance profile, SecureString |
| `ec2.tf` | AMI lookup, key pair, Elastic IP, the instance |
| `user_data.tftpl` | cloud-init: Docker, AWS CLI, clone, secret, compose up |
| `outputs.tf` | URLs, ids, ssh command, verification checklist |
| `terraform.tfvars.example` | Placeholder values, safe to commit |
