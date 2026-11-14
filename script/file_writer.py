"""
============================================
生成器文件写入 - 冲突检查与导入注册
============================================
通过静态读取现有代码识别重复映射，禁止覆盖已存在的生成目标。
同表文件成组写入，失败时清理本次产物并尽量恢复本次追加的导入。
"""

import ast
import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from script.configuration import PROJECT_ROOT, CodegenError, output_directory
from script.metadata import GenerationPlan


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
