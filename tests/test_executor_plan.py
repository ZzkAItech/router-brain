"""executor / provider_catalog 的纯逻辑测试（不真跑 headless / 不发网络请求）。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from router_brain.config import Config
from router_brain.models import ProviderRef, RouterError
from router_brain.provider_catalog import (
    load_providers,
    provider_exists,
    render_patch,
    render_run_settings,
)

FIXTURES = Path(__file__).parent / "fixtures"

FAKE_PROVIDERS = {
    "fake-provider": {
        "displayName": "Fake Provider",
        "apiKeyEnv": "FAKE_API_KEY",
        "api": "openai-completions",
        "baseURL": "https://api.fake-example.com/v1",
        "models": [{"id": "fake-model-1", "name": "Fake Model 1"}],
    }
}


class TestExecutorPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_render_run_settings(self):
        dest = self.root / "run" / "settings.yaml"
        render_run_settings(FAKE_PROVIDERS, "fake-provider", "fake-model-1", dest)
        doc = yaml.safe_load(dest.read_text(encoding="utf-8"))
        self.assertEqual(doc["agent-default-model"], {"provider": "fake-provider", "model": "fake-model-1"})
        self.assertEqual(doc["llm-pi-ai"]["providers"]["fake-provider"]["baseURL"], "https://api.fake-example.com/v1")

    def test_render_run_settings_missing_provider(self):
        with self.assertRaises(RouterError):
            render_run_settings(FAKE_PROVIDERS, "no-such-provider", "x", self.root / "s.yaml")

    def test_render_run_settings_injects_missing_model(self):
        dest = self.root / "s.yaml"
        render_run_settings(FAKE_PROVIDERS, "fake-provider", "fake-model-new", dest,
                            model_name="Fake Model New", context_window=1000000)
        doc = yaml.safe_load(dest.read_text(encoding="utf-8"))
        models = doc["llm-pi-ai"]["providers"]["fake-provider"]["models"]
        self.assertIn("fake-model-new", [m["id"] for m in models])
        self.assertEqual(doc["agent-default-model"]["model"], "fake-model-new")

    def test_injected_max_tokens_never_exceeds_131072(self):
        # 上游对多数新模型 max_tokens 有硬上限（131072）
        dest = self.root / "s.yaml"
        render_run_settings(FAKE_PROVIDERS, "fake-provider", "fake-model-huge", dest, context_window=1000000)
        doc = yaml.safe_load(dest.read_text(encoding="utf-8"))
        entry = next(m for m in doc["llm-pi-ai"]["providers"]["fake-provider"]["models"] if m["id"] == "fake-model-huge")
        self.assertLessEqual(entry["maxTokens"], 131072)

    def test_render_run_settings_keeps_existing(self):
        dest = self.root / "s.yaml"
        render_run_settings(FAKE_PROVIDERS, "fake-provider", "fake-model-1", dest)
        doc = yaml.safe_load(dest.read_text(encoding="utf-8"))
        models = doc["llm-pi-ai"]["providers"]["fake-provider"]["models"]
        self.assertEqual(len([m for m in models if m["id"] == "fake-model-1"]), 1)

    def test_render_patch(self):
        dest = self.root / "patch.yml"
        render_patch(self.root / "settings.yaml", dest)
        patch = yaml.safe_load(dest.read_text(encoding="utf-8"))
        self.assertEqual(patch[0]["id"], "settings")
        self.assertEqual(patch[0]["config"]["path"], str(self.root / "settings.yaml"))

    def test_render_patch_with_extras(self):
        extras = self.root / "extras.yml"
        extras.write_text("- id: tool-goal\n  name: '@deepseek-ai/dsh-tool-goal'\n", encoding="utf-8")
        dest = self.root / "patch2.yml"
        render_patch(self.root / "settings.yaml", dest, extras_path=extras)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("settings", text)
        self.assertIn("tool-goal", text)

    def test_worker_standard_file_exists(self):
        from pathlib import Path
        ws = Path(__file__).resolve().parent.parent / "config" / "worker-standard.yml"
        self.assertTrue(ws.exists())
        txt = ws.read_text(encoding="utf-8")
        self.assertIn("tool-goal", txt)
        self.assertIn("skill-filesystem", txt)

    def test_provider_exists(self):
        self.assertTrue(provider_exists(FAKE_PROVIDERS, "fake-provider"))
        self.assertFalse(provider_exists(FAKE_PROVIDERS, "nope"))

    def test_cfg_provider_from_fixture(self):
        cfg = Config(
            pool_path=FIXTURES / "test_pool.yaml",
            routing_path=FIXTURES / "test_routing.yaml",
        )
        self.assertEqual(cfg.provider("test-channel-a").base_url, "https://api.example-a.com/v1")
        self.assertEqual(cfg.provider("test-channel-b").base_url, "https://api.example-b.com/v1")

    def test_render_run_settings_no_side_effect(self):
        # #6: 验证 render_run_settings 不会修改原始 providers dict
        original_models = list(FAKE_PROVIDERS["fake-provider"]["models"])
        original_len = len(original_models)
        dest = self.root / "s.yaml"
        # 使用一个不存在的模型 id，会触发自动添加
        render_run_settings(FAKE_PROVIDERS, "fake-provider", "new-model-id", dest, context_window=1000000)
        # 验证原始 providers 未被修改
        self.assertEqual(len(FAKE_PROVIDERS["fake-provider"]["models"]), original_len)
        self.assertEqual(FAKE_PROVIDERS["fake-provider"]["models"], original_models)
        # 验证生成的文件包含新模型
        doc = yaml.safe_load(dest.read_text(encoding="utf-8"))
        models = doc["llm-pi-ai"]["providers"]["fake-provider"]["models"]
        self.assertIn("new-model-id", [m["id"] for m in models])


class TestAgentExecutor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_agent_timeout_kills_process(self):
        # #1: 验证子进程超时会被正确终止并返回部分输出
        from router_brain.executor import AgentExecutor, AgentOutcome
        from router_brain.config import Config
        from router_brain.models import ModelSpec

        cfg = Config()
        executor = AgentExecutor(cfg)

        # Mock Popen 模拟超时场景（轮询实现：poll 一直返回 None 直到超时）
        mock_proc = Mock()
        mock_proc.poll.return_value = None  # 进程一直未退出 → 触发超时 kill
        mock_proc.returncode = 1

        with patch('router_brain.executor.subprocess.Popen', return_value=mock_proc):
            with patch('router_brain.executor._dsh_bin', return_value='dsh'):
                with patch('router_brain.executor.load_providers', return_value=FAKE_PROVIDERS):
                    with patch('router_brain.executor.provider_exists', return_value=True):
                        with patch('router_brain.executor.render_run_settings', return_value=self.root / "settings.yaml"):
                            with patch('router_brain.executor.render_patch', return_value=self.root / "patch.yml"):
                                with patch.object(executor, '_cfg') as mock_cfg:
                                    mock_cfg.execution = {"dsh_tools_mode": "danger-full-access"}
                                    run_dir = self.root / "test-task"
                                    run_dir.mkdir(parents=True, exist_ok=True)
                                    (run_dir / "task.txt").write_text("test")

                                    model = ModelSpec(
                                        id="fake-model-1",
                                        providers=(ProviderRef(channel="test-channel-a", dsh_provider="fake-provider"),),
                                        kind="chat",
                                        cost="low",
                                        context=100000
                                    )

                                    result = executor.execute(
                                        model=model,
                                        task="test task",
                                        provider=model.primary,
                                        cwd=self.root,
                                        run_dir=run_dir,
                                        timeout_s=1,
                                        session_cleanup=False
                                    )

                                    # 验证超时后被正确终止
                                    mock_proc.kill.assert_called_once()
                                    mock_proc.wait.assert_called_once()
                                    # 验证返回超时错误
                                    self.assertFalse(result.ok)
                                    self.assertIn("超时", result.error)


if __name__ == "__main__":
    unittest.main()
