"""
============================================
应用组装模块
============================================
main.py 只做导入和调用，具体实现在各子模块中。
"""

from app.setup.middleware import register_middleware
from app.setup.exception import register_exception_handlers
from app.setup.routes import register_routes, register_root_route, register_static_files
from app.setup.docs import register_docs
from app.setup.lifecycle import register_lifecycle

__all__ = [
    "register_middleware",
    "register_exception_handlers",
    "register_routes",
    "register_root_route",
    "register_static_files",
    "register_docs",
    "register_lifecycle",
]
