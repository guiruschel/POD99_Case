"""CloudWatch custom metrics: records processed, DQ rejections, job duration.

Optional by design, same pattern as common/batch_control.py: local Docker
runs don't pass --cloudwatch_namespace, so put_metric() is a no-op instead
of trying to call AWS without credentials.
"""
from common.batch_control import get_optional_arg


def put_metric(metric_name: str, value: float, job_name_tag: str, unit: str = "Count", logger=None) -> None:
    namespace = get_optional_arg("cloudwatch_namespace")
    if not namespace:
        return

    import boto3

    boto3.client("cloudwatch").put_metric_data(
        Namespace=namespace,
        MetricData=[
            {
                "MetricName": metric_name,
                "Value": value,
                "Unit": unit,
                "Dimensions": [{"Name": "JobName", "Value": job_name_tag}],
            }
        ],
    )

    if logger is not None:
        logger.info(f"metric_published name={metric_name} value={value} job_name={job_name_tag}")
