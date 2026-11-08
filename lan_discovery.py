import socket
import threading


LAN_DISCOVERY_REFRESH_SECONDS = 15


class LanDiscoveryError(RuntimeError):
    pass


def get_advertised_ip():
    """Return the active LAN IPv4 address, or None when no address is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if not address.startswith("127."):
                return address
    except OSError:
        pass

    try:
        addresses = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return None
    for address in addresses:
        ipv4_address = address[4][0]
        if not ipv4_address.startswith("127."):
            return ipv4_address
    return None


class LanServiceDiscovery:
    def __init__(self, port, hostname, refresh_interval=LAN_DISCOVERY_REFRESH_SECONDS):
        from zeroconf import Error as ZeroconfError
        from zeroconf import ServiceInfo, Zeroconf

        self._zeroconf_error = ZeroconfError
        self._service_info_type = ServiceInfo
        self._zeroconf = Zeroconf()
        self._port = port
        advertised_hostname = hostname.rstrip(".")
        if not advertised_hostname.endswith(".local"):
            advertised_hostname = f"{advertised_hostname}.local"
        self._server = f"{advertised_hostname}."
        self._service_type = "_http._tcp.local."
        self._service_name = "School Assessment._http._tcp.local."
        self._stop_event = threading.Event()
        self._refresh_interval = refresh_interval
        self._service_info = None

        address = get_advertised_ip()
        if address is None:
            self._zeroconf.close()
            raise OSError("No active LAN IPv4 address is available.")
        self._service_info = self._make_service_info(address)
        try:
            self._zeroconf.register_service(self._service_info)
        except (OSError, ValueError, ZeroconfError) as error:
            self._zeroconf.close()
            raise LanDiscoveryError(f"Could not register the LAN service: {error}") from error

        self._thread = threading.Thread(
            target=self._refresh_address,
            name="lan-service-discovery",
            daemon=True,
        )
        self._thread.start()

    def _make_service_info(self, address):
        return self._service_info_type(
            self._service_type,
            self._service_name,
            addresses=[socket.inet_aton(address)],
            port=self._port,
            server=self._server,
            properties={"path": "/"},
        )

    def _refresh_address(self):
        last_error = None
        while not self._stop_event.wait(self._refresh_interval):
            try:
                address = get_advertised_ip()
                if address is None:
                    continue
                packed_address = socket.inet_aton(address)
                if packed_address not in self._service_info.addresses:
                    updated_info = self._make_service_info(address)
                    self._zeroconf.update_service(updated_info)
                    self._service_info = updated_info
                    print(f"LAN address updated: http://{address}:{self._port}")
                last_error = None
            except (OSError, ValueError, self._zeroconf_error) as error:
                if str(error) != last_error:
                    print(f"LAN name update failed; will retry: {error}")
                    last_error = str(error)

    def close(self):
        self._stop_event.set()
        self._thread.join()
        try:
            self._zeroconf.unregister_service(self._service_info)
        except (OSError, self._zeroconf_error) as error:
            print(f"Could not unregister the LAN service cleanly: {error}")
        finally:
            self._zeroconf.close()
