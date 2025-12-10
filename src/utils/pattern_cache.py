"""
パターン分析用キャッシュシステム

予測結果やBEFORE情報をキャッシュして高速化
"""

import functools
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import logging


class PatternCache:
    """パターン分析用キャッシュクラス"""

    def __init__(self, ttl_minutes: int = 15):
        """
        初期化

        Args:
            ttl_minutes: キャッシュの有効期限（分）
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.ttl_minutes = ttl_minutes
        self.logger = logging.getLogger(__name__)
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }

    def get(self, key: str) -> Optional[Any]:
        """
        キャッシュから値を取得

        Args:
            key: キャッシュキー

        Returns:
            キャッシュされた値、存在しない or 期限切れの場合はNone
        """
        if key not in self._cache:
            self.stats['misses'] += 1
            return None

        entry = self._cache[key]
        expires_at = entry['expires_at']

        # 期限切れチェック
        if datetime.now() > expires_at:
            del self._cache[key]
            self.stats['evictions'] += 1
            self.stats['misses'] += 1
            return None

        self.stats['hits'] += 1
        return entry['value']

    def set(self, key: str, value: Any) -> None:
        """
        キャッシュに値を設定

        Args:
            key: キャッシュキー
            value: 保存する値
        """
        expires_at = datetime.now() + timedelta(minutes=self.ttl_minutes)
        self._cache[key] = {
            'value': value,
            'expires_at': expires_at,
            'created_at': datetime.now()
        }

    def clear(self) -> None:
        """キャッシュをクリア"""
        self._cache.clear()
        self.logger.info("Cache cleared")

    def cleanup_expired(self) -> int:
        """
        期限切れエントリを削除

        Returns:
            削除したエントリ数
        """
        now = datetime.now()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry['expires_at']
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            self.stats['evictions'] += len(expired_keys)
            self.logger.debug(f"Cleaned up {len(expired_keys)} expired entries")

        return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """
        キャッシュ統計を取得

        Returns:
            {
                'size': int,
                'hits': int,
                'misses': int,
                'hit_rate': float,
                'evictions': int
            }
        """
        total = self.stats['hits'] + self.stats['misses']
        hit_rate = self.stats['hits'] / total if total > 0 else 0.0

        return {
            'size': len(self._cache),
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate': round(hit_rate, 3),
            'evictions': self.stats['evictions']
        }


def cached_prediction(ttl_minutes: int = 15):
    """
    予測結果をキャッシュするデコレーター

    Args:
        ttl_minutes: キャッシュの有効期限（分）

    Usage:
        @cached_prediction(ttl_minutes=15)
        def predict_race(self, race_id):
            ...
    """
    cache = PatternCache(ttl_minutes=ttl_minutes)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # キャッシュキー生成（race_idベース）
            if len(args) > 1:
                race_id = args[1]  # self, race_id の順
            elif 'race_id' in kwargs:
                race_id = kwargs['race_id']
            else:
                # race_idが取れない場合はキャッシュしない
                return func(*args, **kwargs)

            cache_key = f"race_{race_id}"

            # キャッシュチェック
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # キャッシュミス：実行して保存
            result = func(*args, **kwargs)
            cache.set(cache_key, result)

            return result

        # キャッシュ統計取得用
        wrapper.cache = cache
        return wrapper

    return decorator


class RaceDataCache:
    """レースデータ専用キャッシュ"""

    def __init__(self):
        self.before_info_cache = PatternCache(ttl_minutes=30)  # BEFORE情報
        self.prediction_cache = PatternCache(ttl_minutes=15)   # 予測結果
        self.pattern_match_cache = PatternCache(ttl_minutes=15)  # パターンマッチ結果

    def get_before_info(self, race_id: int) -> Optional[Any]:
        """BEFORE情報をキャッシュから取得"""
        return self.before_info_cache.get(f"before_{race_id}")

    def set_before_info(self, race_id: int, data: Any) -> None:
        """BEFORE情報をキャッシュに保存"""
        self.before_info_cache.set(f"before_{race_id}", data)

    def get_prediction(self, race_id: int) -> Optional[Any]:
        """予測結果をキャッシュから取得"""
        return self.prediction_cache.get(f"pred_{race_id}")

    def set_prediction(self, race_id: int, data: Any) -> None:
        """予測結果をキャッシュに保存"""
        self.prediction_cache.set(f"pred_{race_id}", data)

    def get_pattern_matches(self, race_id: int, pit_number: int) -> Optional[Any]:
        """パターンマッチ結果をキャッシュから取得"""
        return self.pattern_match_cache.get(f"pattern_{race_id}_{pit_number}")

    def set_pattern_matches(self, race_id: int, pit_number: int, data: Any) -> None:
        """パターンマッチ結果をキャッシュに保存"""
        self.pattern_match_cache.set(f"pattern_{race_id}_{pit_number}", data)

    def clear_all(self) -> None:
        """全キャッシュをクリア"""
        self.before_info_cache.clear()
        self.prediction_cache.clear()
        self.pattern_match_cache.clear()

    def cleanup_all(self) -> Dict[str, int]:
        """
        全キャッシュの期限切れエントリを削除

        Returns:
            削除したエントリ数の辞書
        """
        return {
            'before_info': self.before_info_cache.cleanup_expired(),
            'prediction': self.prediction_cache.cleanup_expired(),
            'pattern_match': self.pattern_match_cache.cleanup_expired()
        }

    def get_all_stats(self) -> Dict[str, Dict]:
        """全キャッシュの統計を取得"""
        return {
            'before_info': self.before_info_cache.get_stats(),
            'prediction': self.prediction_cache.get_stats(),
            'pattern_match': self.pattern_match_cache.get_stats()
        }
