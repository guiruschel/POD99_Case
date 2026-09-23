output "state_machine_arn" {
  value = aws_sfn_state_machine.pipeline.arn
}

output "state_machine_name" {
  value = aws_sfn_state_machine.pipeline.name
}

output "eventbridge_rule_name" {
  value = aws_cloudwatch_event_rule.daily_pipeline.name
}
