# -*- coding: utf-8 -*-
"""
オッズ逆算による2着・3着予測精度改善バックテスト

アプローチ4: 3連単オッズから市場の2着・3着予測確率を逆算し、
機械学習予測と統合して精度改善を測定する。

テスト内容:
1. baseline: 現行システム（オッズ統合なし）
2. alpha=0.1: 市場確率10%統合
3. alpha=0.2: 市場確率20%統合
4. alpha=0.3: 市場確率30%統合

評価指標:
- ROI
- 的中率（3連単）
- 2着的中率
- 3着的中率
- 購入数

期間: 2025-11-28 ~ 2025-12-10（オッズデータ取得済み期間）
"""
import sys
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

# プロジェクトルートをパスに追加
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.race_predictor import RacePredictor
from src.analysis.scorers.odds_calibrator import OddsCalibrator
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OddsIntegrationBacktester:
    """オッズ統合バックテスター"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.predictor = RacePredictor(db_path)
        self.evaluator = BetTargetEvaluator()

    def get_test_races(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """
        テスト対象レースを取得

        オッズデータが存在し、結果データもあるレースのみ
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT
                r.id as race_id,
                r.venue_code,
                r.race_date,
                r.race_number
            FROM races r
            INNER JOIN trifecta_odds o ON r.id = o.race_id
            INNER JOIN results res ON r.id = res.race_id
            WHERE r.race_date BETWEEN ? AND ?
            AND res.is_invalid = 0
            ORDER BY r.race_date, r.venue_code, r.race_number
        """, (start_date, end_date))

        races = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return races

    def get_actual_result(self, race_id: int) -> Optional[Dict]:
        """実際のレース結果を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ?
            AND is_invalid = 0
            AND rank IN ('1', '2', '3')
            ORDER BY rank
        """, (race_id,))

        rows = cursor.fetchall()
        conn.close()

        if len(rows) < 3:
            return None

        return {
            'rank1': rows[0]['pit_number'],
            'rank2': rows[1]['pit_number'],
            'rank3': rows[2]['pit_number']
        }

    def get_payout(self, race_id: int, combination: str) -> Optional[float]:
        """払戻金を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT amount
            FROM payouts
            WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
        """, (race_id, combination))

        row = cursor.fetchone()
        conn.close()

        return row['amount'] if row else None

    def get_odds(self, race_id: int, combination: str) -> Optional[float]:
        """オッズを取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        """, (race_id, combination))

        row = cursor.fetchone()
        conn.close()

        return row['odds'] if row else None

    def get_c1_rank(self, race_id: int) -> str:
        """1コースの級別を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT racer_rank
            FROM entries
            WHERE race_id = ? AND pit_number = 1
        """, (race_id,))

        row = cursor.fetchone()
        conn.close()

        return row['racer_rank'] if row else 'B1'

    def run_single_race(
        self,
        race_id: int,
        alpha: float,
        odds_calibrator: OddsCalibrator = None
    ) -> Dict:
        """
        1レースのバックテスト実行

        Args:
            race_id: レースID
            alpha: オッズ統合係数（0でbaseline）
            odds_calibrator: オッズキャリブレーター

        Returns:
            結果辞書
        """
        result = {
            'race_id': race_id,
            'alpha': alpha,
            'purchased': False,
            'hit': False,
            'bet_amount': 0,
            'payout': 0,
            'combination': None,
            'actual_combination': None,
            'rank1_correct': False,
            'rank2_correct': False,
            'rank3_correct': False,
            'confidence': None
        }

        # 予測を取得
        try:
            predictions = self.predictor.predict_race(race_id)
        except Exception as e:
            logger.debug(f"Race {race_id}: 予測エラー - {e}")
            return result

        if not predictions or len(predictions) < 6:
            return result

        # オッズ統合を適用（alpha > 0の場合）
        if alpha > 0 and odds_calibrator:
            predictions = odds_calibrator.calibrate_rank23_predictions(
                predictions, race_id, alpha=alpha
            )

        # 信頼度を取得
        confidence = predictions[0].get('confidence', 'E')
        result['confidence'] = confidence

        # 信頼度A/Bは購入対象外
        if confidence in ['A', 'B']:
            return result

        # 予測TOP3
        predicted_top3 = [p['pit_number'] for p in predictions[:3]]
        combination = f"{predicted_top3[0]}-{predicted_top3[1]}-{predicted_top3[2]}"
        result['combination'] = combination

        # オッズを取得
        odds = self.get_odds(race_id, combination)
        if not odds:
            return result

        # 1コース級別
        c1_rank = self.get_c1_rank(race_id)
        venue_code = None  # レース情報から取得可能だが省略

        # 購入判定
        eval_result = self.evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=combination,
            new_combo=combination,
            old_odds=odds,
            new_odds=odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        if eval_result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            return result

        # 購入対象
        result['purchased'] = True
        result['bet_amount'] = eval_result.bet_amount

        # 実際の結果
        actual = self.get_actual_result(race_id)
        if not actual:
            return result

        actual_combination = f"{actual['rank1']}-{actual['rank2']}-{actual['rank3']}"
        result['actual_combination'] = actual_combination

        # 各着順の正解判定
        result['rank1_correct'] = (predicted_top3[0] == actual['rank1'])
        result['rank2_correct'] = (predicted_top3[1] == actual['rank2'])
        result['rank3_correct'] = (predicted_top3[2] == actual['rank3'])

        # 3連単的中判定
        if combination == actual_combination:
            result['hit'] = True
            payout = self.get_payout(race_id, actual_combination)
            if payout:
                result['payout'] = (result['bet_amount'] / 100) * payout

        return result

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        alpha: float
    ) -> Dict:
        """
        バックテスト実行

        Args:
            start_date: 開始日
            end_date: 終了日
            alpha: オッズ統合係数

        Returns:
            集計結果
        """
        logger.info(f"バックテスト開始: alpha={alpha}, 期間={start_date}〜{end_date}")

        # テスト対象レース取得
        races = self.get_test_races(start_date, end_date)
        logger.info(f"対象レース数: {len(races)}")

        # オッズキャリブレーター（alpha > 0の場合のみ使用）
        odds_calibrator = None
        if alpha > 0:
            odds_calibrator = OddsCalibrator(
                self.db_path,
                alpha=0.5,  # 1着校正係数
                temperature=4.0,
                rank23_alpha=alpha  # 2着・3着統合係数
            )

        # 集計
        stats = {
            'alpha': alpha,
            'total_races': len(races),
            'purchased': 0,
            'hit': 0,
            'total_bet': 0,
            'total_payout': 0,
            'rank1_correct': 0,
            'rank2_correct': 0,
            'rank3_correct': 0,
            'by_confidence': defaultdict(lambda: {
                'purchased': 0, 'hit': 0, 'bet': 0, 'payout': 0,
                'rank1_correct': 0, 'rank2_correct': 0, 'rank3_correct': 0
            })
        }

        for race in races:
            race_id = race['race_id']

            result = self.run_single_race(
                race_id, alpha, odds_calibrator
            )

            if result['purchased']:
                stats['purchased'] += 1
                stats['total_bet'] += result['bet_amount']

                conf = result['confidence']
                stats['by_confidence'][conf]['purchased'] += 1
                stats['by_confidence'][conf]['bet'] += result['bet_amount']

                if result['hit']:
                    stats['hit'] += 1
                    stats['total_payout'] += result['payout']
                    stats['by_confidence'][conf]['hit'] += 1
                    stats['by_confidence'][conf]['payout'] += result['payout']

                if result['rank1_correct']:
                    stats['rank1_correct'] += 1
                    stats['by_confidence'][conf]['rank1_correct'] += 1
                if result['rank2_correct']:
                    stats['rank2_correct'] += 1
                    stats['by_confidence'][conf]['rank2_correct'] += 1
                if result['rank3_correct']:
                    stats['rank3_correct'] += 1
                    stats['by_confidence'][conf]['rank3_correct'] += 1

        # 派生指標を計算
        if stats['purchased'] > 0:
            stats['hit_rate'] = stats['hit'] / stats['purchased']
            stats['rank1_accuracy'] = stats['rank1_correct'] / stats['purchased']
            stats['rank2_accuracy'] = stats['rank2_correct'] / stats['purchased']
            stats['rank3_accuracy'] = stats['rank3_correct'] / stats['purchased']
        else:
            stats['hit_rate'] = 0
            stats['rank1_accuracy'] = 0
            stats['rank2_accuracy'] = 0
            stats['rank3_accuracy'] = 0

        if stats['total_bet'] > 0:
            stats['roi'] = stats['total_payout'] / stats['total_bet']
            stats['profit'] = stats['total_payout'] - stats['total_bet']
        else:
            stats['roi'] = 0
            stats['profit'] = 0

        return stats


def print_comparison_report(results: List[Dict]):
    """比較レポートを出力"""
    print("\n" + "=" * 100)
    print("オッズ逆算による2着・3着予測精度改善バックテスト結果")
    print("=" * 100)

    print("\n【全体サマリー】\n")
    print(f"{'alpha':<10} {'購入数':<10} {'的中数':<10} {'的中率':<12} {'投資額':<14} {'払戻額':<14} {'ROI':<10} {'収支':<14}")
    print("-" * 100)

    for r in results:
        alpha = r['alpha']
        purchased = r['purchased']
        hit = r['hit']
        hit_rate = r['hit_rate'] * 100 if r['hit_rate'] else 0
        total_bet = r['total_bet']
        total_payout = r['total_payout']
        roi = r['roi'] * 100 if r['roi'] else 0
        profit = r['profit']

        print(f"{alpha:<10} {purchased:<10} {hit:<10} {hit_rate:>8.2f}% "
              f"{total_bet:>12,.0f}円 {total_payout:>12,.0f}円 "
              f"{roi:>8.1f}% {profit:>+12,.0f}円")

    print("\n【各順位の的中率】\n")
    print(f"{'alpha':<10} {'1着的中率':<14} {'2着的中率':<14} {'3着的中率':<14}")
    print("-" * 60)

    for r in results:
        alpha = r['alpha']
        rank1 = r['rank1_accuracy'] * 100 if r['rank1_accuracy'] else 0
        rank2 = r['rank2_accuracy'] * 100 if r['rank2_accuracy'] else 0
        rank3 = r['rank3_accuracy'] * 100 if r['rank3_accuracy'] else 0

        print(f"{alpha:<10} {rank1:>10.2f}% {rank2:>10.2f}% {rank3:>10.2f}%")

    # baselineとの比較
    if len(results) > 1:
        baseline = results[0]
        print("\n【baselineとの比較】\n")
        print(f"{'alpha':<10} {'ROI差':<12} {'的中率差':<12} {'2着的中率差':<14} {'3着的中率差':<14}")
        print("-" * 70)

        for r in results[1:]:
            alpha = r['alpha']
            roi_diff = (r['roi'] - baseline['roi']) * 100 if baseline['roi'] else 0
            hit_diff = (r['hit_rate'] - baseline['hit_rate']) * 100 if baseline['hit_rate'] else 0
            rank2_diff = (r['rank2_accuracy'] - baseline['rank2_accuracy']) * 100 if baseline['rank2_accuracy'] else 0
            rank3_diff = (r['rank3_accuracy'] - baseline['rank3_accuracy']) * 100 if baseline['rank3_accuracy'] else 0

            print(f"{alpha:<10} {roi_diff:>+10.2f}pt {hit_diff:>+10.2f}pt "
                  f"{rank2_diff:>+12.2f}pt {rank3_diff:>+12.2f}pt")

    print("\n" + "=" * 100)


def main():
    """メイン処理"""
    # メインDBが空の場合はバックアップを使用
    db_path = ROOT_DIR / "data" / "boatrace.db"
    backup_db_path = ROOT_DIR / "data" / "boatrace_backup_20251212_145413.db"

    # DBサイズをチェックして適切なパスを選択
    import os
    if not os.path.exists(db_path) or os.path.getsize(db_path) < 1000:
        if os.path.exists(backup_db_path) and os.path.getsize(backup_db_path) > 0:
            db_path = backup_db_path
            print(f"バックアップDBを使用: {db_path}")

    # バックテスト期間
    start_date = '2025-11-28'
    end_date = '2025-12-10'

    print(f"\n{'='*100}")
    print(f"オッズ逆算による2着・3着予測精度改善バックテスト")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"期間: {start_date} 〜 {end_date}")
    print(f"{'='*100}")

    # バックテスター作成
    backtester = OddsIntegrationBacktester(str(db_path))

    # テストするalpha値
    alpha_values = [0.0, 0.1, 0.2, 0.3]

    results = []
    for alpha in alpha_values:
        print(f"\n--- alpha={alpha} のテスト開始 ---")
        stats = backtester.run_backtest(start_date, end_date, alpha)
        results.append(stats)

        # 中間結果表示
        print(f"  購入数: {stats['purchased']}")
        print(f"  的中数: {stats['hit']}")
        print(f"  的中率: {stats['hit_rate']*100:.2f}%")
        print(f"  ROI: {stats['roi']*100:.1f}%")
        print(f"  収支: {stats['profit']:+,.0f}円")

    # 比較レポート出力
    print_comparison_report(results)

    # 結果を返す
    return results


if __name__ == "__main__":
    results = main()
