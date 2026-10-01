# ==========================================================
# Job Market Intelligence & Skill Analytics Platform
# infra/terraform/versions.tf
#
# Terraform / provider version constraints, plus where the state lives.
#
# Everything in infra/terraform/ provisions ONE thing: a single EC2
# instance that runs the existing docker-compose.yml stack
# (postgres :5432 internal, api :8000, dashboard :8501).
# Nothing here deploys application code - user_data.tftpl clones the
# repository and lets Compose build the two images.
# ==========================================================

terraform {
  # >= 1.10 is required by the S3 backend: state locking uses the native
  # lockfile (use_lockfile = true, see backend.hcl.example), which did not
  # exist before 1.10. It also keeps lifecycle preconditions and
  # try()/coalesce() behaviour stable, which variables.tf and ec2.tf rely on.
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # ------------------------------------------------------------
  # Remote state
  # ------------------------------------------------------------
  # Left deliberately EMPTY so nothing can be applied by accident and no
  # bucket is hardcoded. Local validation therefore uses:
  #
  #   terraform init -backend=false
  #
  # A REAL deployment should use an encrypted, versioned S3 backend
  # (bucket + DynamoDB lock table, or S3-native locking). Configure it
  # EITHER here with no values (backend "s3" {}) and pass
  # -backend-config=backend.hcl, OR leave it out entirely and use
  # `terraform init -backend-config=...` - but never commit state
  # containing the SSM SecureString value to Git.
  # See README.md -> "State handling".
  # ------------------------------------------------------------
  backend "s3" {}
}
