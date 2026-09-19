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
