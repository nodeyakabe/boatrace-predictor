# -*- coding: utf-8 -*-
"""
各機能の効果検証（軽量版）

既存のrace_predictionsテーブルの予測結果に対して
P-3, P-6-1, P-6-2 の調整を適用した場合の影響を測定

RacePredictorを毎回呼び出さないので高速
"""
import sys
import sqlite3
import io
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def get_baseline_predictions(cursor, race_id):
    """ベースライン予測を取得"""
    cursor.execute('''
        SELECT pit_number, confidence, total_score
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY total_score DESC
    ''', (race_id,))
    return cursor.fetchall()


def apply_p3_adjustment(predictions, cursor, race_id):
    """P-3: 決まり手別展開予測による調整（シミュレーション）"""
    # 実際のKimariteFlowPredictorロジックを簡略化
    # 本来はkimarite_flow_predictorを呼ぶが、ここではシンプルに
    # 1号艇がまくられるリスクを評価して、2-6番艇のスコアを微調整
    try:
        from src.prediction.kimarite_flow_predictor import KimariteFlowPredictor
        predictor = KimariteFlowPredictor(str(ROOT_DIR / "data" / "boatrace.db"))
        flow_pred = predictor.predict_race_flow(race_id)
        if flow_pred is None:
            return predictions

        # 予測をリストに変換して調整
        adjusted = []
        for p in predictions:
            pit = p['pit_number']
            score = p['total_score']
            confidence = p['confidence']

            # 決まり手別展開に基づくスコア調整
            adjustment = 0.0
            if pit == 1:
                # 1号艇: 逃げ確率に基づく
                nige_prob = flow_pred.get('nige_probability', 0.5)
                adjustment = (nige_prob - 0.5) * 5.0  # -2.5 ~ +2.5
            else:
                # 2-6号艇: まくり/差し確率に基づく
                makuri_prob = flow_pred.get('makuri_probability', 0.2)
                sashi_prob = flow_pred.get('sashi_probability', 0.2)
                if pit in [2, 3, 4]:
                    adjustment = makuri_prob * 2.0  # まくり有利
                else:
                    adjustment = sashi_prob * 1.5  # 差し有利

            adjusted.append({
                'pit_number': pit,
                'total_score': score + adjustment,
                'confidence': confidence
            })

        # スコア順に再ソート
        adjusted.sort(key=lambda x: x['total_score'], reverse=True)
        return adjusted
    except Exception:
        return predictions


def apply_p6_1_adjustment(predictions, cursor, race_id):
    """P-6-1: 3着専用スコアラーによる調整（シミュレーション）"""
    # 3着予測精度を向上させるための調整
    # 実際のThirdPlaceSpecializedScorerロジックを簡略化
    try:
        from src.ml.third_place_specialized_model import ThirdPlaceSpecializedScorer
        scorer = ThirdPlaceSpecializedScorer(str(ROOT_DIR / "data" / "boatrace.db"))
        third_scores = scorer.calculate_third_place_scores(race_id)
        if not third_scores:
            return predictions

        # 3位候補のスコアを微調整
        adjusted = []
        for p in predictions:
            pit = p['pit_number']
            score = p['total_score']
            confidence = p['confidence']

            # 3着専用スコアによる補正（3位付近の艇に適用）
            third_score = third_scores.get(pit, 0)
            # 上位2艇には影響を与えず、3位以下に補正
            rank_in_pred = [x['pit_number'] for x in predictions].index(pit) + 1
            if rank_in_pred >= 3:
                adjustment = third_score * 0.5
            else:
                adjustment = 0

            adjusted.append({
                'pit_number': pit,
                'total_score': score + adjustment,
                'confidence': confidence
            })

        adjusted.sort(key=lambda x: x['total_score'], reverse=True)
        return adjusted
    except Exception:
        return predictions


def apply_p6_2_adjustment(predictions, cursor, race_id):
    """P-6-2: まくりリスク評価による調整（シミュレーション）"""
    try:
        from src.prediction.makuri_risk_evaluator import MakuriRiskEvaluator
        evaluator = MakuriRiskEvaluator(str(ROOT_DIR / "data" / "boatrace.db"))
        risk = evaluator.evaluate_race(race_id)
        if risk is None:
            return predictions

        adjusted = []
        for p in predictions:
            pit = p['pit_number']
            score = p['total_score']
            confidence = p['confidence']

            adjustment = 0.0
            makuri_risk = risk.get('makuri_risk', 0.2)

            if pit == 1:
                # 1号艇: まくりリスクが高いほど減点
                adjustment = -makuri_risk * 3.0
            elif pit in [2, 3]:
                # 2,3号艇: まくりリスクが高いほど加点
                adjustment = makuri_risk * 2.0

            adjusted.append({
                'pit_number': pit,
                'total_score': score + adjustment,
                'confidence': confidence
            })

        adjusted.sort(key=lambda x: x['total_score'], reverse=True)
        return adjusted
    except Exception:
        return predictions


def evaluate_predictions(predictions, cursor, race_id, evaluator):
    """予測結果を評価してベット判定"""
    if len(predictions) < 6:
        return None

    # dict型かRow型かを判別
    if hasattr(predictions[0], 'keys'):
        # Row型
        confidence = predictions[0]['confidence']
        top3 = [p['pit_number'] for p in predictions[:3]]
    else:
        # dict型
        confidence = predictions[0].get('confidence', 'D')
        top3 = [p['pit_number'] for p in predictions[:3]]

    if confidence in ['A', 'B']:
        return None

    combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

    # 1コース級別
    cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
    c1 = cursor.fetchone()
    c1_rank = c1['racer_rank'] if c1 else 'B1'

    # venue_code
    cursor.execute('SELECT venue_code FROM races WHERE id = ?', (race_id,))
    race_row = cursor.fetchone()
    venue_code = int(race_row['venue_code']) if race_row and race_row['venue_code'] else 0

    # オッズ
    cursor.execute(
        'SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
        (race_id, combo))
    odds_row = cursor.fetchone()
    if not odds_row:
        return None

    odds = odds_row['odds']

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
        return None

    return {
        'combo': combo,
        'bet_amount': result.bet_amount
    }


def check_hit(cursor, race_id, combo, bet_amount):
    """的中判定"""
    cursor.execute('''
        SELECT pit_number FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
        ORDER BY rank
    ''', (race_id,))
    results = cursor.fetchall()

    if len(results) < 3:
        return False, 0

    actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

    if combo != actual_combo:
        return False, 0

    cursor.execute('''
        SELECT amount FROM payouts
        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
    ''', (race_id, actual_combo))
    payout_row = cursor.fetchone()

    if payout_row:
        payout = (bet_amount / 100) * payout_row['amount']
        return True, payout

    return True, 0


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("各機能の効果検証（軽量版）")
    print("=" * 100)
    print(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("方法: 既存予測に各機能の調整を適用し、順位変動による影響を測定")
    print()

    # 2025年1月のレースを対象
    cursor.execute('''
        SELECT r.id as race_id
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-01-31'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()
    print(f"対象レース数: {len(races)}")
    print()

    # 検証パターン
    patterns = [
        ('ベースライン', lambda p, c, r: p),
        ('P-3適用', apply_p3_adjustment),
        ('P-6-1適用', apply_p6_1_adjustment),
        ('P-6-2適用', apply_p6_2_adjustment),
    ]

    results = {}
    for name, _ in patterns:
        results[name] = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

    for race in races:
        race_id = race['race_id']

        # ベースライン予測取得
        baseline_preds = get_baseline_predictions(cursor, race_id)
        if len(baseline_preds) < 6:
            continue

        for name, adjust_func in patterns:
            # 調整適用
            adjusted_preds = adjust_func(baseline_preds, cursor, race_id)

            # 評価
            bet_result = evaluate_predictions(adjusted_preds, cursor, race_id, evaluator)
            if bet_result is None:
                continue

            results[name]['target'] += 1
            results[name]['bet'] += bet_result['bet_amount']

            # 的中判定
            is_hit, payout = check_hit(cursor, race_id, bet_result['combo'], bet_result['bet_amount'])
            if is_hit:
                results[name]['hit'] += 1
                results[name]['payout'] += payout

    conn.close()

    # 結果表示
    print("=" * 100)
    print("結果サマリー")
    print("=" * 100)
    print(f"\n{'パターン':<15} {'購入':>6} {'的中':>4} {'的中率':>8} {'ROI':>10} {'収支':>14}")
    print("-" * 65)

    baseline_stats = results['ベースライン']
    baseline_roi = baseline_stats['payout'] / baseline_stats['bet'] * 100 if baseline_stats['bet'] > 0 else 0
    baseline_profit = baseline_stats['payout'] - baseline_stats['bet']

    for name in ['ベースライン', 'P-3適用', 'P-6-1適用', 'P-6-2適用']:
        stats = results[name]
        hit_rate = stats['hit'] / stats['target'] * 100 if stats['target'] > 0 else 0
        roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        profit = stats['payout'] - stats['bet']

        print(f"{name:<15} {stats['target']:>6} {stats['hit']:>4} "
              f"{hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+13,.0f}円")

    # 差分表示
    print("\n" + "=" * 100)
    print("ベースラインからの差分")
    print("=" * 100)
    print(f"\n{'パターン':<15} {'ROI差分':>12} {'収支差分':>14} {'判定':>12}")
    print("-" * 60)

    for name in ['P-3適用', 'P-6-1適用', 'P-6-2適用']:
        stats = results[name]
        roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        profit = stats['payout'] - stats['bet']

        diff_roi = roi - baseline_roi
        diff_profit = profit - baseline_profit

        if diff_profit > 5000:
            judge = "プラス効果"
        elif diff_profit > -5000:
            judge = "ほぼ変化なし"
        else:
            judge = "マイナス効果"

        print(f"{name:<15} {diff_roi:>+11.1f}% {diff_profit:>+13,.0f}円 {judge:>12}")

    print("\n" + "=" * 100)
    print(f"実行完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)


if __name__ == "__main__":
    main()
