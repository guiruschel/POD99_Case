variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "alert_email" {
  type        = string
  description = "Email that receives pipeline failure alerts (Glue job failures, Step Functions execution failures)."
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

variable "state_machine_arn" {
  type = string
}
