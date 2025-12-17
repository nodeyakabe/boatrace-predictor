# -*- coding: utf-8 -*-
"""
B-1: 会場別ROI分析スクリプト

目的:
- 2025年全期間で会場別ROIを集計
- 購入数、的中数、ROI、収支を計算
- トップ会場・ワースト会場をリスト化
- venue_filter.yaml の設定に使用するデータを生成
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


# 会場コードと名称のマッピング
VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}


@dataclass
class VenueROIStats:
    """会場別ROI統計"""
    venue_code: int
    venue_name: str
    purchase_count: int
    hit_count: int
    total_bet: int
    total_payout: float
    roi: float
    profit: float
    hit_rate: float


class VenueROIAnalyzer:
    """会場別ROI分析クラス"""

    def __init__(self, db_path: Path):
        """初期化"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def analyze(
        self,
        start_date: str = '2025-01-01',
        end_date: str = '2025-11-30',
        prediction_type: str = 'before',
        confidences: List[str] = ['C', 'D']
    ) -> Dict[int, VenueROIStats]:
        """
        会場別ROIを分析

        Args:
            start_date: 開始日
            end_date: 終了日
            prediction_type: 予測タイプ（'before' or 'advance'）
            confidences: 対象信頼度リスト

        Returns:
            会場コード -> VenueROIStats のマッピング
        """
        cursor = self.conn.cursor()

        # 対象レースを取得
        cursor.execute('''
            SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
            FROM races r
            WHERE r.race_date >= ? AND r.race_date <= ?
            ORDER BY r.race_date, r.venue_code, r.race_number
        ''', (start_date, end_date))
        races = cursor.fetchall()

        print(f"対象レース数: {len(races):,}件")
        print()

        # 会場別統計初期化
        venue_stats = defaultdict(lambda: {
            'purchase_count': 0,
            'hit_count': 0,
            'total_bet': 0,
            'total_payout': 0.0
        })

        for race in races:
            race_id = race['race_id']
            venue_code = int(race['venue_code']) if race['venue_code'] else 0

            if venue_code == 0:
                continue

            # 1コース級別を取得
            cursor.execute('''
                SELECT racer_rank FROM entries
                WHERE race_id = ? AND pit_number = 1
            ''', (race_id,))
            c1 = cursor.fetchone()
            c1_rank = c1['racer_rank'] if c1 else 'B1'

            # A1以外は除外
            if c1_rank != 'A1':
                continue

            # 予測情報を取得
            cursor.execute('''
                SELECT pit_number, confidence
                FROM race_predictions
                WHERE race_id = ? AND prediction_type = ?
                ORDER BY rank_prediction
            ''', (race_id, prediction_type))
            preds = cursor.fetchall()

            if len(preds) < 6:
                continue

            confidence = preds[0]['confidence']

            # 対象信頼度のみ
            if confidence not in confidences:
                continue

            top3 = [p['pit_number'] for p in preds[:3]]
            combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

            # オッズ取得
            cursor.execute('''
                SELECT combination, odds FROM trifecta_odds
                WHERE race_id = ? AND combination = ?
            ''', (race_id, combo))
            odds_row = cursor.fetchone()

            if not odds_row:
                continue

            odds = odds_row['odds']

            # オッズ範囲チェック（戦略Bの条件）
            bet_amount = 0
            if confidence == 'C':
                if 20 <= odds < 60:
                    bet_amount = 400 if odds < 40 else 500
            elif confidence == 'D':
                if 20 <= odds < 50:
                    bet_amount = 300

            if bet_amount == 0:
                continue

            # 購入対象
            venue_stats[venue_code]['purchase_count'] += 1
            venue_stats[venue_code]['total_bet'] += bet_amount

            # 実際の結果を取得
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results = cursor.fetchall()

            if len(results) >= 3:
                actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

                if combo == actual_combo:
                    # 的中
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        payout = (bet_amount / 100) * payout_row['amount']
                        venue_stats[venue_code]['hit_count'] += 1
                        venue_stats[venue_code]['total_payout'] += payout

        # 結果を整理
        result = {}
        for venue_code, stats in venue_stats.items():
            if stats['purchase_count'] > 0:
                roi = (stats['total_payout'] / stats['total_bet'] * 100) if stats['total_bet'] > 0 else 0
                profit = stats['total_payout'] - stats['total_bet']
                hit_rate = (stats['hit_count'] / stats['purchase_count'] * 100) if stats['purchase_count'] > 0 else 0

                result[venue_code] = VenueROIStats(
                    venue_code=venue_code,
                    venue_name=VENUE_NAMES.get(venue_code, f'会場{venue_code}'),
                    purchase_count=stats['purchase_count'],
                    hit_count=stats['hit_count'],
                    total_bet=stats['total_bet'],
                    total_payout=stats['total_payout'],
                    roi=roi,
                    profit=profit,
                    hit_rate=hit_rate
                )

        return result

    def generate_tier_recommendation(
        self,
        venue_stats: Dict[int, VenueROIStats],
        tier1_threshold: float = 200.0,
        tier3_threshold: float = 80.0,
        min_samples: int = 10
    ) -> Dict[str, List[int]]:
        """
        Tier分類の推奨を生成

        Args:
            venue_stats: 会場別統計
            tier1_threshold: Tier1（高ROI会場）のROI閾値
            tier3_threshold: Tier3（低ROI会場）のROI閾値
            min_samples: 最小サンプル数（これ未満は除外）

        Returns:
            {'tier1': [venue_codes], 'tier2': [venue_codes], 'tier3': [venue_codes]}
        """
        tier1 = []
        tier2 = []
        tier3 = []

        for venue_code, stats in venue_stats.items():
            # サンプル数が少ない会場は除外
            if stats.purchase_count < min_samples:
                continue

            if stats.roi >= tier1_threshold:
                tier1.append(venue_code)
            elif stats.roi < tier3_threshold:
                tier3.append(venue_code)
            else:
                tier2.append(venue_code)

        # ROIでソート
        tier1.sort(key=lambda x: venue_stats[x].roi, reverse=True)
        tier3.sort(key=lambda x: venue_stats[x].roi)

        return {'tier1': tier1, 'tier2': tier2, 'tier3': tier3}

    def close(self):
        """接続を閉じる"""
        self.conn.close()


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print("=" * 100)
    print("B-1: 会場別ROI分析")
    print("=" * 100)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("【分析条件】")
    print("  - 期間: 2025年1月〜11月")
    print("  - 予測タイプ: before（直前情報あり）")
    print("  - 対象信頼度: C, D")
    print("  - 1コース級別: A1のみ")
    print("  - オッズ範囲: 信頼度C(20-60倍), D(20-50倍)")
    print()
    print("=" * 100)

    analyzer = VenueROIAnalyzer(db_path)

    try:
        # 分析実行
        print("\n[分析実行中...]")
        venue_stats = analyzer.analyze(
            start_date='2025-01-01',
            end_date='2025-11-30',
            prediction_type='before',
            confidences=['C', 'D']
        )

        # 結果をROI順にソート
        sorted_venues = sorted(
            venue_stats.values(),
            key=lambda x: x.roi,
            reverse=True
        )

        # 全体サマリー
        total_purchase = sum(v.purchase_count for v in sorted_venues)
        total_hit = sum(v.hit_count for v in sorted_venues)
        total_bet = sum(v.total_bet for v in sorted_venues)
        total_payout = sum(v.total_payout for v in sorted_venues)
        overall_roi = (total_payout / total_bet * 100) if total_bet > 0 else 0
        overall_profit = total_payout - total_bet

        print(f"\n【全体サマリー】")
        print(f"  - 購入レース数: {total_purchase:,}件")
        print(f"  - 的中数: {total_hit:,}件（的中率 {total_hit/total_purchase*100:.2f}%）")
        print(f"  - 総賭け金: {total_bet:,.0f}円")
        print(f"  - 総払戻: {total_payout:,.0f}円")
        print(f"  - 総収支: {overall_profit:+,.0f}円")
        print(f"  - 全体ROI: {overall_roi:.1f}%")
        print()

        # 会場別詳細
        print("=" * 100)
        print("【会場別ROI（降順）】")
        print("=" * 100)
        print()

        print(f"{'順位':<4} {'会場':<8} {'購入':>8} {'的中':>6} {'的中率':>8} {'賭け金':>12} {'払戻':>12} {'収支':>12} {'ROI':>8}")
        print("-" * 100)

        for rank, stats in enumerate(sorted_venues, 1):
            print(f"{rank:>3}  {stats.venue_name:<8} {stats.purchase_count:>8,} {stats.hit_count:>6} "
                  f"{stats.hit_rate:>7.1f}% {stats.total_bet:>12,.0f} {stats.total_payout:>12,.0f} "
                  f"{stats.profit:>+12,.0f} {stats.roi:>7.1f}%")

        print()

        # Tier分類の推奨
        tiers = analyzer.generate_tier_recommendation(
            venue_stats,
            tier1_threshold=200.0,
            tier3_threshold=80.0,
            min_samples=10
        )

        print("=" * 100)
        print("【Tier分類推奨】")
        print("=" * 100)
        print()

        print("▼ Tier1（ROI 200%以上、購入量1.5倍推奨）:")
        for venue_code in tiers['tier1']:
            stats = venue_stats[venue_code]
            print(f"  - {stats.venue_code:2d}: {stats.venue_name} (ROI {stats.roi:.1f}%, {stats.purchase_count}件)")

        print()
        print("▼ Tier2（ROI 80-200%、通常購入）:")
        for venue_code in tiers['tier2']:
            stats = venue_stats[venue_code]
            print(f"  - {stats.venue_code:2d}: {stats.venue_name} (ROI {stats.roi:.1f}%, {stats.purchase_count}件)")

        print()
        print("▼ Tier3（ROI 80%未満、購入量0.5倍推奨）:")
        for venue_code in tiers['tier3']:
            stats = venue_stats[venue_code]
            print(f"  - {stats.venue_code:2d}: {stats.venue_name} (ROI {stats.roi:.1f}%, {stats.purchase_count}件)")

        print()

        # YAMLフォーマットで出力
        print("=" * 100)
        print("【venue_filter.yaml 推奨設定】")
        print("=" * 100)
        print()
        print("# config/venue_filter.yaml にコピー")
        print("venue_filter:")
        print("  enabled: true")
        print()
        print("  # Tier1: 購入量1.5倍（ROI 200%以上）")
        print("  tier1_venues:")
        for venue_code in tiers['tier1']:
            print(f"    - {venue_code}  # {VENUE_NAMES.get(venue_code, '')} (ROI {venue_stats[venue_code].roi:.1f}%)")
        print("  tier1_multiplier: 1.5")
        print()
        print("  # Tier2: 通常購入（ROI 80-200%）")
        print("  tier2_venues: []  # それ以外")
        print("  tier2_multiplier: 1.0")
        print()
        print("  # Tier3: 購入量0.5倍（ROI 80%未満）")
        print("  tier3_venues:")
        for venue_code in tiers['tier3']:
            print(f"    - {venue_code}  # {VENUE_NAMES.get(venue_code, '')} (ROI {venue_stats[venue_code].roi:.1f}%)")
        print("  tier3_multiplier: 0.5")

        # 期待効果の試算
        print()
        print("=" * 100)
        print("【期待効果の試算】")
        print("=" * 100)
        print()

        # 現状
        print("▼ 現状（フィルターなし）:")
        print(f"  - 総賭け金: {total_bet:,.0f}円")
        print(f"  - 総払戻: {total_payout:,.0f}円")
        print(f"  - 収支: {overall_profit:+,.0f}円")
        print(f"  - ROI: {overall_roi:.1f}%")
        print()

        # フィルター適用後の試算
        adjusted_bet = 0
        adjusted_payout = 0

        for stats in sorted_venues:
            if stats.venue_code in tiers['tier1']:
                multiplier = 1.5
            elif stats.venue_code in tiers['tier3']:
                multiplier = 0.5
            else:
                multiplier = 1.0

            adjusted_bet += stats.total_bet * multiplier
            adjusted_payout += stats.total_payout * multiplier

        adjusted_roi = (adjusted_payout / adjusted_bet * 100) if adjusted_bet > 0 else 0
        adjusted_profit = adjusted_payout - adjusted_bet

        print("▼ フィルター適用後（試算）:")
        print(f"  - 総賭け金: {adjusted_bet:,.0f}円")
        print(f"  - 総払戻: {adjusted_payout:,.0f}円")
        print(f"  - 収支: {adjusted_profit:+,.0f}円")
        print(f"  - ROI: {adjusted_roi:.1f}%")
        print()

        print("▼ 改善効果:")
        print(f"  - ROI改善: {adjusted_roi - overall_roi:+.1f}pt")
        print(f"  - 収支改善: {adjusted_profit - overall_profit:+,.0f}円")

    finally:
        analyzer.close()

    print()
    print("=" * 100)
    print("会場別ROI分析完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
