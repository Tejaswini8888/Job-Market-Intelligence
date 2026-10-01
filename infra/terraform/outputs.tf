# ==========================================================
# Job Market Intelligence & Skill Analytics Platform
# infra/terraform/outputs.tf
#
# Read-only summary of what was built, so the URLs and the ssh
# command can be pasted straight into the README or a demo.
#
# NOTHING SENSITIVE IS OUTPUT. The database password is never printed,
# the SSM SecureString value is never output, and no credential of any
# kind appears below. The parameter NAME is safe to show: the instance
# needs it to fetch the value through its IAM role.
# ==========================================================

locals {
  # try() so this keeps working whether or not an Elastic IP was created.
  public_ip = try(aws_eip.app[0].public_ip, aws_instance.app.public_ip, "pending")

  # Built here rather than inside an output, because Terraform does not
  # allow one output to reference another.
  api_health_url = "http://${local.public_ip}:${var.api_port}/health"
  api_url        = "http://${local.public_ip}:${var.api_port}"
  dashboard_url  = "http://${local.public_ip}:${var.dashboard_port}"
  ssh_command    = "ssh -i <path-to-your-private-key> ubuntu@${local.public_ip}"
}

output "vpc_id" {
  description = "ID of the VPC created for this deployment."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnets that host the EC2 instance (index 0 is used)."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnets reserved for a future RDS instance or worker tier. They have no route to the internet."
  value       = aws_subnet.private[*].id
}

output "security_group_id" {
  description = "Security group attached to the instance. Its only inbound rules are the API port, the dashboard port and optionally SSH."
  value       = aws_security_group.app.id
}

output "instance_id" {
  description = "ID of the EC2 instance running the Compose stack."
  value       = aws_instance.app.id
}

output "instance_type" {
  description = "Instance type that was launched."
  value       = aws_instance.app.instance_type
}

output "instance_availability_zone" {
  description = "Availability zone the instance was launched into."
  value       = aws_instance.app.availability_zone
}

output "public_ip" {
  description = "Public IPv4 address of the instance (Elastic IP when enable_elastic_ip is true). Use this to build the URLs below."
  value       = local.public_ip
}

output "dashboard_url" {
  description = "Streamlit dashboard URL, matching the 8501:8501 mapping in docker-compose.yml."
  value       = local.dashboard_url
}

output "api_url" {
  description = "FastAPI base URL, matching the 8000:8000 mapping in docker-compose.yml."
  value       = local.api_url
}

output "api_health_url" {
  description = "Health endpoint to use as the post-deployment smoke test; returns 200 with database status \"up\" once PostgreSQL is reachable."
  value       = local.api_health_url
}

output "api_docs_url" {
  description = "Interactive FastAPI documentation (Swagger UI) served by the same container."
  value       = "${local.api_url}/docs"
}

output "ssh_command" {
  description = "Ready-to-paste SSH command for the instance."
  value       = local.ssh_command
}

output "database_access_note" {
  description = "Reminder that PostgreSQL is deliberately not reachable from the internet."
  value       = "PostgreSQL listens on 5432 only inside the Compose network. No host port is published and no security-group rule opens 5432; reach it with: docker compose exec postgres psql -U ${var.db_user} -d ${var.db_name}"
}

output "db_password_parameter_name" {
  description = "Name (not value) of the SSM SecureString holding the database password, for reference or for rotation."
  value       = aws_ssm_parameter.db_password.name
}

output "ec2_instance_role_arn" {
  description = "ARN of the instance role, whose only secret permission is ssm:GetParameter on the single parameter above."
  value       = aws_iam_role.app.arn
}

output "connection_instructions" {
  description = "Ordered checklist for verifying the deployment after a future apply."
  value = join("\n", [
    "1. curl ${local.api_health_url}   -> expect HTTP 200 and {\"database\": \"up\"}",
    "2. open ${local.dashboard_url}     -> Streamlit dashboard",
    "3. ${local.ssh_command}",
    "4. on the host: cd ${var.app_dir} && docker compose ps   -> three healthy services",
    "5. on the host: docker compose logs -f api",
    "",
    "PostgreSQL is NOT public: no host port is published and no security-group rule",
    "allows 5432. Only ${var.api_port} (API) and ${var.dashboard_port} (dashboard) accept inbound traffic${var.enable_ssh ? ", plus 22 for SSH" : ""}.",
  ])
}
