"""Tests for common/batch_control.py -- the DynamoDB batch-status tracker."""
from unittest.mock import MagicMock, patch

from common.batch_control import get_optional_arg, update_batch_status


def test_get_optional_arg_present():
    with patch("sys.argv", ["job.py", "--batch_control_table", "my-table"]):
        assert get_optional_arg("batch_control_table") == "my-table"


def test_get_optional_arg_missing():
    with patch("sys.argv", ["job.py", "--other_arg", "value"]):
        assert get_optional_arg("batch_control_table") is None


def test_update_batch_status_noop_without_table():
    """Local Docker runs don't pass --batch_control_table -- must not call AWS."""
    with patch("sys.argv", ["job.py"]), patch("boto3.resource") as mock_resource:
        update_batch_status("2026-08-01", "silver", "PROCESSED")

    mock_resource.assert_not_called()


def test_update_batch_status_writes_item_when_table_configured():
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    with (
        patch("sys.argv", ["job.py", "--batch_control_table", "my-table"]),
        patch("boto3.resource", return_value=mock_dynamodb) as mock_resource,
    ):
        update_batch_status("2026-08-01", "silver", "PROCESSED", row_count=4873)

    mock_resource.assert_called_once_with("dynamodb")
    mock_dynamodb.Table.assert_called_once_with("my-table")
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args.kwargs["Item"]
    assert item["id_lote"] == "2026-08-01"
    assert item["job_name"] == "silver"
    assert item["status"] == "PROCESSED"
    assert item["row_count"] == 4873
    assert "updated_at" in item
