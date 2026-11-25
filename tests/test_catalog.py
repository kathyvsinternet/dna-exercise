"""The catalog matches the published marts and the schema, and the validator catches drift.

Each drift test writes a small catalog to a temp file, so the real semantic/catalog.yml
is never changed.
"""

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "pipeline"))

from catalog import CatalogError, load_catalog, validate_catalog  # noqa: E402


class CatalogFileTests(unittest.TestCase):
    def _write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
        handle.write(textwrap.dedent(text))
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    def _validate(self, text):
        catalog = load_catalog(self._write(text))
        return validate_catalog(catalog)

    def test_published_catalog_is_valid(self):
        self.assertEqual(validate_catalog(load_catalog()), [])

    def test_published_catalog_covers_every_published_mart_it_claims(self):
        catalog = load_catalog()
        for name in ("mart_user_info_counts", "mart_user_qtr_counts", "mart_content_engagement"):
            self.assertIn(name, catalog["marts"])
        self.assertIn("mart_user_share_country", catalog["marts"])

    def test_share_tables_come_from_user_share_py(self):
        catalog = load_catalog()
        share = {name for name in catalog["marts"] if name.startswith("mart_user_share_")}
        self.assertEqual(
            share,
            {
                "mart_user_share_age",
                "mart_user_share_channel",
                "mart_user_share_country",
                "mart_user_share_device",
                "mart_user_share_subs_active",
                "mart_user_share_subs_paid",
            },
        )

    def test_restricted_column_in_catalog_is_flagged(self):
        problems = self._validate(
            """
            marts:
              mart_user_qtr_counts:
                columns:
                  quarter: {role: dimension, type: date}
                  email: {role: dimension, type: text}
            """
        )
        self.assertTrue(any("restricted" in p and "email" in p for p in problems), problems)

    def test_column_missing_from_published_mart_is_flagged(self):
        problems = self._validate(
            """
            marts:
              mart_user_qtr_counts:
                columns:
                  quarter: {role: dimension, type: date}
                  not_a_column: {role: measure, type: integer, aggregation: sum}
            """
        )
        self.assertTrue(any("not_a_column" in p and "not a column" in p for p in problems), problems)

    def test_catalog_type_must_match_published_type(self):
        problems = self._validate(
            """
            marts:
              mart_user_info_counts:
                columns:
                  n_users_active: {role: measure, type: text, aggregation: none}
            """
        )
        self.assertTrue(any("does not match" in p for p in problems), problems)

    def test_share_table_cannot_be_defined_in_the_yaml(self):
        with self.assertRaises(CatalogError) as raised:
            self._validate(
                """
                marts:
                  mart_user_share_country:
                    columns:
                      user_geo_country: {role: dimension, type: text}
                """
            )
        self.assertIn("pipeline/user_share.py", str(raised.exception))

    def test_mart_missing_from_site_is_flagged(self):
        problems = self._validate(
            """
            marts:
              mart_does_not_exist:
                columns:
                  n_users: {role: measure, type: integer, aggregation: sum}
            """
        )
        self.assertTrue(any("no published mart" in p for p in problems), problems)

    def test_small_cell_exception_must_point_at_a_people_measure(self):
        problems = self._validate(
            """
            small_cell_exceptions: [mart_user_qtr_counts]
            marts:
              mart_user_qtr_counts:
                columns:
                  quarter: {role: dimension, type: date}
                  user_subscriptions: {role: measure, type: integer, aggregation: sum}
            """
        )
        self.assertTrue(any("no people measure" in p for p in problems), problems)

    def test_measure_needs_an_aggregation(self):
        with self.assertRaises(CatalogError):
            self._validate(
                """
                marts:
                  mart_user_info_counts:
                    columns:
                      n_users_active: {role: measure, type: integer}
                """
            )

    def test_dimension_cannot_have_an_aggregation(self):
        with self.assertRaises(CatalogError):
            self._validate(
                """
                marts:
                  mart_user_share_country:
                    columns:
                      user_geo_country: {role: dimension, type: text, aggregation: sum}
                """
            )

    def test_unknown_role_or_type_is_refused(self):
        with self.assertRaises(CatalogError):
            self._validate(
                """
                marts:
                  mart_user_share_country:
                    columns:
                      user_geo_country: {role: attribute, type: text}
                """
            )
        with self.assertRaises(CatalogError):
            self._validate(
                """
                marts:
                  mart_user_share_country:
                    columns:
                      user_geo_country: {role: dimension, type: blob}
                """
            )


if __name__ == "__main__":
    unittest.main()
