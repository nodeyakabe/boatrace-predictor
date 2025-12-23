# -*- coding: utf-8 -*-
"""
2025年改善効果バックテスト比較スクリプト

目的:
- ベースライン（現状ROI 167%, +166,860円, 的中率4.34%）との比較
- P-1, P-3, P-6-1, P-6-2 改善効果の定量評価
- 一晩かけて実行（時間制限なし）

比較方法:
1. 既存予測（race_predictionsテーブル）でのバックテスト → ベースライン
2. 改善ロジックでリアルタイム予測生成 → 改善版

実行時間: 数時間〜一晩（2025年全期間のレースを処理）
"""
import sys
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import warnings
import io

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus
from src.analysis.race_predictor import RacePredictor
from config.feature_flags import is_feature_enabled, set_feature_flag, get_enabled_features

# 結果保存用ログファイル
LOG_DIR = ROOT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f'backtest_improvement_comparison_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'


def log(message: str):
    """ログ出力（画面とファイル両方）"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_msg + '\n')


def run_baseline_backtest(db_path, start_date, end_date):
    """
    ベースラインバックテスト（既存予測を使用）
    - race_predictionsテーブルに保存された予測結果を使用
    - 現状の実績値を算出
    """
    log("=" * 100)
    log("ベースラインバックテスト（既存予測使用）")
    log("=" * 100)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    # 対象レース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))
    races = cursor.fetchall()

    log(f"対象レース数: {len(races):,}")

    stats = {
        'total_races': len(races),
        'target': 0, 'hit': 0, 'bet': 0, 'payout': 0,
        'by_month': defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})
    }

    processed = 0
    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_date = race['race_date']
        month = race_date[:7]

        # 1コース級別取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 予測情報取得（before）
        cursor.execute('''
            SELECT pit_number, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']

        # 信頼度A/Bは除外
        if confidence in ['A', 'B']:
            continue

        # 予測トップ3
        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # オッズ取得
        cursor.execute(
            'SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
            (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

        # bet_target_evaluatorで購入判定
        result = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=combo,
            new_combo=combo,
            old_odds=odds,
            new_odds=odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            continue

        bet_amount = result.bet_amount
        stats['target'] += 1
        stats['bet'] += bet_amount
        stats['by_month'][month]['target'] += 1
        stats['by_month'][month]['bet'] += bet_amount

        # 実際の結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            if combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    actual_payout = (bet_amount / 100) * payout_row['amount']
                    stats['hit'] += 1
                    stats['payout'] += actual_payout
                    stats['by_month'][month]['hit'] += 1
                    stats['by_month'][month]['payout'] += actual_payout

        processed += 1
        if processed % 5000 == 0:
            log(f"  進捗: {processed:,}/{len(races):,} レース処理完了")

    conn.close()

    # 結果計算
    hit_rate = stats['hit'] / stats['target'] * 100 if stats['target'] > 0 else 0
    roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
    profit = stats['payout'] - stats['bet']

    log("")
    log(f"[ベースライン結果]")
    log(f"  購入レース数: {stats['target']:,}")
    log(f"  的中数: {stats['hit']:,}")
    log(f"  的中率: {hit_rate:.2f}%")
    log(f"  総投資: {stats['bet']:,.0f}円")
    log(f"  総払戻: {stats['payout']:,.0f}円")
    log(f"  収支: {profit:+,.0f}円")
    log(f"  ROI: {roi:.1f}%")
    log("")

    return stats


def run_improved_backtest(db_path, start_date, end_date):
    """
    改善版バックテスト（リアルタイム予測生成）
    - RacePredictorを使って各レースを予測
    - P-1, P-3, P-6-1, P-6-2 の改善効果を含む
    """
    log("=" * 100)
    log("改善版バックテスト（リアルタイム予測）")
    log("=" * 100)

    # 有効な機能フラグを確認
    enabled_features = get_enabled_features()
    improvement_features = [
        'forward_mover_filter',          # P-1
        'kimarite_flow_prediction',      # P-3
        'third_place_specialized_scorer', # P-6-1
        'makuri_risk_adjustment'         # P-6-2
    ]
    log(f"有効な改善機能:")
    for feat in improvement_features:
        status = "ON" if feat in enabled_features else "OFF"
        log(f"  - {feat}: {status}")
    log("")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()
    predictor = RacePredictor(db_path=str(db_path))

    # 対象レース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND EXISTS (SELECT 1 FROM race_details WHERE race_id = r.id)
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
          AND EXISTS (
              SELECT 1 FROM entries
              WHERE race_id = r.id
              GROUP BY race_id
              HAVING COUNT(DISTINCT pit_number) = 6
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))
    races = cursor.fetchall()

    log(f"対象レース数: {len(races):,}")

    stats = {
        'total_races': len(races),
        'target': 0, 'hit': 0, 'bet': 0, 'payout': 0,
        'prediction_success': 0, 'prediction_fail': 0,
        'by_month': defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})
    }

    processed = 0
    start_time = datetime.now()

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_date = race['race_date']
        month = race_date[:7]

        try:
            # 改善版ロジックで予測生成
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)

            if not predictions or len(predictions) < 6:
                stats['prediction_fail'] += 1
                continue

            stats['prediction_success'] += 1

            # 信頼度取得
            confidence = predictions[0].get('confidence', 'D')

            # 信頼度A/Bは除外
            if confidence in ['A', 'B']:
                continue

            # 予測トップ3
            top3 = [p['pit_number'] for p in predictions[:3]]
            combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

            # 1コース級別取得
            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1 = cursor.fetchone()
            c1_rank = c1['racer_rank'] if c1 else 'B1'

            # オッズ取得
            cursor.execute(
                'SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                (race_id, combo))
            odds_row = cursor.fetchone()

            if not odds_row:
                continue

            odds = odds_row['odds']

            # bet_target_evaluatorで購入判定
            result = evaluator.evaluate(
                confidence=confidence,
                c1_rank=c1_rank,
                old_combo=combo,
                new_combo=combo,
                old_odds=odds,
                new_odds=odds,
                has_beforeinfo=True,
                venue_code=venue_code
            )

            if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                continue

            bet_amount = result.bet_amount
            stats['target'] += 1
            stats['bet'] += bet_amount
            stats['by_month'][month]['target'] += 1
            stats['by_month'][month]['bet'] += bet_amount

            # 実際の結果取得
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            results = cursor.fetchall()

            if len(results) >= 3:
                actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

                if combo == actual_combo:
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        actual_payout = (bet_amount / 100) * payout_row['amount']
                        stats['hit'] += 1
                        stats['payout'] += actual_payout
                        stats['by_month'][month]['hit'] += 1
                        stats['by_month'][month]['payout'] += actual_payout

        except Exception as e:
            stats['prediction_fail'] += 1
            if stats['prediction_fail'] <= 10:
                log(f"  [ERROR] {race_date} {venue_code}場: {str(e)[:50]}")

        processed += 1
        if processed % 1000 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = (len(races) - processed) / rate if rate > 0 else 0
            log(f"  進捗: {processed:,}/{len(races):,} ({processed/len(races)*100:.1f}%) "
                f"残り約{remaining/60:.0f}分")

    conn.close()

    # 結果計算
    hit_rate = stats['hit'] / stats['target'] * 100 if stats['target'] > 0 else 0
    roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
    profit = stats['payout'] - stats['bet']

    log("")
    log(f"[改善版結果]")
    log(f"  予測成功: {stats['prediction_success']:,}")
    log(f"  予測失敗: {stats['prediction_fail']:,}")
    log(f"  購入レース数: {stats['target']:,}")
    log(f"  的中数: {stats['hit']:,}")
    log(f"  的中率: {hit_rate:.2f}%")
    log(f"  総投資: {stats['bet']:,.0f}円")
    log(f"  総払戻: {stats['payout']:,.0f}円")
    log(f"  収支: {profit:+,.0f}円")
    log(f"  ROI: {roi:.1f}%")
    log("")

    return stats


def compare_results(baseline_stats, improved_stats):
    """結果比較"""
    log("=" * 100)
    log("比較結果サマリー")
    log("=" * 100)

    # ベースライン
    baseline_hit_rate = baseline_stats['hit'] / baseline_stats['target'] * 100 if baseline_stats['target'] > 0 else 0
    baseline_roi = baseline_stats['payout'] / baseline_stats['bet'] * 100 if baseline_stats['bet'] > 0 else 0
    baseline_profit = baseline_stats['payout'] - baseline_stats['bet']

    # 改善版
    improved_hit_rate = improved_stats['hit'] / improved_stats['target'] * 100 if improved_stats['target'] > 0 else 0
    improved_roi = improved_stats['payout'] / improved_stats['bet'] * 100 if improved_stats['bet'] > 0 else 0
    improved_profit = improved_stats['payout'] - improved_stats['bet']

    # 差分
    diff_hit_rate = improved_hit_rate - baseline_hit_rate
    diff_roi = improved_roi - baseline_roi
    diff_profit = improved_profit - baseline_profit

    log("")
    log(f"{'指標':<20} {'ベースライン':>15} {'改善版':>15} {'差分':>15}")
    log("-" * 70)
    log(f"{'購入レース数':<20} {baseline_stats['target']:>15,} {improved_stats['target']:>15,} {improved_stats['target'] - baseline_stats['target']:>+15,}")
    log(f"{'的中数':<20} {baseline_stats['hit']:>15,} {improved_stats['hit']:>15,} {improved_stats['hit'] - baseline_stats['hit']:>+15,}")
    log(f"{'的中率':<20} {baseline_hit_rate:>14.2f}% {improved_hit_rate:>14.2f}% {diff_hit_rate:>+14.2f}%")
    log(f"{'ROI':<20} {baseline_roi:>14.1f}% {improved_roi:>14.1f}% {diff_roi:>+14.1f}%")
    log(f"{'収支（円）':<20} {baseline_profit:>+15,.0f} {improved_profit:>+15,.0f} {diff_profit:>+15,.0f}")
    log("")

    # 月別比較
    log("-" * 100)
    log("月別ROI比較")
    log("-" * 100)
    log(f"{'月':<12} {'ベースライン':>12} {'改善版':>12} {'差分':>12}")
    log("-" * 50)

    all_months = sorted(set(baseline_stats['by_month'].keys()) | set(improved_stats['by_month'].keys()))
    for month in all_months:
        b_stats = baseline_stats['by_month'].get(month, {'bet': 0, 'payout': 0})
        i_stats = improved_stats['by_month'].get(month, {'bet': 0, 'payout': 0})

        b_roi = b_stats['payout'] / b_stats['bet'] * 100 if b_stats['bet'] > 0 else 0
        i_roi = i_stats['payout'] / i_stats['bet'] * 100 if i_stats['bet'] > 0 else 0
        diff = i_roi - b_roi

        log(f"{month:<12} {b_roi:>11.1f}% {i_roi:>11.1f}% {diff:>+11.1f}%")

    log("")
    log("=" * 100)
    log("判定")
    log("=" * 100)

    if diff_profit > 50000:
        log("[EXCELLENT] 大幅改善: +5万円以上の収益増加")
    elif diff_profit > 10000:
        log("[GOOD] 改善: +1万円以上の収益増加")
    elif diff_profit > 0:
        log("[MARGINAL] 微増: 収益がわずかに改善")
    elif diff_profit > -10000:
        log("[NEUTRAL] ほぼ変化なし")
    else:
        log("[NG] 悪化: 収益が減少")

    log("")
    log(f"ログファイル: {LOG_FILE}")
    log("=" * 100)


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"

    log("=" * 100)
    log("2025年改善効果バックテスト比較")
    log("=" * 100)
    log(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"ログファイル: {LOG_FILE}")
    log("")
    log("比較対象:")
    log("  ベースライン: 既存予測（race_predictionsテーブル）")
    log("  改善版: リアルタイム予測（P-1, P-3, P-6-1, P-6-2有効）")
    log("")
    log("参考値（現状実績）:")
    log("  年間ROI: 167.0%")
    log("  年間収支: +166,860円")
    log("  的中率: 4.34%")
    log("")

    start_time = datetime.now()

    # 1. ベースラインバックテスト
    baseline_stats = run_baseline_backtest(
        db_path=db_path,
        start_date='2025-01-01',
        end_date='2025-12-31'
    )

    # 2. 改善版バックテスト
    improved_stats = run_improved_backtest(
        db_path=db_path,
        start_date='2025-01-01',
        end_date='2025-12-31'
    )

    # 3. 結果比較
    compare_results(baseline_stats, improved_stats)

    elapsed = (datetime.now() - start_time).total_seconds()
    log(f"\n総実行時間: {elapsed/60:.1f}分（{elapsed/3600:.2f}時間）")
    log(f"実行完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
