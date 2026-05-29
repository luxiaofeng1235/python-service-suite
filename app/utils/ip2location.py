"""
============================================
IP 地址解析工具类 — 基于 ipip.net .ipdb 数据库
============================================
封装了 IP 地址到地理位置的解析逻辑，业务层直接调用即可。

使用方式：
    from app.utils.ip2location import Ip2Location

    # 解析 IP 地址
    location = Ip2Location.parse("1.2.4.8")
    # 返回: {"province": "广东", "city": "广州", "full_name": "广东·广州"}

    # 获取城市名称
    city = Ip2Location.get_city_name("1.2.4.8")
    # 返回: "广州"

    # 获取省市完整名称
    full = Ip2Location.get_full_name("1.2.4.8")
    # 返回: "广东·广州"

说明：
    - 数据库文件位置: public/resource/ipv4_china.ipdb
    - 单例模式：只加载一次数据库，后续复用
    - 解析失败时返回空字符串，不会抛异常
    - 支持 ipip.net ipdb 格式的 IPv4 城市数据库
"""

import logging
from pathlib import Path

from ipdb import City

logger = logging.getLogger(__name__)

UNKNOWN_CITY_PLACEHOLDER = "未知城市"

# 数据库路径（项目根目录下 public/resource/ipv4_china.ipdb）
_DB_PATH = Path(__file__).resolve().parent.parent.parent / "public" / "resource" / "ipv4_china.ipdb"


class Ip2Location:
    """
    IP 地址解析工具类

    所有方法均为 classmethod，无需实例化，直接 Ip2Location.parse() 调用。

    Attributes:
        _reader: City 数据库读取器（单例，只初始化一次）
    """

    _reader: City | None = None

    # ==================== 初始化 ====================

    @classmethod
    def _ensure_reader(cls) -> City | None:
        """
        确保数据库读取器已初始化（单例懒加载）

        Returns:
            City 实例，初始化失败返回 None
        """
        if cls._reader is not None:
            return cls._reader

        db_path = _DB_PATH
        if not db_path.is_file():
            logger.warning(f"ipdb 数据库文件不存在: {db_path}")
            return None

        try:
            cls._reader = City(str(db_path))
            logger.info(f"✅ ipdb 数据库加载成功: {db_path}")
        except Exception as e:
            logger.error(f"ipdb 数据库初始化失败: {e}")
            cls._reader = None

        return cls._reader

    # ==================== 核心解析 ====================

    @classmethod
    def parse(cls, ip: str) -> dict:
        """
        解析 IP 地址，返回完整的地理位置信息

        Args:
            ip: IPv4 地址字符串（如 "1.2.4.8"）

        Returns:
            dict 包含以下字段:
                - country:   国家（如 "中国"）
                - province:  省份（如 "广东"）
                - city:      城市（如 "广州"）
                - district:  区县（可能为空）
                - isp:       运营商（如 "电信"）
                - full_name: 完整名称（如 "广东·广州"）
                - latitude:  纬度（字符串）
                - longitude: 经度（字符串）
            IP 为空或解析失败时所有字段为空字符串
        """
        result = {
            "country": "",
            "province": "",
            "city": "",
            "district": "",
            "isp": "",
            "full_name": "",
            "latitude": "",
            "longitude": "",
        }

        if not ip:
            return result

        reader = cls._ensure_reader()
        if reader is None:
            return result

        try:
            info = reader.find_map(ip, "CN")
        except Exception as e:
            logger.warning(f"IP 解析失败 ({ip}): {e}")
            return result

        if not info:
            return result

        # 提取字段
        country = info.get("country_name", "") or ""
        province = info.get("region_name", "") or ""
        city = info.get("city_name", "") or ""
        isp = info.get("isp_domain", "") or ""
        lat = info.get("latitude", "") or ""
        lng = info.get("longitude", "") or ""

        result.update(
            country=country,
            province=province,
            city=city,
            isp=isp,
            latitude=lat,
            longitude=lng,
        )

        # 构建 full_name
        result["full_name"] = cls._build_full_name(province, city)

        return result

    # ==================== 常用快捷方法 ====================

    @classmethod
    def get_city_name(cls, ip: str) -> str:
        """
        获取 IP 所在城市名称

        Args:
            ip: IPv4 地址

        Returns:
            城市名，如 "广州"；解析失败返回 "未知城市"
        """
        data = cls.parse(ip)
        return data["city"] or data["province"] or UNKNOWN_CITY_PLACEHOLDER

    @classmethod
    def get_province_name(cls, ip: str) -> str:
        """
        获取 IP 所在省份名称

        Args:
            ip: IPv4 地址

        Returns:
            省份名，如 "广东"；解析失败返回 "未知城市"
        """
        data = cls.parse(ip)
        return data["province"] or data["city"] or UNKNOWN_CITY_PLACEHOLDER

    @classmethod
    def get_full_name(cls, ip: str) -> str:
        """
        获取 IP 所在省市完整名称

        Args:
            ip: IPv4 地址

        Returns:
            完整名称，如 "广东·广州"；解析失败返回 "未知城市"
        """
        data = cls.parse(ip)
        return data["full_name"] or UNKNOWN_CITY_PLACEHOLDER

    @classmethod
    def get_country_name(cls, ip: str) -> str:
        """
        获取 IP 所在国家名称

        Args:
            ip: IPv4 地址

        Returns:
            国家名，如 "中国"；解析失败返回空字符串
        """
        data = cls.parse(ip)
        return data["country"]

    # ==================== 内部工具 ====================

    @staticmethod
    def _build_full_name(province: str, city: str) -> str:
        """
        构建 "省·市" 格式的完整名称

        Args:
            province: 省份名称
            city:     城市名称

        Returns:
            "省·市" 格式字符串
        """
        if province and city and province != city:
            return f"{province}·{city}"
        elif city:
            return city
        elif province:
            return province
        return ""
