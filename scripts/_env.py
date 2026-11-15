# -*- coding: utf-8 -*-
"""
轻量 .env 加载器（零依赖）：读取项目根目录 .env 写入 os.environ。

规则:
  - 已存在的环境变量优先（shell 里 export 的值不会被 .env 覆盖）
  - 空值（KEY=）不写入，避免空字符串覆盖脚本内默认值
  - 支持 # 注释、前后空白、可选的 export 前缀与首尾引号

用法（脚本顶部）:
    import _env  # noqa: F401   # 导入即加载
"""
import os

ENV_PATH = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".env"))


def load_env(path: str = ENV_PATH) -> int:
    """加载 .env，返回写入的变量个数"""
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            if not key or not val:
                continue
            if key not in os.environ:
                os.environ[key] = val
                n += 1
    return n


load_env()
