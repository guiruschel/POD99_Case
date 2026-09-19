"""Generates a synthetic dataset matching the fin_contabilidade_saldo_contrato contract."""
import argparse
import uuid
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

TIPO_CONTRATO = ["CC", "POUP", "CDB", "LCI", "CONSORCIO", "SEGURO"]
TIPO_LANCAMENTO = ["DEBITO", "CREDITO", "TARIFA", "JUROS", "IOF"]
TIPO_LANCAMENTO_WEIGHTS = [0.45, 0.45, 0.06, 0.03, 0.01]

# Small COSIF domain table: code -> (description, expected tipo_contrato)
COSIF_DOMAIN = [
    ("1.1.1.10.00", "Disponibilidades - Caixa", "CC"),
    ("1.1.3.10.00", "Depositos a Vista", "CC"),
    ("1.1.3.20.00", "Depositos de Poupanca", "POUP"),
    ("1.4.1.10.00", "Aplicacoes em CDB", "CDB"),
    ("1.4.1.20.00", "Aplicacoes em LCI", "LCI"),
    ("2.1.5.10.00", "Consorcios a Pagar", "CONSORCIO"),
    ("2.1.6.10.00", "Provisao Tecnica de Seguros", "SEGURO"),
    ("7.1.1.10.00", "Rendas de Tarifas", "CC"),
    ("7.1.2.10.00", "Rendas de Juros", "CDB"),
    ("8.1.1.10.00", "Despesas de IOF", "CC"),
]


def generate_accounts_and_contracts(num_accounts: int, min_contracts: int, max_contracts: int, num_agencias: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    account_ids = [f"CONTA-{i:09d}" for i in range(num_accounts)]
    agencias = [f"AG-{i:04d}" for i in range(num_agencias)]
    account_agencia = rng.choice(agencias, size=num_accounts)

    rows = []
    for account_id, agencia in zip(account_ids, account_agencia):
        n_contracts = rng.integers(min_contracts, max_contracts + 1)
        contract_types = rng.choice(TIPO_CONTRATO, size=n_contracts, replace=True)
        for tipo_contrato in contract_types:
            rows.append(
                {
                    "id_conta": account_id,
                    "cod_agencia": agencia,
                    "id_contrato": f"CTR-{uuid.uuid4().hex[:16]}",
                    "tipo_contrato": tipo_contrato,
                }
            )
    return pd.DataFrame(rows)


def generate_cosif_domain() -> pd.DataFrame:
    return pd.DataFrame(COSIF_DOMAIN, columns=["cod_cosif", "descricao", "tipo_contrato_esperado"])


def generate_transactions(
    contracts: pd.DataFrame,
    cosif_domain: pd.DataFrame,
    total_transactions: int,
    start_date: date,
    num_days: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = total_transactions

    contract_idx = rng.integers(0, len(contracts), size=n)
    sampled_contracts = contracts.iloc[contract_idx].reset_index(drop=True)

    day_offsets = rng.integers(0, num_days, size=n)
    dt_processamento = pd.to_datetime(start_date) + pd.to_timedelta(day_offsets, unit="D")
    seconds_in_day = rng.integers(0, 24 * 3600, size=n)
    dt_lancamento = dt_processamento + pd.to_timedelta(seconds_in_day, unit="s")

    tipo_lancamento = rng.choice(TIPO_LANCAMENTO, size=n, p=TIPO_LANCAMENTO_WEIGHTS)
    valor_lancamento = np.round(rng.lognormal(mean=6.5, sigma=1.2, size=n), 2)
    valor_lancamento = np.clip(valor_lancamento, 0.01, 250_000.00)

    flag_estorno = rng.random(n) < 0.02

    # COSIF codes matching each contract's tipo_contrato, with a small share left null.
    cosif_by_tipo = cosif_domain.groupby("tipo_contrato_esperado")["cod_cosif"].apply(list).to_dict()
    cod_cosif = []
    null_cosif_mask = rng.random(n) < 0.05
    for tipo_contrato, is_null in zip(sampled_contracts["tipo_contrato"], null_cosif_mask):
        if is_null:
            cod_cosif.append(None)
            continue
        candidates = cosif_by_tipo.get(tipo_contrato, cosif_domain["cod_cosif"].tolist())
        cod_cosif.append(candidates[rng.integers(0, len(candidates))])

    lote_dates = dt_processamento.strftime("%Y%m%d")

    return pd.DataFrame(
        {
            "id_transacao": [str(uuid.uuid4()) for _ in range(n)],
            "id_contrato": sampled_contracts["id_contrato"].values,
            "id_conta": sampled_contracts["id_conta"].values,
            "cod_agencia": sampled_contracts["cod_agencia"].values,
            "tipo_contrato": sampled_contracts["tipo_contrato"].values,
            "tipo_lancamento": tipo_lancamento,
            "valor_lancamento": valor_lancamento,
            "dt_lancamento": dt_lancamento,
            "dt_processamento": dt_processamento.date,
            "cod_cosif": cod_cosif,
            "flag_estorno": flag_estorno,
            "id_lote": "LOTE-" + lote_dates,
        }
    )


def inject_dq_violations(df: pd.DataFrame, error_rate: float, seed: int) -> pd.DataFrame:
    """Flips a share of rows into contract-violating records, to exercise Bronze DQ checks."""
    if error_rate <= 0:
        return df
    rng = np.random.default_rng(seed)
    n_errors = int(len(df) * error_rate)
    error_idx = rng.choice(df.index, size=n_errors, replace=False)
    kinds = rng.integers(0, 4, size=n_errors)

    for idx, kind in zip(error_idx, kinds):
        if kind == 0:
            # Negative value without the reversal flag.
            df.loc[idx, "valor_lancamento"] = -abs(df.loc[idx, "valor_lancamento"])
            df.loc[idx, "flag_estorno"] = False
        elif kind == 1:
            # Entry dated after the processing date.
            df.loc[idx, "dt_lancamento"] = pd.Timestamp(df.loc[idx, "dt_processamento"]) + pd.Timedelta(days=1)
        elif kind == 2:
            # Unknown COSIF code.
            df.loc[idx, "cod_cosif"] = "9.9.9.99.99"
        else:
            # Duplicate transaction id (copies the id of a random other row).
            other_idx = rng.choice(df.index)
            df.loc[idx, "id_transacao"] = df.loc[other_idx, "id_transacao"]
    return df


def write_partitioned_parquet(df: pd.DataFrame, output_dir: Path) -> None:
    raw_dir = output_dir / "raw"
    for dt_processamento, partition_df in df.groupby("dt_processamento"):
        partition_dir = raw_dir / f"dt_processamento={dt_processamento}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        partition_df.drop(columns=["dt_processamento"]).to_parquet(
            partition_dir / "part-0.parquet", index=False
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data_generator/output"))
    parser.add_argument("--num-accounts", type=int, default=20_000)
    parser.add_argument("--min-contracts-per-account", type=int, default=3)
    parser.add_argument("--max-contracts-per-account", type=int, default=5)
    parser.add_argument("--num-agencias", type=int, default=50)
    parser.add_argument("--total-transactions", type=int, default=1_000_000)
    parser.add_argument("--num-days", type=int, default=30)
    parser.add_argument("--start-date", type=str, default="2026-08-01")
    parser.add_argument("--dq-error-rate", type=float, default=0.0, help="Fraction of rows to corrupt for testing DQ rejection")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date)

    contracts = generate_accounts_and_contracts(
        args.num_accounts, args.min_contracts_per_account, args.max_contracts_per_account, args.num_agencias, args.seed
    )
    cosif_domain = generate_cosif_domain()
    transactions = generate_transactions(
        contracts, cosif_domain, args.total_transactions, start_date, args.num_days, args.seed
    )
    transactions = inject_dq_violations(transactions, args.dq_error_rate, args.seed)

    write_partitioned_parquet(transactions, args.output_dir)
    ref_dir = args.output_dir / "ref"
    ref_dir.mkdir(parents=True, exist_ok=True)
    cosif_domain.to_parquet(ref_dir / "cosif_domain.parquet", index=False)

    print(f"Generated {len(transactions):,} transactions across {contracts['id_contrato'].nunique():,} contracts")
    print(f"Written to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
