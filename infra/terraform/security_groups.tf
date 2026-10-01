# ==========================================================
# Job Market Intelligence & Skill Analytics Platform
# infra/terraform/security_groups.tf
#
# One security group, attached to the EC2 instance, is the ONLY thing
# standing between the internet and the containers.
#
# Inbound rules, and why each one exists:
#
#   8000/tcp   FastAPI   published by docker-compose.yml as 8000:8000
#   8501/tcp   Streamlit published by docker-compose.yml as 8501:8501
#   22/tcp     SSH       administration only, optional (enable_ssh)
#
# What is NOT here, on purpose:
#
#   5432/tcp   PostgreSQL. docker-compose.yml deliberately does not
#              publish the database port - the API and dashboard reach
#              it over the private Compose network as "postgres:5432".
#              With no host port published there is nothing on the
#              instance's network interface for 5432, so the database
#              cannot be reached from outside even though the host is
#              in a public subnet. Do not add a 5432 rule.
#
#   9090/3000  Prometheus / Grafana. They are placeholders in
#              .env.example only and are not deployed here.
#
# Egress is unrestricted because the host needs it at boot: apt for the
# Docker packages, the GitHub container registry and GitHub itself for
# the clone, and the SSM API to read the database password.
# ==========================================================

resource "aws_security_group" "app" {
  name        = "${local.name_prefix}-sg"
  description = "Job Market Intelligence - API 8000, dashboard 8501, optional SSH 22"
  vpc_id      = aws_vpc.this.id

  # Ingress and egress are declared as standalone rules below
  # (aws_vpc_security_group_ingress_rule / _egress_rule) so that this
  # resource keeps no inline rules. That avoids the well-known
  # "rules are outside of Terraform" drift diff when someone edits a
  # rule in the AWS console.
  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-sg"
  })
}

# ------------------------------------------------------------
# Ingress - application ports
#
# aws_vpc_security_group_ingress_rule takes a SINGLE cidr_ipv4, so
# for_each over the variable's CIDRs creates one rule per address range
# and keeps the list form of var.app_allowed_cidrs working.
# ------------------------------------------------------------
resource "aws_vpc_security_group_ingress_rule" "api" {
  for_each = toset(var.app_allowed_cidrs)

  security_group_id = aws_security_group.app.id
  description       = "FastAPI backend (docker-compose port mapping ${var.api_port}:8000)"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = var.api_port
  to_port           = var.api_port
}

resource "aws_vpc_security_group_ingress_rule" "dashboard" {
  for_each = toset(var.app_allowed_cidrs)

  security_group_id = aws_security_group.app.id
  description       = "Streamlit dashboard (docker-compose port mapping ${var.dashboard_port}:8501)"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = var.dashboard_port
  to_port           = var.dashboard_port
}

# ------------------------------------------------------------
# Ingress - SSH (optional)
# ------------------------------------------------------------
resource "aws_vpc_security_group_ingress_rule" "ssh" {
  # The conditional is applied to the LIST and then converted to a set, so
  # both branches share a type. enable_ssh = false yields an empty set and
  # therefore no SSH rules at all.
  for_each = toset(var.enable_ssh ? var.ssh_allowed_cidrs : [])


  security_group_id = aws_security_group.app.id
  description       = "SSH administration - narrow this CIDR to your own address"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

# ------------------------------------------------------------
# Egress
#
# Unrestricted on purpose: the bootstrap pulls Docker from
# download.docker.com, clones the repository, and calls the SSM API to
# read the database password at boot.
# ------------------------------------------------------------
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.app.id
  description       = "All outbound traffic (apt, container images, git clone, SSM API)"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
