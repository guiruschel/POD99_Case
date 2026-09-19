variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "account_id" {
  description = "Used to make the bucket name globally unique"
  type        = string
}
