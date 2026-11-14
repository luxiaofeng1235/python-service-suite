"""
============================================
数据库代码生成器 - Model 与 Schema 命令行入口
============================================
读取项目根目录 generator.yaml，从已存在的 MySQL 表生成基础代码。
只协调配置、读表、渲染和写入，不包含业务接口或表结构变更。
"""

import argparse
import sys
from pathlib import Path

from jinja2 import TemplateError

from script.configuration import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    CodegenError,
    load_config,
    validate_identifier,
)
from script.database_reader import read_table
from script.file_writer import find_conflict, generation_lock, write_plan
from script.rendering import render_plan


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
