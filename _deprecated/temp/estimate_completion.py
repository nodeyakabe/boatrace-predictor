"""レース詳細補完の完了予測"""
from datetime import datetime, timedelta

# 前回の測定値（サマリーから）
previous_missing = 227681  # 前回チェック時（71.1%完了）
current_missing = 38694    # 現在

# 処理済み
processed = previous_missing - current_missing

print("=" * 80)
print("レース詳細補完 - 完了予測")
print("=" * 80)
print(f"前回欠損数: {previous_missing:,}件 (レースレベル換算)")
print(f"現在欠損数: {current_missing:,}件")
print()

# 注: 前回の値は実際には40,494レースの処理対象でした
# (227,681は6艇分のレコード数だった可能性)
# 実際の進捗を再計算

previous_race_missing = 40494  # 前回の実レース欠損数（補完スクリプト起動時）
current_race_missing = 38694   # 現在の欠損数

actual_processed = previous_race_missing - current_race_missing

# 経過時間を推定（前回チェックから現在まで）
# サマリーから: 決まり手完了が129分前、その後にレース詳細が開始
# 仮に3-4時間経過していると仮定
elapsed_hours = 3.5  # 推定

if actual_processed > 0:
    processing_rate = actual_processed / (elapsed_hours * 60)  # 件/分
    remaining_minutes = current_race_missing / processing_rate

    print(f"処理済みレース数: {actual_processed:,}件")
    print(f"推定経過時間: {elapsed_hours:.1f}時間")
    print(f"処理速度: {processing_rate:.2f}件/分 ({processing_rate*60:.1f}件/時)")
    print()
    print(f"残りレース数: {current_race_missing:,}件")
    print(f"予想残り時間: {remaining_minutes:.0f}分 ({remaining_minutes/60:.1f}時間)")
    print()

    completion_time = datetime.now() + timedelta(minutes=remaining_minutes)
    print(f"完了予想時刻: {completion_time.strftime('%Y-%m-%d %H:%M')}")
else:
    print("処理が完了しているか、データに不整合があります")

print("=" * 80)
