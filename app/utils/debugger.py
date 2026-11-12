"""
============================================
调试打印类
============================================
主要用于调试打印变量的基础信息，可以临时调试用，用于挂起当前操作快速定位
from app.utils.debugger import  DebugHelper
"""
"""
============================================
调试打印类 (DebugHelper)
============================================
主要用于调试打印变量的基础信息，支持 FastAPI 常驻内存及 CLI 临时调试。
- hang(): 挂起打印，打印变量和调用栈，不中断程序。
- dd(): Dump & Die，打印变量和调用栈后，主动抛出异常终止当前流程。
"""
import sys
import time
import traceback
from typing import Any


class DebugStopException(Exception):
    """用于 DebugHelper.dd() 强行终止当前请求/流程的自定义异常"""
    pass


class DebugHelper:
    @staticmethod
    def hang(*args: Any, tag: str = "DEBUG", **kwargs: Any):
        """挂起打印：仅打印变量与调用栈，程序继续向下执行"""
        # 1. 获取精确到毫秒的时间戳，便于并发或多进程时辨别先后
        timestamp = time.strftime("%H:%M:%S", time.localtime()) + f".{int(time.time() * 1000) % 1000:03d}"

        # 2. 打印标题栏（加入 flush=True 确保立即输出，防止缓存丢失）
        print(f"\n{'=' * 15} [{tag}] 调试输出 @ {timestamp} {'=' * 15}", flush=True)

        # 3. 合并位置参数 (*args) 和关键字参数 (**kwargs)
        all_values = list(args) + list(kwargs.values())

        if all_values:
            print(f"--- 变量输出 (共 {len(all_values)} 个) ---", flush=True)
            for i, val in enumerate(all_values):
                val_type = type(val).__name__
                try:
                    # 序号从 1 开始计数 ([第1个输出]...)
                    print(f"[第{i + 1}个输出] ({val_type}): {val}", flush=True)
                except Exception as e:
                    print(f"[第{i + 1}个输出] ({val_type}): <无法打印的对象: {e}>", flush=True)

        # 4. 打印调用栈信息（定位到具体哪一行触发）
        print(f"--- 调用栈信息 ---", flush=True)
        traceback.print_stack(file=sys.stdout, limit=5)

        # 5. 底部收尾分隔符
        print(f"{'=' * 50}\n", flush=True)

    @staticmethod
    def dump(*args: Any, tag: str = "DEBUG", **kwargs: Any):
        """Dump & Die：打印变量及调用栈后，立刻抛出异常终止当前流程
           一般用于打印cli直接返回结果的，执行中断看结果的这种流程
        """
        # 先调用 hang 把当前状态完整打印出来
        DebugHelper.hang(*args, tag=tag, **kwargs)
        # 抛出异常，强制中断后续业务逻辑
        raise DebugStopException()

