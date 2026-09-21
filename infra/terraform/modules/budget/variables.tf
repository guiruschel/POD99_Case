variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "monthly_limit_usd" {
  description = "Monthly cost threshold. Kept low on purpose (see ADR on cost budget) since Glue Jobs are the only billed service in this project."
  type        = string
  default     = "5"
}

variable "alert_email" {
  description = "Email that receives the budget alert notifications"
  type        = string
}
