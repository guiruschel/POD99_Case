"""Loads the data contract YAML (data_contracts/*.yaml) into a plain dict."""
import yaml


def load_contract(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def required_columns(contract: dict) -> list[str]:
    return [field["name"] for field in contract["schema"] if not field["nullable"]]
