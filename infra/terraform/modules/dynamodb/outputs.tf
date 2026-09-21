output "table_name" {
  value = aws_dynamodb_table.batch_control.name
}

output "table_arn" {
  value = aws_dynamodb_table.batch_control.arn
}
