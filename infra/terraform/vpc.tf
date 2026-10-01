# ==========================================================
# Job Market Intelligence & Skill Analytics Platform
# infra/terraform/vpc.tf
#
# A deliberately small network: one VPC, one internet gateway, one
# public subnet per AZ and one private subnet per AZ.
#
# COST DECISION (this is a portfolio/demo project):
#   There is NO NAT Gateway. A NAT Gateway is roughly USD 32/month plus
#   data processing charges - by far the largest fixed cost in a stack
#   like this, and it would dwarf the EC2 instance itself. Instead the
#   single EC2 instance runs in a PUBLIC subnet with a public IP, and
#   its reachability is controlled entirely by the security group in
#   security_groups.tf (only 8000, 8501 and optionally 22).
#
#   The private subnets are created anyway, with no default route, so
#   that a future stage can drop in an RDS instance or a private worker
#   without renumbering anything. They are unreachable from the
#   internet by design.
#
# A production deployment would flip the instance into the private
# subnets and pay for a NAT Gateway (or a NAT instance) so it can pull
# images and clone the repository without a public IP.
# ==========================================================

data "aws_availability_zones" "available" {
  state = "available"

  # Default filters: exclude zones that are not opted-in for this account.
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

resource "aws_vpc" "this" {
  cidr_block = var.vpc_cidr

  # Required for Docker: containers resolve service names such as
  # "postgres" over the embedded DNS server, and the API/dashboard
  # containers reach each other by name.
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-igw"
  })
}

# ------------------------------------------------------------
# Public subnets - host the EC2 instance (see the COST DECISION above)
# ------------------------------------------------------------
resource "aws_subnet" "public" {
  count = length(local.azs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-${local.azs[count.index]}"
    Tier = "public"
  })
}

# ------------------------------------------------------------
# Private subnets - reserved for a future RDS / worker tier.
# No route to the internet on purpose (no NAT Gateway).
# ------------------------------------------------------------
resource "aws_subnet" "private" {
  count = length(local.azs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index + length(local.azs))
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-private-${local.azs[count.index]}"
    Tier = "private"
  })
}

# ------------------------------------------------------------
# Routing
# ------------------------------------------------------------
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-rt"
  })
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# No default route here on purpose: without a NAT Gateway an egress
# route would black-hole traffic rather than forward it.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-private-rt"
  })
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
