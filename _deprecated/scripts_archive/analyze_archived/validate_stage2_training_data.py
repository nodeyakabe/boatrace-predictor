"""
Stage2学習データの検証スクリプト

問題: 学習データは実際の1位を条件としているが、予測時は予想1位を条件としている
目的: この分布ミスマッチの影響を定量化する
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import joblib
import json

# データベースパス
DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"
MODEL_DIR = Path(__file__).parent.parent / "models"

def load_models():
    """既存のStage2モデルとメタ情報を読み込み"""
    meta_path = MODEL_DIR / "conditional_meta.json"
    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    stage1 = joblib.load(MODEL_DIR / "conditional_stage1.joblib")
    stage2 = joblib.load(MODEL_DIR / "conditional_stage2.joblib")

    return stage1, stage2, meta

def analyze_training_data_distribution():
    """学習データの分布を分析"""
    print("=" * 80)
    print("【Stage2学習データの分析】")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)

    # 2024-2025年のデータを取得
    query = """
    SELECT
        e.race_id,
        e.pit_number,
        r.rank,
        e.win_rate,
        e.second_rate,
        rd.exhibition_time,
        rd.st_time as avg_st,
        COALESCE(rd.actual_course, e.pit_number) as actual_course
    FROM entries e
    JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    JOIN races race ON e.race_id = race.id
    WHERE race.race_date >= '2024-01-01' AND race.race_date < '2026-01-01'
      AND r.is_invalid = 0
    ORDER BY e.race_id, e.pit_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"\n総データ数: {len(df):,}件")
    print(f"レース数: {df['race_id'].nunique():,}レース")

    # 6艇完備のレースのみ
    race_counts = df.groupby('race_id').size()
    valid_races = race_counts[race_counts == 6].index
    df = df[df['race_id'].isin(valid_races)]

    print(f"6艇完備レース数: {len(valid_races):,}レース")

    # 1着艇の情報
    first_place = df[df['rank'] == 1][['race_id', 'pit_number']].copy()
    first_place.columns = ['race_id', 'first_pit']

    # 各レースのスコア最高艇（予想1位）を計算
    # 簡易版: win_rate基準
    predicted_first = df.loc[df.groupby('race_id')['win_rate'].idxmax()][['race_id', 'pit_number']].copy()
    predicted_first.columns = ['race_id', 'predicted_first_pit']

    # マージ
    analysis = first_place.merge(predicted_first, on='race_id')

    # 実際の1位と予想1位の一致率
    match_rate = (analysis['first_pit'] == analysis['predicted_first_pit']).mean() * 100

    print(f"\n【予想1位と実際の1位の一致率】")
    print(f"一致率: {match_rate:.2f}%")
    print(f"不一致率: {100 - match_rate:.2f}%")

    print(f"\n→ **{100 - match_rate:.1f}%のケースで学習データと予測時のデータ分布が異なる**")

    return analysis, df

def analyze_stage2_accuracy_by_condition():
    """条件別のStage2精度を分析"""
    print("\n" + "=" * 80)
    print("【条件別のStage2（2位予測）精度】")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)

    query = """
    WITH race_features AS (
        SELECT
            e.race_id,
            e.pit_number,
            r.rank,
            e.win_rate,
            e.second_rate,
            rd.exhibition_time,
            rd.st_time as avg_st,
            COALESCE(rd.actual_course, e.pit_number) as actual_course
        FROM entries e
        JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
        LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
        JOIN races race ON e.race_id = race.id
        WHERE race.race_date >= '2024-01-01' AND race.race_date < '2026-01-01'
          AND r.is_invalid = 0
    ),
    actual_first AS (
        SELECT race_id, pit_number as actual_first_pit
        FROM race_features
        WHERE rank = 1
    ),
    predicted_first AS (
        SELECT race_id, pit_number as predicted_first_pit
        FROM (
            SELECT race_id, pit_number, win_rate,
                   ROW_NUMBER() OVER (PARTITION BY race_id ORDER BY win_rate DESC, pit_number) as rn
            FROM race_features
        )
        WHERE rn = 1
    ),
    actual_second AS (
        SELECT race_id, pit_number as actual_second_pit
        FROM race_features
        WHERE rank = 2
    ),
    predicted_second AS (
        SELECT race_id, pit_number as predicted_second_pit
        FROM (
            SELECT race_id, pit_number, win_rate,
                   ROW_NUMBER() OVER (PARTITION BY race_id ORDER BY win_rate DESC, pit_number) as rn
            FROM race_features
        )
        WHERE rn = 2
    )
    SELECT
        af.race_id,
        af.actual_first_pit,
        pf.predicted_first_pit,
        asec.actual_second_pit,
        psec.predicted_second_pit,
        CASE WHEN af.actual_first_pit = pf.predicted_first_pit THEN 1 ELSE 0 END as first_match,
        CASE WHEN asec.actual_second_pit = psec.predicted_second_pit THEN 1 ELSE 0 END as second_match
    FROM actual_first af
    JOIN predicted_first pf ON af.race_id = pf.race_id
    JOIN actual_second asec ON af.race_id = asec.race_id
    JOIN predicted_second psec ON af.race_id = psec.race_id
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    total = len(df)

    # ケース1: 予想1位が当たった場合
    case1 = df[df['first_match'] == 1]
    case1_count = len(case1)
    case1_second_rate = (case1['second_match'].sum() / case1_count * 100) if case1_count > 0 else 0

    # ケース2: 予想1位が外れた場合
    case2 = df[df['first_match'] == 0]
    case2_count = len(case2)
    case2_second_rate = (case2['second_match'].sum() / case2_count * 100) if case2_count > 0 else 0

    # 全体
    overall_second_rate = df['second_match'].sum() / total * 100

    print(f"\n総レース数: {total:,}")

    print(f"\n【ケース1: 予想1位が的中した場合】")
    print(f"レース数: {case1_count:,} ({case1_count/total*100:.1f}%)")
    print(f"2位予想的中率: {case1_second_rate:.2f}%")

    print(f"\n【ケース2: 予想1位が外れた場合】")
    print(f"レース数: {case2_count:,} ({case2_count/total*100:.1f}%)")
    print(f"2位予想的中率: {case2_second_rate:.2f}%")
    print(f"→ ケース1より {case1_second_rate - case2_second_rate:.2f}pt 低い")

    print(f"\n【全体】")
    print(f"2位予想的中率: {overall_second_rate:.2f}%")

    print(f"\n【考察】")
    print(f"- 学習データは主にケース1（実際の1位を条件）で作られている")
    print(f"- しかし予測時は{case2_count/total*100:.1f}%がケース2（予想1位外れ）となる")
    print(f"- この分布ミスマッチが2位予測精度低下の原因")

def propose_solution():
    """改善策の提案"""
    print("\n" + "=" * 80)
    print("【改善策の提案】")
    print("=" * 80)

    print("\n1. 予想1位を条件とした学習データ作成")
    print("   - 各レースで予想1位を計算（Stage1モデルまたはスコアベース）")
    print("   - 予想1位を条件として2位を学習")
    print("   - 予想1位が外れるケースも学習データに含まれる")

    print("\n2. アンサンブル学習")
    print("   - モデルA: 実際の1位を条件（現在のモデル）")
    print("   - モデルB: 予想1位を条件（新モデル）")
    print("   - 予測時: 0.5 * prob_A + 0.5 * prob_B")

    print("\n3. 予想1位の信頼度による重み付け")
    print("   - 予想1位の確率が高い → モデルAの重み大")
    print("   - 予想1位の確率が低い → モデルBの重み大")

    print("\n【推奨アクション】")
    print("1. prepare_stage2_data_v2() を実装")
    print("2. モデルBを学習")
    print("3. バックテストで精度比較")
    print("4. より良いモデルを採用")

def main():
    """メイン処理"""
    print("Stage2学習データの検証を開始します...")
    print(f"データベース: {DB_PATH}")
    print(f"モデルディレクトリ: {MODEL_DIR}")

    # モデル読み込み
    try:
        stage1, stage2, meta = load_models()
        print(f"\nモデル読み込み成功:")
        print(f"  Stage1 AUC: {meta['metrics']['stage1']['cv_auc_mean']:.4f}")
        print(f"  Stage2 AUC: {meta['metrics']['stage2']['cv_auc_mean']:.4f}")
        print(f"  Stage3 AUC: {meta['metrics']['stage3']['cv_auc_mean']:.4f}")
    except Exception as e:
        print(f"\nモデル読み込みエラー: {e}")
        return

    # 分析実行
    analysis, df = analyze_training_data_distribution()
    analyze_stage2_accuracy_by_condition()
    propose_solution()

    # 結果保存
    output_path = Path(__file__).parent.parent / "results" / f"stage2_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_path.parent.mkdir(exist_ok=True)
    analysis.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n分析結果を保存しました: {output_path}")

if __name__ == "__main__":
    main()
