output "bronze_job_name" {
  value = aws_glue_job.bronze_ingest.name
}

output "silver_job_name" {
  value = aws_glue_job.silver_transform.name
}

output "gold_job_name" {
  value = aws_glue_job.gold_aggregate.name
}
