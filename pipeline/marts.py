"""Run the SQL in data/marts and write one CSV per mart.

Each .sql file in data/marts/sql is one select. The file name is the mart name. A mart may read
the dimension and fact CSVs, and any mart earlier in MART_ORDER. DuckDB runs
the SQL. The Python build only writes the result.
"""

import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
MARTS_DIR = ROOT / "data" / "marts"
MODEL_TABLES = (
    "dim_business",
    "dim_user",
    "dim_creator",
    "dim_content",
    "fct_subscription",
    "fct_engagement_event",
)
MART_ORDER = (
    "mart_subscription",
    "mart_plans",
    "mart_plan_starts",
    "mart_active_subscribers",
    "mart_business",
    "mart_content",
)


def build_marts(root=ROOT):
    root = Path(root)
    connection = duckdb.connect()
    try:
        for name in MODEL_TABLES:
            _view_from_csv(connection, name, root / "data" / "model" / f"{name}.csv")
        marts = {}
        for name in MART_ORDER:
            sql_path = root / "data" / "marts" / "sql" / f"{name}.sql"
            if not sql_path.exists():
                raise FileNotFoundError(f"Missing {sql_path.relative_to(root)}")
            cursor = connection.execute(sql_path.read_text())
            columns = [item[0] for item in cursor.description]
            rows = [
                {column: "" if value is None else str(value) for column, value in zip(columns, record)}
                for record in cursor.fetchall()
            ]
            csv_path = root / "data" / "marts" / f"{name}.csv"
            _write_csv(csv_path, columns, rows)
            _view_from_csv(connection, name, csv_path)
            marts[name] = rows
        return marts
    finally:
        connection.close()


def _view_from_csv(connection, name, path):
    escaped = str(path).replace("'", "''")
    connection.execute(
        f"create or replace view {name} as "
        f"select * from read_csv('{escaped}', header = true, all_varchar = true)"
    )


def _write_csv(path, columns, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
