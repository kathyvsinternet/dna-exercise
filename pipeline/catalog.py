"""Load the governed catalog and check it against the published marts.

semantic/catalog.yml is the only list of what the chat interface may query.
load_catalog() reads it and adds one entry per mart_user_share_* table from
pipeline/user_share.py. validate_catalog() checks every entry against the
published JSON in site/data/marts/ and against data/model/schema.yml, and
returns a list of problems. pipeline/build.py fails if the list is not empty.
"""

import json
from pathlib import Path

import yaml

from user_share import user_share_manifest

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "semantic" / "catalog.yml"
SITE_MARTS = ROOT / "site" / "data" / "marts"
SCHEMA_PATH = ROOT / "data" / "model" / "schema.yml"

ROLES = {"dimension", "measure"}
AGGREGATIONS = {"sum", "none"}
TYPES = {"text", "integer", "number", "date"}

# Published JSON column types (DuckDB names) that each catalog type may use.
JSON_TYPES = {
    "text": {"VARCHAR"},
    "integer": {"BIGINT", "HUGEINT", "INTEGER"},
    "number": {"DOUBLE", "DECIMAL"},
    "date": {"DATE"},
}


class CatalogError(Exception):
    """semantic/catalog.yml cannot be read or has an entry the loader cannot use."""


def load_catalog(path=CATALOG_PATH):
    """Return {"marts": {...}, "small_cell_exceptions": set, "not_answerable": [...]}.

    Each mart entry has label, description, grain, notes, and columns. Each column
    has role, type, label, synonyms, caveat, and for measures aggregation and people.
    """
    try:
        data = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as error:
        raise CatalogError(f"Cannot read {path}: {error}") from error
    if not isinstance(data, dict) or "marts" not in data:
        raise CatalogError(f"{path} must have a top-level marts section.")

    generated = {item["mart"] for item in user_share_manifest()}
    marts = {}
    for name, spec in data["marts"].items():
        if name in generated:
            raise CatalogError(
                f"{name} is generated from pipeline/user_share.py. Remove it from {path}; "
                "change USER_SHARE_CUTS instead."
            )
        marts[name] = _mart_entry(name, spec)
    for item in user_share_manifest():
        marts[item["mart"]] = _share_entry(item)

    return {
        "marts": marts,
        "small_cell_exceptions": set(data.get("small_cell_exceptions") or []),
        "not_answerable": list(data.get("not_answerable") or []),
    }


def validate_catalog(catalog, site_marts=SITE_MARTS, schema_path=SCHEMA_PATH):
    """Return a list of problems. An empty list means the catalog matches the marts."""
    problems = []
    restricted = restricted_columns(schema_path)
    schema_columns = schema_marts(schema_path)

    for name in sorted(catalog["marts"]):
        entry = catalog["marts"][name]
        path = Path(site_marts) / f"{name}.json"
        if not path.exists():
            problems.append(f"{name}: no published mart at {path.relative_to(ROOT)}.")
            continue
        published = {c["name"]: c["type"] for c in json.loads(path.read_text())["columns"]}
        documented = schema_columns.get(name)
        if documented is None:
            problems.append(f"{name}: not documented in data/model/schema.yml.")
        for column, spec in entry["columns"].items():
            if column in restricted:
                problems.append(f"{name}.{column}: restricted in schema.yml. It must not be in the catalog.")
            if column not in published:
                problems.append(f"{name}.{column}: not a column of the published mart.")
                continue
            if published[column] not in JSON_TYPES[spec["type"]]:
                problems.append(
                    f"{name}.{column}: catalog type {spec['type']} does not match published {published[column]}."
                )
            if documented is not None and column not in documented:
                problems.append(f"{name}.{column}: not documented in schema.yml.")

    for name in sorted(catalog["small_cell_exceptions"]):
        entry = catalog["marts"].get(name)
        if entry is None:
            problems.append(f"small_cell_exceptions lists {name}, which is not in the catalog.")
        elif not any(spec.get("people") for spec in entry["columns"].values()):
            problems.append(f"small_cell_exceptions lists {name}, which has no people measure.")
    return problems


def restricted_columns(schema_path=SCHEMA_PATH):
    """Column names marked access: restricted in any table in schema.yml."""
    schema = _read_schema(schema_path)
    return {
        column["name"]
        for table in schema.get("tables", [])
        for column in table.get("columns", [])
        if column.get("access") == "restricted"
    }


def schema_marts(schema_path=SCHEMA_PATH):
    """{mart name: set of documented column names} from the marts section of schema.yml."""
    schema = _read_schema(schema_path)
    return {
        mart["name"]: {column["name"] for column in mart.get("columns", [])}
        for mart in schema.get("marts", [])
    }


def _read_schema(schema_path):
    try:
        return yaml.safe_load(Path(schema_path).read_text()) or {}
    except (OSError, yaml.YAMLError) as error:
        raise CatalogError(f"Cannot read {schema_path}: {error}") from error


def _mart_entry(name, spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("columns"), dict):
        raise CatalogError(f"{name} needs a columns section.")
    columns = {}
    for column, column_spec in spec["columns"].items():
        columns[column] = _column_entry(name, column, column_spec)
    return {
        "name": name,
        "label": spec.get("label", name),
        "description": spec.get("description", ""),
        "grain": spec.get("grain", ""),
        "notes": list(spec.get("notes") or []),
        "columns": columns,
    }


def _column_entry(mart, column, spec):
    where = f"{mart}.{column}"
    if not isinstance(spec, dict):
        raise CatalogError(f"{where} must be a mapping.")
    role = spec.get("role")
    kind = spec.get("type")
    if role not in ROLES:
        raise CatalogError(f"{where}: role must be one of {sorted(ROLES)}.")
    if kind not in TYPES:
        raise CatalogError(f"{where}: type must be one of {sorted(TYPES)}.")
    entry = {
        "role": role,
        "type": kind,
        "label": spec.get("label", column),
        "synonyms": list(spec.get("synonyms") or []),
        "caveat": spec.get("caveat", ""),
        "aggregation": None,
        "people": bool(spec.get("people", False)),
    }
    if role == "measure":
        aggregation = spec.get("aggregation")
        if aggregation not in AGGREGATIONS:
            raise CatalogError(f"{where}: a measure needs aggregation sum or none.")
        entry["aggregation"] = aggregation
    elif "aggregation" in spec:
        raise CatalogError(f"{where}: only measures have an aggregation.")
    elif entry["people"]:
        raise CatalogError(f"{where}: only measures can be people counts.")
    return entry


def _share_entry(item):
    column = item["column"]
    value_type = "integer" if column.startswith("n_subs_") else "text"
    return {
        "name": item["mart"],
        "label": item["title"],
        "description": item["title"],
        "grain": f"one row per {column}",
        "notes": ["Counts are distinct active non-test users. Rows partition the active users, so n_users adds up to the total within this table."],
        "columns": {
            column: {
                "role": "dimension",
                "type": value_type,
                "label": item["header"],
                "synonyms": [],
                "caveat": "",
                "aggregation": None,
                "people": False,
            },
            "n_users": {
                "role": "measure",
                "type": "integer",
                "label": "Active users",
                "synonyms": ["users", "people", "active users"],
                "caveat": "",
                "aggregation": "sum",
                "people": True,
            },
            "n_share": {
                "role": "measure",
                "type": "number",
                "label": "Share of active users",
                "synonyms": ["share", "percent", "percentage"],
                "caveat": "A share of the active users in this table. It cannot be added across rows.",
                "aggregation": "none",
                "people": False,
            },
        },
    }
