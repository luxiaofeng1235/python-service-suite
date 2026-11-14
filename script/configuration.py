"""
============================================
生成器配置 - YAML 读取与命名约定
============================================
校验项目根目录的生成配置，统一解析输出目录及 Python 模块命名。
数据库凭据由项目 Settings 维护，不写入生成器配置。
"""

import keyword
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "generator.yaml"


class CodegenError(Exception):
    """生成过程中的可读错误，不包含数据库连接凭据。"""


class ConfigSection(BaseModel):
    """配置必须显式定义，拒绝拼错或已废弃的配置项。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class OutputConfig(ConfigSection):
    """文件输出位置。"""

    dir: str


class ModelConfig(OutputConfig):
    """Model 输出位置及 ORM 基类导入路径。"""

    dir: str = "app/models"
    base_import: str = "app.database.Base"


class RegistrationConfig(ConfigSection):
    """是否向目标包追加模型导入。"""

    model: bool = True
    schema_enabled: bool = Field(False, alias="schema", description="是否注册 Schema 包导入")


class NameOverride(ConfigSection):
    """指定表对应的模块名与类名。"""

    file: str
    class_name: str = Field(alias="class", description="生成类的 PascalCase 名称")


class NamingConfig(ConfigSection):
    """常规单数化及特殊表名映射。"""

    singularize: bool = True
    overrides: dict[str, NameOverride] = Field(
        default_factory=dict, description="数据库表名对应的特殊命名映射"
    )


class SchemaOptions(ConfigSection):
    """需要生成的 Schema 类以及字段排除规则。"""

    create: bool = True
    update: bool = True
    response: bool = True
    request_exclude_fields: list[str] = Field(
        default_factory=lambda: ["id", "created_at", "updated_at"],
        description="请求模型排除的数据库字段",
    )
    response_exclude_fields: list[str] = Field(
        default_factory=lambda: [
            "password",
            "password_hash",
            "token",
            "access_token",
            "refresh_token",
            "secret_key",
        ],
        description="响应模型排除的数据库字段",
    )

    @model_validator(mode="after")
    def validate_classes(self) -> "SchemaOptions":
        """至少生成一种 Schema，避免留下无实际内容的文件。"""
        if not (self.create or self.update or self.response):
            raise ValueError("至少启用一种 Schema 类")
        return self


class GeneratorConfig(ConfigSection):
    """生成器完整配置。"""

    model: ModelConfig = Field(default_factory=ModelConfig, description="数据库模型生成配置")
    schema_output: OutputConfig = Field(
        default_factory=lambda: OutputConfig(dir="app/schemas"),
        alias="schema",
        description="请求与响应模型生成配置",
    )
    on_exists: Literal["skip", "error"] = "skip"
    registration: RegistrationConfig = Field(
        default_factory=RegistrationConfig, description="包导入注册开关"
    )
    naming: NamingConfig = Field(default_factory=NamingConfig, description="文件与类的命名规则")
    schema_options: SchemaOptions = Field(
        default_factory=SchemaOptions, description="请求与响应模型生成选项"
    )


def validate_identifier(value: str, *, label: str) -> str:
    """只接受可直接用于 Python 代码的英文标识符。"""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value) or keyword.iskeyword(value):
        raise CodegenError(f"{label}不是有效的英文 Python 标识符：{value}")
    return value


def output_directory(value: str) -> Path:
    """目录必须在项目内且能组成合法包路径，拒绝符号链接。"""
    path = Path(value)
    path = path if path.is_absolute() else PROJECT_ROOT / path
    try:
        parts = path.relative_to(PROJECT_ROOT).parts
    except ValueError as exc:
        raise CodegenError("生成目录必须位于项目根目录内") from exc
    if not parts:
        raise CodegenError("生成目录不能直接使用项目根目录")
    current = PROJECT_ROOT
    for part in parts:
        validate_identifier(part, label="目录名")
        current /= part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise CodegenError(f"生成目录不能使用符号链接或普通文件：{current}")
    return path


def load_config(path: Path) -> GeneratorConfig:
    """安全加载 YAML，并在连接数据库之前校验目录和命名配置。"""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = GeneratorConfig.model_validate(raw)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CodegenError(f"无法读取生成配置：{path}") from exc
    except ValidationError as exc:
        locations = [".".join(str(part) for part in item["loc"]) for item in exc.errors()]
        raise CodegenError(
            f"生成配置不符合约定，请检查：{', '.join(locations) or '配置根节点'}"
        ) from exc
    if output_directory(config.model.dir) == output_directory(config.schema_output.dir):
        raise CodegenError("Model 和 Schema 生成目录不能相同")
    for part in config.model.base_import.split("."):
        validate_identifier(part, label="ORM 基类导入路径")
    if "." not in config.model.base_import:
        raise CodegenError("ORM 基类必须使用完整导入路径，例如 app.database.Base")
    for table, override in config.naming.overrides.items():
        validate_identifier(table, label="表名")
        validate_identifier(override.file, label="文件名")
        validate_identifier(override.class_name, label="类名")
    return config


def resolve_names(table_name: str, naming: NamingConfig) -> tuple[str, str]:
    """遵循 snake_case 文件名和 PascalCase 类名，特殊复数要求配置映射。"""
    validate_identifier(table_name, label="表名")
    override = naming.overrides.get(table_name)
    if override is not None:
        module, class_name = override.file, override.class_name
    else:
        module = table_name
        if naming.singularize:
            prefix, separator, tail = module.rpartition("_")
            if tail.endswith("ies"):
                tail = tail[:-3] + "y"
            elif tail.endswith(("sses", "shes", "ches", "xes", "zes")):
                tail = tail[:-2]
            elif tail.endswith("s") and not tail.endswith(("ss", "us", "is", "news")):
                tail = tail[:-1]
            module = prefix + separator + tail
        class_name = "".join(part[:1].upper() + part[1:] for part in module.split("_"))
    validate_identifier(module, label="文件名")
    validate_identifier(class_name, label="类名")
    if module != module.lower() or class_name[:1].islower():
        raise CodegenError("文件名必须使用小写下划线，类名必须使用大写开头的 PascalCase")
    return module, class_name
