import unittest
from pathlib import Path

from router_brain.classifier import Classifier
from router_brain.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


class TestClassifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = Config(
            pool_path=FIXTURES / "test_pool.yaml",
            routing_path=FIXTURES / "test_routing.yaml",
        )
        cls.clf = Classifier(cls.cfg)

    def test_code(self):
        self.assertEqual(self.clf.classify("帮我写一个 python 脚本解析 JSON"), "code")

    def test_math(self):
        self.assertEqual(self.clf.classify("证明勾股定理并给出推导"), "math")

    def test_translate(self):
        self.assertEqual(self.clf.classify("把这段话翻译成英文"), "translate")

    def test_writing(self):
        self.assertEqual(self.clf.classify("帮我写一篇产品文案标题"), "writing")

    def test_vision_by_keyword(self):
        self.assertEqual(self.clf.classify("识别这张图片里的文字"), "vision")

    def test_vision_by_extension(self):
        self.assertEqual(self.clf.classify("看看这个文件内容", hints="screenshot.png"), "vision")

    def test_qa(self):
        self.assertEqual(self.clf.classify("什么是机器学习"), "qa")

    def test_extract(self):
        self.assertEqual(self.clf.classify("从这段话提取关键信息"), "extract")

    def test_fallback(self):
        self.assertEqual(self.clf.classify("今天天气怎么样"), "fallback")

    def test_priority_first_match(self):
        # 同时含"代码"与"报错"，按表顺序 code 在 debug 前
        self.assertEqual(self.clf.classify("这段代码报错了怎么修"), "code")

    # ---- 英文任务分类（国际化）----
    def test_en_code(self):
        self.assertEqual(self.clf.classify("write a python script to parse json"), "code")

    def test_en_debug(self):
        self.assertEqual(self.clf.classify("fix the bug in this code"), "debug")

    def test_en_math(self):
        self.assertEqual(self.clf.classify("prove pythagorean theorem"), "math")

    def test_en_translate(self):
        self.assertEqual(self.clf.classify("translate this to chinese"), "translate")

    def test_en_writing(self):
        self.assertEqual(self.clf.classify("write a product ad headline"), "writing")

    def test_en_qa(self):
        self.assertEqual(self.clf.classify("what is machine learning"), "qa")

    def test_en_extract(self):
        self.assertEqual(self.clf.classify("extract keywords from this text"), "extract")

    def test_en_classify(self):
        self.assertEqual(self.clf.classify("classify these items into categories"), "classify")

    def test_en_refactor(self):
        self.assertEqual(self.clf.classify("refactor this function"), "refactor")

    def test_en_plan(self):
        self.assertEqual(self.clf.classify("plan a project roadmap"), "plan")

    def test_en_complex(self):
        self.assertEqual(self.clf.classify("analyze the tradeoffs of this design"), "complex")

    def test_en_longtext(self):
        self.assertEqual(self.clf.classify("summarize this long report"), "longtext")

    def test_en_vision(self):
        self.assertEqual(self.clf.classify("look at this screenshot"), "vision")

    def test_en_creative(self):
        self.assertEqual(self.clf.classify("brainstorm some creative names"), "creative")

    def test_empty_task_raises_valueerror(self):
        # #9: 空任务应抛出 ValueError
        with self.assertRaises(ValueError):
            self.clf.classify("")
        with self.assertRaises(ValueError):
            self.clf.classify("   ")
        with self.assertRaises(ValueError):
            self.clf.classify(None)


if __name__ == "__main__":
    unittest.main()
