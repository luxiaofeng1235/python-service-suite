"""
============================================
生成器渲染 - Model 与 Schema 代码模板
============================================
把表结构转换成符合项目规范的 Python 文件，统一中文文件头及字段说明。
仅推导数据库能够确定的基础约束，业务验证规则由开发者补充。
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from script.configuration import CodegenError, GeneratorConfig, output_directory, resolve_names
from script.database_reader import ColumnSpec, TableSpec


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


TEMPLATE_DIRECTORY = Path(__file__).with_name("templates")


def _doc_text(value: str) -> str:
    """转义文档字符串，避免数据库注释破坏生成代码。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _model_field(column: ColumnSpec) -> str:
    """保留数据库默认表达式和计算列，ORM 不擅自补充时间行为。"""
    arguments = [column.model_type]
    if column.computed is not None:
        persisted = (
            f", persisted={column.computed_persisted!r}"
            if column.computed_persisted is not None
            else ""
        )
        arguments.append(f"Computed({column.computed!r}{persisted})")
    if column.primary_key:
        arguments.append("primary_key=True")
        arguments.append(f"autoincrement={column.autoincrement!r}")
    arguments.append(f"nullable={column.nullable!r}")
    if column.default is not None and column.computed is None:
        arguments.append(f"server_default=text({column.default!r})")
        if re.search(r"\bON\s+UPDATE\b", column.default, re.I):
            arguments.append("server_onupdate=FetchedValue()")
    arguments.append(f"comment={column.comment!r}")
    return (
        f"    {column.name} = Column(\n"
        + "".join(f"        {argument},\n" for argument in arguments)
        + "    )"
    )


def _literal_default(column: ColumnSpec) -> tuple[str | None, tuple[str, ...]]:
    """只提取可无歧义转换的常量默认值，其余默认值留给数据库处理。"""
    value = column.default
    if value is None:
        return None, ()
    if re.fullmatch(r"'(?:[^'\\]|'')*'", value):
        value = value[1:-1].replace("''", "'")
        if column.annotation == "str" or column.annotation.startswith("Literal["):
            return repr(value), ()
    if column.annotation == "int" and re.fullmatch(r"[+-]?\d+", value):
        return repr(int(value)), ()
    if column.annotation in {"float", "Decimal"} and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        if column.annotation == "Decimal":
            return f"Decimal({value!r})", ("from decimal import Decimal",)
        return repr(float(value)), ()
    if column.annotation == "bool" and value in {"0", "1"}:
        return "True" if value == "1" else "False", ()
    return None, ()


def _schema_field(column: ColumnSpec, kind: str) -> tuple[str, tuple[str, ...]]:
    """生成字段；省略字段与显式 null 的区别由请求基类校验。"""
    annotation = column.annotation
    imports = column.schema_imports
    default = "..."
    description = column.comment
    if kind == "update":
        default = "None"
    elif kind == "create":
        literal, extra_imports = _literal_default(column)
        imports += extra_imports
        if literal is not None:
            default = literal
        elif column.nullable or column.default is not None:
            default = "None"
            if column.default is not None:
                description += "（省略时由数据库提供默认值）"
    if column.nullable or default == "None":
        annotation += " | None"
    arguments = [default, *column.constraints, f"description={description!r}"]
    # 响应仅序列化现有数据，不追加请求验证的精度和长度限制。
    if kind == "response":
        arguments = [default, f"description={description!r}"]
    return f"    {column.name}: {annotation} = Field({', '.join(arguments)})", imports


def render_plan(table: TableSpec, config: GeneratorConfig) -> GenerationPlan:
    """同时渲染一张表的两个文件，生成过程不执行模板中的 Python 代码。"""
    module, class_name = resolve_names(table.name, config.naming)
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIRECTORY),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["doc_text"] = _doc_text
    environment.filters["py_repr"] = repr
    base_module, _, base_name = config.model.base_import.rpartition(".")
    reserved = {
        base_name,
        "mysql",
        *table.model_imports,
        "Field",
        "BaseModel",
        "Self",
        "model_validator",
        "date",
        "datetime",
        "time",
        "Decimal",
        "Literal",
        "JsonValue",
        "validate_nonnullable_fields",
    }
    if class_name in reserved:
        raise CodegenError(f"生成类名 {class_name} 与模板导入名称冲突，请配置 naming.overrides")
    for column in table.columns:
        if column.name in reserved:
            raise CodegenError(f"字段 {column.name} 与模板名称冲突，请手动映射")
    primary_keys = [column.name for column in table.columns if column.primary_key]
    repr_body = ", ".join(f"{name}={{self.{name}!r}}" for name in primary_keys)
    model_imports = set(table.model_imports)
    if not any(column.default is not None and column.computed is None for column in table.columns):
        model_imports.discard("text")
    model_source = environment.get_template("model.py.j2").render(
        table=table,
        class_name=class_name,
        base_module=base_module,
        base_name=base_name,
        model_imports=sorted(model_imports),
        model_fields=[_model_field(column) for column in table.columns],
        repr_body=repr_body,
    )
    writable = [
        column
        for column in table.columns
        if not column.autoincrement
        and column.computed is None
        and column.name not in config.schema_options.request_exclude_fields
    ]
    schema_imports: set[str] = set()
    classes: list[tuple[str, str, list[str]]] = []
    for kind, enabled, suffix, title in (
        ("create", config.schema_options.create, "CreateRequest", "创建请求参数"),
        ("update", config.schema_options.update, "UpdateRequest", "更新请求参数"),
        ("response", config.schema_options.response, "Response", "响应数据"),
    ):
        if not enabled:
            continue
        columns = (
            writable
            if kind != "response"
            else [
                column
                for column in table.columns
                if column.name not in config.schema_options.response_exclude_fields
            ]
        )
        fields: list[str] = []
        for column in columns:
            source, imports = _schema_field(column, kind)
            fields.append(source)
            schema_imports.update(imports)
        classes.append((class_name + suffix, title, fields))
    write_enabled = config.schema_options.create or config.schema_options.update
    # 按导入来源归并，保持标准库、第三方库的项目约定顺序。
    grouped: dict[str, set[str]] = {"pydantic": {"BaseModel"}}
    if any(item[2] for item in classes):
        grouped["pydantic"].add("Field")
    for line in schema_imports:
        source, _, names = line.removeprefix("from ").partition(" import ")
        grouped.setdefault(source, set()).update(names.split(", "))
    if write_enabled:
        grouped.setdefault("typing", set()).add("Self")
        grouped["pydantic"].add("model_validator")
    standard_imports = [
        f"from {source} import {', '.join(sorted(names))}"
        for source, names in sorted(grouped.items())
        if source != "pydantic"
    ]
    schema_source = environment.get_template("schema.py.j2").render(
        table=table,
        class_name=class_name,
        classes=classes,
        write_enabled=write_enabled,
        nonnullable=tuple(column.name for column in writable if not column.nullable),
        standard_imports=standard_imports,
        pydantic_import=f"from pydantic import {', '.join(sorted(grouped['pydantic']))}",
    )
    # 写入前检查模板产物语法，不导入生成文件、不运行业务或连接数据库。
    for source in (model_source, schema_source):
        ast.parse(source)
    return GenerationPlan(
        table.name,
        class_name,
        (
            GeneratedFile(
                output_directory(config.model.dir) / f"{module}.py",
                model_source,
                (class_name,),
                config.registration.model,
            ),
            GeneratedFile(
                output_directory(config.schema_output.dir) / f"{module}.py",
                schema_source,
                tuple(item[0] for item in classes),
                config.registration.schema_enabled,
            ),
        ),
    )
