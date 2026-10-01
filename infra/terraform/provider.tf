# ==========================================================
# Job Market Intelligence & Skill Analytics Platform
# infra/terraform/provider.tf
#
# AWS provider configuration.
#
# NO CREDENTIALS ARE CONFIGURED HERE, ON PURPOSE.
# There is no access_key / secret_key argument anywhere in this
# directory. Terraform authenticates using the standard AWS credential
# chain, in this order:
#
#   1. AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN
#      exported in the shell for a one-off session
#   2. A named profile:            export AWS_PROFILE=my-profile
#   3. ~/.aws/credentials
#   4. An assumed role / SSO / instance role
#
# Key files and .aws/credentials stay out of this repository: .gitignore
# already excludes *.pem, *.key and *.tfvars.
#
# default_tags stamp every resource with the project name, the
# environment and the owning repository, so the EC2 console, Cost
# Explorer and any teardown script can find them again.
# ==========================================================

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}
