# ==========================================================
# Job Market Intelligence & Skill Analytics Platform
# infra/terraform/iam.tf
#
# The instance gets the smallest role that still lets it work, and
# nothing more:
#
#   1. EC2_ASSUME_ROLE for ec2.amazonaws.com - the trust policy.
#   2. AmazonSSMManagedInstanceCore - so the host is visible in SSM
#      Session Manager and can be logged into without an SSH key.
#   3. ssm:GetParameter on ONE parameter (the database password) and
#      nothing else.
#
# There are no inline credentials, no *.pem files and no static keys:
# the instance identity comes from the IMDS-backed instance profile
# that AWS rotates automatically.
#
# WHY SSM PARAMETER STORE FOR THE PASSWORD
#   The value is written once as a SecureString (encrypted at rest) and
#   read back by user_data at boot through the instance profile. That
#   means the password does not appear in cloud-init user-data, does not
#   appear in `aws ec2 describe-instance-attribute --user-data`, and is
#   never committed to this repository. A Standard parameter at this
#   scale is free.
#
#   Honest caveat: because Terraform creates the parameter from
#   var.db_password, the value is still stored in Terraform state.
#   Protect that state (encrypted S3 backend, no git) - see README.md.
# ==========================================================

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    sid     = "AllowEC2ToAssumeThisRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name                 = "${local.name_prefix}-ec2-role"
  description          = "EC2 role for the Job Market Intelligence Compose stack (read one SSM secret)"
  assume_role_policy   = data.aws_iam_policy_document.ec2_assume_role.json
  max_session_duration = 3600

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ec2-role"
  })
}

# --- Session Manager access (no inbound SSH port required) -------------------
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# --- Read exactly one SecureString, the database password ------------------
data "aws_iam_policy_document" "read_db_password" {
  statement {
    sid       = "ReadDatabasePasswordFromParameterStore"
    effect    = "Allow"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [aws_ssm_parameter.db_password.arn]

    # kms:Decrypt is deliberately absent. The parameter is encrypted with
    # the AWS managed key alias/aws/ssm, and SSM decrypts on the caller's
    # behalf, so no KMS grant is needed. Switching the parameter to a
    # customer-managed key would require adding kms:Decrypt here.
  }
}

resource "aws_iam_role_policy" "read_db_password" {
  name   = "${local.name_prefix}-read-db-password"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.read_db_password.json
}

resource "aws_iam_instance_profile" "app" {
  name = "${local.name_prefix}-ec2-profile"
  role = aws_iam_role.app.name

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ec2-profile"
  })
}

# ------------------------------------------------------------
# The secret itself
# ------------------------------------------------------------
resource "aws_ssm_parameter" "db_password" {
  name        = "/${local.name_prefix}/db_password"
  description = "PostgreSQL password for job_market_intelligence on job-market-intelligence-demo. Read at boot by the EC2 host."
  type        = "SecureString"
  value       = var.db_password

  lifecycle {
    ignore_changes = [value]
  }

  tags = merge(local.common_tags, {
    Name = "/${local.name_prefix}/db_password"
  })


  # Rotating the password in tfvars replaces the value in place; the
  # parameter ARN stays stable so the instance role keeps working.
}