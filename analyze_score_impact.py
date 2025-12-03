"""
統合スコアへのbefore_scoreの影響を分析
"""

from src.analysis.race_predictor import RacePredictor

race_id = 132764

print("=" * 80)
print("統合スコアへのbefore_scoreの影響分析")
print(f"race_id: {race_id}")
print("=" * 80)
print()

predictor = RacePredictor(db_path='data/boatrace.db')
predictions = predictor.predict_race(race_id)

print("全艇のスコア詳細:")
print("-" * 80)
print(f"{'艇':^4} | {'PRE':^6} | {'BEFORE':^7} | {'統合':^6} | {'重み':^12} | {'差分':^6}")
print("-" * 80)

# PRE単体でソート
pre_sorted = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)

for pred in predictions:
    pit = pred['pit_number']
    pre = pred.get('pre_score', 0)
    before = pred.get('beforeinfo_score', 0)
    total = pred.get('total_score', 0)
    pre_w = pred.get('pre_weight', 0)
    before_w = pred.get('before_weight', 0)

    # 理論値との差分確認
    theoretical = pre * pre_w + before * before_w
    diff = total - theoretical

    print(f"{pit:2d}号 | {pre:6.1f} | {before:7.1f} | {total:6.1f} | {pre_w:.2f}/{before_w:.2f} | {diff:6.2f}")

print("-" * 80)
print()

# PRE単体順位と統合後順位の比較
print("順位比較:")
print("-" * 80)

# PRE単体での順位
pre_rank = {pred['pit_number']: i+1 for i, pred in enumerate(pre_sorted)}

# 統合スコアでの順位
total_sorted = sorted(predictions, key=lambda x: x.get('total_score', 0), reverse=True)
total_rank = {pred['pit_number']: i+1 for i, pred in enumerate(total_sorted)}

print(f"{'艇':^4} | {'PRE順位':^8} | {'統合順位':^8} | {'変動':^6}")
print("-" * 80)

for pit in range(1, 7):
    pre_r = pre_rank.get(pit, '-')
    total_r = total_rank.get(pit, '-')
    change = total_r - pre_r if isinstance(pre_r, int) and isinstance(total_r, int) else '-'
    change_str = f"{change:+d}" if isinstance(change, int) else '-'

    print(f"{pit:2d}号 | {pre_r:^8} | {total_r:^8} | {change_str:^6}")

print("-" * 80)
print()

# 最も影響が大きかったケースを探す
max_change = 0
for pit in range(1, 7):
    pre_r = pre_rank.get(pit, 0)
    total_r = total_rank.get(pit, 0)
    if isinstance(pre_r, int) and isinstance(total_r, int):
        change = abs(total_r - pre_r)
        if change > max_change:
            max_change = change

print(f"最大順位変動: {max_change}位")
if max_change == 0:
    print("→ before_scoreの影響で順位が変わった艇はありません")
    print()
    print("理由:")
    print("  1. beforeinfo_scoreの絶対値が小さい（-15〜+18点程度）")
    print("  2. before_weightが0.15と小さい（PRE_SCOREが85%の影響）")
    print("  3. PRE_SCOREの差が大きいため、before_scoreでは覆せない")
else:
    print(f"→ {max_change}位の変動がありました")

print()
print("=" * 80)
