# -*- coding: utf-8 -*-
"""
買い目ログ管理

購入記録の保存・読み込み・分析
"""

import os
import json
import csv
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class BetRecord:
    """買い目レコード"""
    date: str                    # 日付（YYYY-MM-DD）
    race_id: str                 # レースID
    venue_code: int              # 会場コード
    race_number: int             # レース番号
    bet_type: str                # 賭け式（trifecta/exacta）
    combination: str             # 買い目（例: "1-2-3"）
    odds: Optional[float]        # オッズ
    bet_amount: int              # 賭け金
    ev: float                    # 期待値
    edge: float                  # Edge
    confidence: str              # 信頼度
    method: str                  # 方式
    logic_version: str           # ロジックバージョン
    result: Optional[str]        # 結果（"hit"/"miss"/None）
    payout: Optional[int]        # 払戻金
    roi: Optional[float]         # ROI


class BetLogger:
    """
    買い目ログ管理

    保存項目:
    - 日付
    - レースID
    - 券種
    - 買い目
    - オッズ
    - 確率
    - EV
    - 結果
    - ROI
    """

    def __init__(self, log_dir: str = 'logs/betting'):
        """
        初期化

        Args:
            log_dir: ログディレクトリ
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def save_logs(self, records: List[BetRecord], date: str = None):
        """
        ログを保存

        Args:
            records: BetRecordのリスト
            date: 日付（ファイル名用）
        """
        if not records:
            return

        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        # JSON形式で保存
        json_path = self.log_dir / f'bets_{date}.json'
        data = [asdict(r) for r in records]

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # CSV形式でも保存（集計用）
        csv_path = self.log_dir / f'bets_{date}.csv'
        self._save_csv(records, csv_path)

    def _save_csv(self, records: List[BetRecord], path: Path):
        """CSV形式で保存"""
        if not records:
            return

        fieldnames = [
            'date', 'race_id', 'venue_code', 'race_number',
            'bet_type', 'combination', 'odds', 'bet_amount',
            'ev', 'edge', 'confidence', 'method', 'logic_version',
            'result', 'payout', 'roi'
        ]

        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                writer.writerow(asdict(r))

    def load_logs(self, date: str) -> List[BetRecord]:
        """
        ログを読み込み

        Args:
            date: 日付（YYYY-MM-DD）

        Returns:
            BetRecordのリスト
        """
        json_path = self.log_dir / f'bets_{date}.json'

        if not json_path.exists():
            return []

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return [BetRecord(**d) for d in data]

    def load_logs_range(
        self,
        start_date: str,
        end_date: str
    ) -> List[BetRecord]:
        """
        期間指定でログを読み込み

        Args:
            start_date: 開始日
            end_date: 終了日

        Returns:
            BetRecordのリスト
        """
        records = []

        for json_file in self.log_dir.glob('bets_*.json'):
            date_str = json_file.stem.replace('bets_', '')
            if start_date <= date_str <= end_date:
                records.extend(self.load_logs(date_str))

        # 日付順にソート
        records.sort(key=lambda r: (r.date, r.race_id))

        return records

    def update_result(
        self,
        date: str,
        race_id: str,
        result: str,
        payout: int = 0
    ):
        """
        結果を更新

        Args:
            date: 日付
            race_id: レースID
            result: 結果（"hit"/"miss"）
            payout: 払戻金
        """
        records = self.load_logs(date)

        for r in records:
            if r.race_id == race_id:
                r.result = result
                r.payout = payout
                r.roi = (payout / r.bet_amount * 100) if r.bet_amount > 0 else 0

        self.save_logs(records, date)

    def get_summary(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        期間サマリーを取得

        Args:
            start_date: 開始日
            end_date: 終了日

        Returns:
            サマリー情報
        """
        records = self.load_logs_range(start_date, end_date)

        if not records:
            return {
                'period': f'{start_date} ~ {end_date}',
                'total_bets': 0,
                'total_hits': 0,
                'hit_rate': 0,
                'total_invested': 0,
                'total_payout': 0,
                'profit': 0,
                'roi': 0,
            }

        total_bets = len(records)
        total_hits = sum(1 for r in records if r.result == 'hit')
        total_invested = sum(r.bet_amount for r in records)
        total_payout = sum(r.payout or 0 for r in records)

        return {
            'period': f'{start_date} ~ {end_date}',
            'total_bets': total_bets,
            'total_hits': total_hits,
            'hit_rate': total_hits / total_bets * 100 if total_bets > 0 else 0,
            'total_invested': total_invested,
            'total_payout': total_payout,
            'profit': total_payout - total_invested,
            'roi': total_payout / total_invested * 100 if total_invested > 0 else 0,
        }

    def get_summary_by_confidence(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        信頼度別サマリーを取得

        Args:
            start_date: 開始日
            end_date: 終了日

        Returns:
            信頼度別のサマリー
        """
        records = self.load_logs_range(start_date, end_date)

        summary = {}

        for r in records:
            conf = r.confidence
            if conf not in summary:
                summary[conf] = {
                    'bets': 0,
                    'hits': 0,
                    'invested': 0,
                    'payout': 0,
                }

            summary[conf]['bets'] += 1
            if r.result == 'hit':
                summary[conf]['hits'] += 1
            summary[conf]['invested'] += r.bet_amount
            summary[conf]['payout'] += r.payout or 0

        # ROI計算
        for conf in summary:
            s = summary[conf]
            s['hit_rate'] = s['hits'] / s['bets'] * 100 if s['bets'] > 0 else 0
            s['profit'] = s['payout'] - s['invested']
            s['roi'] = s['payout'] / s['invested'] * 100 if s['invested'] > 0 else 0

        return summary

    def get_summary_by_version(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        ロジックバージョン別サマリーを取得

        Args:
            start_date: 開始日
            end_date: 終了日

        Returns:
            バージョン別のサマリー
        """
        records = self.load_logs_range(start_date, end_date)

        summary = {}

        for r in records:
            ver = r.logic_version
            if ver not in summary:
                summary[ver] = {
                    'bets': 0,
                    'hits': 0,
                    'invested': 0,
                    'payout': 0,
                }

            summary[ver]['bets'] += 1
            if r.result == 'hit':
                summary[ver]['hits'] += 1
            summary[ver]['invested'] += r.bet_amount
            summary[ver]['payout'] += r.payout or 0

        # ROI計算
        for ver in summary:
            s = summary[ver]
            s['hit_rate'] = s['hits'] / s['bets'] * 100 if s['bets'] > 0 else 0
            s['profit'] = s['payout'] - s['invested']
            s['roi'] = s['payout'] / s['invested'] * 100 if s['invested'] > 0 else 0

        return summary

    def export_to_dataframe(
        self,
        start_date: str,
        end_date: str
    ):
        """
        DataFrameにエクスポート

        Args:
            start_date: 開始日
            end_date: 終了日

        Returns:
            pandas.DataFrame
        """
        try:
            import pandas as pd
            records = self.load_logs_range(start_date, end_date)
            return pd.DataFrame([asdict(r) for r in records])
        except ImportError:
            raise ImportError("pandas is required for export_to_dataframe")


def write_log(bets: List[Dict[str, Any]], log_dir: str = 'logs/betting'):
    """
    シンプルなログ書き込み関数

    Args:
        bets: 買い目情報のリスト
        log_dir: ログディレクトリ
    """
    logger = BetLogger(log_dir=log_dir)
    date = datetime.now().strftime('%Y-%m-%d')

    records = []
    for bet in bets:
        records.append(BetRecord(
            date=date,
            race_id=bet.get('race_id', ''),
            venue_code=bet.get('venue_code', 0),
            race_number=bet.get('race_number', 0),
            bet_type=bet.get('bet_type', 'trifecta'),
            combination=bet.get('combination', ''),
            odds=bet.get('odds'),
            bet_amount=bet.get('bet_amount', 100),
            ev=bet.get('ev', 0),
            edge=bet.get('edge', 0),
            confidence=bet.get('confidence', ''),
            method=bet.get('method', ''),
            logic_version=bet.get('logic_version', 'v1.0'),
            result=bet.get('result'),
            payout=bet.get('payout'),
            roi=bet.get('roi'),
        ))

    logger.save_logs(records, date)
