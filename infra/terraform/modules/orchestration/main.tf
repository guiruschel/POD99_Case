# Step Functions orchestrates Bronze -> Silver -> Gold as a single pipeline,
# using the native Glue "startJobRun.sync" integration (polls the job run
# until it finishes -- no custom polling/Lambda glue code needed). Silver and
# Gold receive --processing_date from the execution input; Bronze does not
# (see jobs/bronze_ingest.py -- it ingests the whole raw/ prefix per run, not
# a single business day).
data "aws_iam_policy_document" "step_functions_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "step_functions" {
  name               = "${var.project_name}-${var.environment}-step-functions-role"
  assume_role_policy = data.aws_iam_policy_document.step_functions_assume_role.json
}

data "aws_iam_policy_document" "step_functions_glue_access" {
  statement {
    sid = "RunGlueJobs"

    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:BatchStopJobRun",
    ]

    resources = [var.bronze_job_arn, var.silver_job_arn, var.gold_job_arn]
  }
}

resource "aws_iam_role_policy" "step_functions_glue_access" {
  name   = "${var.project_name}-${var.environment}-step-functions-glue-access"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.step_functions_glue_access.json
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.project_name}-${var.environment}-pipeline"
  role_arn = aws_iam_role.step_functions.arn

  definition = jsonencode({
    Comment = "Bronze -> Silver -> Gold daily pipeline for fin_contabilidade_saldo_contrato. Input: {\"processing_date\": \"YYYY-MM-DD\"}."
    StartAt = "RunBronze"
    States = {
      RunBronze = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startJobRun.sync"
        Parameters = {
          JobName = var.bronze_job_name
        }
        # Without this, the Task's output (the Glue job-run result object)
        # replaces the state's whole input by default -- found for real:
        # $.processing_date disappeared after RunBronze, so RunSilver failed
        # with States.Runtime ("JSONPath ... could not be found"). Discarding
        # the job-run result here keeps the original execution input intact.
        ResultPath = null
        Next       = "RunSilver"
        Catch      = [{ ErrorEquals = ["States.ALL"], Next = "PipelineFailed" }]
      }
      RunSilver = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startJobRun.sync"
        Parameters = {
          JobName = var.silver_job_name
          Arguments = {
            "--processing_date.$" = "$.processing_date"
          }
        }
        ResultPath = null # same reason as RunBronze -- RunGold also needs $.processing_date
        Next       = "RunGold"
        Catch      = [{ ErrorEquals = ["States.ALL"], Next = "PipelineFailed" }]
      }
      RunGold = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startJobRun.sync"
        Parameters = {
          JobName = var.gold_job_name
          Arguments = {
            "--processing_date.$" = "$.processing_date"
          }
        }
        End   = true
        Catch = [{ ErrorEquals = ["States.ALL"], Next = "PipelineFailed" }]
      }
      PipelineFailed = {
        Type  = "Fail"
        Error = "PipelineFailed"
        Cause = "One of the Glue jobs failed -- check the Glue job run or the batch_control DynamoDB table for details"
      }
    }
  })
}

# EventBridge: daily schedule trigger. The rule ships DISABLED on purpose --
# computing "yesterday" as a real date needs either a small Lambda or an
# EventBridge Scheduler date expression, out of scope for this case study,
# and an enabled schedule would fire unattended (and cost money) for the
# rest of the case's lifetime. Documented here, not hidden: a production
# rollout would enable it with a real date-computation step in front.
data "aws_iam_policy_document" "eventbridge_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge_invoke_step_functions" {
  name               = "${var.project_name}-${var.environment}-eventbridge-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume_role.json
}

data "aws_iam_policy_document" "eventbridge_start_execution" {
  statement {
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.pipeline.arn]
  }
}

resource "aws_iam_role_policy" "eventbridge_start_execution" {
  name   = "${var.project_name}-${var.environment}-eventbridge-start-execution"
  role   = aws_iam_role.eventbridge_invoke_step_functions.id
  policy = data.aws_iam_policy_document.eventbridge_start_execution.json
}

resource "aws_cloudwatch_event_rule" "daily_pipeline" {
  name                = "${var.project_name}-${var.environment}-daily-pipeline"
  description         = "Triggers the Bronze->Silver->Gold pipeline daily"
  schedule_expression = var.schedule_expression
  state               = "DISABLED"
}

resource "aws_cloudwatch_event_target" "pipeline" {
  rule     = aws_cloudwatch_event_rule.daily_pipeline.name
  arn      = aws_sfn_state_machine.pipeline.arn
  role_arn = aws_iam_role.eventbridge_invoke_step_functions.arn

  # Placeholder date -- see the module-level comment above.
  input = jsonencode({
    processing_date = "REPLACE_WITH_YYYY-MM-DD"
  })
}
