"""Loads the data contract YAML (data_contracts/*.yaml) into a plain dict."""
import yaml


def load_contract(path: str) -> dict:
    if path.startswith("s3://"):
        import boto3

        bucket, key = path[len("s3://") :].split("/", 1)
        body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
        return yaml.safe_load(body)

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def required_columns(contract: dict) -> list[str]:
    return [field["name"] for field in contract["schema"] if not field["nullable"]]
