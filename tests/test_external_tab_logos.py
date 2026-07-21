import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication

from src.ui.external_tab import ExternalDisplayTab


class ExternalTabLogoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_encode_logos_scopes_to_current_flights_not_full_catalog(self) -> None:
        # The device parses POST /config into a fixed 64 KB buffer; the full
        # airline catalog's logos alone hex-encode to far more than that, so
        # _encode_logos() must only cover airlines from currently displayed
        # flights. The full catalog still reaches the device separately via
        # _push_all_logos()'s small batched POST /logos calls.
        tab = ExternalDisplayTab(main_window=SimpleNamespace(_flights=[]))

        with patch.object(
            tab,
            '_collect_flight_airlines',
            return_value=[('BAW', 'BA', 'British Airways'), ('EZY', 'U2', 'easyJet')],
        ), patch.object(
            tab,
            '_collect_airline_catalog',
            return_value=[
                ('BAW', 'BA', 'British Airways'), ('EZY', 'U2', 'easyJet'),
                ('DLH', 'LH', 'Lufthansa'),
            ],
        ), patch('src.api.logos.get_logo', return_value=Image.new('RGB', (24, 24))):
            logos = tab._encode_logos()

        self.assertEqual(set(logos.keys()), {'BAW', 'EZY'})

    def test_connection_fields_restore_last_values_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'device_ip.json'
            path.write_text(json.dumps({'ip': '192.168.1.55', 'port': 4211}))

            with patch('src.ui.external_tab._DEVICE_IP_FILE', path):
                tab = ExternalDisplayTab(main_window=SimpleNamespace(_flights=[]))

            self.assertEqual(tab._txt_ip.text(), '192.168.1.55')
            self.assertEqual(tab._spin_port.value(), 4211)
            self.assertEqual(tab._txt_push_ip.text(), '192.168.1.55')


if __name__ == '__main__':
    unittest.main()
