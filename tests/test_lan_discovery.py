import socket
import time
import unittest
from unittest.mock import patch

from lan_discovery import LanServiceDiscovery


class FakeServiceInfo:
    def __init__(self, service_type, name, addresses, port, server, properties):
        self.service_type = service_type
        self.name = name
        self.addresses = addresses
        self.port = port
        self.server = server
        self.properties = properties


class FakeZeroconf:
    instances = []

    def __init__(self):
        self.registered = []
        self.updated = []
        self.unregistered = []
        self.closed = False
        self.instances.append(self)

    def register_service(self, service_info):
        self.registered.append(service_info)

    def update_service(self, service_info):
        self.updated.append(service_info)

    def unregister_service(self, service_info):
        self.unregistered.append(service_info)

    def close(self):
        self.closed = True


class LanDiscoveryTests(unittest.TestCase):
    def setUp(self):
        FakeZeroconf.instances.clear()

    def test_service_advertisement_tracks_lan_ip_changes(self):
        addresses = iter(("192.168.1.20", "10.0.0.20"))
        with (
            patch("zeroconf.Zeroconf", FakeZeroconf),
            patch("zeroconf.ServiceInfo", FakeServiceInfo),
            patch("lan_discovery.get_advertised_ip", side_effect=lambda: next(addresses, "10.0.0.20")),
        ):
            discovery = LanServiceDiscovery(5000, "school-assessment.local", refresh_interval=0.01)
            deadline = time.monotonic() + 1
            while not FakeZeroconf.instances[0].updated and time.monotonic() < deadline:
                time.sleep(0.01)
            discovery.close()

        service = FakeZeroconf.instances[0]
        self.assertEqual(socket.inet_ntoa(service.registered[0].addresses[0]), "192.168.1.20")
        self.assertEqual(socket.inet_ntoa(service.updated[0].addresses[0]), "10.0.0.20")
        self.assertEqual(service.unregistered, [service.updated[0]])
        self.assertTrue(service.closed)


if __name__ == "__main__":
    unittest.main()
