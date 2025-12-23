"""信頼度BのCSVデータから詳細分析"""
import pandas as pd
from pathlib import Path

# CSVファイルを読み込み
CSV_PATH = Path(__file__).parent.parent / "results" / "confidence_b_comprehensive_20251209_132108.csv"
df = pd.read_csv(CSV_PATH, encoding='utf-8-sig')

print("=" * 80)
print("信頼度B予想の詳細分析結果")
print("=" * 80)
print(f"\n対象レース数: {len(df):,}レース")
print(f"期間: {df['race_date'].min()} ~ {df['race_date'].max()}")

# 1. スコアリング精度
print("\n" + "=" * 80)
print("1. スコアリング精度（実際の着順とスコア順位の関係）")
print("=" * 80)

print("\n実際の1着艇のスコア順位:")
for rank in range(1, 7):
    count = (df['actual_rank1_score_rank'] == rank).sum()
    pct = count / len(df) * 100
    print(f"  スコア{rank}位: {count:4d}レース ({pct:5.1f}%)")

print("\n実際の2着艇のスコア順位:")
for rank in range(1, 7):
    count = (df['actual_rank2_score_rank'] == rank).sum()
    pct = count / len(df) * 100
    print(f"  スコア{rank}位: {count:4d}レース ({pct:5.1f}%)")

print("\n実際の3着艇のスコア順位:")
for rank in range(1, 7):
    count = (df['actual_rank3_score_rank'] == rank).sum()
    pct = count / len(df) * 100
    print(f"  スコア{rank}位: {count:4d}レース ({pct:5.1f}%)")

# スコア上位3艇で決着した割合
score_top3_finish = ((df['actual_rank1_score_rank'] <= 3) &
                     (df['actual_rank2_score_rank'] <= 3) &
                     (df['actual_rank3_score_rank'] <= 3)).sum()
print(f"\nスコア上位3艇で決着: {score_top3_finish}/{len(df)} ({score_top3_finish/len(df)*100:.1f}%)")

# 2. スコア下位艇の関与
print("\n" + "=" * 80)
print("2. スコア下位艇（4-6位）の3連単への関与")
print("=" * 80)

low_in_result = df['low_score_in_result'].sum()
low_in_prediction = df['low_score_in_prediction'].sum()

print(f"\n実際の三連単にスコア下位艇が含まれる:")
print(f"  {low_in_result}/{len(df)}レース ({low_in_result/len(df)*100:.1f}%)")

print(f"\n予想にスコア下位艇を含む:")
print(f"  {low_in_prediction}/{len(df)}レース ({low_in_prediction/len(df)*100:.1f}%)")

# スコア下位が絡んだ時の的中率
df_low_in_result = df[df['low_score_in_result'] == 1]
df_no_low_in_result = df[df['low_score_in_result'] == 0]

if len(df_low_in_result) > 0:
    hit_rate_with_low = df_low_in_result['is_hit'].mean() * 100
    print(f"\nスコア下位艇が実際に絡んだ時の的中率:")
    print(f"  {df_low_in_result['is_hit'].sum()}/{len(df_low_in_result)} = {hit_rate_with_low:.2f}%")

if len(df_no_low_in_result) > 0:
    hit_rate_no_low = df_no_low_in_result['is_hit'].mean() * 100
    print(f"\nスコア上位3艇のみで決着した時の的中率:")
    print(f"  {df_no_low_in_result['is_hit'].sum()}/{len(df_no_low_in_result)} = {hit_rate_no_low:.2f}%")

# 3. 三連単的中率
print("\n" + "=" * 80)
print("3. 三連単的中率")
print("=" * 80)

hits = df['is_hit'].sum()
total = len(df)
hit_rate = hits / total * 100

print(f"\n的中: {hits}/{total}レース = {hit_rate:.2f}%")
print(f"ランダム期待値: 0.83%")
print(f"改善倍率: {hit_rate / 0.83:.1f}倍")

# 4. 的中・不的中レースの比較
print("\n" + "=" * 80)
print("4. 的中・不的中レースの比較")
print("=" * 80)

df_hit = df[df['is_hit'] == 1]
df_miss = df[df['is_hit'] == 0]

print(f"\n的中レース: {len(df_hit)}レース")
print(f"不的中レース: {len(df_miss)}レース")

# オッズ比較
print("\n【払戻金（実際のオッズ）の比較】")
if len(df_hit) > 0:
    print(f"\n的中時の払戻金:")
    print(f"  平均: {df_hit['actual_odds'].mean():.2f}倍")
    print(f"  中央値: {df_hit['actual_odds'].median():.2f}倍")
    print(f"  最小: {df_hit['actual_odds'].min():.2f}倍")
    print(f"  最大: {df_hit['actual_odds'].max():.2f}倍")

if len(df_miss) > 0:
    print(f"\n不的中時の払戻金:")
    print(f"  平均: {df_miss['actual_odds'].mean():.2f}倍")
    print(f"  中央値: {df_miss['actual_odds'].median():.2f}倍")
    print(f"  最小: {df_miss['actual_odds'].min():.2f}倍")
    print(f"  最大: {df_miss['actual_odds'].max():.2f}倍")

# オッズ帯別的中率
print("\n【不的中レースのオッズ分布】")
miss_odds_ranges = [
    (0, 10, "10倍未満"),
    (10, 30, "10-30倍"),
    (30, 100, "30-100倍"),
    (100, float('inf'), "100倍以上")
]

for low, high, label in miss_odds_ranges:
    count = ((df_miss['actual_odds'] >= low) & (df_miss['actual_odds'] < high)).sum()
    pct = count / len(df_miss) * 100 if len(df_miss) > 0 else 0
    print(f"  {label}: {count}レース ({pct:.1f}%)")

# 1号艇の成績
print("\n【1号艇の成績】")
if len(df_hit) > 0:
    pit1_in_top3_hit = (df_hit['pit1_actual_rank'] <= 3).sum()
    print(f"\n的中時に1号艇が3着以内:")
    print(f"  {pit1_in_top3_hit}/{len(df_hit)} = {pit1_in_top3_hit/len(df_hit)*100:.1f}%")

if len(df_miss) > 0:
    pit1_in_top3_miss = (df_miss['pit1_actual_rank'] <= 3).sum()
    print(f"\n不的中時に1号艇が3着以内:")
    print(f"  {pit1_in_top3_miss}/{len(df_miss)} = {pit1_in_top3_miss/len(df_miss)*100:.1f}%")

# スコア1位艇の実際の着順
print("\n【スコア1位艇の実際の着順】")
if len(df_hit) > 0:
    print(f"\n的中時:")
    for rank in [1, 2, 3]:
        count = (df_hit['top_score_actual_rank'] == rank).sum()
        pct = count / len(df_hit) * 100 if len(df_hit) > 0 else 0
        print(f"  {rank}着: {count}レース ({pct:.1f}%)")

if len(df_miss) > 0:
    print(f"\n不的中時:")
    for rank in [1, 2, 3]:
        count = (df_miss['top_score_actual_rank'] == rank).sum()
        pct = count / len(df_miss) * 100 if len(df_miss) > 0 else 0
        print(f"  {rank}着: {count}レース ({pct:.1f}%)")

    top3_outside = (df_miss['top_score_actual_rank'] > 3).sum()
    pct = top3_outside / len(df_miss) * 100 if len(df_miss) > 0 else 0
    print(f"  3着圏外: {top3_outside}レース ({pct:.1f}%)")

# 5. スコア分布と的中率の関係
print("\n" + "=" * 80)
print("5. スコア分布と的中率の関係")
print("=" * 80)

print("\n【スコア1位~6位の差（スコア差）と的中率】")
print(f"全体の平均スコア差: {df['score_gap'].mean():.2f}")
print(f"的中時の平均スコア差: {df_hit['score_gap'].mean():.2f}" if len(df_hit) > 0 else "")
print(f"不的中時の平均スコア差: {df_miss['score_gap'].mean():.2f}" if len(df_miss) > 0 else "")

# スコア差カテゴリ別的中率
print("\n【スコア差カテゴリ別】")
categories = df['score_gap_category'].unique()
for cat in sorted([c for c in categories if pd.notna(c)]):
    df_cat = df[df['score_gap_category'] == cat]
    if len(df_cat) > 0:
        hits_cat = df_cat['is_hit'].sum()
        rate_cat = hits_cat / len(df_cat) * 100
        print(f"  {cat}: {hits_cat}/{len(df_cat)} = {rate_cat:.1f}%")

# 6. まとめ
print("\n" + "=" * 80)
print("6. 重要な発見")
print("=" * 80)

# スコア1位艇が1着になる確率
score1_rank1 = (df['actual_rank1_score_rank'] == 1).sum()
score1_rank1_rate = score1_rank1 / len(df) * 100
print(f"\n1) スコア1位艇が実際に1着: {score1_rank1}/{len(df)} = {score1_rank1_rate:.1f}%")

# スコア下位艇が絡むと的中率が激減
if len(df_low_in_result) > 0 and len(df_no_low_in_result) > 0:
    hit_diff = hit_rate_no_low - hit_rate_with_low
    print(f"\n2) スコア下位艇が絡むと的中率が{hit_diff:.1f}pt低下")
    print(f"   スコア上位3艇のみ: {hit_rate_no_low:.1f}%")
    print(f"   スコア下位艇含む: {hit_rate_with_low:.1f}%")

# 不的中レースは高配当レースが多い
high_odds_miss = (df_miss['actual_odds'] >= 30).sum()
high_odds_miss_rate = high_odds_miss / len(df_miss) * 100 if len(df_miss) > 0 else 0
print(f"\n3) 不的中レースの{high_odds_miss_rate:.1f}%が30倍以上の高配当レース")

print("\n" + "=" * 80)
print("分析完了")
print("=" * 80)
