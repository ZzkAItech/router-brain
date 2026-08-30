"""规则式任务分类器：任务文本 → task_type。

确定性、零成本、毫秒级。关键词表来自 routing.yaml 的 classifier 段。
命中多个类型时按关键词在表里的出现顺序取第一个命中（表顺序即优先级）。
"""
from __future__ import annotations

from .config import Config


class Classifier:
    def __init__(self, cfg: Config) -> None:
        self._keywords = cfg.keywords
        self._ordered_types = list(self._keywords.keys())
        # 预先将所有关键词转为小写，避免每次循环都调用 lower()
        self._keywords_lower = {
            task_type: [kw.lower() for kw in keywords]
            for task_type, keywords in self._keywords.items()
        }

    def classify(self, task: str, hints: str = "") -> str:
        if not task or not task.strip():
            raise ValueError("任务不能为空")
        text = task + " " + (hints or "")
        text_lower = text.lower()
        for task_type in self._ordered_types:
            for kw in self._keywords_lower.get(task_type, []):
                if kw in text_lower:
                    return task_type
        # 带图片提示强制视觉
        if any(t in text_lower for t in ("图片", "截图", ".png", ".jpg", ".jpeg", ".webp", "image")):
            return "vision"
        return "fallback"
