# -*- coding: utf-8 -*-
"""
B-1: 会場フィルター効果検証バックテスト

目的:
- 会場フィルターあり/なしでバックテスト
- ROI改善効果を測定
- 統計的有意性を確認（p<0.05）
"""

import sys
import sqlite3
import yaml
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from scipy import stats

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
class BacktestResult:
    """バックテスト結果"""
    name: str
    purchase_count: int
    hit_count: int
    total_bet: int
    total_payout: float
    roi: float
    profit: float
    hit_rate: float
    rois_per_race: List[float]


class VenueFilterBacktester:
    """会場フィルターバックテストクラス"""

    def __init__(self, db_path: Path, config_path: Optional[Path] = None):
        """初期化"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        # 設定読み込み
        if config_path and config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        else:
            # デフォルト設定
            self.config = {
                'venue_filter': {
                    'enabled': True,
                    'tier1_venues': [14, 15, 7],  # 鳴門, 丸亀, 蒲郡
                    'tier1_multiplier': 1.5,
                    'tier2_venues': [],
                    'tier2_multiplier': 1.0,
                    'tier3_venues': [],
                    'tier3_multiplier': 0.5,
                    'min_bet_amount': 100,
                    'max_bet_amount': 2000,
                }
            }

    def _get_multiplier(self, venue_code: int) -> float:
        """会場の購入倍率を取得"""
        filter_config = self.config.get('venue_filter', {})

        if venue_code in filter_config.get('tier1_venues', []):
            return filter_config.get('tier1_multiplier', 1.5)
        elif venue_code in filter_config.get('tier3_venues', []):
            return filter_config.get('tier3_multiplier', 0.5)
        else:
            return filter_config.get('tier2_multiplier', 1.0)

    def _apply_multiplier(self, bet_amount: int, multiplier: float) -> int:
        """購入金額に倍率を適用"""
        filter_config = self.config.get('venue_filter', {})
        min_bet = filter_config.get('min_bet_amount', 100)
        max_bet = filter_config.get('max_bet_amount', 2000)

        adjusted = int(bet_amount * multiplier)
        # 100円単位に丸める
        adjusted = (adjusted // 100) * 100
        # 上下限適用
        adjusted = max(min_bet, min(max_bet, adjusted))

        return adjusted

    def run_backtest(
        self,
        start_date: str = '2025-01-01',
        end_date: str = '2025-11-30',
        use_filter: bool = True,
        prediction_type: str = 'before',
        confidences: List[str] = ['C', 'D']
    ) -> BacktestResult:
        """
        バックテスト実行

        Args:
            start_date: 開始日
            end_date: 終了日
            use_filter: フィルター使用フラグ
            prediction_type: 予測タイプ
            confidences: 対象信頼度

        Returns:
            BacktestResult
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

        stats = {
            'purchase_count': 0,
            'hit_count': 0,
            'total_bet': 0,
            'total_payout': 0.0,
            'rois_per_race': []
        }

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
            base_bet_amount = 0
            if confidence == 'C':
                if 20 <= odds < 60:
                    base_bet_amount = 400 if odds < 40 else 500
            elif confidence == 'D':
                if 20 <= odds < 50:
                    base_bet_amount = 300

            if base_bet_amount == 0:
                continue

            # フィルター適用
            if use_filter:
                multiplier = self._get_multiplier(venue_code)
                bet_amount = self._apply_multiplier(base_bet_amount, multiplier)
            else:
                bet_amount = base_bet_amount

            # 購入対象
            stats['purchase_count'] += 1
            stats['total_bet'] += bet_amount

            # 実際の結果を取得
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results = cursor.fetchall()

            race_roi = 0.0
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
                        stats['hit_count'] += 1
                        stats['total_payout'] += payout
                        race_roi = payout / bet_amount if bet_amount > 0 else 0

            stats['rois_per_race'].append(race_roi)

        # 結果を整理
        roi = (stats['total_payout'] / stats['total_bet'] * 100) if stats['total_bet'] > 0 else 0
        profit = stats['total_payout'] - stats['total_bet']
        hit_rate = (stats['hit_count'] / stats['purchase_count'] * 100) if stats['purchase_count'] > 0 else 0

        return BacktestResult(
            name='フィルターあり' if use_filter else 'フィルターなし',
            purchase_count=stats['purchase_count'],
            hit_count=stats['hit_count'],
            total_bet=stats['total_bet'],
            total_payout=stats['total_payout'],
            roi=roi,
            profit=profit,
            hit_rate=hit_rate,
            rois_per_race=stats['rois_per_race']
        )

    def statistical_test(
        self,
        baseline: BacktestResult,
        treatment: BacktestResult
    ) -> Dict[str, float]:
        """
        統計的有意性検定（t検定）

        Args:
            baseline: ベースライン結果
            treatment: 処理後結果

        Returns:
            検定結果
        """
        baseline_rois = baseline.rois_per_race
        treatment_rois = treatment.rois_per_race

        if len(baseline_rois) < 30 or len(treatment_rois) < 30:
            return {
                't_statistic': np.nan,
                'p_value': np.nan,
                'is_significant': False,
                'note': 'サンプルサイズ不足（30件未満）'
            }

        # Welchのt検定
        t_stat, p_value = stats.ttest_ind(treatment_rois, baseline_rois, equal_var=False)

        return {
            't_statistic': t_stat,
            'p_value': p_value,
            'is_significant': p_value < 0.05,
            'note': '有意' if p_value < 0.05 else '有意差なし'
        }

    def close(self):
        """接続を閉じる"""
        self.conn.close()


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"
    config_path = ROOT_DIR / "config" / "venue_filter.yaml"

    print("=" * 100)
    print("B-1: 会場フィルター効果検証バックテスト")
    print("=" * 100)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("【バックテスト条件】")
    print("  - 期間: 2025年1月〜11月")
    print("  - 予測タイプ: before（直前情報あり）")
    print("  - 対象信頼度: C, D")
    print("  - 1コース級別: A1のみ")
    print()

    # 設定読み込み
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            filter_config = config.get('venue_filter', {})
        print("【会場フィルター設定】")
        print(f"  - Tier1会場: {filter_config.get('tier1_venues', [])}")
        print(f"  - Tier1倍率: {filter_config.get('tier1_multiplier', 1.5)}倍")
        print(f"  - Tier3会場: {filter_config.get('tier3_venues', [])}")
        print(f"  - Tier3倍率: {filter_config.get('tier3_multiplier', 0.5)}倍")
    else:
        print("【会場フィルター設定】デフォルト設定を使用")
    print()
    print("=" * 100)

    backtester = VenueFilterBacktester(db_path, config_path)

    try:
        # フィルターなしでバックテスト
        print("\n[バックテスト実行中: フィルターなし...]")
        baseline = backtester.run_backtest(
            start_date='2025-01-01',
            end_date='2025-11-30',
            use_filter=False
        )

        # フィルターありでバックテスト
        print("[バックテスト実行中: フィルターあり...]")
        treatment = backtester.run_backtest(
            start_date='2025-01-01',
            end_date='2025-11-30',
            use_filter=True
        )

        # 結果表示
        print("\n" + "=" * 100)
        print("【バックテスト結果】")
        print("=" * 100)
        print()

        print(f"{'パターン':<20} {'購入数':>10} {'的中':>8} {'的中率':>8} {'賭け金':>12} {'払戻':>12} {'収支':>12} {'ROI':>8}")
        print("-" * 100)

        for result in [baseline, treatment]:
            print(f"{result.name:<20} {result.purchase_count:>10,} {result.hit_count:>8} "
                  f"{result.hit_rate:>7.2f}% {result.total_bet:>12,.0f} {result.total_payout:>12,.0f} "
                  f"{result.profit:>+12,.0f} {result.roi:>7.1f}%")

        print()

        # 改善効果
        print("=" * 100)
        print("【改善効果】")
        print("=" * 100)
        print()

        roi_diff = treatment.roi - baseline.roi
        profit_diff = treatment.profit - baseline.profit
        bet_diff = treatment.total_bet - baseline.total_bet

        print(f"  - ROI改善: {roi_diff:+.1f}pt ({baseline.roi:.1f}% → {treatment.roi:.1f}%)")
        print(f"  - 収支改善: {profit_diff:+,.0f}円 ({baseline.profit:+,.0f}円 → {treatment.profit:+,.0f}円)")
        print(f"  - 賭け金変化: {bet_diff:+,.0f}円 ({baseline.total_bet:,.0f}円 → {treatment.total_bet:,.0f}円)")
        print()

        # 統計的検定
        print("=" * 100)
        print("【統計的有意性検定】")
        print("=" * 100)
        print()

        test_result = backtester.statistical_test(baseline, treatment)

        print(f"  - ベースライン平均ROI: {np.mean(baseline.rois_per_race) * 100:.2f}%")
        print(f"  - フィルター適用平均ROI: {np.mean(treatment.rois_per_race) * 100:.2f}%")
        print(f"  - t値: {test_result['t_statistic']:.4f}")
        print(f"  - p値: {test_result['p_value']:.6f}")
        print(f"  - 判定: {test_result['note']}")
        print()

        if test_result['is_significant']:
            if treatment.roi > baseline.roi:
                print("★★★ 会場フィルターは統計的に有意にROIを改善しています ★★★")
            else:
                print("★ 会場フィルターは統計的に有意にROIを悪化させています")
        else:
            print("△ 会場フィルターの効果は統計的に有意ではありません（追加検証推奨）")

        # 推奨事項
        print()
        print("=" * 100)
        print("【推奨事項】")
        print("=" * 100)
        print()

        if roi_diff > 0 and test_result['is_significant']:
            print("  ✅ 会場フィルターの採用を推奨")
            print(f"     期待年間収支改善: {profit_diff:+,.0f}円")
        elif roi_diff > 0 and not test_result['is_significant']:
            print("  △ 会場フィルターは改善傾向だが、サンプル追加後に再検証を推奨")
            print("     より長期間のデータでの検証が必要")
        elif roi_diff <= 0:
            print("  ❌ 会場フィルターは効果なし（または悪化）")
            print("     Tier分類の見直しを推奨")

        print()
        print("【注意事項】")
        print("  - 現行ROI 167%を下回らないことを確認してください")
        print("  - データセットの一貫性: prediction_type='before', 信頼度C/D")

    finally:
        backtester.close()

    print()
    print("=" * 100)
    print("バックテスト完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
