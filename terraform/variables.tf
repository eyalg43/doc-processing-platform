variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "eu-west-3"
}

variable "project_name" {
  description = "Project name used for naming all resources"
  type        = string
  default     = "doc-platform"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "db_password" {
  description = "Postgres master password"
  type        = string
  sensitive   = true
}

variable "jwt_secret" {
  description = "JWT signing secret"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}
