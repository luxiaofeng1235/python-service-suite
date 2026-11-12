"""
============================================
页面模板渲染 - 统一视图入口
============================================
从固定的 app/templates 目录加载 Jinja2 模板。
通过 display 方法传入请求和页面数据，返回 HTML 响应。
"""

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
_templates = Jinja2Templates(directory=TEMPLATE_DIR)


def display(
    request: Request,
    template_name: str,
    context: dict[str, object] | None = None,
) -> HTMLResponse:
    """渲染固定模板目录中的页面，并将页面数据传入模板。"""
    return _templates.TemplateResponse(
        request=request,
        name=template_name,
        context=context if context is not None else {},
    )
