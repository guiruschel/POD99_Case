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

module "dynamodb" {
  source = "./modules/dynamodb"

  project_name = var.project_name
  environment  = var.environment
}

module "iam" {
  source = "./modules/iam"

  project_name            = var.project_name
  environment             = var.environment
  data_lake_bucket_arn    = module.s3.bucket_arn
  glue_catalog_arn        = local.glue_catalog_arn
  glue_database_arn       = local.glue_database_arn
  glue_tables_arn         = local.glue_tables_arn
  batch_control_table_arn = module.dynamodb.table_arn
}

module "glue_jobs" {
  source = "./modules/glue_jobs"

  project_name          = var.project_name
  environment           = var.environment
  glue_job_role_arn     = module.iam.glue_job_role_arn
  data_lake_bucket_name = module.s3.bucket_id
  glue_database_name    = module.glue_catalog.database_name
  batch_control_table   = module.dynamodb.table_name
}

module "orchestration" {
  source = "./modules/orchestration"

  project_name    = var.project_name
  environment     = var.environment
  bronze_job_name = module.glue_jobs.bronze_job_name
  silver_job_name = module.glue_jobs.silver_job_name
  gold_job_name   = module.glue_jobs.gold_job_name
  bronze_job_arn  = local.bronze_job_arn
  silver_job_arn  = local.silver_job_arn
  gold_job_arn    = local.gold_job_arn
}

module "monitoring" {
  source = "./modules/monitoring"

  project_name      = var.project_name
  environment       = var.environment
  alert_email       = var.budget_alert_email
  bronze_job_name   = module.glue_jobs.bronze_job_name
  silver_job_name   = module.glue_jobs.silver_job_name
  gold_job_name     = module.glue_jobs.gold_job_name
  state_machine_arn = module.orchestration.state_machine_arn
}

module "budget" {
  source = "./modules/budget"

  project_name      = var.project_name
  environment       = var.environment
  monthly_limit_usd = "5"
  alert_email       = var.budget_alert_email
}
