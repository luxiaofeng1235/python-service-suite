"""
============================================
生成器读表工具 - 现有 MySQL 表结构反射
============================================
复用项目数据库配置，只读取表结构、索引和约束。
将支持的数据库类型转换为模板数据，不猜测业务校验规则。
"""

import re

from pydantic import BaseModel
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.type_api import TypeEngine

from script.configuration import PROJECT_ROOT, CodegenError, validate_identifier
from script.metadata import ColumnSpec, TableSpec

INTEGER_BITS = {"TINYINT": 8, "SMALLINT": 16, "MEDIUMINT": 24, "INTEGER": 32, "BIGINT": 64}
TEXT_TYPES = {"CHAR", "VARCHAR", "NCHAR", "NVARCHAR", "TEXT", "TINYTEXT", "MEDIUMTEXT", "LONGTEXT"}
BINARY_TYPES = {"BINARY", "VARBINARY", "BLOB", "TINYBLOB", "MEDIUMBLOB", "LONGBLOB"}
DATE_TYPES = {"DATE": "date", "DATETIME": "datetime", "TIMESTAMP": "datetime", "TIME": "time"}
RESERVED_FIELDS = {"metadata", "registry", "query", "query_class"}


def chinese_description(value: str | None, fallback: str) -> str:
    """保留数据库中文注释，缺失或纯英文注释补充中文说明。"""
    description = " ".join((value or "").split())
    if not description:
        return fallback
    return (
        description if re.search(r"[\u3400-\u9fff]", description) else f"{fallback}：{description}"
    )


def _type_mapping(type_: TypeEngine) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    """只转换明确支持的 MySQL 类型，未知类型直接报错。"""
    name = type(type_).__name__
    arguments: list[str] = []
    imports: tuple[str, ...] = ()
    constraints: list[str] = []
    if name in INTEGER_BITS:
        annotation = "int"
        bits = INTEGER_BITS[name]
        unsigned = bool(getattr(type_, "unsigned", False))
        constraints.extend(
            [
                f"ge={0 if unsigned else -(2 ** (bits - 1))}",
                f"le={2**bits - 1 if unsigned else 2 ** (bits - 1) - 1}",
            ]
        )
    elif name in TEXT_TYPES:
        annotation = "str"
    elif name in BINARY_TYPES:
        annotation = "bytes"
    elif name in {"DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL"}:
        decimal = name in {"DECIMAL", "NUMERIC"} or bool(getattr(type_, "asdecimal", False))
        annotation = "Decimal" if decimal else "float"
        imports = ("from decimal import Decimal",) if decimal else ()
        for attr in ("precision", "scale"):
            value = getattr(type_, attr, None)
            if value is not None:
                arguments.append(f"{attr}={value!r}")
        if name in {"DECIMAL", "NUMERIC"}:
            precision, scale = getattr(type_, "precision", None), getattr(type_, "scale", None)
            if precision is not None:
                constraints.append(f"max_digits={precision}")
            if scale is not None:
                constraints.append(f"decimal_places={scale}")
        if getattr(type_, "unsigned", False):
            constraints.append("ge=0")
        if name in {"FLOAT", "DOUBLE", "REAL"}:
            arguments.append(f"asdecimal={decimal!r}")
    elif name in DATE_TYPES:
        annotation = DATE_TYPES[name]
        imports = (f"from datetime import {annotation}",)
        fsp = getattr(type_, "fsp", None)
        if fsp is not None:
            arguments.append(f"fsp={fsp!r}")
    elif name in {"ENUM", "SET"}:
        values = tuple(getattr(type_, "enums" if name == "ENUM" else "values", ()))
        if not values or not all(isinstance(value, str) for value in values):
            raise CodegenError("枚举类型无法可靠识别，请手动维护对应模型")
        arguments.extend(repr(value) for value in values)
        if name == "SET" and getattr(type_, "retrieve_as_bitwise", False):
            arguments.append("retrieve_as_bitwise=True")
        literal = f"Literal[{', '.join(repr(value) for value in values)}]"
        annotation = literal if name == "ENUM" else f"set[{literal}]"
        imports = ("from typing import Literal",)
    elif name == "JSON":
        annotation, imports = "JsonValue", ("from pydantic import JsonValue",)
    elif name in {"BOOLEAN", "Boolean"}:
        name, annotation = "BOOLEAN", "bool"
    elif name in {"BIT", "YEAR"}:
        annotation = "int"
        if name == "BIT" and getattr(type_, "length", None) is not None:
            arguments.append(f"length={type_.length!r}")
    else:
        raise CodegenError(f"暂不支持的数据库类型：{name}，请手动维护对应模型")
    if name in TEXT_TYPES | BINARY_TYPES:
        length = getattr(type_, "length", None)
        if length is not None:
            arguments.append(f"length={length!r}")
            constraints.append(f"max_length={length}")
    if name in TEXT_TYPES | {"ENUM", "SET"}:
        for attr in ("charset", "collation"):
            value = getattr(type_, attr, None)
            if value is not None:
                arguments.append(f"{attr}={value!r}")
    if name in INTEGER_BITS or name in {"DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL"}:
        for attr in ("unsigned", "zerofill"):
            if getattr(type_, attr, False):
                arguments.append(f"{attr}=True")
    return f"mysql.{name}({', '.join(arguments)})", annotation, imports, tuple(constraints)


def read_table(table_name: str) -> TableSpec:
    """读取一张现有表，连接在成功或异常后均关闭，不执行任何 DDL。"""
    from app.core.config import Settings

    try:
        # 显式定位根目录 .env，不依赖执行 CLI 时所在目录。
        settings = Settings(_env_file=PROJECT_ROOT / ".env")
        url = make_url(settings.DATABASE_URL)
        if url.get_backend_name() != "mysql":
            raise CodegenError("当前生成器仅支持 MySQL，请检查 DATABASE_URL")
        engine = create_engine(url.set(drivername="mysql+pymysql"), poolclass=NullPool, echo=False)
    except (SQLAlchemyError, ValueError, ImportError) as exc:
        raise CodegenError("无法加载数据库连接，请检查项目依赖及 .env 配置") from exc
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            if table_name not in inspector.get_table_names():
                raise CodegenError(f"数据库中不存在该普通表：{table_name}")
            primary = set(inspector.get_pk_constraint(table_name)["constrained_columns"])
            if not primary:
                raise CodegenError(f"表 {table_name} 没有主键，不能自动生成 ORM 模型")
            columns: list[ColumnSpec] = []
            for field in inspector.get_columns(table_name):
                name = validate_identifier(field["name"], label="字段名")
                if name in RESERVED_FIELDS or name.startswith("model_") or hasattr(BaseModel, name):
                    raise CodegenError(f"字段 {name} 与 ORM 或 Schema 保留名称冲突，请手动映射")
                model_type, annotation, imports, constraints = _type_mapping(field["type"])
                computed = field.get("computed")
                if field.get("identity"):
                    raise CodegenError(f"字段 {name} 使用暂不支持的标识列，请手动维护")
                columns.append(
                    ColumnSpec(
                        name=name,
                        model_type=model_type,
                        annotation=annotation,
                        schema_imports=imports,
                        constraints=constraints,
                        nullable=field["nullable"],
                        primary_key=name in primary,
                        autoincrement=field.get("autoincrement") is True,
                        default=field.get("default"),
                        computed=computed["sqltext"] if computed else None,
                        computed_persisted=computed.get("persisted") if computed else None,
                        comment=chinese_description(field.get("comment"), f"字段 {name}"),
                    )
                )
            args: list[str] = []
            model_imports = {"Column", "text"}
            if any(column.computed for column in columns):
                model_imports.add("Computed")
            if any(
                column.default and re.search(r"\bON\s+UPDATE\b", column.default, re.I)
                for column in columns
            ):
                model_imports.add("FetchedValue")
            indexes = inspector.get_indexes(table_name)
            for index in indexes:
                names = index["column_names"]
                if not names or not all(isinstance(name, str) for name in names):
                    raise CodegenError("存在表达式索引，暂不能自动生成，请手动维护")
                if index.get("column_sorting"):
                    raise CodegenError("存在带排序规则的索引，暂不能自动生成，请手动维护")
                model_imports.add("Index")
                options = [repr(index["name"]), *(repr(name) for name in names)]
                if index["unique"]:
                    options.append("unique=True")
                for key, value in index.get("dialect_options", {}).items():
                    if key not in {
                        "mysql_length",
                        "mysql_prefix",
                        "mysql_using",
                        "mysql_with_parser",
                    }:
                        raise CodegenError(f"暂不支持的索引选项：{key}")
                    options.append(f"{key}={value!r}")
                args.append(f"Index({', '.join(options)})")
            index_names = {index["name"] for index in indexes}
            for unique in inspector.get_unique_constraints(table_name):
                if unique.get("duplicates_index") or unique["name"] in index_names:
                    continue
                model_imports.add("UniqueConstraint")
                options = [
                    *(repr(name) for name in unique["column_names"]),
                    f"name={unique['name']!r}",
                ]
                args.append(f"UniqueConstraint({', '.join(options)})")
            for foreign in inspector.get_foreign_keys(table_name):
                model_imports.add("ForeignKeyConstraint")
                schema = foreign.get("referred_schema")
                target = f"{schema}." if schema else ""
                targets = [
                    f"{target}{foreign['referred_table']}.{name}"
                    for name in foreign["referred_columns"]
                ]
                options = [
                    repr(foreign["constrained_columns"]),
                    repr(targets),
                    f"name={foreign['name']!r}",
                ]
                for key, value in foreign.get("options", {}).items():
                    if key not in {"onupdate", "ondelete", "match", "deferrable", "initially"}:
                        raise CodegenError(f"暂不支持的外键选项：{key}")
                    options.append(f"{key}={value!r}")
                args.append(f"ForeignKeyConstraint({', '.join(options)})")
            for check in inspector.get_check_constraints(table_name):
                model_imports.add("CheckConstraint")
                args.append(f"CheckConstraint({check['sqltext']!r}, name={check['name']!r})")
            title = chinese_description(
                inspector.get_table_comment(table_name).get("text"), f"数据表 {table_name}"
            )
            # AUTO_INCREMENT 当前值属于运行状态，不写入模型模板。
            table_options = {
                key: value
                for key, value in inspector.get_table_options(table_name).items()
                if key
                in {
                    "mysql_engine",
                    "mysql_default_charset",
                    "mysql_charset",
                    "mysql_collate",
                    "mysql_row_format",
                }
            }
            table_options["comment"] = title
            args.append(repr(table_options))
            return TableSpec(
                table_name, title, tuple(columns), tuple(args), tuple(sorted(model_imports))
            )
    except SQLAlchemyError as exc:
        raise CodegenError("数据库结构读取失败，请检查连接、表名及读取权限") from exc
    finally:
        engine.dispose()
