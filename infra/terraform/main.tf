provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = local.common_tags
  }
}

data "aws_caller_identity" "current" {}

module "s3" {
  source = "./modules/s3"

  project_name = var.project_name
  environment  = var.environment
  account_id   = data.aws_caller_identity.current.account_id
}

module "glue_catalog" {
  source = "./modules/glue_catalog"

  project_name = var.project_name
  environment  = var.environment
}

module "iam" {
  source = "./modules/iam"

  project_name          = var.project_name
  environment           = var.environment
  data_lake_bucket_arn   = module.s3.bucket_arn
}
