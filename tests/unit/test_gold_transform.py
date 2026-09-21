"""Unit tests for the Gold aggregations (common/gold_transform.py)."""
from common.gold_transform import (
    classificacao_cosif,
    reconciliacao_agencia,
    saldo_por_conta,
    saldo_por_contrato,
)


def test_saldo_por_contrato_sums_credito_and_debito(make_transactions):
    rows = [
        {"tipo_lancamento": "CREDITO", "valor_lancamento": 300.0},
        {"tipo_lancamento": "DEBITO", "valor_lancamento": 100.0},
    ]
    result = saldo_por_contrato(make_transactions(rows))

    assert result.count() == 1
    row = result.collect()[0]
    assert row["saldo"] == 200.0
    assert row["qtd_lancamentos"] == 2


def test_saldo_por_contrato_estorno_flips_sign(make_transactions):
    rows = [
        {"tipo_lancamento": "CREDITO", "valor_lancamento": 300.0},
        {"tipo_lancamento": "CREDITO", "valor_lancamento": 300.0, "flag_estorno": True},
    ]
    result = saldo_por_contrato(make_transactions(rows))

    assert result.collect()[0]["saldo"] == 0.0


def test_saldo_por_contrato_separates_by_contrato(make_transactions):
    rows = [
        {"id_contrato": "c1", "tipo_lancamento": "CREDITO", "valor_lancamento": 100.0},
        {"id_contrato": "c2", "tipo_lancamento": "CREDITO", "valor_lancamento": 50.0},
    ]
    result = saldo_por_contrato(make_transactions(rows))

    assert result.count() == 2


def test_saldo_por_conta_aggregates_across_contratos(make_transactions):
    rows = [
        {"id_contrato": "c1", "id_conta": "conta1", "tipo_lancamento": "CREDITO", "valor_lancamento": 100.0},
        {"id_contrato": "c2", "id_conta": "conta1", "tipo_lancamento": "CREDITO", "valor_lancamento": 50.0},
    ]
    contrato_df = saldo_por_contrato(make_transactions(rows))
    result = saldo_por_conta(contrato_df)

    assert result.count() == 1
    row = result.collect()[0]
    assert row["saldo"] == 150.0
    assert row["qtd_contratos"] == 2


def test_classificacao_cosif_enriches_with_descricao(make_transactions, cosif_domain):
    result = classificacao_cosif(make_transactions([{}]), cosif_domain)  # default cod_cosif = "1.1.1.10.00"

    row = result.collect()[0]
    assert row["cosif_descricao"] == "Disponibilidades - Caixa"
    assert row["saldo"] == 100.0


def test_reconciliacao_agencia_totals_debito_and_credito_separately(make_transactions):
    rows = [
        {"cod_agencia": "0001", "tipo_lancamento": "CREDITO", "valor_lancamento": 300.0},
        {"cod_agencia": "0001", "tipo_lancamento": "DEBITO", "valor_lancamento": 100.0},
        {"cod_agencia": "0001", "tipo_lancamento": "TARIFA", "valor_lancamento": 5.0},
    ]
    result = reconciliacao_agencia(make_transactions(rows))

    row = result.collect()[0]
    assert row["total_credito"] == 300.0
    assert row["total_debito"] == 100.0
    assert row["diferenca_credito_debito"] == 200.0


def test_reconciliacao_agencia_separates_by_agencia(make_transactions):
    rows = [
        {"cod_agencia": "0001", "tipo_lancamento": "CREDITO", "valor_lancamento": 100.0},
        {"cod_agencia": "0002", "tipo_lancamento": "CREDITO", "valor_lancamento": 200.0},
    ]
    result = reconciliacao_agencia(make_transactions(rows))

    assert result.count() == 2
