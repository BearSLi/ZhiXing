"""依赖一致性自检：比对 requirements.txt 与当前环境实际安装的包

为什么需要它：
    虚拟环境是按某个时间点的 requirements.txt 建的。之后只要有人往清单里
    加了新依赖，环境就"过期"了——而症状往往是启动时报一句难以理解的错误
    （例如 "Form data requires python-multipart to be installed"），
    或者更糟：跑起来才发现某个功能坏掉。

    这个脚本把"环境与清单是否一致"变成一次显式检查，10 毫秒出结果。

用法：
    python check_deps.py           # 有缺失则退出码 1，并打印安装命令
"""
import importlib.metadata as md
import re
import sys
from pathlib import Path

REQ_FILE = Path(__file__).parent / "requirements.txt"


def parse_requirements(path: Path) -> list[str]:
    """从 requirements.txt 里取出包名（忽略注释、空行与版本约束）"""
    names = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 去掉版本约束与 extras：uvicorn[standard]==0.53.0 → uvicorn
        name = re.split(r"[=<>!~\[]", line)[0].strip()
        if name:
            names.append(name)
    return names


def main() -> int:
    if not REQ_FILE.exists():
        print(f"[check_deps] 找不到 {REQ_FILE}")
        return 1

    required = parse_requirements(REQ_FILE)
    missing = []
    for name in required:
        try:
            md.version(name)
        except md.PackageNotFoundError:
            missing.append(name)

    print(f"[check_deps] 清单 {len(required)} 项，已安装 {len(required) - len(missing)} 项")
    if missing:
        print(f"[check_deps] 缺失: {', '.join(missing)}")
        print(f"[check_deps] 安装命令: python -m pip install {' '.join(missing)}")
        return 1

    print("[check_deps] 环境与依赖清单一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
