resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "rds" {
  name   = "${var.project_name}-rds"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }
}

resource "aws_db_instance" "main" {
  identifier        = "${var.project_name}-postgres"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = "db.t3.micro"
  allocated_storage = 20

  db_name  = "docplatform"
  username = "postgres"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  skip_final_snapshot = true
  publicly_accessible = false

  # Enable pgvector extension support
  parameter_group_name = aws_db_parameter_group.main.name
}

resource "aws_db_parameter_group" "main" {
  name   = "${var.project_name}-postgres"
  family = "postgres16"
}
