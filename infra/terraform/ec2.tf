# ==========================================================
# Job Market Intelligence & Skill Analytics Platform
# infra/terraform/ec2.tf
#
# The compute: one Ubuntu LTS instance that installs Docker, clones this
# repository, writes a .env file from SSM Parameter Store and runs
#
#     docker compose up -d --build
#
# which produces exactly the same three services that already run
# locally: postgres (internal :5432), api (:8000) and dashboard (:8501).
#
# No application code, schema, seed data or ML artefact is changed here.
# The instance only runs the repository's own Dockerfiles and
# docker-compose.yml.
# ==========================================================

# Canonical Ubuntu 24.04 LTS (Noble) AMD64 server image.
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# ------------------------------------------------------------
# SSH key pair
#
# Imported from the public half of an existing key. The private key is
# never uploaded to AWS and never enters this repository or the state
# file. If neither ssh_public_key nor ssh_public_key_path resolves,
# the precondition on the instance below fails with a clear message.
# ------------------------------------------------------------
resource "aws_key_pair" "app" {
  count = local.ssh_public_key == null ? 0 : 1

  key_name   = "${local.name_prefix}-key"
  public_key = local.ssh_public_key

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-key"
  })
}

# ------------------------------------------------------------
# Elastic IP (optional, free while attached)
# ------------------------------------------------------------
resource "aws_eip" "app" {
  count  = local.elastic_ip_enabled ? 1 : 0
  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-eip"
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_eip_association" "app" {
  count = local.elastic_ip_enabled ? 1 : 0

  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app[0].id
}

# ------------------------------------------------------------
# ------------------------------------------------------------
# The instance
# ------------------------------------------------------------
resource "aws_instance" "app" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.app.id]
  iam_instance_profile        = aws_iam_instance_profile.app.name
  key_name                    = local.ssh_public_key == null ? null : aws_key_pair.app[0].key_name
  associate_public_ip_address = var.associate_public_ip && !local.elastic_ip_enabled

  # Detailed (one-minute) metrics are billed separately; off by default.
  monitoring = var.enable_detailed_monitoring

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    encrypted             = true
    delete_on_termination = true

    tags = merge(local.common_tags, {
      Name = "${local.name_prefix}-root"
    })
  }

  # cloud-init bootstrap: Docker, AWS CLI, git clone, .env from SSM,
  # docker compose up -d --build. See user_data.tftpl.
  user_data                   = templatefile("${path.module}/user_data.tftpl", local.user_data_vars)
  user_data_replace_on_change = true

  # The bootstrap reads the database password from SSM at boot.
  # The explicit dependency ensures the parameter exists before
  # the instance starts.
  depends_on = [aws_ssm_parameter.db_password]

  # IMDSv2 only.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ec2"
    Role = "api+dashboard+postgres"
  })

  lifecycle {
    ignore_changes = [
      associate_public_ip_address
    ]

    precondition {
      condition     = local.ssh_public_key != null
      error_message = "No SSH public key found. Set var.ssh_public_key to the contents of your id_ed25519.pub, or point var.ssh_public_key_path at that file."
    }

    precondition {
      condition     = var.instance_type != ""
      error_message = "instance_type must be set (t3.small is the realistic minimum for postgres + api + dashboard)."
    }
  }
}