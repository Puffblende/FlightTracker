import unittest

from src.ui.external_tab import _parse_host_port


class ExternalTabParsingTests(unittest.TestCase):
    def test_parses_host_port_from_manual_input(self):
        host, port = _parse_host_port("192.168.1.50:80", 4211)
        self.assertEqual(host, "192.168.1.50")
        self.assertEqual(port, 80)

    def test_uses_default_port_when_none_is_supplied(self):
        host, port = _parse_host_port("192.168.1.50", 4211)
        self.assertEqual(host, "192.168.1.50")
        self.assertEqual(port, 4211)

    def test_ignores_http_prefix(self):
        host, port = _parse_host_port("http://192.168.1.50:8080", 80)
        self.assertEqual(host, "192.168.1.50")
        self.assertEqual(port, 8080)


if __name__ == "__main__":
    unittest.main()
