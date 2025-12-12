"""
全コース（1-6）の会場×風向補正スコア計算

2025年通年データから抽出した会場別・風向別・コース別の補正パターン
風速3m以上、サンプル数10件以上、差分±10pt以上のパターンを収録

Priority 3実装: 2-6コースへの気象補正拡張
"""
import os
import json
from typing import Optional

# 補正テーブルのキャッシュ
_WIND_VENUE_TABLE = None


def _load_wind_venue_table():
    """風向×会場補正テーブルを読み込み"""
    global _WIND_VENUE_TABLE

    if _WIND_VENUE_TABLE is not None:
        return _WIND_VENUE_TABLE

    # テーブルファイルのパス
    current_dir = os.path.dirname(os.path.abspath(__file__))
    table_path = os.path.join(current_dir, 'wind_venue_table_all_courses.json')

    try:
        with open(table_path, 'r', encoding='utf-8') as f:
            _WIND_VENUE_TABLE = json.load(f)
        return _WIND_VENUE_TABLE
    except FileNotFoundError:
        # テーブルが見つからない場合は空の辞書を返す
        _WIND_VENUE_TABLE = {}
        return _WIND_VENUE_TABLE


def calculate_wind_venue_adjustment(
    course: int,
    venue_code: str,
    wind_speed: Optional[float],
    wind_direction: Optional[str]
) -> float:
    """
    会場×風向による補正スコアを計算（全コース対応）

    Args:
        course: コース番号(1-6)
        venue_code: 会場コード（'01'~'24'）
        wind_speed: 風速(m/s)
        wind_direction: 風向（'北'、'南東'など）

    Returns:
        補正スコア（-10.0 ~ +10.0点）
    """
    # 風速・風向がない場合は補正なし
    if wind_speed is None or wind_direction is None:
        return 0.0

    # 風速3m未満は補正なし
    if wind_speed < 3.0:
        return 0.0

    # テーブルを読み込み
    wind_table = _load_wind_venue_table()

    # コース番号を文字列に変換
    course_str = str(course)

    # コースがテーブルに存在しない場合は0
    if course_str not in wind_table:
        return 0.0

    course_table = wind_table[course_str]

    # 会場コードを整数に変換してから文字列化（'01' → '1'）
    try:
        venue_id = str(int(venue_code))
    except (ValueError, TypeError):
        return 0.0

    if venue_id not in course_table:
        return 0.0

    venue_table = course_table[venue_id]

    # 風向がテーブルに存在しない場合は0
    if wind_direction not in venue_table:
        return 0.0

    # 差分を取得
    diff_pt = venue_table[wind_direction]

    # 補正スコアに変換
    # 差分±30pt以上: ±10.0点（最大）
    # 差分±20pt以上: ±7.0点
    # 差分±15pt以上: ±5.0点
    # 差分±10pt以上: ±3.0点（最小）

    if abs(diff_pt) >= 30.0:
        score = 10.0 if diff_pt > 0 else -10.0
    elif abs(diff_pt) >= 20.0:
        score = 7.0 if diff_pt > 0 else -7.0
    elif abs(diff_pt) >= 15.0:
        score = 5.0 if diff_pt > 0 else -5.0
    else:
        # 差分±10pt以上（最小レベル）
        score = 3.0 if diff_pt > 0 else -3.0

    # スコア範囲を制限（-10.0 ~ +10.0点）
    return min(max(score, -10.0), 10.0)


if __name__ == "__main__":
    # テスト
    print("=" * 100)
    print("全コース対応の風向×会場補正スコアのテスト")
    print("=" * 100)

    # テーブルを読み込み
    wind_table = _load_wind_venue_table()

    print(f"\nテーブル読み込み: {len(wind_table)}コース")

    # コース別のパターン数
    print("\nコース別のパターン数:")
    for course in sorted(wind_table.keys(), key=int):
        venue_data = wind_table[course]
        pattern_count = sum(len(wind_dirs) for wind_dirs in venue_data.values())
        print(f"  {course}コース: {pattern_count}パターン")

    # テストケース
    test_cases = [
        # (コース, 会場, 風速, 風向, 期待される効果)
        (1, '13', 5.0, '西', "1コース尼崎西風（+31.5pt → +10.0点）"),
        (1, '02', 4.0, '北', "1コース戸田北風（-26.6pt → -7.0点）"),
        (2, '04', 4.0, '南南西', "2コース平和島南南西（+31.0pt → +10.0点）"),
        (3, '02', 4.0, '北', "3コース戸田北風（+12.9pt → +3.0点）"),
        (4, '08', 4.0, '北北東', "4コース常滑北北東（+16.7pt → +5.0点）"),
        (5, '17', 4.0, '南北西', "5コース宮島南北西（+14.5pt → +5.0点）"),
        (6, '07', 3.5, '南南西', "6コース蒲郡南南西（+13.5pt → +3.0点）"),
        (1, '02', 2.5, '北', "風速不足（補正なし）"),
        (1, '01', 5.0, '南', "データなし（補正なし）"),
    ]

    print("\nテストケース:")
    print(f"{'コース':<8} {'会場':<8} {'風速':<8} {'風向':<12} {'補正スコア':<12} {'説明':<50}")
    print("-" * 100)

    for course, venue, wind_speed, wind_dir, expected in test_cases:
        score = calculate_wind_venue_adjustment(course, venue, wind_speed, wind_dir)
        print(f"{course}コース  {venue:>4}   {wind_speed:>4.1f}m  {wind_dir:<12} {score:+6.1f}点     {expected}")

    # 各コースの上位3パターン
    print("\n" + "=" * 100)
    print("各コースの上位3パターン（差分の絶対値が大きい順）")
    print("=" * 100)

    venue_names = {
        '1': "桐生", '2': "戸田", '3': "江戸川", '4': "平和島", '5': "多摩川", '6': "浜名湖",
        '7': "蒲郡", '8': "常滑", '9': "津", '10': "三国", '11': "びわこ", '12': "住之江",
        '13': "尼崎", '14': "鳴門", '15': "丸亀", '16': "児島", '17': "宮島", '18': "徳山",
        '19': "下関", '20': "若松", '21': "芦屋", '22': "福岡", '23': "唐津", '24': "大村"
    }

    for course in sorted(wind_table.keys(), key=int):
        venue_data = wind_table[course]

        print(f"\n【{course}コース】")
        print(f"{'会場':<10} {'風向':<15} {'差分':<10} {'スコア':<10}")
        print("-" * 50)

        # 全パターンを差分の絶対値でソート
        all_patterns = []
        for venue_id, wind_dirs in venue_data.items():
            for wind_dir, diff in wind_dirs.items():
                all_patterns.append((venue_id, wind_dir, diff))

        all_patterns.sort(key=lambda x: abs(x[2]), reverse=True)

        for venue_id, wind_dir, diff in all_patterns[:3]:
            venue_name = venue_names.get(venue_id, f"会場{venue_id}")
            # スコア計算（テスト）
            venue_code = f"{int(venue_id):02d}"
            score = calculate_wind_venue_adjustment(int(course), venue_code, 5.0, wind_dir)
            print(f"{venue_name:<10} {wind_dir:<15} {diff:+5.1f}pt   {score:+5.1f}点")

    print("\n" + "=" * 100)
