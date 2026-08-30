"""router-brain: 模型路由大脑。

决策面（本进程）负责分类 + 选模型 + 编排；
执行面（DeepSeek Harness headless agent）负责真正动手干活。
"""

__version__ = "1.1.3"

# 导出核心类
from .config import Config
from .degrade import Runner
from .classifier import Classifier
from .router import Router

__all__ = ["Config", "Runner", "Classifier", "Router", "__version__"]
