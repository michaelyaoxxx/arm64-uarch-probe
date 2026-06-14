import unittest

from arm64_probe.cli.render import render_list
from arm64_probe.registry.catalog import Catalog


class CliRenderTests(unittest.TestCase):
    def test_empty_registered_category_renders_a_header_only_table(self):
        catalog = Catalog((), (), (), ())

        rendered = render_list(catalog, "capabilities", "table")

        self.assertIn("KIND", rendered)
        self.assertIn("ID", rendered)
        self.assertNotIn("Traceback", rendered)


if __name__ == "__main__":
    unittest.main()
