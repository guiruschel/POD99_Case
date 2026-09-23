"""Tests for common/metrics.py -- the CloudWatch custom-metrics publisher."""
from unittest.mock import MagicMock, patch

from common.metrics import put_metric


def test_put_metric_noop_without_namespace():
    """Local Docker runs don't pass --cloudwatch_namespace -- must not call AWS."""
    with patch("sys.argv", ["job.py"]), patch("boto3.client") as mock_client:
        put_metric("records_processed", 4873, "bronze")

    mock_client.assert_not_called()


def test_put_metric_publishes_when_namespace_configured():
    mock_cw = MagicMock()

    with (
        patch("sys.argv", ["job.py", "--cloudwatch_namespace", "Pod99FinCase"]),
        patch("boto3.client", return_value=mock_cw) as mock_client,
    ):
        put_metric("records_processed", 4873, "bronze", unit="Count")

    mock_client.assert_called_once_with("cloudwatch")
    mock_cw.put_metric_data.assert_called_once()
    call = mock_cw.put_metric_data.call_args.kwargs
    assert call["Namespace"] == "Pod99FinCase"
    metric = call["MetricData"][0]
    assert metric["MetricName"] == "records_processed"
    assert metric["Value"] == 4873
    assert metric["Unit"] == "Count"
    assert metric["Dimensions"] == [{"Name": "JobName", "Value": "bronze"}]
