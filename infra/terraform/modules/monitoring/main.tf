# Failure alerting for the pipeline: any Glue job (Bronze/Silver/Gold)
# failing, or the Step Functions execution as a whole failing, sends an
# email. Two separate paths because they use different native AWS event
# sources, but both land on the same SNS topic.
resource "aws_sns_topic" "pipeline_alerts" {
  name = "${var.project_name}-${var.environment}-pipeline-alerts"
}

resource "aws_sns_topic_subscription" "pipeline_alerts_email" {
  topic_arn = aws_sns_topic.pipeline_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- Path 1: individual Glue job failures, via EventBridge -----------------
# Glue automatically emits "Glue Job State Change" events to the account's
# default EventBridge bus -- no extra instrumentation needed in the jobs.
data "aws_iam_policy_document" "sns_publish_from_events" {
  statement {
    sid     = "AllowEventBridgePublish"
    actions = ["sns:Publish"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    resources = [aws_sns_topic.pipeline_alerts.arn]
  }
}

resource "aws_sns_topic_policy" "allow_eventbridge_publish" {
  arn    = aws_sns_topic.pipeline_alerts.arn
  policy = data.aws_iam_policy_document.sns_publish_from_events.json
}

resource "aws_cloudwatch_event_rule" "glue_job_failed" {
  name        = "${var.project_name}-${var.environment}-glue-job-failed"
  description = "Fires when any pipeline Glue job (Bronze/Silver/Gold) fails, times out, or errors"

  event_pattern = jsonencode({
    source      = ["aws.glue"]
    detail-type = ["Glue Job State Change"]
    detail = {
      jobName = [var.bronze_job_name, var.silver_job_name, var.gold_job_name]
      state   = ["FAILED", "TIMEOUT", "ERROR"]
    }
  })
}

resource "aws_cloudwatch_event_target" "glue_job_failed_to_sns" {
  rule = aws_cloudwatch_event_rule.glue_job_failed.name
  arn  = aws_sns_topic.pipeline_alerts.arn
}

# --- Path 2: whole-pipeline (Step Functions execution) failures ------------
# AWS/States ExecutionsFailed is a native metric, no custom instrumentation
# needed either.
resource "aws_cloudwatch_metric_alarm" "pipeline_execution_failed" {
  alarm_name          = "${var.project_name}-${var.environment}-pipeline-execution-failed"
  alarm_description   = "Fires when a Step Functions execution of the Bronze->Silver->Gold pipeline fails"
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  dimensions          = { StateMachineArn = var.state_machine_arn }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.pipeline_alerts.arn]
}
