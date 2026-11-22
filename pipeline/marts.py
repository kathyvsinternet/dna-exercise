"""Run the SQL models in data/marts and publish each mart.

Layout:

    data/marts/sql/*.sql    intermediate models (int_*). Built as views, not published.
    data/marts/*.sql        marts (mart_*). Published as a CSV beside the SQL and as
                            JSON in site/data/marts/ for the dashboard.

A model is one select. The file name is the model name. A model may read the
dimension and fact CSVs in data/model and any other model. Order is worked out
from the names a model's SQL mentions, so a new file needs no registration.
DuckDB runs the SQL. Python only orders the models and writes the results.
"""

import csv
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
MODEL_TABLES = (
    "dim_business",
    "dim_user",
    "dim_creator",
    "dim_content",
    "fct_subscription",
    "fct_engagement_event",
)
SITE_MARTS = Path("site") / "data" / "marts"

# CSV cells carry no type. Every model column is read as text, except the numeric
# columns listed here. Empty cells load as NULL, so an invalid price is NULL.
MODEL_COLUMN_TYPES = {
    "fct_subscription": {"monthly_price_usd": "DOUBLE"},
}


class ModelError(Exception):
    """A SQL model could not be found, ordered, or run."""


def build_marts(root=ROOT):
    """Run every model. Returns {mart name: rows} for the published marts."""
    root = Path(root)
    models = discover_models(root)
    ordered = order_models(models)
    connection = duckdb.connect()
    try:
        for name in MODEL_TABLES:
            _view_from_csv(
                connection,
                name,
                root / "data" / "model" / f"{name}.csv",
                MODEL_COLUMN_TYPES.get(name),
            )
        marts = {}
        for name in ordered:
            model = models[name]
            try:
                connection.execute(f"create or replace view {name} as {model['sql']}")
                if model["published"]:
                    cursor = connection.execute(model["sql"])
                    columns = [(item[0], str(item[1])) for item in cursor.description]
                    rows = [dict(zip([c[0] for c in columns], record)) for record in cursor.fetchall()]
            except duckdb.Error as error:
                raise ModelError(f"{model['path']} failed: {error}") from error
            if model["published"]:
                _write_csv(root / "data" / "marts" / f"{name}.csv", columns, rows)
                _write_json(root / SITE_MARTS / f"{name}.json", model, columns, rows)
                marts[name] = rows
        return marts
    finally:
        connection.close()


def discover_models(root=ROOT):
    root = Path(root)
    marts_dir = root / "data" / "marts"
    found = {}
    for folder, published in ((marts_dir / "sql", False), (marts_dir, True)):
        for path in sorted(folder.glob("*.sql")):
            name = path.stem
            if name in found:
                raise ModelError(f"{name} is defined twice: {found[name]['path']} and {path.relative_to(root)}.")
            if name in MODEL_TABLES:
                raise ModelError(f"{path.relative_to(root)} is named like the model table {name}.")
            found[name] = {
                "name": name,
                "path": str(path.relative_to(root)),
                "sql": path.read_text().strip().rstrip(";").strip(),
                "published": published,
            }
    if not any(model["published"] for model in found.values()):
        raise ModelError("data/marts has no mart .sql file to publish.")
    for model in found.values():
        model["depends_on"] = _references(model, found)
    return found


def order_models(models):
    """Dependencies first. Raises on a cycle."""
    ordered, state = [], {}

    def visit(name, trail):
        if state.get(name) == "done":
            return
        if state.get(name) == "visiting":
            raise ModelError("Circular reference: " + " -> ".join([*trail, name]))
        state[name] = "visiting"
        for parent in models[name]["depends_on"]:
            if parent in models:
                visit(parent, [*trail, name])
        state[name] = "done"
        ordered.append(name)

    for name in sorted(models):
        visit(name, [])
    return ordered


def _references(model, models):
    """Names of other models and model tables that this model's SQL mentions."""
    text = re.sub(r"--[^\n]*|/\*.*?\*/", " ", model["sql"], flags=re.S)
    words = set(re.findall(r"[a-z_][a-z0-9_]*", text.lower()))
    known = (set(models) | set(MODEL_TABLES)) - {model["name"]}
    return sorted(words & known)


def _view_from_csv(connection, name, path, types=None):
    escaped = str(path).replace("'", "''")
    type_clause = ""
    if types:
        pairs = ", ".join(f"'{column}': '{kind}'" for column, kind in types.items())
        type_clause = f", types = {{{pairs}}}"
    connection.execute(
        f"create or replace view {name} as "
        f"select * from read_csv('{escaped}', header = true, all_varchar = true{type_clause})"
    )


def _write_csv(path, columns, rows):
    names = [name for name, _ in columns]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(names)
        for row in rows:
            writer.writerow(["" if row[name] is None else _plain(row[name]) for name in names])


def _write_json(path, model, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": model["name"],
        "sql": model["sql"],
        "depends_on": model["depends_on"],
        "columns": [{"name": name, "type": kind} for name, kind in columns],
        "rows": [{name: _json_value(row[name]) for name, _ in columns} for row in rows],
    }
    path.write_text(json.dumps(payload, indent=1) + "\n")


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10] if type(value) is date else value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _plain(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)
