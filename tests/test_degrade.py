import time
import unittest

from router_brain.degrade import CircuitBreaker
from router_brain.models import RunResult


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.breaker = CircuitBreaker(failures=2, cooldown=60)

    def test_opens_after_threshold(self):
        self.assertFalse(self.breaker.is_open("m", "c"))
        self.breaker.record_failure("m", "c", "direct")
        self.assertFalse(self.breaker.is_open("m", "c"))
        self.breaker.record_failure("m", "c", "direct")
        self.assertTrue(self.breaker.is_open("m", "c"))

    def test_channel_isolated(self):
        # 熔断按 (模型,通道) 隔离：m@c1 熔断不影响 m@c2
        self.breaker.record_failure("m", "c1", "direct")
        self.breaker.record_failure("m", "c1", "direct")
        self.assertTrue(self.breaker.is_open("m", "c1"))
        self.assertFalse(self.breaker.is_open("m", "c2"))

    def test_success_resets(self):
        self.breaker.record_failure("m", "c", "direct")
        self.breaker.record_success("m", "c")
        self.assertFalse(self.breaker.is_open("m", "c"))
        self.breaker.record_failure("m", "c", "direct")
        self.assertFalse(self.breaker.is_open("m", "c"))

    def test_auth_opens_immediately(self):
        self.breaker.record_failure("m", "c", "auth")
        self.assertTrue(self.breaker.is_open("m", "c"))

    def test_permanent_opens_immediately(self):
        self.breaker.record_failure("m", "c", "permanent")
        self.assertTrue(self.breaker.is_open("m", "c"))

    def test_cooldown_expiry(self):
        b = CircuitBreaker(failures=1, cooldown=0.05)
        b.record_failure("m", "c", "direct")
        self.assertTrue(b.is_open("m", "c"))
        time.sleep(0.08)
        self.assertFalse(b.is_open("m", "c"))

    def test_runresult_json(self):
        r = RunResult(task_id="t1", ok=True, model="x", task_type="code", execution="agent", output="hi")
        j = r.to_json()
        self.assertEqual(j["ok"], True)
        self.assertEqual(j["task_id"], "t1")


if __name__ == "__main__":
    unittest.main()
