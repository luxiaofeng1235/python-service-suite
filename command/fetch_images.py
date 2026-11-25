"""
百度图片抓取 + OSS 转存 + 入库 + 更新索引
四步走：
  1. Playwright 抓取百度图片直链
  2. 通过 /api/file/upload/oss 转存到 OSS
  3. 更新数据库
  4. 更新向量索引（让新图片在语义搜索中生效）
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import httpx
from playwright.async_api import async_playwright

# ─── 配置 ───
API_BASE = "http://127.0.0.1:8001"
BAIDU_SEARCH_URL = "https://image.baidu.com/search/index?tn=baiduimage&word={keyword}"


def find_chrome_path() -> str | None:
    """自动查找可用的 Chrome/Chromium 路径"""
    cache_dirs = [
        Path.home() / ".cache" / "ms-playwright",
        Path("/ms-playwright"),
    ]
    for cache_dir in cache_dirs:
        if not cache_dir.exists():
            continue
        chromium_dirs = sorted(
            cache_dir.glob("chromium-*"),
            key=lambda p: p.name,
            reverse=True,
        )
        for chromium_dir in chromium_dirs:
            candidates = [
                chromium_dir / "chrome-linux64" / "chrome",
                chromium_dir / "chrome-linux" / "chrome",
            ]
            for chrome_path in candidates:
                if chrome_path.exists():
                    return str(chrome_path)
    return None


CHROME_PATH = find_chrome_path()

# 允许的直链域名（百度 CDN）
ALLOWED_DOMAINS = [
    "bdstatic.com",
    "bcebos.com",
    "baidu.com/it/u=",  # 百度用户头像 CDN
]

# 拒绝的域名/模式
REJECT_PATTERNS = [
    "gimg2.baidu.com/image_search",  # 代理 URL，OSS 不认
    "baidu.com/link",                # 跳转链接
    "@",                             # 含 @ 的 URL 不规范
]

# 允许的图片后缀
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def is_valid_image_url(url: str) -> bool:
    """校验图片 URL 是否合规"""
    if not url or len(url) > 2000:
        return False

    # 拒绝含 @ 的 URL
    if "@" in url:
        return False

    # 拒绝匹配拒绝模式
    for pattern in REJECT_PATTERNS:
        if pattern in url:
            return False

    # 检查是否是允许的域名
    domain_ok = any(d in url for d in ALLOWED_DOMAINS)
    if not domain_ok:
        return False

    # 尝试从 URL 中提取后缀
    # 百度 URL 可能是编码的，先解码
    decoded = unquote(url)
    # 检查是否有图片后缀
    has_ext = any(decoded.lower().split("?")[0].endswith(ext) for ext in IMAGE_EXTENSIONS)
    if not has_ext:
        # 没有明确后缀的也放行，只要是百度 CDN 域名
        pass

    return True


async def scrape_baidu_image(keyword: str) -> str | None:
    """用 Playwright 从百度图片搜索抓取一张合规的直链 URL"""
    if CHROME_PATH is None:
        print("  ❌ 未找到可用的 Chrome/Chromium，请运行: playwright install chromium")
        return None
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        page = await browser.new_page()

        try:
            url = BAIDU_SEARCH_URL.format(keyword=keyword)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            # 提取所有图片的 data-objurl（原始大图 URL）
            candidates = await page.evaluate("""
                () => {
                    const imgs = document.querySelectorAll('img.main_img.img-hover');
                    const urls = [];
                    imgs.forEach(img => {
                        const objUrl = img.getAttribute('data-objurl');
                        if (objUrl) urls.push(objUrl);
                    });
                    // 如果没找到 hover 的，取所有 data-objurl
                    if (urls.length === 0) {
                        document.querySelectorAll('img[data-objurl]').forEach(img => {
                            urls.push(img.getAttribute('data-objurl'));
                        });
                    }
                    return urls;
                }
            """)

            # 过滤合规 URL
            for candidate in candidates:
                if is_valid_image_url(candidate):
                    return candidate

            print(f"  ⚠️  {keyword}: 抓取到 {len(candidates)} 个 URL 但都不合规")
            return None

        except Exception as e:
            print(f"  ❌ {keyword}: 抓取异常 - {e}")
            return None
        finally:
            await browser.close()


async def upload_to_oss(image_url: str) -> str | None:
    """通过 /api/file/upload/oss 接口转存到 OSS，返回 OSS URL"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API_BASE}/api/file/upload/oss",
            data={"upload_type": "url", "url": image_url},
        )
        result = resp.json()
        if result.get("code") == 1:
            return result["data"]["url"]
        else:
            print(f"  ⚠️  OSS 上传失败: {result.get('msg')}")
            return None


async def process_brands():
    """Step 1+2+3: 品牌图片抓取 → OSS → 入库（品牌图片不在向量索引中，无需更新索引）"""
    from sqlalchemy import text
    from app.database import async_session

    async with async_session() as db:
        result = await db.execute(text(
            "SELECT id, name FROM goods_brands WHERE image = '' ORDER BY id"
        ))
        brands = result.fetchall()

    if not brands:
        print("✅ 品牌图片已全部补全，无需处理")
        return []

    print(f"\n{'='*50}")
    print(f"📦 品牌图片补全: {len(brands)} 个")
    print(f"{'='*50}")

    success = 0
    for brand_id, name in brands:
        print(f"\n[{brand_id}] {name}")

        # Step 1: 抓取
        keyword = f"{name} 品牌标志"
        raw_url = await scrape_baidu_image(keyword)
        if not raw_url:
            # 换个关键词重试
            keyword = f"{name} logo"
            raw_url = await scrape_baidu_image(keyword)
        if not raw_url:
            print(f"  ❌ 未抓取到合规图片")
            continue
        print(f"  ✅ 抓取: {raw_url[:80]}...")

        # Step 2: OSS 转存
        oss_url = await upload_to_oss(raw_url)
        if not oss_url:
            print(f"  ❌ OSS 转存失败")
            continue
        print(f"  ✅ OSS: {oss_url}")

        # Step 3: 入库
        async with async_session() as db:
            await db.execute(text(
                "UPDATE goods_brands SET image = :url WHERE id = :id"
            ), {"url": oss_url, "id": brand_id})
            await db.commit()
        print(f"  ✅ 入库成功")
        success += 1

    print(f"\n📦 品牌完成: {success}/{len(brands)} 成功")
    return []  # 品牌图片不在向量索引中，无需更新索引


async def process_products():
    """Step 1+2+3+4: 商品图片抓取 → OSS → 入库 → 更新索引"""
    from sqlalchemy import text
    from app.database import async_session

    async with async_session() as db:
        result = await db.execute(text(
            "SELECT id, name FROM goods_products WHERE cover_image IS NULL OR cover_image = '' ORDER BY id"
        ))
        products = result.fetchall()

    if not products:
        print("✅ 商品图片已全部补全，无需处理")
        return []

    print(f"\n{'='*50}")
    print(f"📦 商品图片补全: {len(products)} 个")
    print(f"{'='*50}")

    success = 0
    updated_product_ids: list[int] = []
    for product_id, name in products:
        print(f"\n[{product_id}] {name}")

        # Step 1: 抓取
        keyword = name
        raw_url = await scrape_baidu_image(keyword)
        if not raw_url:
            # 去掉型号等后缀再试
            short_name = name.split()[0]
            keyword = f"{short_name} 产品图"
            raw_url = await scrape_baidu_image(keyword)
        if not raw_url:
            print(f"  ❌ 未抓取到合规图片")
            continue
        print(f"  ✅ 抓取: {raw_url[:80]}...")

        # Step 2: OSS 转存
        oss_url = await upload_to_oss(raw_url)
        if not oss_url:
            print(f"  ❌ OSS 转存失败")
            continue
        print(f"  ✅ OSS: {oss_url}")

        # Step 3: 入库
        async with async_session() as db:
            await db.execute(text(
                "UPDATE goods_products SET cover_image = :url WHERE id = :id"
            ), {"url": oss_url, "id": product_id})
            await db.commit()
        print(f"  ✅ 入库成功")
        success += 1
        updated_product_ids.append(product_id)

    print(f"\n📦 商品完成: {success}/{len(products)} 成功")
    return updated_product_ids


async def refresh_index(product_ids: list[int]):
    """Step 4: 更新向量索引，让新图片的商品在语义搜索中生效"""
    if not product_ids:
        print("\n📦 无需更新索引（没有商品图片变更）")
        return

    print(f"\n{'='*50}")
    print(f"📦 更新向量索引: {len(product_ids)} 个商品")
    print(f"{'='*50}")

    from app.services.agent.goods_service import GoodsService

    service = GoodsService()
    try:
        await service.refresh_index(product_ids)
        print(f"✅ 索引更新完成，{len(product_ids)} 个商品已同步")
    except Exception as e:
        print(f"❌ 索引更新失败: {e}")
    finally:
        await service.vector_service.aclose()


async def main():
    print("🚀 图片补全脚本启动")
    print(f"   API: {API_BASE}")
    print(f"   Chrome: {CHROME_PATH}")

    await process_brands()  # 品牌图片不在向量索引中
    updated_ids = await process_products()

    # Step 4: 更新向量索引（只更新商品图片变更的）
    await refresh_index(updated_ids)

    print(f"\n{'='*50}")
    print("🎉 全部完成!")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
