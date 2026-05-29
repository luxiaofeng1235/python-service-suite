.PHONY: dev build docker-up docker-down docker-logs clean test alembic-init alembic-migrate alembic-upgrade help

APP_NAME = fastapi-ai
PORT = 8000

## —— Local Development ——

dev:  ## 本地热重载启动
	uvicorn app.main:app --reload --host 0.0.0.0 --port $(PORT)

install:  ## 安装依赖
	pip install -r requirements.txt

## —— Docker ——

build:  ## 构建 Docker 镜像
	docker compose build

docker-up:  ## 启动所有 Docker 服务（后台）
	docker compose up -d

docker-down:  ## 停止并移除所有 Docker 服务
	docker compose down

docker-restart: docker-down docker-up  ## 重启 Docker 服务

docker-logs:  ## 查看 Docker 日志
	docker compose logs -f app

docker-shell:  ## 进入运行中的 app 容器
	docker exec -it fastapi-ai /bin/bash

docker-clean:  ## 清理 Docker 资源（停止 + 删卷）
	docker compose down -v
	docker system prune -f

## —— Database (Alembic) ——

alembic-init:  ## 初始化 Alembic 迁移仓库
	alembic init migrations

alembic-migrate:  ## 自动生成迁移脚本
	alembic revision --autogenerate -m "auto migration"

alembic-upgrade:  ## 升级数据库到最新版本
	alembic upgrade head

alembic-downgrade:  ## 回退一步
	alembic downgrade -1

## —— Quality ——

lint:  ## 代码检查
	ruff check app/

format:  ## 代码格式化
	ruff format app/

clean:  ## 清理缓存和临时文件
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytype" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf logs/*.log
	rm -rf uploads/*
	rm -rf tmp/ temp/

## —— Help ——

help:  ## 显示帮助信息
	@echo "========== $(APP_NAME) Makefile =========="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
