"""让 pytest 能从 backend/ 目录导入应用模块（main / database / services ...）

为什么需要它：
    pytest 默认只把「测试文件所在目录」加入 sys.path。我们的测试在 backend/tests/ 下，
    而应用模块在 backend/ 下，直接 import main 会失败。
    在 backend/ 放一个 conftest.py，pytest 会把该目录也加入 sys.path。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
