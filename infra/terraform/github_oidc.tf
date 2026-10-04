# ==========================================================
# GitHub Actions OIDC deployment
# Allows ONLY this repository's main branch to assume the
# deployment role. No long-lived AWS access keys are used.
# ==========================================================

resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com"
  ]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-github-oidc"
  })
}

data "aws_iam_policy_document" "github_deploy_assume_role" {
  statement {
    sid     = "AllowGitHubActionsFromMain"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type = "Federated"
      identifiers = [
        aws_iam_openid_connect_provider.github.arn
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:Tejaswini8888@154421074/Job-Market-Intelligence@1394870909:ref:refs/heads/main"
      ]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name                 = "${local.name_prefix}-github-deploy-role"
  description          = "GitHub Actions deployment role for the Job Market Intelligence main branch"
  assume_role_policy   = data.aws_iam_policy_document.github_deploy_assume_role.json
  max_session_duration = 3600

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-github-deploy-role"
  })
}

data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid    = "DeployThroughSSM"
    effect = "Allow"

    actions = [
      "ssm:SendCommand"
    ]

    resources = [
      "arn:aws:ssm:${var.aws_region}:*:document/AWS-RunShellScript"
    ]
  }

  statement {
    sid    = "TargetExistingInstance"
    effect = "Allow"

    actions = [
      "ssm:SendCommand"
    ]

    resources = [
      aws_instance.app.arn
    ]
  }

  statement {
    sid    = "ReadCommandResult"
    effect = "Allow"

    actions = [
      "ssm:GetCommandInvocation"
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${local.name_prefix}-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}

output "github_deploy_role_arn" {
  description = "IAM role ARN used by GitHub Actions through OIDC"
  value       = aws_iam_role.github_deploy.arn
}

output "github_deploy_instance_id" {
  description = "EC2 instance ID targeted by GitHub Actions deployment"
  value       = aws_instance.app.id
}