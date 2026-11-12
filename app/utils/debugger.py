"""
============================================
调试打印类
============================================
主要用于调试打印变量的基础信息，可以临时调试用，用于挂起当前操作快速定位
from app.utils.debugger import  DebugHelper
"""
import sys
import traceback
from typing import Any


class DebugHelper:
    @staticmethod
    def hang(*args: Any, tag: str = "DEBUG", **kwargs: Any):
        # 1. 打印标题栏
        print(f"\n{'=' * 20} [{tag}] 调试输出 {'=' * 20}")

        # 2. 把位置参数 (*args) 和 关键字参数的值 (**kwargs) 合并到一起
        # 这样不管你是怎么传的，最终都统一按顺序编号
        all_values = list(args) + list(kwargs.values())

        if all_values:
            print(f"--- 变量输出 (共 {len(all_values)} 个) ---")
            for i, val in enumerate(all_values):
                print(f"[第{i}个输出]: {val}")

        # 3. 打印调用栈追踪
        traceback.print_stack(file=sys.stdout, limit=5)
        print(f"{'=' * 50}\n")
