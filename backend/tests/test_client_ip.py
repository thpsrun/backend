from api.client_ip import _get_trusted_proxies, client_ip
from django.test import RequestFactory, TestCase, override_settings


@override_settings(DEBUG=False, TRUSTED_PROXIES="172.18.0.0/16")
class ClientIpTests(TestCase):
    """Resolution of the real client IP from REMOTE_ADDR and X-Forwarded-For."""

    def setUp(
        self,
    ) -> None:
        """Reset the cached trusted-proxy parse and build a request factory."""
        _get_trusted_proxies.cache_clear()
        self.factory = RequestFactory()

    def tearDown(
        self,
    ) -> None:
        """Clear the cache so an overridden TRUSTED_PROXIES never leaks to other tests."""
        _get_trusted_proxies.cache_clear()

    def test_ignores_client_forged_left_most_forwarded_for_entry(
        self,
    ) -> None:
        """A forged left-most XFF entry must lose to the proxy-appended real client IP."""
        request = self.factory.get(
            "/api/v1/runs",
            REMOTE_ADDR="172.18.0.5",
            HTTP_X_FORWARDED_FOR="9.9.9.9, 203.0.113.7",
        )

        self.assertEqual(client_ip(request), "203.0.113.7")

    def test_returns_single_forwarded_for_entry_from_trusted_proxy(
        self,
    ) -> None:
        """With one proxy hop the lone XFF entry is the client and is returned as-is."""
        request = self.factory.get(
            "/api/v1/runs",
            REMOTE_ADDR="172.18.0.5",
            HTTP_X_FORWARDED_FOR="203.0.113.7",
        )

        self.assertEqual(client_ip(request), "203.0.113.7")

    def test_skips_unparseable_forged_forwarded_for_entries(
        self,
    ) -> None:
        """Junk forged entries fail to parse and are skipped, not returned."""
        request = self.factory.get(
            "/api/v1/runs",
            REMOTE_ADDR="172.18.0.5",
            HTTP_X_FORWARDED_FOR="not-an-ip, 203.0.113.7",
        )

        self.assertEqual(client_ip(request), "203.0.113.7")

    def test_peels_off_a_second_trusted_proxy_hop(
        self,
    ) -> None:
        """Chained trusted proxies are skipped to reach the real downstream client."""
        with override_settings(TRUSTED_PROXIES="172.18.0.0/16,10.0.0.0/8"):
            _get_trusted_proxies.cache_clear()
            request = self.factory.get(
                "/api/v1/runs",
                REMOTE_ADDR="172.18.0.5",
                HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.2",
            )

            self.assertEqual(client_ip(request), "203.0.113.7")

    def test_untrusted_remote_addr_ignores_forwarded_for(
        self,
    ) -> None:
        """A direct (untrusted) peer is returned verbatim; its XFF is not believed."""
        request = self.factory.get(
            "/api/v1/runs",
            REMOTE_ADDR="203.0.113.9",
            HTTP_X_FORWARDED_FOR="9.9.9.9",
        )

        self.assertEqual(client_ip(request), "203.0.113.9")

    def test_falls_back_to_remote_addr_when_chain_is_all_trusted(
        self,
    ) -> None:
        """If every XFF entry is a trusted proxy, fall back to REMOTE_ADDR."""
        request = self.factory.get(
            "/api/v1/runs",
            REMOTE_ADDR="172.18.0.5",
            HTTP_X_FORWARDED_FOR="172.18.0.9",
        )

        self.assertEqual(client_ip(request), "172.18.0.5")

    def test_no_trusted_proxies_configured_returns_remote_addr(
        self,
    ) -> None:
        """With no proxies configured, X-Forwarded-For is ignored entirely."""
        with override_settings(TRUSTED_PROXIES=""):
            _get_trusted_proxies.cache_clear()
            request = self.factory.get(
                "/api/v1/runs",
                REMOTE_ADDR="172.18.0.5",
                HTTP_X_FORWARDED_FOR="203.0.113.7",
            )

            self.assertEqual(client_ip(request), "172.18.0.5")
