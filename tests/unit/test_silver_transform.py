"""Unit tests for Silver dedup + enrichment (common/silver_transform.py)."""
from datetime import datetime

from common.silver_transform import dedup_and_enrich


def test_dedup_keeps_latest_entry_per_transaction(make_transactions, cosif_domain):
    rows = [
        {"id_transacao": "dup", "dt_lancamento": datetime(2026, 1, 1, 8, 0)},
        {"id_transacao": "dup", "dt_lancamento": datetime(2026, 1, 1, 20, 0)},
    ]
    result = dedup_and_enrich(make_transactions(rows), cosif_domain)

    assert result.count() == 1
    assert result.collect()[0]["dt_lancamento"] == datetime(2026, 1, 1, 20, 0)


def test_enrich_adds_cosif_metadata_when_matched(make_transactions, cosif_domain):
    result = dedup_and_enrich(make_transactions([{}]), cosif_domain)  # default cod_cosif = "1.1.1.10.00"

    row = result.collect()[0]
    assert row["cosif_descricao"] == "Disponibilidades - Caixa"
    assert row["cosif_tipo_contrato_esperado"] == "CC"


def test_enrich_leaves_metadata_null_when_no_match(make_transactions, cosif_domain):
    result = dedup_and_enrich(make_transactions([{"cod_cosif": "9.9.9.99.99"}]), cosif_domain)

    row = result.collect()[0]
    assert row["cosif_descricao"] is None
    assert row["cosif_tipo_contrato_esperado"] is None


def test_enrich_keeps_all_transaction_rows_even_without_match(make_transactions, cosif_domain):
    rows = [{"cod_cosif": "1.1.1.10.00"}, {"cod_cosif": "9.9.9.99.99"}]
    result = dedup_and_enrich(make_transactions(rows), cosif_domain)

    assert result.count() == 2
