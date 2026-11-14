"""
============================================
生成器元数据 - 表结构及模板数据定义
============================================
使用明确的数据结构连接数据库反射、代码渲染和文件写入。
不依赖应用 Model，避免读取表结构时触发 ORM 注册。
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ColumnSpec:
    """一个数据库字段及其 Python 映射信息。"""

    name: str
    model_type: str
    annotation: str
    schema_imports: tuple[str, ...]
    constraints: tuple[str, ...]
    nullable: bool
    primary_key: bool
    autoincrement: bool
    default: str | None
    computed: str | None
    computed_persisted: bool | None
    comment: str


@dataclass(frozen=True)
class TableSpec:
    """读取完成的单表结构，表达式均由受控转换器生成。"""

    name: str
    title: str
    columns: tuple[ColumnSpec, ...]
    table_args: tuple[str, ...]
    model_imports: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedFile:
    """待生成文件及其需要导出的类名。"""

    path: Path
    content: str
    classes: tuple[str, ...]
    register: bool


@dataclass(frozen=True)
class GenerationPlan:
    """同一张表的 Model 与 Schema 必须作为一组写入。"""

    table_name: str
    model_class: str
    files: tuple[GeneratedFile, ...]
