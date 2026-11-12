"""
============================================
调试打印类
============================================
主要用于调试打印变量的基础信息，可以临时调试用，用于挂起当前操作快速定位
from app.utils.debugger import  DebugHelper
"""
import sys
import time
import traceback
from typing import Any


class DebugHelper:
    @staticmethod
    def hang(*args: Any, tag: str = "DEBUG", **kwargs: Any):
        # 1. 获取当前精确时间，方便多请求并发时区分先后
        timestamp = time.strftime("%H:%M:%S", time.localtime()) + f".{int(time.time() * 1000) % 1000:03d}"

        # 2. 打印标题栏（修复了原代码中的拼接瑕疵）
        print(f"\n{'=' * 15} [{tag}] 调试输出 @ {timestamp} {'=' * 15}")

        # 3. 合并所有传入的参数
        all_values = list(args) + list(kwargs.values())

        if all_values:
            print(f"--- 变量输出 (共 {len(all_values)} 个) ---")
            for i, val in enumerate(all_values):
                # 尝试安全地获取类型，防止部分对象打印崩掉
                val_type = type(val).__name__
                try:
                    print(f"[第{i+1}个输出] ({val_type}): {val}")
                except Exception as e:
                    print(f"[第{i+1}个输出] ({val_type}): <无法打印的对象: {e}>")

        # 4. 打印调用栈追踪
        print(f"--- 调用栈信息 ---")
        traceback.print_stack(file=sys.stdout, limit=5)

        # 5. 底部收尾分隔符（修复了原代码中的瑕疵）
        print(f"{'=' * 50}\n")
