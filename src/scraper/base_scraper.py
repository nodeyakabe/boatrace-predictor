"""
スクレイパー基底クラス (エイリアス)
互換性のためSafeScraperBaseを継承
"""

from .safe_scraper_base import SafeScraperBase


class BaseScraper(SafeScraperBase):
    """BaseScraper - SafeScraperBaseのエイリアス"""
    pass
