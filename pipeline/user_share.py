"""Share-of-users tables, one per cut of mart_user_info.

To add a table, add a line to USER_SHARE_CUTS and run python pipeline/build.py.
No SQL file is needed. Each cut becomes the mart mart_user_share_<name>, written
to data/marts/ as a CSV and to site/data/marts/ as JSON. The dashboard reads
site/data/user_share.json, so the new table appears there too.

Each line is (name, column on mart_user_info, label shown on the dashboard).
"""

import re

SOURCE = "mart_user_info"
PREFIX = "mart_user_share_"

USER_SHARE_CUTS = [
    ("country", "user_geo_country", "Country"),
    ("age", "user_age_band", "Age Band"),
    ("channel", "user_acq_channel", "Acquisition Channel"),
    ("device", "user_prim_device", "Primary Device"),
]

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class UserShareError(Exception):
    """USER_SHARE_CUTS has a line that cannot be built."""


def user_share_models():
    """One generated model per cut, in the same shape as a model read from a .sql file."""
    models = {}
    for name, column, _label in _cuts():
        mart = PREFIX + name
        models[mart] = {
            "name": mart,
            "path": "pipeline/user_share.py",
            "sql": user_share_sql(column),
            "published": True,
        }
    return models


def user_share_sql(column):
    return (
        f"SELECT\n"
        f"  {column},\n"
        f"  COUNT(DISTINCT user_id) AS n_users,\n"
        f"  ROUND(COUNT(DISTINCT user_id) / SUM(COUNT(DISTINCT user_id)) OVER (), 4) AS n_share\n"
        f"FROM {SOURCE}\n"
        f"GROUP BY {column}\n"
        f"ORDER BY n_users DESC, {column}"
    )


def user_share_manifest():
    """What the dashboard needs to draw each table: the mart, the value column, and a label."""
    return [
        {"mart": PREFIX + name, "column": column, "label": label}
        for name, column, label in _cuts()
    ]


def user_share_columns():
    """{mart name: value column}, used by the build checks."""
    return {PREFIX + name: column for name, column, _label in _cuts()}


def _cuts():
    seen = set()
    for cut in USER_SHARE_CUTS:
        if len(cut) != 3:
            raise UserShareError(f"{cut!r} must be (name, column, label).")
        name, column, label = cut
        for part in (name, column):
            if not _IDENTIFIER.match(part):
                raise UserShareError(f"{part!r} must be lowercase letters, digits, and underscores.")
        if name in seen:
            raise UserShareError(f"USER_SHARE_CUTS repeats the name {name}.")
        seen.add(name)
        yield name, column, label
