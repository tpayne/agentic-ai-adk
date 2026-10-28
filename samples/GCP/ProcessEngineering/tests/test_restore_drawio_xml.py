import os
import tempfile
import unittest
from unittest.mock import patch

from process_toolkit import paths as toolkit_paths
from process_toolkit.cloudarch.layout import build_structured_drawio_xml
from process_agents.common.utils import restore_drawio_xml


class RestoreDrawioXmlTest(unittest.TestCase):
    """restore_drawio_xml -- CloudArch_Import_Agent's own literal-restore
    persistence function. Developed in tandem with the neuro-san port's
    own coded_tools.cloudarch.restore_drawio_xml_tool.RestoreDrawioXmlCodedTool,
    which delegates to the same-shaped canonical save function on that
    side."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.output_dir = os.path.join(self.tmp_dir.name, "output")
        os.makedirs(self.output_dir)
        self.output_dir_patch = patch.object(toolkit_paths, "OUTPUT_DIR", self.output_dir)
        self.output_dir_patch.start()
        self.addCleanup(self.output_dir_patch.stop)

    def test_well_formed_structured_engine_xml_round_trips_byte_for_byte(self):
        # The realistic case: a cloudarch_drawio.xml downloaded earlier
        # THIS session (always produced by the structured layout engine,
        # already correctly styled) is re-attached -- restoring it must
        # not alter a single byte, the same "verbatim" guarantee the
        # process/design JSON restore path gives.
        xml = build_structured_drawio_xml(
            title="Test Architecture", subtitle=None,
            zones=[{"id": "edge", "label": "Edge"}],
            components=[{"id": "waf", "zone_id": "edge", "label": "WAF", "color": "#DD344C"}],
            edges=[],
            provider="aws",
        )

        result = restore_drawio_xml(xml)

        self.assertIn("SUCCESS", result)
        with open(os.path.join(self.output_dir, "cloudarch_drawio.xml"), encoding="utf-8") as f:
            on_disk = f.read()
        self.assertEqual(on_disk.strip(), xml.strip())

    def test_rejects_malformed_xml(self):
        result = restore_drawio_xml("<not valid xml")
        self.assertIn("ERROR", result)

    def test_rejects_empty_content(self):
        self.assertIn("ERROR", restore_drawio_xml(""))
        self.assertIn("ERROR", restore_drawio_xml("   "))

    def test_unchanged_restore_is_a_no_op(self):
        xml = build_structured_drawio_xml(
            title="T", subtitle=None, zones=[{"id": "z", "label": "Z"}],
            components=[{"id": "c", "zone_id": "z", "label": "C"}], edges=[],
        )
        restore_drawio_xml(xml)
        second = restore_drawio_xml(xml)
        self.assertIn("unchanged", str(second))


if __name__ == "__main__":
    unittest.main()
