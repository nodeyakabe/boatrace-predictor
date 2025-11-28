#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
統合オリジナル展示データ収集器

優先順位:
1. Boatersサイトから収集を試行
2. 失敗した場合は各場の公式HPから収集
3. 両方失敗した場合はスキップ

これにより、データ収集率を大幅に向上させる
"""
import logging
from typing import Dict, Optional
from datetime import datetime

from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper
from src.scraper.venue_tenji_scraper import VenueTenjiScraper

logger = logging.getLogger(__name__)


class UnifiedTenjiCollector:
    """
    Boatersサイト + 各場公式HPの統合収集器

    フォールバック戦略:
    1次: Boaters (高速、一括対応)
    2次: 各場HP (遅い、個別対応)
    """

    def __init__(self, headless=True, timeout=15):
        """
        初期化

        Args:
            headless: ヘッドレスモードで実行するか
            timeout: ページ読み込みタイムアウト（秒）
        """
        self.boaters_scraper = OriginalTenjiBrowserScraper(headless=headless, timeout=timeout)
        self.venue_scraper = VenueTenjiScraper(headless=headless, timeout=timeout)

        self.stats = {
            'boaters_success': 0,
            'venue_success': 0,
            'total_attempts': 0,
            'failures': 0
        }

    def get_original_tenji(self, venue_code: str, target_date, race_number: int) -> Optional[Dict]:
        """
        オリジナル展示データを取得（フォールバック機能付き）

        Args:
            venue_code: 会場コード（例: "20"）
            target_date: 対象日（datetime or "YYYY-MM-DD"）
            race_number: レース番号（1-12）

        Returns:
            dict: {
                1: {'chikusen_time': 6.11, 'isshu_time': 36.85, 'mawariashi_time': 5.84},
                2: {'chikusen_time': 6.29, 'isshu_time': 38.29, 'mawariashi_time': 6.63},
                ...
                'source': 'boaters' or 'venue_hp'  # データソース情報
            }
            エラー時やデータなしの場合は None
        """
        self.stats['total_attempts'] += 1

        # 1次試行: Boatersサイト
        try:
            logger.debug(f"Trying Boaters for {venue_code} R{race_number} on {target_date}")
            tenji_data = self.boaters_scraper.get_original_tenji(venue_code, target_date, race_number)

            if tenji_data and self._validate_tenji_data(tenji_data):
                tenji_data['source'] = 'boaters'
                self.stats['boaters_success'] += 1
                logger.info(f"✓ Boaters: {venue_code} R{race_number}")
                return tenji_data
        except Exception as e:
            logger.warning(f"Boaters failed for {venue_code} R{race_number}: {e}")

        # 2次試行: 各場の公式HP
        try:
            logger.debug(f"Trying venue HP for {venue_code} R{race_number} on {target_date}")
            tenji_data = self.venue_scraper.get_original_tenji(venue_code, target_date, race_number)

            if tenji_data and self._validate_tenji_data(tenji_data):
                tenji_data['source'] = 'venue_hp'
                self.stats['venue_success'] += 1
                logger.info(f"✓ Venue HP: {venue_code} R{race_number}")
                return tenji_data
        except Exception as e:
            logger.warning(f"Venue HP failed for {venue_code} R{race_number}: {e}")

        # 両方失敗
        self.stats['failures'] += 1
        logger.warning(f"✗ Both sources failed: {venue_code} R{race_number}")
        return None

    def _validate_tenji_data(self, tenji_data: Dict) -> bool:
        """
        収集したデータが有効かチェック

        Args:
            tenji_data: 収集したデータ

        Returns:
            bool: 有効ならTrue
        """
        if not tenji_data:
            return False

        # 最低1艇分のデータがあること
        valid_boats = 0
        for boat_num in range(1, 7):
            if boat_num in tenji_data:
                boat_data = tenji_data[boat_num]

                # 少なくとも1つのタイムがあること
                if (boat_data.get('chikusen_time') or
                    boat_data.get('isshu_time') or
                    boat_data.get('mawariashi_time')):
                    valid_boats += 1

        return valid_boats > 0

    def get_stats(self) -> Dict:
        """収集統計を取得"""
        total = self.stats['total_attempts']
        success = self.stats['boaters_success'] + self.stats['venue_success']

        return {
            **self.stats,
            'success_rate': (success / total * 100) if total > 0 else 0,
            'boaters_rate': (self.stats['boaters_success'] / total * 100) if total > 0 else 0,
            'venue_rate': (self.stats['venue_success'] / total * 100) if total > 0 else 0,
        }

    def reset_stats(self):
        """統計をリセット"""
        self.stats = {
            'boaters_success': 0,
            'venue_success': 0,
            'total_attempts': 0,
            'failures': 0
        }

    def close(self):
        """リソースを解放"""
        self.boaters_scraper.close()
        self.venue_scraper.close()

    def __del__(self):
        """デストラクタ"""
        self.close()
