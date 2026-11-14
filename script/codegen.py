"""
============================================
数据库代码生成器 - Model 与 Schema 命令行入口
============================================
读取项目根目录 generator.yaml，从已存在的 MySQL 表生成基础代码。
统一执行冲突检查、文件写入和导入注册，不包含业务接口或表结构变更。
"""

import argparse
import ast
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from jinja2 import TemplateError

from script.configuration import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    CodegenError,
    load_config,
    output_directory,
    validate_identifier,
)
from script.database_reader import read_table
from script.rendering import GenerationPlan, render_plan


def _read_source(path: Path) -> str:
    """读取现有源文件，失败时停止生成，避免漏检重复映射。"""
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise CodegenError(f"无法读取现有代码，请检查：{path}") from exc


def _syntax_tree(path: Path) -> ast.Module:
    """只解析代码，不导入现有 Model 或 Schema。"""
    try:
        return ast.parse(_read_source(path), filename=str(path))
    except SyntaxError as exc:
        raise CodegenError(f"现有文件存在语法错误，无法检查冲突：{path}") from exc


def find_conflict(plan: GenerationPlan) -> str | None:
    """识别目标文件、同名类及已有表映射，包括原有集中定义的模型。"""
    for generated in plan.files:
        output_directory(str(generated.path.parent))
        if generated.path.exists() or generated.path.is_symlink():
            return f"目标文件已存在：{generated.path}"
    for position, generated in enumerate(plan.files):
        default_root = PROJECT_ROOT / "app" / ("models" if position == 0 else "schemas")
        roots = {default_root, generated.path.parent}
        visited: set[Path] = set()
        for root in roots:
            for path in root.rglob("*.py"):
                if path in visited:
                    continue
                visited.add(path)
                tree = _syntax_tree(path)
                for node in tree.body:
                    if not isinstance(node, ast.ClassDef):
                        continue
                    if node.name in generated.classes:
                        return f"类 {node.name} 已定义于 {path}"
                    if position != 0:
                        continue
                    for statement in node.body:
                        if isinstance(statement, ast.Assign):
                            targets, value = statement.targets, statement.value
                        elif isinstance(statement, ast.AnnAssign):
                            targets, value = [statement.target], statement.value
                        else:
                            continue
                        if (
                            any(
                                isinstance(target, ast.Name) and target.id == "__tablename__"
                                for target in targets
                            )
                            and isinstance(value, ast.Constant)
                            and value.value == plan.table_name
                        ):
                            return f"表 {plan.table_name} 已映射于 {path}"
        init_path = generated.path.parent / "__init__.py"
        if init_path.is_symlink():
            raise CodegenError(f"不能修改符号链接形式的包入口：{init_path}")
        if init_path.exists() and generated.register:
            for node in _syntax_tree(init_path).body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        name = alias.asname or alias.name.split(".")[0]
                        if name in generated.classes:
                            return f"包入口已经导入同名类 {name}：{init_path}"
    return None


@contextmanager
def generation_lock() -> Iterator[None]:
    """禁止多个生成器进程同时追加包入口，异常退出时由维护者确认后清理锁。"""
    lock = Path(__file__).with_name(".codegen.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise CodegenError(
            "已有生成器运行，或 script/.codegen.lock 尚未清理，请确认后再执行"
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _create_file(path: Path, content: bytes, created: list[tuple[Path, bytes]]) -> None:
    """排他创建文件，目标即使在预检后出现也不会被覆盖。"""
    with path.open("xb") as handle:
        # 先记录文件所有权，发生写入异常时也能清理本次创建的空文件。
        created.append((path, content))
        handle.write(content)


def _ensure_packages(directory: Path, created: list[tuple[Path, bytes]]) -> None:
    """补充包目录和中文文件头，不改写已经存在的包入口。"""
    directory.mkdir(parents=True, exist_ok=True)
    for parent in reversed((directory, *directory.parents)):
        if parent == PROJECT_ROOT or not parent.is_relative_to(PROJECT_ROOT):
            continue
        init_path = parent / "__init__.py"
        if init_path.is_symlink():
            raise CodegenError(f"包入口不能使用符号链接：{init_path}")
        if not init_path.exists():
            content = (
                '"""\n============================================\n'
                f"{parent.name} 数据模块 - 模型与结构定义\n"
                "============================================\n"
                '组织当前目录的 Python 模块，供业务按需导入。\n"""\n'
            )
            _create_file(init_path, content.encode("utf-8"), created)


def write_plan(plan: GenerationPlan) -> None:
    """生成同表文件并追加导入；失败时撤销本次操作，不删除原有代码。"""
    created: list[tuple[Path, bytes]] = []
    appended: list[tuple[Path, bytes, bytes]] = []
    try:
        conflict = find_conflict(plan)
        if conflict:
            raise CodegenError(conflict)
        for generated in plan.files:
            _ensure_packages(generated.path.parent, created)
            _create_file(generated.path, generated.content.encode("utf-8"), created)
        for generated in plan.files:
            if not generated.register:
                continue
            init_path = generated.path.parent / "__init__.py"
            module = ".".join(generated.path.relative_to(PROJECT_ROOT).with_suffix("").parts)
            original = init_path.read_bytes()
            newline = b"\r\n" if b"\r\n" in original else b"\n"
            prefix = b"" if not original or original.endswith(b"\n") else newline
            addition = (
                prefix
                + (f"from {module} import {', '.join(generated.classes)}  # noqa: F401").encode()
                + newline
            )
            tree = ast.parse(original.decode("utf-8-sig"))
            if any(
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "__all__"
                    for target in node.targets
                )
                for node in tree.body
            ):
                addition += f"__all__ += type(__all__)({generated.classes!r})".encode() + newline
            # 若用户正好也编辑了包入口，停止操作，防止按旧内容追加。
            if init_path.is_symlink() or init_path.read_bytes() != original:
                raise CodegenError(f"包入口在生成期间发生变化，请重新执行：{init_path}")
            appended.append((init_path, original, original + addition))
            with init_path.open("ab") as handle:
                handle.write(addition)
    except BaseException:
        # 只有文件仍等于本次写入结果时才恢复，避免撤销别人的并发编辑。
        for path, original, expected in reversed(appended):
            with suppress(OSError):
                if path.exists() and not path.is_symlink() and path.read_bytes() == expected:
                    path.write_bytes(original)
        for path, expected in reversed(created):
            with suppress(OSError):
                if path.exists() and not path.is_symlink():
                    current = path.read_bytes()
                    if current == expected or expected.startswith(current):
                        path.unlink()
        raise


def _parser() -> argparse.ArgumentParser:
    """定义 CLI 参数，配置路径和输出目录均以项目根目录为基准。"""
    parser = argparse.ArgumentParser(
        description="从现有 MySQL 表生成 Model 和 Schema，不覆盖已有文件"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="YAML 配置路径，默认根目录 generator.yaml",
    )
    parser.add_argument("--table", required=True, help="需要生成的数据库表名，每次处理一张表")
    parser.add_argument(
        "--dry-run", action="store_true", help="连接数据库读取结构并预览代码，不写入文件"
    )
    return parser


def main() -> int:
    """执行一次生成；失败返回非零状态码，错误输出不包含数据库异常详情。"""
    args = _parser().parse_args()
    try:
        validate_identifier(args.table, label="表名")
        config_path = args.config if args.config.is_absolute() else PROJECT_ROOT / args.config
        config = load_config(config_path)
        plan = render_plan(read_table(args.table), config)
        if args.dry_run:
            conflict = find_conflict(plan)
            if conflict:
                sys.stdout.write(f"冲突提示：{conflict}\n")
            for generated in plan.files:
                sys.stdout.write(f"\n预览文件：{generated.path.relative_to(PROJECT_ROOT)}\n")
                sys.stdout.write(generated.content)
            return 1 if conflict and config.on_exists == "error" else 0
        with generation_lock():
            conflict = find_conflict(plan)
            if conflict:
                if config.on_exists == "error":
                    raise CodegenError(conflict)
                sys.stdout.write(f"已整组跳过：{conflict}\n")
                return 0
            write_plan(plan)
        for generated in plan.files:
            sys.stdout.write(f"生成成功：{generated.path.relative_to(PROJECT_ROOT)}\n")
        sys.stdout.write(
            "请完善业务验证和响应字段；保存请求时使用 model_dump(exclude_unset=True)。\n"
        )
        return 0
    except CodegenError as exc:
        sys.stderr.write(f"生成失败：{exc}\n")
    except (OSError, UnicodeError):
        sys.stderr.write("生成失败：请检查文件读写权限、磁盘空间及文件编码。\n")
    except (SyntaxError, TemplateError):
        sys.stderr.write("生成失败：模板或生成代码存在语法问题，请检查 script/templates。\n")
    except KeyboardInterrupt:
        sys.stderr.write("生成已中断。\n")
        return 130
    except Exception:
        # 不输出异常链，防止数据库连接或设置校验异常携带凭据。
        sys.stderr.write("生成失败：出现未预期错误，请审查生成器配置及代码。\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
