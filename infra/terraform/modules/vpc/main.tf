# VPC with public subnets (NAT gateways, load balancers) and private
# subnets (EKS nodes, RDS, ElastiCache, MSK — nothing that needs a public
# IP). WHY private subnets for the data layer specifically: every
# datastore this platform uses (Postgres, Redis, Kafka) should be
# unreachable from the public internet even if a security group rule is
# ever misconfigured — network-layer isolation is the second line of
# defense behind (not instead of) security groups.

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "platform-vpc" }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "platform-igw" }
}

resource "aws_subnet" "public" {
  count                   = var.availability_zone_count
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                     = "platform-public-${count.index}"
    "kubernetes.io/role/elb" = "1" # required tag for the AWS Load Balancer Controller to discover this subnet
  }
}

resource "aws_subnet" "private" {
  count             = var.availability_zone_count
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + var.availability_zone_count)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name                              = "platform-private-${count.index}"
    "kubernetes.io/role/internal-elb" = "1"
  }
}

# One NAT gateway per AZ (not a single shared one) — a single NAT gateway
# is a cross-AZ single point of failure for all outbound traffic from
# every private subnet; losing that AZ takes down internet egress
# cluster-wide, not just for that AZ's nodes.
resource "aws_eip" "nat" {
  count  = var.availability_zone_count
  domain = "vpc"
  tags   = { Name = "platform-nat-eip-${count.index}" }
}

resource "aws_nat_gateway" "main" {
  count         = var.availability_zone_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags          = { Name = "platform-nat-${count.index}" }
  depends_on    = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "platform-public-rt" }
}

resource "aws_route_table" "private" {
  count  = var.availability_zone_count
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[count.index].id
  }
  tags = { Name = "platform-private-rt-${count.index}" }
}

resource "aws_route_table_association" "public" {
  count          = var.availability_zone_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = var.availability_zone_count
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
