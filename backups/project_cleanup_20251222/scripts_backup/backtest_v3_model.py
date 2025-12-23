# -*- coding: utf-8 -*-
"""
v3条件付きモデルのROI効果検証バックテスト

2025-12-16作成: S-1改善の効果検証

【検証内容】
- v3モデル（予想1着/2着を条件）vs baseline（スコアベース）
- ROIの変化を統計的に検証
- 的中率の変化を確認

【重要な制約】
- 現行ROI 167%を下回らないこと
- 統計的有意性（p<0.05）を確認すること
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from scipy import stats

from src.ml.conditional_rank_model import ConditionalRankModel
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def load_v3_model(model_name: str = 'conditional_rank_v3_20251216_134119') -> ConditionalRankModel:
    """v3モデルを読み込み"""
    model = ConditionalRankModel(model_dir='models')
    model.load(model_name)
    return model


def load_race_data(db_path: str, start_date: str, end_date: str) -> pd.DataFrame:
    """レースデータを読み込み"""
    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        CAST(res.pit_number AS INTEGER) as pit_number,
        CAST(res.rank AS INTEGER) as rank,
        e.racer_rank,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        e.local_win_rate,
        e.local_second_rate,
        e.motor_second_rate,
        e.boat_second_rate,
        e.avg_st,
        rd.exhibition_time,
        rd.st_time as exhibition_st,
        rd.exhibition_course,
        rd.tilt_angle,
        rc.wind_speed,
        rc.wave_height,
        rp.total_score,
        rp.confidence,
        rp.rank_prediction
    FROM races r
    JOIN results res ON r.id = res.race_id
    JOIN entries e ON r.id = e.race_id AND res.pit_number = e.pit_number
    LEFT JOIN race_details rd ON r.id = rd.race_id AND res.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc ON r.id = rc.race_id
    LEFT JOIN race_predictions rp ON r.id = rp.race_id
        AND res.pit_number = rp.pit_number
        AND rp.prediction_type = 'before'
    WHERE r.race_date >= ?
      AND r.race_date <= ?
      AND res.rank IS NOT NULL
      AND CAST(res.rank AS INTEGER) <= 6
    ORDER BY r.race_date, r.id, res.pit_number
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    # total_scoreがない場合はwin_rateで代用
    if 'total_score' not in df.columns or df['total_score'].isna().all():
        df['total_score'] = df['win_rate']
    else:
        df['total_score'] = df['total_score'].fillna(df['win_rate'])

    # 欠損値の処理
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isnull().sum() > 0:
            df[col] = df[col].fillna(df[col].median())

    return df


def load_odds_and_payouts(db_path: str, race_ids: list) -> dict:
    """オッズと払戻金を読み込み"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    odds_data = {}
    payouts_data = {}

    for race_id in race_ids:
        # オッズ
        cursor = conn.execute(
            'SELECT combination, odds FROM trifecta_odds WHERE race_id = ?',
            (race_id,)
        )
        odds_data[race_id] = {row['combination']: row['odds'] for row in cursor.fetchall()}

        # 払戻金
        cursor = conn.execute(
            "SELECT combination, amount FROM payouts WHERE race_id = ? AND bet_type = 'trifecta'",
            (race_id,)
        )
        payouts_data[race_id] = {row['combination']: row['amount'] for row in cursor.fetchall()}

    conn.close()
    return odds_data, payouts_data


def predict_with_v3_model(model: ConditionalRankModel, race_df: pd.DataFrame, use_v2_method: bool = True) -> dict:
    """
    v3モデルで三連単確率を予測

    注意: v3モデルはXGBoostのjson形式で保存されており、
    predict_trifecta_probabilities_v2メソッドを使用（学習時と同じ条件）

    Args:
        model: 学習済みv3モデル
        race_df: レースデータ（6艇分）
        use_v2_method: v2版予測メソッドを使用するか（推奨: True）
    """
    try:
        if use_v2_method:
            probs = model.predict_trifecta_probabilities_v2(race_df)
        else:
            probs = model.predict_trifecta_probabilities(race_df)
        return probs
    except Exception as e:
        # エラーの場合はNoneを返す
        return None


def get_baseline_prediction(race_df: pd.DataFrame) -> str:
    """
    baselineの予測（スコア上位3艇）

    現行システムはtotal_scoreの上位3艇を三連単予測としている
    """
    race_df = race_df.sort_values('total_score', ascending=False)
    top3 = race_df.head(3)['pit_number'].values
    return f"{int(top3[0])}-{int(top3[1])}-{int(top3[2])}"


def get_v3_prediction(model: ConditionalRankModel, race_df: pd.DataFrame, debug: bool = False) -> tuple:
    """
    v3モデルの予測（最高確率の組み合わせ）

    Returns:
        (top_combo, probs, is_v3_used)
    """
    probs = predict_with_v3_model(model, race_df)
    if probs is None:
        baseline = get_baseline_prediction(race_df)
        return baseline, None, False

    # 最高確率の組み合わせを取得
    top_combo = max(probs.items(), key=lambda x: x[1])[0]

    if debug:
        print(f"  v3予測: {top_combo} (prob={probs[top_combo]:.4f})")
        baseline = get_baseline_prediction(race_df)
        print(f"  baseline: {baseline}")

    return top_combo, probs, True


def run_backtest(
    db_path: str,
    start_date: str = '2025-01-01',
    end_date: str = '2025-11-30',
    model_name: str = 'conditional_rank_v3_20251216_134119'
):
    """
    バックテスト実行

    baseline（スコアベース）vs v3モデルを比較
    """
    print("=" * 80)
    print("v3条件付きモデル ROI効果検証バックテスト")
    print("=" * 80)
    print(f"期間: {start_date} ~ {end_date}")
    print(f"モデル: {model_name}")
    print()

    # データ読み込み
    print("データ読み込み中...")
    df = load_race_data(db_path, start_date, end_date)
    print(f"  レコード数: {len(df):,}")
    print(f"  レース数: {df['race_id'].nunique():,}")

    # 6艇完備レースのみ
    race_counts = df.groupby('race_id').size()
    valid_races = race_counts[race_counts == 6].index
    df = df[df['race_id'].isin(valid_races)].copy()
    print(f"  有効レース数: {df['race_id'].nunique():,}")

    # v3モデル読み込み
    print("\nv3モデル読み込み中...")
    try:
        model = load_v3_model(model_name)
        v3_available = True
        print("  v3モデル読み込み成功")
    except Exception as e:
        print(f"  [警告] v3モデル読み込み失敗: {e}")
        print("  baselineのみで評価します")
        v3_available = False

    # オッズと払戻金を読み込み
    race_ids = df['race_id'].unique().tolist()
    print(f"\nオッズ・払戻金読み込み中...")
    odds_data, payouts_data = load_odds_and_payouts(db_path, race_ids)

    # BetTargetEvaluator
    evaluator = BetTargetEvaluator()

    # 結果を格納
    baseline_results = []
    v3_results = []

    print("\nバックテスト実行中...")
    processed = 0

    for race_id in race_ids:
        race_df = df[df['race_id'] == race_id].copy()

        if len(race_df) != 6:
            continue

        race_date = race_df['race_date'].iloc[0]
        venue_code = race_df['venue_code'].iloc[0]

        # 1コース級別
        c1_rank_row = race_df[race_df['pit_number'] == 1]
        c1_rank = c1_rank_row['racer_rank'].values[0] if len(c1_rank_row) > 0 else 'B1'

        # 信頼度
        confidence_row = race_df[race_df['rank_prediction'] == 1]
        confidence = confidence_row['confidence'].values[0] if len(confidence_row) > 0 and pd.notna(confidence_row['confidence'].values[0]) else 'D'

        # A/Bは除外
        if confidence in ['A', 'B']:
            continue

        # === baseline予測 ===
        baseline_combo = get_baseline_prediction(race_df)

        # オッズ確認
        if race_id not in odds_data or baseline_combo not in odds_data[race_id]:
            continue

        baseline_odds = odds_data[race_id][baseline_combo]

        # 購入判定
        result = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=baseline_combo,
            new_combo=baseline_combo,
            old_odds=baseline_odds,
            new_odds=baseline_odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            continue

        bet_amount = result.bet_amount

        # 実際の結果
        actual_top3 = race_df.sort_values('rank').head(3)['pit_number'].values
        actual_combo = f"{int(actual_top3[0])}-{int(actual_top3[1])}-{int(actual_top3[2])}"

        # baseline結果
        baseline_hit = 1 if baseline_combo == actual_combo else 0
        baseline_payout = 0
        if baseline_hit and race_id in payouts_data and actual_combo in payouts_data[race_id]:
            baseline_payout = (bet_amount / 100) * payouts_data[race_id][actual_combo]

        baseline_results.append({
            'race_id': race_id,
            'race_date': race_date,
            'bet_amount': bet_amount,
            'combo': baseline_combo,
            'actual': actual_combo,
            'hit': baseline_hit,
            'payout': baseline_payout,
            'profit': baseline_payout - bet_amount
        })

        # === v3予測 ===
        if v3_available:
            try:
                debug_mode = (processed < 5)  # 最初の5件だけデバッグ出力
                v3_combo, v3_probs, is_v3_used = get_v3_prediction(model, race_df, debug=debug_mode)

                # 予測の違いをカウント
                if v3_combo != baseline_combo:
                    if not hasattr(run_backtest, 'diff_count'):
                        run_backtest.diff_count = 0
                    run_backtest.diff_count += 1

                # v3のオッズ確認
                if race_id in odds_data and v3_combo in odds_data[race_id]:
                    v3_odds = odds_data[race_id][v3_combo]

                    # 同じ購入条件で評価（オッズが条件内かチェック）
                    v3_result = evaluator.evaluate(
                        confidence=confidence,
                        c1_rank=c1_rank,
                        old_combo=v3_combo,
                        new_combo=v3_combo,
                        old_odds=v3_odds,
                        new_odds=v3_odds,
                        has_beforeinfo=True,
                        venue_code=venue_code
                    )

                    if v3_result.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                        v3_bet_amount = v3_result.bet_amount
                        v3_hit = 1 if v3_combo == actual_combo else 0
                        v3_payout = 0
                        if v3_hit and race_id in payouts_data and actual_combo in payouts_data[race_id]:
                            v3_payout = (v3_bet_amount / 100) * payouts_data[race_id][actual_combo]

                        v3_results.append({
                            'race_id': race_id,
                            'race_date': race_date,
                            'bet_amount': v3_bet_amount,
                            'combo': v3_combo,
                            'actual': actual_combo,
                            'hit': v3_hit,
                            'payout': v3_payout,
                            'profit': v3_payout - v3_bet_amount,
                            'same_as_baseline': v3_combo == baseline_combo
                        })
            except Exception as e:
                # v3予測失敗の場合はスキップ
                if processed < 5:
                    print(f"  [警告] v3予測失敗: {e}")
                pass

        processed += 1
        if processed % 1000 == 0:
            print(f"  {processed:,}レース処理完了...")

    print(f"\n処理完了: {processed:,}レース")

    # 予測の違いをレポート
    diff_count = getattr(run_backtest, 'diff_count', 0)
    print(f"v3とbaselineの予測が異なるレース: {diff_count}件")

    # 結果集計
    print("\n" + "=" * 80)
    print("結果サマリー")
    print("=" * 80)

    # baseline結果
    baseline_df = pd.DataFrame(baseline_results)
    if len(baseline_df) > 0:
        baseline_total_bet = baseline_df['bet_amount'].sum()
        baseline_total_payout = baseline_df['payout'].sum()
        baseline_total_hit = baseline_df['hit'].sum()
        baseline_hit_rate = baseline_total_hit / len(baseline_df) * 100
        baseline_roi = baseline_total_payout / baseline_total_bet * 100 if baseline_total_bet > 0 else 0
        baseline_profit = baseline_total_payout - baseline_total_bet

        print("\n【baseline（スコアベース）】")
        print(f"  購入数: {len(baseline_df):,}件")
        print(f"  的中数: {baseline_total_hit:,}件")
        print(f"  的中率: {baseline_hit_rate:.2f}%")
        print(f"  総投資: {baseline_total_bet:,.0f}円")
        print(f"  総払戻: {baseline_total_payout:,.0f}円")
        print(f"  収支: {baseline_profit:+,.0f}円")
        print(f"  ROI: {baseline_roi:.1f}%")

    # v3結果
    if v3_available and len(v3_results) > 0:
        v3_df = pd.DataFrame(v3_results)
        v3_total_bet = v3_df['bet_amount'].sum()
        v3_total_payout = v3_df['payout'].sum()
        v3_total_hit = v3_df['hit'].sum()
        v3_hit_rate = v3_total_hit / len(v3_df) * 100
        v3_roi = v3_total_payout / v3_total_bet * 100 if v3_total_bet > 0 else 0
        v3_profit = v3_total_payout - v3_total_bet

        print("\n【v3モデル】")
        print(f"  購入数: {len(v3_df):,}件")
        print(f"  的中数: {v3_total_hit:,}件")
        print(f"  的中率: {v3_hit_rate:.2f}%")
        print(f"  総投資: {v3_total_bet:,.0f}円")
        print(f"  総払戻: {v3_total_payout:,.0f}円")
        print(f"  収支: {v3_profit:+,.0f}円")
        print(f"  ROI: {v3_roi:.1f}%")

        # 比較
        print("\n" + "=" * 80)
        print("比較分析")
        print("=" * 80)

        roi_diff = v3_roi - baseline_roi
        profit_diff = v3_profit - baseline_profit
        hit_rate_diff = v3_hit_rate - baseline_hit_rate

        print(f"\n【ROI比較】")
        print(f"  baseline: {baseline_roi:.1f}%")
        print(f"  v3モデル: {v3_roi:.1f}%")
        print(f"  差分: {roi_diff:+.1f}pt")

        print(f"\n【収支比較】")
        print(f"  baseline: {baseline_profit:+,.0f}円")
        print(f"  v3モデル: {v3_profit:+,.0f}円")
        print(f"  差分: {profit_diff:+,.0f}円")

        print(f"\n【的中率比較】")
        print(f"  baseline: {baseline_hit_rate:.2f}%")
        print(f"  v3モデル: {v3_hit_rate:.2f}%")
        print(f"  差分: {hit_rate_diff:+.2f}pt")

        # 統計的有意性検定
        print("\n" + "=" * 80)
        print("統計的有意性検定")
        print("=" * 80)

        # 共通レースでの比較
        common_races = set(baseline_df['race_id']) & set(v3_df['race_id'])
        print(f"\n共通レース数: {len(common_races):,}件")

        if len(common_races) >= 30:
            baseline_common = baseline_df[baseline_df['race_id'].isin(common_races)]
            v3_common = v3_df[v3_df['race_id'].isin(common_races)]

            baseline_profits = baseline_common.groupby('race_id')['profit'].sum()
            v3_profits = v3_common.groupby('race_id')['profit'].sum()

            # 対応のあるt検定
            t_stat, p_value = stats.ttest_rel(
                v3_profits.reindex(common_races),
                baseline_profits.reindex(common_races)
            )

            print(f"\n対応のあるt検定（profit比較）:")
            print(f"  t統計量: {t_stat:.4f}")
            print(f"  p値: {p_value:.4f}")

            if p_value < 0.05:
                print(f"  結果: 統計的に有意 (p < 0.05)")
                if t_stat > 0:
                    print(f"  → v3モデルの方が有意に良い")
                else:
                    print(f"  → baselineの方が有意に良い")
            else:
                print(f"  結果: 統計的に有意ではない (p >= 0.05)")

        # 判定
        print("\n" + "=" * 80)
        print("最終判定")
        print("=" * 80)

        target_roi = 167.0  # 現行ROI

        if v3_roi >= target_roi:
            print(f"\n[PASS] v3モデルは目標ROI ({target_roi}%) を達成")
            if roi_diff > 0:
                print(f"       ROI改善: {roi_diff:+.1f}pt")
            recommendation = "採用推奨"
        elif v3_roi >= baseline_roi:
            print(f"\n[NEUTRAL] v3モデルはbaselineと同等以上")
            print(f"          ただし目標ROI ({target_roi}%) には未達")
            recommendation = "追加検証が必要"
        else:
            print(f"\n[FAIL] v3モデルはbaselineを下回る")
            print(f"       ROI低下: {roi_diff:.1f}pt")
            recommendation = "不採用"

        print(f"\n推奨: {recommendation}")

    return {
        'baseline': baseline_df if len(baseline_results) > 0 else None,
        'v3': v3_df if v3_available and len(v3_results) > 0 else None
    }


def main():
    print("#" * 80)
    print("# v3条件付きモデル ROI効果検証")
    print("#" * 80)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db_path = 'data/boatrace.db'

    results = run_backtest(
        db_path=db_path,
        start_date='2025-01-01',
        end_date='2025-11-30',
        model_name='conditional_rank_v3_20251216_134119'
    )

    print("\n" + "#" * 80)
    print("# 完了")
    print("#" * 80)

    return results


if __name__ == '__main__':
    main()
