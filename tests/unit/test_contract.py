"""Regression tests for common/contract.py -- found via a real AWS run where
open("s3://...") silently doesn't work like a local path."""
from unittest.mock import MagicMock, patch

from common.contract import load_contract, required_columns

CONTRACT_YAML = b"""
dataset: test_dataset
schema:
  - name: id
    nullable: false
  - name: optional_field
    nullable: true
"""


def test_load_contract_from_local_path(tmp_path):
    contract_file = tmp_path / "contract.yaml"
    contract_file.write_bytes(CONTRACT_YAML)

    contract = load_contract(str(contract_file))

    assert contract["dataset"] == "test_dataset"


def test_load_contract_from_s3_path():
    mock_body = MagicMock()
    mock_body.read.return_value = CONTRACT_YAML
    mock_s3_client = MagicMock()
    mock_s3_client.get_object.return_value = {"Body": mock_body}

    with patch("boto3.client", return_value=mock_s3_client):
        contract = load_contract("s3://my-bucket/scripts/contract.yaml")

    mock_s3_client.get_object.assert_called_once_with(Bucket="my-bucket", Key="scripts/contract.yaml")
    assert contract["dataset"] == "test_dataset"


def test_required_columns():
    contract = {"schema": [{"name": "id", "nullable": False}, {"name": "optional_field", "nullable": True}]}
    assert required_columns(contract) == ["id"]
