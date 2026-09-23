variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "bronze_job_name" {
  type = string
}

variable "silver_job_name" {
  type = string
}

variable "gold_job_name" {
  type = string
}

variable "bronze_job_arn" {
  type = string
}

variable "silver_job_arn" {
  type = string
}

variable "gold_job_arn" {
  type = string
}

variable "schedule_expression" {
  type        = string
  default     = "cron(0 22 * * ? *)"
  description = "When the daily pipeline fires (UTC cron). Demo default echoes the challenge's D+0 22h start of the closing window. The EventBridge rule ships DISABLED (see main.tf) so this never actually fires unattended during the case study."
}
