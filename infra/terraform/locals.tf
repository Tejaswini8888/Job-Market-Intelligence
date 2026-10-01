# ==========================================================
# Job Market Intelligence & Skill Analytics Platform
# infra/terraform/locals.tf
#
# Derived values shared by the other files. Nothing here creates a
# resource; it only keeps naming and lookup logic in one place.
# ==========================================================

locals {
  # "<project>-<environment>" - e.g. job-market-intelligence-demo
  name_prefix = "${var.project_name}-${var.environment}"

  # Tags applied to every resource through provider.tf default_tags.
  common_tags = merge(var.tags, {
    Name        = local.name_prefix
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "job-market-intelligence"
  })

  # ------------------------------------------------------------
  # Availability zones
  #
  # An explicit list always wins. Otherwise take the first var.az_count
  # zones the region reports. `slice` keeps the request inside the
  # returned list even in regions that report only two zones.
  # ------------------------------------------------------------
  azs = length(var.availability_zones) > 0 ? var.availability_zones : slice(
    data.aws_availability_zones.available.names, 0, var.az_count
  )

  # ------------------------------------------------------------
  # SSH key
  #
  # Only the public half is ever loaded. `try()` turns a missing file
  # into null instead of a hard error, so ec2.tf can raise a readable
  # precondition message instead of a bare "no such file".
  # ------------------------------------------------------------
  ssh_public_key = try(
    coalesce(var.ssh_public_key, file(pathexpand(var.ssh_public_key_path))),
    null
  )

  # Fixed Elastic IP is optional; see var.enable_elastic_ip.
  elastic_ip_enabled = var.enable_elastic_ip && var.associate_public_ip

  # ------------------------------------------------------------
  # Secret storage
  #
  # One SSM Standard SecureString per deployment. Standard parameters
  # are free at this scale and the value is encrypted at rest.
  # ------------------------------------------------------------
  db_password_parameter_name = coalesce(
    var.db_password_parameter_name, "/${local.name_prefix}/db_password"
  )

  # ------------------------------------------------------------
  # Bootstrap inputs handed to user_data.tftpl
  # ------------------------------------------------------------
  user_data_vars = {
    app_dir            = var.app_dir
    aws_region         = var.aws_region
    dashboard_port     = var.dashboard_port
    api_port           = var.api_port
    db_name            = var.db_name
    db_user            = var.db_user
    git_branch         = var.git_branch
    repo_url           = var.repo_url
    ssm_parameter_name = local.db_password_parameter_name
  }
}
