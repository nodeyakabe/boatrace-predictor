#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データ投入前のバリデーション

DB投入前にデータの整合性をチェックします。
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class DataValidator:
    """データバリデータークラス"""

    def __init__(self, db_path: Path):
        """
        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path

    def validate_date_format(self, date_str: str) -> Tuple[bool, str]:
        """
        日付形式の検証

        Args:
            date_str: 日付文字列

        Returns:
            (検証結果, 形式)
        """
        if not date_str:
            return False, "空の日付"

        # YYYY-MM-DD形式
        if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
                return True, "YYYY-MM-DD"
            except ValueError:
                return False, "不正なYYYY-MM-DD"

        # YYYYMMDD形式
        if len(date_str) == 8 and date_str.isdigit():
            try:
                datetime.strptime(date_str, '%Y%m%d')
                return True, "YYYYMMDD"
            except ValueError:
                return False, "不正なYYYYMMDD"

        return False, "未知の形式"

    def detect_date_format(self, races_data: List[Dict]) -> Dict[str, int]:
        """
        データ内の日付形式を検出

        Args:
            races_data: レースデータのリスト

        Returns:
            形式ごとのカウント
        """
        formats = {}

        for row in races_data:
            race_date = row.get('race_date', '')
            is_valid, format_type = self.validate_date_format(race_date)

            if is_valid:
                formats[format_type] = formats.get(format_type, 0) + 1
            else:
                formats[format_type] = formats.get(format_type, 0) + 1

        return formats

    def validate_race_data(self, races_data: List[Dict]) -> Dict[str, any]:
        """
        レースデータの包括的な検証

        Args:
            races_data: レースデータのリスト

        Returns:
            検証結果サマリー
        """
        if not races_data:
            return {
                'valid': False,
                'error': 'データが空です'
            }

        # 日付形式の検出
        date_formats = self.detect_date_format(races_data)

        # 日付範囲の取得
        dates = [row['race_date'] for row in races_data if row.get('race_date')]
        min_date = min(dates) if dates else None
        max_date = max(dates) if dates else None

        # 会場コードの取得
        venues = set(row['venue_code'] for row in races_data if row.get('venue_code'))

        # レース番号の範囲
        race_numbers = [int(row['race_number']) for row in races_data if row.get('race_number')]
        min_race = min(race_numbers) if race_numbers else None
        max_race = max(race_numbers) if race_numbers else None

        return {
            'valid': True,
            'record_count': len(races_data),
            'date_formats': date_formats,
            'date_range': {
                'min': min_date,
                'max': max_date
            },
            'venues': sorted(list(venues)),
            'venue_count': len(venues),
            'race_number_range': {
                'min': min_race,
                'max': max_race
            }
        }
