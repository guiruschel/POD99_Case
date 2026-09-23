output "data_lake_bucket_name" {
  description = "S3 bucket holding the raw/bronze/silver/gold prefixes"
  value       = module.s3.bucket_id
}

output "glue_database_name" {
  description = "Glue Data Catalog database for this project"
  value       = module.glue_catalog.database_name
}

output "glue_job_role_arn" {
  description = "IAM role assumed by the Glue jobs"
  value       = module.iam.glue_job_role_arn
}

output "bronze_job_name" {
  description = "Name of the Bronze Glue job"
  value       = module.glue_jobs.bronze_job_name
}

output "silver_job_name" {
  description = "Name of the Silver Glue job"
  value       = module.glue_jobs.silver_job_name
}

output "gold_job_name" {
  description = "Name of the Gold Glue job"
  value       = module.glue_jobs.gold_job_name
}

output "state_machine_name" {
  description = "Name of the Step Functions pipeline (Bronze -> Silver -> Gold)"
  value       = module.orchestration.state_machine_name
}

output "pipeline_alerts_topic_arn" {
  description = "SNS topic that receives Glue job / Step Functions pipeline failure alerts"
  value       = module.monitoring.sns_topic_arn
}

output "budget_name" {
  description = "AWS Budgets cost guard for this project"
  value       = module.budget.budget_name
}
