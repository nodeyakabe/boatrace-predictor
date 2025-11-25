"""
選手データの包括的分析スクリプト

目的:
1. 選手の基本統計情報の集計
2. パフォーマンス指標の計算
3. 強み・弱みの特定
4. 選手詳細ページ用のデータ生成
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import json

print("=" * 80)
print("選手データ包括分析")
print("=" * 80)
print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# データベース接続
conn = sqlite3.connect('data/boatrace.db')

# ========================================
# 1. 選手の基本統計情報
# ========================================
print("[Step 1] 選手の基本統計情報の集計")
print("-" * 80)

# 全選手の基本情報を取得（最新のエントリーから）
query_basic = """
SELECT
    racer_number,
    racer_name,
    racer_rank,
    racer_home,
    racer_age,
    racer_weight,
    win_rate,
    second_rate,
    third_rate,
    f_count,
    l_count,
    avg_st
FROM entries
WHERE race_id IN (
    SELECT id FROM races
    WHERE race_date >= '2024-01-01'
)
GROUP BY racer_number
HAVING MAX(created_at)
"""

df_racers = pd.read_sql(query_basic, conn)
print(f"  分析対象選手数: {len(df_racers):,}名")
print()

# 級別の分布
print("級別の分布:")
rank_dist = df_racers['racer_rank'].value_counts().sort_index()
for rank, count in rank_dist.items():
    pct = count / len(df_racers) * 100
    print(f"  {rank}: {count:>4}名 ({pct:>5.2f}%)")
print()

# 年齢の統計
print("年齢の統計:")
print(f"  平均: {df_racers['racer_age'].mean():.1f}歳")
print(f"  中央値: {df_racers['racer_age'].median():.0f}歳")
print(f"  最小-最大: {df_racers['racer_age'].min():.0f}〜{df_racers['racer_age'].max():.0f}歳")
print()

# 勝率の統計
print("勝率の統計（級別ごと）:")
for rank in ['A1', 'A2', 'B1', 'B2']:
    rank_data = df_racers[df_racers['racer_rank'] == rank]['win_rate']
    if len(rank_data) > 0:
        print(f"  {rank}: 平均{rank_data.mean():.2f}%, 中央値{rank_data.median():.2f}%")
print()

# ========================================
# 2. パフォーマンス指標の計算
# ========================================
print("[Step 2] パフォーマンス指標の計算")
print("-" * 80)

# 2024年のレース結果を集計
query_results = """
SELECT
    e.racer_number,
    COUNT(*) as total_races,
    SUM(CASE WHEN r.rank = '1' THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN r.rank IN ('1', '2') THEN 1 ELSE 0 END) as top2,
    SUM(CASE WHEN r.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as top3,
    AVG(CAST(r.rank AS REAL)) as avg_rank,
    SUM(CASE WHEN e.pit_number = 1 THEN 1 ELSE 0 END) as pit1_count,
    SUM(CASE WHEN e.pit_number = 1 AND r.rank = '1' THEN 1 ELSE 0 END) as pit1_wins
FROM entries e
INNER JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
INNER JOIN races ra ON e.race_id = ra.id
WHERE ra.race_date >= '2024-01-01'
    AND r.rank IS NOT NULL
    AND r.rank != ''
GROUP BY e.racer_number
HAVING total_races >= 10
"""

df_performance = pd.read_sql(query_results, conn)
print(f"  パフォーマンスデータ取得: {len(df_performance):,}名")

# 勝率・連対率・3連対率を計算
df_performance['actual_win_rate'] = df_performance['wins'] / df_performance['total_races'] * 100
df_performance['actual_place_rate'] = df_performance['top2'] / df_performance['total_races'] * 100
df_performance['actual_show_rate'] = df_performance['top3'] / df_performance['total_races'] * 100
df_performance['pit1_win_rate'] = np.where(
    df_performance['pit1_count'] > 0,
    df_performance['pit1_wins'] / df_performance['pit1_count'] * 100,
    0
)

print(f"  実勝率の統計:")
print(f"    平均: {df_performance['actual_win_rate'].mean():.2f}%")
print(f"    中央値: {df_performance['actual_win_rate'].median():.2f}%")
print(f"    最大: {df_performance['actual_win_rate'].max():.2f}%")
print()

# ========================================
# 3. 強み・弱みの分析
# ========================================
print("[Step 3] 選手の強み・弱みの特定")
print("-" * 80)

# 選手とパフォーマンスをマージ
df_analysis = df_racers.merge(df_performance, on='racer_number', how='left')

# 1号艇勝率による分類
df_analysis['pit1_strength'] = pd.cut(
    df_analysis['pit1_win_rate'].fillna(0),
    bins=[0, 30, 50, 70, 100],
    labels=['弱い', '普通', '強い', '非常に強い']
)

# スタート力の評価
df_analysis['start_quality'] = pd.cut(
    df_analysis['avg_st'].fillna(0.20),
    bins=[0, 0.13, 0.16, 0.20, 1.0],
    labels=['優秀', '良好', '普通', '要改善']
)

# フライング・出遅れリスク
df_analysis['reliability'] = np.where(
    df_analysis['f_count'] + df_analysis['l_count'] == 0, '高信頼',
    np.where(df_analysis['f_count'] + df_analysis['l_count'] <= 2, '中信頼', '低信頼')
)

print("1号艇勝率の分布:")
pit1_dist = df_analysis['pit1_strength'].value_counts()
for strength, count in pit1_dist.items():
    print(f"  {strength}: {count}名")
print()

print("スタート力の分布:")
start_dist = df_analysis['start_quality'].value_counts()
for quality, count in start_dist.items():
    print(f"  {quality}: {count}名")
print()

print("信頼性の分布:")
reliability_dist = df_analysis['reliability'].value_counts()
for rel, count in reliability_dist.items():
    print(f"  {rel}: {count}名")
print()

# ========================================
# 4. 選手別詳細データの生成
# ========================================
print("[Step 4] 選手別詳細データの生成")
print("-" * 80)

# 選手ごとの詳細情報を辞書化
racer_profiles = {}

for idx, row in df_analysis.iterrows():
    racer_num = row['racer_number']

    # 基本情報
    profile = {
        'racer_number': racer_num,
        'racer_name': row['racer_name'],
        'racer_rank': row['racer_rank'],
        'racer_home': row['racer_home'],
        'racer_age': int(row['racer_age']) if pd.notna(row['racer_age']) else None,
        'racer_weight': float(row['racer_weight']) if pd.notna(row['racer_weight']) else None,

        # 成績
        'statistics': {
            'win_rate': float(row['win_rate']) if pd.notna(row['win_rate']) else 0,
            'second_rate': float(row['second_rate']) if pd.notna(row['second_rate']) else 0,
            'third_rate': float(row['third_rate']) if pd.notna(row['third_rate']) else 0,
            'total_races': int(row['total_races']) if pd.notna(row['total_races']) else 0,
            'wins': int(row['wins']) if pd.notna(row['wins']) else 0,
            'actual_win_rate': float(row['actual_win_rate']) if pd.notna(row['actual_win_rate']) else 0,
            'actual_place_rate': float(row['actual_place_rate']) if pd.notna(row['actual_place_rate']) else 0,
            'actual_show_rate': float(row['actual_show_rate']) if pd.notna(row['actual_show_rate']) else 0,
            'avg_rank': float(row['avg_rank']) if pd.notna(row['avg_rank']) else 0,
        },

        # スタート
        'start_performance': {
            'avg_st': float(row['avg_st']) if pd.notna(row['avg_st']) else 0,
            'f_count': int(row['f_count']) if pd.notna(row['f_count']) else 0,
            'l_count': int(row['l_count']) if pd.notna(row['l_count']) else 0,
            'start_quality': str(row['start_quality']) if pd.notna(row['start_quality']) else '不明',
            'reliability': str(row['reliability']) if pd.notna(row['reliability']) else '不明',
        },

        # 1号艇成績
        'pit1_performance': {
            'pit1_count': int(row['pit1_count']) if pd.notna(row['pit1_count']) else 0,
            'pit1_wins': int(row['pit1_wins']) if pd.notna(row['pit1_wins']) else 0,
            'pit1_win_rate': float(row['pit1_win_rate']) if pd.notna(row['pit1_win_rate']) else 0,
            'pit1_strength': str(row['pit1_strength']) if pd.notna(row['pit1_strength']) else '不明',
        },
    }

    racer_profiles[racer_num] = profile

print(f"  選手プロファイル生成: {len(racer_profiles):,}名")
print()

# JSONファイルとして保存
with open('data/racer_profiles.json', 'w', encoding='utf-8') as f:
    json.dump(racer_profiles, f, ensure_ascii=False, indent=2)
print(f"  保存: data/racer_profiles.json")
print()

# ========================================
# 5. トップ選手の抽出
# ========================================
print("[Step 5] トップ選手の抽出")
print("-" * 80)

# 実勝率トップ20
df_top_win = df_analysis[df_analysis['total_races'] >= 50].nlargest(20, 'actual_win_rate')
print("実勝率トップ20:")
print(f"{'順位':<6} {'選手番号':<10} {'選手名':<20} {'級別':<6} {'出走数':<8} {'実勝率':<10}")
print("-" * 80)
for rank, (idx, row) in enumerate(df_top_win.iterrows(), 1):
    print(f"{rank:<6} {row['racer_number']:<10} {row['racer_name']:<20} {row['racer_rank']:<6} {int(row['total_races']):<8} {row['actual_win_rate']:.2f}%")
print()

# 1号艇勝率トップ20
df_top_pit1 = df_analysis[df_analysis['pit1_count'] >= 20].nlargest(20, 'pit1_win_rate')
print("1号艇勝率トップ20:")
print(f"{'順位':<6} {'選手番号':<10} {'選手名':<20} {'級別':<6} {'1号出走':<10} {'1号勝率':<10}")
print("-" * 80)
for rank, (idx, row) in enumerate(df_top_pit1.iterrows(), 1):
    print(f"{rank:<6} {row['racer_number']:<10} {row['racer_name']:<20} {row['racer_rank']:<6} {int(row['pit1_count']):<10} {row['pit1_win_rate']:.2f}%")
print()

# ========================================
# 6. サマリーCSVの出力
# ========================================
print("[Step 6] サマリーデータの出力")
print("-" * 80)

# CSVとして保存
output_columns = [
    'racer_number', 'racer_name', 'racer_rank', 'racer_home', 'racer_age',
    'win_rate', 'second_rate', 'third_rate',
    'total_races', 'wins', 'actual_win_rate', 'actual_place_rate', 'actual_show_rate',
    'avg_rank', 'avg_st', 'f_count', 'l_count',
    'pit1_count', 'pit1_wins', 'pit1_win_rate',
    'pit1_strength', 'start_quality', 'reliability'
]

df_output = df_analysis[output_columns].copy()
df_output.to_csv('data/racer_analysis_summary.csv', index=False, encoding='utf-8-sig')
print(f"  保存: data/racer_analysis_summary.csv")
print(f"  レコード数: {len(df_output):,}件")
print()

conn.close()

print("=" * 80)
print(f"完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
print()
print("生成ファイル:")
print("  1. data/racer_profiles.json - 選手別詳細プロファイル（選手ページ用）")
print("  2. data/racer_analysis_summary.csv - 選手統計サマリー")
