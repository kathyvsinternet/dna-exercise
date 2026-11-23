"""Share-of-users tables, one per cut of eph_user_info.

To add a table, add a line to USER_SHARE_CUTS and run python pipeline/build.py.
No SQL file is needed. Each cut becomes the mart mart_user_share_<name>, written
to data/marts/ as a CSV and to site/data/marts/ as JSON. The dashboard reads
site/data/user_share.json, so the new table appears there too.

This build does not suppress small cells. The under-5 rule on site/access.html applies
to published people counts, and the subs_active and subs_paid tables are an approved
exception to it: they show groups of fewer than 5 people as they are.

Each line is (name, column on eph_user_info, column header, table title). The header
and title are what the dashboard shows.
"""

import re

SOURCE = "eph_user_info"
PREFIX = "mart_user_share_"

USER_SHARE_CUTS = [
    ("country", "user_geo_country", "Country", "Active Users by Country"),
    ("age", "user_age_band", "Age Band", "Active Users by Age Band"),
    ("channel", "user_acq_channel", "Acquisition Channel", "Active Users by Acquisition Channel"),
    ("device", "user_prim_device", "Primary Device", "Active Users by Primary Device"),
    ("subs_active", "n_subs_active", "Active Subscriptions", "Users by Active Subscriptions"),
    ("subs_paid", "n_subs_paid", "Paid Subscriptions", "Users by Paid Subscriptions"),
]

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class UserShareError(Exception):
    """USER_SHARE_CUTS has a line that cannot be built."""


def user_share_models():
    """One generated model per cut, in the same shape as a model read from a .sql file."""
    models = {}
    for name, column, _header, _title in _cuts():
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
    """What the dashboard needs to draw each table: the mart, the value column, and its text."""
    return [
        {"mart": PREFIX + name, "column": column, "header": header, "title": title}
        for name, column, header, title in _cuts()
    ]


def user_share_columns():
    """{mart name: value column}, used by the build checks."""
    return {PREFIX + name: column for name, column, _header, _title in _cuts()}


def _cuts():
    seen = set()
    for cut in USER_SHARE_CUTS:
        if len(cut) != 4:
            raise UserShareError(f"{cut!r} must be (name, column, header, title).")
        name, column, header, title = cut
        for part in (name, column):
            if not _IDENTIFIER.match(part):
                raise UserShareError(f"{part!r} must be lowercase letters, digits, and underscores.")
        if name in seen:
            raise UserShareError(f"USER_SHARE_CUTS repeats the name {name}.")
        seen.add(name)
        yield name, column, header, title
