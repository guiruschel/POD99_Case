variable "project_name" {
  description = "Short name used as a prefix for all resources"
  type        = string
  default     = "pod99-fin-case"
}

variable "environment" {
  description = "Deployment environment (dev is the only one used for this case study)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region. In a real deployment this would be sa-east-1 (São Paulo) for data residency (regulated Brazilian financial data, COSIF). Set to us-east-2 here to match the demo AWS account/profile actually used for this case study; the residency trade-off is documented as an ADR."
  type        = string
  default     = "us-east-2"
}

variable "aws_profile" {
  description = "Named AWS CLI profile to authenticate with. Left empty by default so Terraform falls back to the AWS_PROFILE env var or the default credential chain — never hardcode credentials here."
  type        = string
  default     = ""
}
