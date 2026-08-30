import unittest
from pathlib import Path

from router_brain.config import Config
from router_brain.router import Router

FIXTURES = Path(__file__).parent / "fixtures"


class TestRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = Config(
            pool_path=FIXTURES / "test_pool.yaml",
            routing_path=FIXTURES / "test_routing.yaml",
        )
        cls.router = Router(cls.cfg)
        # 通用逻辑测试不受全局 force_channel 影响：临时清空
        cls.cfg.routing_doc.setdefault("execution", {})["force_channel"] = ""

    def test_force_channel_restricts_pool(self):
        # force_channel=test-channel-a 时，可用模型只含该通道
        cfg2 = Config(
            pool_path=FIXTURES / "test_pool.yaml",
            routing_path=FIXTURES / "test_routing.yaml",
        )
        cfg2.routing_doc["execution"]["force_channel"] = "test-channel-a"
        avail = {m.id for m in cfg2.available_models()}
        self.assertTrue(all("test-channel-a" in cfg2.model(mid).channels for mid in avail))
        self.assertGreaterEqual(len(avail), 1)
        cfg2.routing_doc["execution"]["force_channel"] = ""

    def test_direct_execution_for_qa(self):
        # 快问快答走 direct（不派活）
        d = self.router.route("qa")
        self.assertEqual(d.execution, "direct")

    def test_agent_execution_for_code(self):
        # 编码任务走 agent
        d = self.router.route("code")
        self.assertEqual(d.execution, "agent")

    def test_default_never_banned_or_unreliable(self):
        # 默认建议模型不是禁用、不是易限流（有其它可用时）
        d = self.router.route("code")
        spec = self.cfg.model(d.selected_model)
        self.assertFalse(spec.banned)
        self.assertFalse(spec.unreliable)

    def test_pool_has_models(self):
        # 测试池模型已加载
        models = self.cfg.models()
        for mid in ["test-model-free", "test-model-low", "test-model-banned",
                    "test-model-unreliable", "test-model-dual-channel",
                    "test-model-dual-with-c", "test-model-vision", "test-model-high"]:
            self.assertIn(mid, models, mid)
        # 双通道模型
        self.assertEqual(set(models["test-model-dual-channel"].channels), {"test-channel-a", "test-channel-b"})

    def test_banned_never_default(self):
        # 任何路由都不应把禁用模型当默认
        for task_type in self.cfg.rules or ["code", "qa", "complex"]:
            d = self.router.route(task_type)
            self.assertNotEqual(d.selected_model, "test-model-banned")

    def test_all_config_models_available(self):
        # 配置里「非禁用且未被排除」的模型全在可用池
        avail = {m.id for m in self.cfg.available_models()}
        for mid, spec in self.cfg.models().items():
            if self.cfg.excluded_reason(spec) is None:
                self.assertIn(mid, avail)
            else:
                self.assertNotIn(mid, avail)

    def test_worker_false_channel_excluded(self):
        # test-channel-c 标了 worker:false（仅大脑）→ 只挂该通道的模型无可用工人通道
        spec = self.cfg.model("test-model-dual-with-c")
        self.assertIsNone(self.cfg.excluded_reason(spec))  # 还有 test-channel-a 可用
        chs = [p.channel for p in self.cfg.usable_channels(spec)]
        self.assertIn("test-channel-a", chs)
        self.assertNotIn("test-channel-c", chs)

    def test_low_quota_models_excluded(self):
        # 低配额(5h<500)模型被排除
        for mid in ["test-model-quota-limited"]:
            self.assertIn("配额过少", self.cfg.excluded_reason(self.cfg.model(mid)) or "", mid)

    def test_channel_blocked_by_quota(self):
        spec = self.cfg.model("test-model-quota-limited")
        self.assertIsNotNone(self.cfg.channel_blocked(spec, "test-channel-a"))
        # 无配额信息的模型不受影响
        spec2 = self.cfg.model("test-model-low")
        self.assertIsNone(self.cfg.channel_blocked(spec2, "test-channel-a"))


if __name__ == "__main__":
    unittest.main()
