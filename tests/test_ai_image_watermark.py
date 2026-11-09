"""
============================================
AI Image Watermark Tests
============================================
Verify local transparent PNG overlays, image preservation, and failed-file cleanup.
"""

from io import BytesIO

import httpx
import pytest
from PIL import Image, ImageChops, ImageDraw

from app.common.exception import AppException
from app.core.config import settings
from app.storage import ai_image


def png_bytes(size=(1024, 768), color=(30, 90, 150)):
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def image_download(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "FILE_IMAGE_MAX_SIZE", 10 * 1024 * 1024)
    watermark_path = tmp_path / "watermark.png"
    mark = Image.new("RGBA", (400, 120), (0, 0, 0, 0))
    ImageDraw.Draw(mark).rectangle((10, 10, 390, 110), fill=(255, 0, 0, 128))
    mark.save(watermark_path)
    monkeypatch.setattr(settings, "AI_IMAGE_WATERMARK_PATH", str(watermark_path))
    original_client = httpx.AsyncClient
    content = [png_bytes()]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=content[0], headers={"Content-Type": "image/png"})

    monkeypatch.setattr(ai_image.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    return tmp_path, watermark_path, content, calls


@pytest.mark.parametrize("size", [(720, 1280), (1440, 720), (1024, 1024)])
async def test_enabled_watermark_preserves_image_and_blends_in_bottom_right(image_download, size):
    tmp_path, _, content, calls = image_download
    content[0] = png_bytes(size=size)
    path = await ai_image.save_generated_image("https://images.test/generated.png", "task", 1, watermark=True)
    with Image.open(tmp_path / "uploads" / path) as saved:
        assert saved.size == size
        assert saved.format == "PNG"
        assert saved.getpixel((0, 0))[:3] == (30, 90, 150)
        difference = ImageChops.difference(saved.convert("RGB"), Image.new("RGB", size, (30, 90, 150)))
        box = difference.getbbox()
        assert box is not None
        left, top, right, bottom = box
        assert left > size[0] * 0.7
        assert top > size[1] * 0.8
        assert right < size[0] and bottom < size[1]
        assert right - left <= round(size[0] * 0.25) + 1
        # 半透明红色与原图混合，没有被当作不透明色块覆盖。
        center = saved.getpixel(((left + right) // 2, (top + bottom) // 2))
        assert 30 < center[0] < 255
    assert "Authorization" not in calls[0].headers
    assert list((tmp_path / "uploads").rglob("*.tmp")) == []


async def test_disabled_watermark_preserves_original_bytes_and_needs_no_logo(image_download, monkeypatch):
    tmp_path, _, content, _ = image_download
    monkeypatch.setattr(settings, "AI_IMAGE_WATERMARK_PATH", str(tmp_path / "missing.png"))
    path = await ai_image.save_generated_image("https://images.test/generated.png", "task", 1, watermark=False)
    assert (tmp_path / "uploads" / path).read_bytes() == content[0]


@pytest.mark.parametrize("failure", ["missing_watermark", "corrupt_watermark", "corrupt_image"])
async def test_watermark_failures_do_not_publish_unmarked_images(image_download, failure):
    tmp_path, mark, content, _ = image_download
    if failure == "missing_watermark":
        mark.unlink()
    elif failure == "corrupt_watermark":
        mark.write_bytes(b"not a png")
    else:
        content[0] = b"not an image"
    with pytest.raises(AppException, match="水印"):
        await ai_image.save_generated_image("https://images.test/generated.png", "task", 1, watermark=True)
    assert list((tmp_path / "uploads").rglob("*.png")) == []
    assert list((tmp_path / "uploads").rglob("*.tmp")) == []


async def test_relative_watermark_path_is_resolved_from_project_root(image_download, tmp_path, monkeypatch):
    _, _, _, _ = image_download
    watermark = tmp_path / "public" / "watermark.png"
    watermark.parent.mkdir()
    Image.new("RGBA", (100, 30), (255, 255, 255, 128)).save(watermark)
    monkeypatch.setattr(ai_image, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(settings, "AI_IMAGE_WATERMARK_PATH", "public/watermark.png")
    monkeypatch.chdir(tmp_path / "public")
    path = await ai_image.save_generated_image("https://images.test/generated.png", "task", 1, watermark=True)
    assert (tmp_path / "uploads" / path).is_file()
