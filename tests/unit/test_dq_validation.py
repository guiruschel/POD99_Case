"""Unit tests for the Bronze data quality rules (common/dq_validation.py)."""
from datetime import datetime

from common.dq_validation import validate_dataframe

CONTRACT = {
    "schema": [
        {"name": "id_transacao", "nullable": False},
        {"name": "id_contrato", "nullable": False},
        {"name": "valor_lancamento", "nullable": False},
        {"name": "cod_cosif", "nullable": True},
    ]
}


def test_valid_row_passes(make_transactions, cosif_domain):
    valid_df, rejected_df = validate_dataframe(make_transactions([{}]), CONTRACT, cosif_domain)
    assert valid_df.count() == 1
    assert rejected_df.count() == 0


def test_duplicate_id_transacao_is_rejected(make_transactions, cosif_domain):
    rows = [{"id_transacao": "dup"}, {"id_transacao": "dup"}]
    valid_df, rejected_df = validate_dataframe(make_transactions(rows), CONTRACT, cosif_domain)
    assert valid_df.count() == 0
    assert rejected_df.count() == 2


def test_negative_value_is_rejected(make_transactions, cosif_domain):
    valid_df, rejected_df = validate_dataframe(make_transactions([{"valor_lancamento": -50.0}]), CONTRACT, cosif_domain)
    assert valid_df.count() == 0
    reasons = rejected_df.collect()[0]["dq_rejection_reasons"]
    assert "valor_lancamento_positive" in reasons


def test_entry_after_processing_date_is_rejected(make_transactions, cosif_domain):
    rows = [{"dt_lancamento": datetime(2026, 1, 5)}]  # dt_processamento defaults to 2026-01-01
    valid_df, rejected_df = validate_dataframe(make_transactions(rows), CONTRACT, cosif_domain)
    assert rejected_df.count() == 1


def test_unknown_cosif_code_is_rejected(make_transactions, cosif_domain):
    valid_df, rejected_df = validate_dataframe(
        make_transactions([{"cod_cosif": "9.9.9.99.99"}]), CONTRACT, cosif_domain
    )
    assert rejected_df.count() == 1


def test_null_cosif_code_is_allowed(make_transactions, cosif_domain):
    valid_df, rejected_df = validate_dataframe(make_transactions([{"cod_cosif": None}]), CONTRACT, cosif_domain)
    assert valid_df.count() == 1
    assert rejected_df.count() == 0


def test_missing_required_field_is_rejected(make_transactions, cosif_domain):
    valid_df, rejected_df = validate_dataframe(make_transactions([{"id_contrato": ""}]), CONTRACT, cosif_domain)
    assert rejected_df.count() == 1
