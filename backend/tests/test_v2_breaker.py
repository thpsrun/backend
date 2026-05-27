from django.core.cache import cache
from django.test import TestCase
from srl.models import BotSession
from srl.srcom.v2 import _V2_ENABLED_CACHE_KEY, is_v2_enabled
from srl.srcom.v2.session import trip_circuit_breaker


class TripCircuitBreakerTest(TestCase):
    def setUp(
        self,
    ) -> None:
        cache.delete(_V2_ENABLED_CACHE_KEY)
        bs = BotSession.load()
        bs.disabled_by_circuit_breaker = False
        bs.v2_enabled_override = True
        bs.save(
            update_fields=["disabled_by_circuit_breaker", "v2_enabled_override"],
        )

    def test_trip_sets_breaker_and_invalidates_cache(
        self,
    ) -> None:
        cache.set(_V2_ENABLED_CACHE_KEY, True, 30)
        self.assertTrue(is_v2_enabled())
        trip_circuit_breaker("test trip", category="v2_auth")
        bs = BotSession.load()
        self.assertTrue(bs.disabled_by_circuit_breaker)
        self.assertFalse(bs.v2_enabled_override)
        self.assertFalse(is_v2_enabled())

    def test_trip_is_idempotent(
        self,
    ) -> None:
        trip_circuit_breaker("first trip", category="v2_auth")
        bs_before = BotSession.load()
        first_ts = bs_before.last_severe_error_at
        trip_circuit_breaker("second trip", category="v2_4xx")
        bs_after = BotSession.load()
        self.assertEqual(bs_after.last_severe_error_at, first_ts)
        self.assertEqual(bs_after.last_severe_error_category, "v2_auth")
