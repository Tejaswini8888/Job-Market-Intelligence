# ==========================================================
# Job Market Intelligence & Skill Analytics Platform
# infra/terraform/variables.tf
#
# Every knob this deployment exposes. Nothing secret is hardcoded:
# db_password has NO default, so Terraform refuses to run until the
# operator supplies it out of band (see README.md -> "Secrets").
#
# Supply values with ONE of:
#   * environment variables   TF_VAR_db_password=...   (never in a shell
#     history on a shared machine; prefix it with a space in bash)
#   * a git-ignored file     terraform.tfvars
#   * -var flags on the command line
# `terraform.tfvars.example` in this directory is the template and is
# safe to commit - it contains placeholders only.
# ==========================================================

# ------------------------------------------------------------
# Naming, region and tags
# ------------------------------------------------------------

variable "aws_region" {
  description = "AWS region to build in. Defaults to the same region the project already documents in .env.example (ap-south-1 / Mumbai)."
  type        = string
  default     = "ap-south-1"

  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like a region id, for example ap-south-1 or eu-west-1."
  }
}

variable "project_name" {
  description = "Short project name used as the prefix for every resource name (VPC, subnets, security group, instance)."
  type        = string
  default     = "job-market-intelligence"
}

variable "environment" {
  description = "Deployment environment name. Keeps demo/staging/production resources distinguishable in the AWS console."
  type        = string
  default     = "demo"

  validation {
    condition     = contains(["dev", "demo", "staging", "production"], var.environment)
    error_message = "environment must be one of: dev, demo, staging, production."
  }
}

variable "tags" {
  description = "Extra tags merged into the default tags on every resource. A good place for Cost = \"portfolio\" or Owner = \"your-name\"."
  type        = map(string)
  default = {
    Project  = "job-market-intelligence"
    Stack    = "ec2-docker-compose"
    Provider = "terraform"
  }
}

# ------------------------------------------------------------
# Networking
# ------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC. The first /24 becomes the public subnets, the second /24 the private subnets (see cidrsubnet math in vpc.tf)."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block, for example 10.20.0.0/16."
  }
}

variable "availability_zones" {
  description = "Optional explicit list of availability zones. Leave empty to auto-select the first var.az_count zones offered by the region."
  type        = list(string)
  default     = []
}

variable "az_count" {
  description = "Number of availability zones (and therefore subnets) to create. Two is the usual minimum for a demo with a standby story."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 1 && var.az_count <= 3 && floor(var.az_count) == var.az_count
    error_message = "az_count must be a whole number between 1 and 3."
  }
}

# ------------------------------------------------------------
# Inbound access
#
# Only the two ports the application actually publishes are opened
# (8000 API, 8501 dashboard), plus SSH for administration. PostgreSQL
# 5432 is deliberately NOT in this file and NOT in security_groups.tf:
# docker-compose.yml never publishes it, so the database is only
# reachable on the container network.
# ------------------------------------------------------------

variable "api_port" {
  description = "Host port for the FastAPI backend, matching the \"8000:8000\" mapping in docker-compose.yml."
  type        = number
  default     = 8000
}

variable "dashboard_port" {
  description = "Host port for the Streamlit dashboard, matching the \"8501:8501\" mapping in docker-compose.yml."
  type        = number
  default     = 8501
}

variable "app_allowed_cidrs" {
  description = "CIDR blocks allowed to reach the API and dashboard ports. 0.0.0.0/0 is fine for a portfolio demo; narrow it to your own IP for anything longer lived."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = length(var.app_allowed_cidrs) > 0
    error_message = "app_allowed_cidrs must contain at least one CIDR block."
  }
}

variable "enable_ssh" {
  description = "Whether to open SSH at all. Set false to run a closed demo instance reachable only through the app ports."
  type        = bool
  default     = true
}

# ------------------------------------------------------------
# SSH access - MUST BE RESTRICTED BEFORE A LONG-LIVED DEPLOYMENT
#
# The default below is 0.0.0.0/0, which exposes port 22 to the whole
# internet. That is kept here only because a short-lived portfolio demo
# needs to be reachable from wherever the reviewer is sitting.
#
# BEFORE LEAVING THIS INSTANCE RUNNING FOR MORE THAN A FEW DAYS, set
# ssh_allowed_cidrs to your own public IP, e.g.
#
#     ssh_allowed_cidrs = ["203.0.113.10/32"]     # your address
#
# or, if the instance has the AmazonSSMManagedInstanceCore role (it
# does - see iam.tf), close the port completely and administer it with:
#
#     enable_ssh = false
#     aws ssm start-session --target <instance-id>
#
# The value is only a convenience default, so forgetting this step does
# not fail validation; it silently leaves SSH open to the world.
# ------------------------------------------------------------
variable "ssh_allowed_cidrs" {
  description = "CIDR blocks allowed to reach SSH (port 22). DEFAULTS TO 0.0.0.0/0 - restrict this to your own IP (or set enable_ssh = false and use SSM Session Manager) before any long-lived deployment."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ------------------------------------------------------------
# EC2 instance
# ------------------------------------------------------------

variable "instance_type" {
  description = "EC2 instance type. t3.small (2 vCPU / 2 GiB) is the realistic floor for postgres + api + dashboard together; t3.micro will thrash."
  type        = string
  default     = "t3.small"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GiB. Holds the OS, the two built Docker images and the PostgreSQL data volume."
  type        = number
  default     = 30

  validation {
    condition     = var.root_volume_size_gb >= 20
    error_message = "root_volume_size_gb must be at least 20 GiB to fit the OS, both images and the database volume."
  }
}

variable "associate_public_ip" {
  description = "Give the instance a public IP address. The instance sits in a public subnet because this configuration deliberately skips a NAT Gateway (see vpc.tf); the app ports are still restricted by var.app_allowed_cidrs."
  type        = bool
  default     = true
}

variable "enable_elastic_ip" {
  description = "Attach a fixed Elastic IP so the demo URL survives stop/start. An attached EIP costs nothing; an unattached one does, so it is destroyed with the instance."
  type        = bool
  default     = true
}

# ------------------------------------------------------------
# SSH key material
#
# Terraform only ever needs the PUBLIC half of the key. The private
# key stays on your laptop, so nothing sensitive enters this repository
# or the state file. Provide it either inline (ssh_public_key) or as a
# path to the .pub file (ssh_public_key_path).
# ------------------------------------------------------------

variable "ssh_public_key" {
  description = "Public SSH key contents (the single line from id_ed25519.pub). Takes precedence over ssh_public_key_path. Never provide a PRIVATE key."
  type        = string
  default     = null
}

variable "ssh_public_key_path" {
  description = "Path to a .pub public key file, used when ssh_public_key is null. '~' is expanded."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

# ------------------------------------------------------------
# Source code deployed onto the instance
#
# The repository must be reachable by the instance over HTTPS without
# credentials (a public GitHub repository is the intended setup for a
# portfolio demo). A private repository would need a deploy key added
# here, which is out of scope on purpose.
# ------------------------------------------------------------

variable "repo_url" {
  description = "Git clone URL of the project. Cloned onto the instance by user_data.tftpl."
  type        = string
  default     = "https://github.com/Tejaswini8888/Job-Market-Intelligence.git"
}

variable "git_branch" {
  description = "Branch to check out and run."
  type        = string
  default     = "main"
}

variable "app_dir" {
  description = "Absolute path the repository is cloned to on the instance."
  type        = string
  default     = "/opt/job-market-intelligence"
}

# ------------------------------------------------------------
# Application / database configuration
#
# These are NOT secrets and may live in a .tfvars file. DB_PASSWORD is
# the only sensitive one and has no default.
# ------------------------------------------------------------

variable "db_name" {
  description = "PostgreSQL database name, matching POSTGRES_DB / DB_NAME in docker-compose.yml and .env.example."
  type        = string
  default     = "job_market_intelligence"
}

variable "db_user" {
  description = "PostgreSQL role created by the postgres image on first boot, matching DB_USER in docker-compose.yml."
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "Password for the PostgreSQL role. NEVER hardcoded and never defaulted: pass it as TF_VAR_db_password or in a git-ignored terraform.tfvars. Terraform stores it in state - see README.md -> \"State handling\"."
  type        = string
  sensitive   = true

  # No default on purpose: omitting the variable is a hard error instead of
  # silently deploying a guessable password.
}

variable "db_password_parameter_name" {
  description = "Name of the SSM Parameter Store SecureString that holds the database password. Leave null for /<project>-<environment>/db_password. The instance reads it at boot through its instance profile, so the value never appears in user-data or in the EC2 console."
  type        = string
  default     = null
}

# ------------------------------------------------------------
# Cost control
# ------------------------------------------------------------

variable "enable_detailed_monitoring" {
  description = "Enable one-minute EC2 CloudWatch metrics. Off by default: detailed monitoring is billed per metric and adds nothing to this demo."
  type        = bool
  default     = false
}
