"""Shared pytest fixtures for the PySpark unit tests."""
from datetime import date, datetime

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import types as T

TRANSACTION_SCHEMA = T.StructType(
    [
        T.StructField("id_transacao", T.StringType(), True),
        T.StructField("id_contrato", T.StringType(), True),
        T.StructField("id_conta", T.StringType(), True),
        T.StructField("cod_agencia", T.StringType(), True),
        T.StructField("tipo_contrato", T.StringType(), True),
        T.StructField("tipo_lancamento", T.StringType(), True),
        T.StructField("valor_lancamento", T.DoubleType(), True),
        T.StructField("dt_lancamento", T.TimestampType(), True),
        T.StructField("dt_processamento", T.DateType(), True),
        T.StructField("cod_cosif", T.StringType(), True),
        T.StructField("flag_estorno", T.BooleanType(), True),
    ]
)

DEFAULT_ROW = {
    "id_transacao": "t1",
    "id_contrato": "c1",
    "id_conta": "conta1",
    "cod_agencia": "0001",
    "tipo_contrato": "CC",
    "tipo_lancamento": "CREDITO",
    "valor_lancamento": 100.0,
    "dt_lancamento": datetime(2026, 1, 1),
    "dt_processamento": date(2026, 1, 1),
    "cod_cosif": "1.1.1.10.00",
    "flag_estorno": False,
}


@pytest.fixture(scope="session")
def spark():
    session = SparkSession.builder.master("local[2]").appName("pytest").getOrCreate()
    yield session
    session.stop()


@pytest.fixture
def make_transactions(spark):
    def _make(rows: list[dict]):
        full_rows = []
        for i, overrides in enumerate(rows):
            row = {**DEFAULT_ROW, "id_transacao": f"t{i}", **overrides}
            full_rows.append(tuple(row[f.name] for f in TRANSACTION_SCHEMA.fields))
        return spark.createDataFrame(full_rows, schema=TRANSACTION_SCHEMA)

    return _make


@pytest.fixture
def cosif_domain(spark):
    return spark.createDataFrame(
        [("1.1.1.10.00", "Disponibilidades - Caixa", "CC")],
        ["cod_cosif", "descricao", "tipo_contrato_esperado"],
    )
