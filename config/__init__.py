"""
============================================
配置入口 — 集中加载所有配置模块
============================================
"""

from .upload import *
from .smtp import *
from .oss import *
from .ai import *

__all__ = [k for k in dir() if k.isupper()]
