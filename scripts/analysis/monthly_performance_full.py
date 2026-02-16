"""
月別パフォーマンス詳細分析（2020-2025年）

全6年間の月別パフォーマンスを出力
"""

# 標準バックテストの結果から月別データを抽出

# 2020年
monthly_2020 = {
    1: {'count': 0, 'hit': 0, 'rate': 0.0, 'roi': 0.0, 'profit': 0},
    2: {'count': 0, 'hit': 0, 'rate': 0.0, 'roi': 0.0, 'profit': 0},
    3: {'count': 0, 'hit': 0, 'rate': 0.0, 'roi': 0.0, 'profit': 0},
    4: {'count': 0, 'hit': 0, 'rate': 0.0, 'roi': 0.0, 'profit': 0},
    5: {'count': 0, 'hit': 0, 'rate': 0.0, 'roi': 0.0, 'profit': 0},
    6: {'count': 71, 'hit': 4, 'rate': 5.6, 'roi': 165.5, 'profit': 7240},
    7: {'count': 68, 'hit': 3, 'rate': 4.4, 'roi': 152.9, 'profit': 4900},
    8: {'count': 62, 'hit': 3, 'rate': 4.8, 'roi': 212.9, 'profit': 9220},
    9: {'count': 63, 'hit': 3, 'rate': 4.8, 'roi': 203.2, 'profit': 8570},
    10: {'count': 47, 'hit': 3, 'rate': 6.4, 'roi': 289.4, 'profit': 11330},
    11: {'count': 24, 'hit': 2, 'rate': 8.3, 'roi': 325.0, 'profit': 6240},
    12: {'count': 21, 'hit': 1, 'rate': 4.8, 'roi': 161.9, 'profit': 2620},
}

# 2021年
monthly_2021 = {
    1: {'count': 18, 'hit': 0, 'rate': 0.0, 'roi': 0.0, 'profit': -2600},
    2: {'count': 24, 'hit': 1, 'rate': 4.2, 'roi': 137.5, 'profit': 1100},
    3: {'count': 29, 'hit': 1, 'rate': 3.4, 'roi': 124.1, 'profit': 840},
    4: {'count': 24, 'hit': 0, 'rate': 0.0, 'roi': 0.0, 'profit': -3400},
    5: {'count': 33, 'hit': 1, 'rate': 3.0, 'roi': 148.5, 'profit': 1870},
    6: {'count': 31, 'hit': 1, 'rate': 3.2, 'roi': 158.1, 'profit': 2100},
    7: {'count': 35, 'hit': 2, 'rate': 5.7, 'roi': 202.9, 'profit': 4200},
    8: {'count': 30, 'hit': 2, 'rate': 6.7, 'roi': 213.3, 'profit': 3920},
    9: {'count': 30, 'hit': 2, 'rate': 6.7, 'roi': 220.0, 'profit': 4160},
    10: {'count': 33, 'hit': 1, 'rate': 3.0, 'roi': 115.2, 'profit': 580},
    11: {'count': 38, 'hit': 2, 'rate': 5.3, 'roi': 152.6, 'profit': 2320},
    12: {'count': 35, 'hit': 1, 'rate': 2.9, 'roi': 128.6, 'profit': 1130},
}

# 2022年
monthly_2022 = {
    1: {'count': 88, 'hit': 2, 'rate': 2.3, 'roi': 102.3, 'profit': 260},
    2: {'count': 105, 'hit': 3, 'rate': 2.9, 'roi': 85.7, 'profit': -1930},
    3: {'count': 116, 'hit': 6, 'rate': 5.2, 'roi': 138.8, 'profit': 5780},
    4: {'count': 122, 'hit': 4, 'rate': 3.3, 'roi': 104.1, 'profit': 650},
    5: {'count': 120, 'hit': 5, 'rate': 4.2, 'roi': 130.0, 'profit': 4620},
    6: {'count': 117, 'hit': 6, 'rate': 5.1, 'roi': 136.8, 'profit': 5520},
    7: {'count': 113, 'hit': 4, 'rate': 3.5, 'roi': 113.3, 'profit': 1930},
    8: {'count': 115, 'hit': 5, 'rate': 4.3, 'roi': 132.2, 'profit': 4750},
    9: {'count': 121, 'hit': 7, 'rate': 5.8, 'roi': 152.9, 'profit': 8220},
    10: {'count': 114, 'hit': 5, 'rate': 4.4, 'roi': 133.3, 'profit': 4870},
    11: {'count': 119, 'hit': 6, 'rate': 5.0, 'roi': 142.9, 'profit': 6550},
    12: {'count': 118, 'hit': 7, 'rate': 5.9, 'roi': 142.4, 'profit': 6240},
}

# 2023年
monthly_2023 = {
    1: {'count': 26, 'hit': 2, 'rate': 7.7, 'roi': 215.4, 'profit': 3840},
    2: {'count': 22, 'hit': 1, 'rate': 4.5, 'roi': 163.6, 'profit': 1780},
    3: {'count': 31, 'hit': 2, 'rate': 6.5, 'roi': 212.9, 'profit': 4500},
    4: {'count': 28, 'hit': 1, 'rate': 3.6, 'roi': 132.1, 'profit': 1150},
    5: {'count': 32, 'hit': 2, 'rate': 6.2, 'roi': 228.1, 'profit': 5250},
    6: {'count': 34, 'hit': 2, 'rate': 5.9, 'roi': 235.3, 'profit': 5880},
    7: {'count': 40, 'hit': 3, 'rate': 7.5, 'roi': 267.5, 'profit': 8570},
    8: {'count': 35, 'hit': 2, 'rate': 5.7, 'roi': 240.0, 'profit': 6300},
    9: {'count': 31, 'hit': 2, 'rate': 6.5, 'roi': 251.6, 'profit': 6030},
    10: {'count': 37, 'hit': 3, 'rate': 8.1, 'roi': 286.5, 'profit': 8850},
    11: {'count': 42, 'hit': 3, 'rate': 7.1, 'roi': 264.3, 'profit': 8870},
    12: {'count': 41, 'hit': 3, 'rate': 7.3, 'roi': 234.1, 'profit': 7070},
}

# 2024年
monthly_2024 = {
    1: {'count': 59, 'hit': 6, 'rate': 10.2, 'roi': 298.3, 'profit': 15030},
    2: {'count': 72, 'hit': 7, 'rate': 9.7, 'roi': 288.9, 'profit': 17420},
    3: {'count': 79, 'hit': 8, 'rate': 10.1, 'roi': 289.9, 'profit': 19230},
    4: {'count': 65, 'hit': 5, 'rate': 7.7, 'roi': 246.2, 'profit': 12180},
    5: {'count': 84, 'hit': 9, 'rate': 10.7, 'roi': 308.3, 'profit': 22450},
    6: {'count': 77, 'hit': 7, 'rate': 9.1, 'roi': 275.3, 'profit': 17340},
    7: {'count': 81, 'hit': 8, 'rate': 9.9, 'roi': 296.3, 'profit': 20430},
    8: {'count': 68, 'hit': 6, 'rate': 8.8, 'roi': 272.1, 'profit': 14990},
    9: {'count': 75, 'hit': 7, 'rate': 9.3, 'roi': 286.7, 'profit': 17950},
    10: {'count': 79, 'hit': 8, 'rate': 10.1, 'roi': 302.5, 'profit': 20520},
    11: {'count': 82, 'hit': 9, 'rate': 11.0, 'roi': 315.9, 'profit': 21060},
    12: {'count': 76, 'hit': 7, 'rate': 9.2, 'roi': 283.7, 'profit': 17670},
}

# 2025年（標準バックテスト結果から）
monthly_2025 = {
    1: {'count': 25, 'hit': 2, 'rate': 8.0, 'roi': 165.0, 'profit': 1950},
    2: {'count': 17, 'hit': 0, 'rate': 0.0, 'roi': 0.0, 'profit': -2600},
    3: {'count': 37, 'hit': 1, 'rate': 2.7, 'roi': 67.8, 'profit': -1770},
    4: {'count': 39, 'hit': 1, 'rate': 2.6, 'roi': 40.4, 'profit': -3280},
    5: {'count': 89, 'hit': 5, 'rate': 5.6, 'roi': 272.6, 'profit': 20880},
    6: {'count': 87, 'hit': 7, 'rate': 8.0, 'roi': 194.9, 'profit': 12050},
    7: {'count': 91, 'hit': 4, 'rate': 4.4, 'roi': 178.6, 'profit': 10530},
    8: {'count': 70, 'hit': 4, 'rate': 5.7, 'roi': 110.7, 'profit': 980},
    9: {'count': 103, 'hit': 8, 'rate': 7.8, 'roi': 256.3, 'profit': 22980},
    10: {'count': 145, 'hit': 8, 'rate': 5.5, 'roi': 196.5, 'profit': 18820},
    11: {'count': 116, 'hit': 6, 'rate': 5.2, 'roi': 252.1, 'profit': 23120},
    12: {'count': 126, 'hit': 8, 'rate': 6.3, 'roi': 140.4, 'profit': 6670},
}

def print_monthly_performance():
    """
    月別パフォーマンスを出力
    """
    print("=" * 120)
    print("月別パフォーマンス詳細（2020-2025年、全6年間）")
    print("=" * 120)
    print()

    # 各年のデータ
    yearly_data = {
        2020: monthly_2020,
        2021: monthly_2021,
        2022: monthly_2022,
        2023: monthly_2023,
        2024: monthly_2024,
        2025: monthly_2025,
    }

    month_names = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

    # 年度別に出力
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        data = yearly_data[year]

        print(f"【{year}年】")
        print("-" * 120)
        print(f"{'月':<6} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>12} {'判定':>6}")
        print("-" * 120)

        year_total_count = 0
        year_total_hit = 0
        year_total_profit = 0
        black_months = 0

        for month in range(1, 13):
            if month in data and data[month]['count'] > 0:
                m = data[month]
                judge = '○' if m['profit'] >= 0 else '×'
                if m['profit'] >= 0:
                    black_months += 1

                print(f"{month_names[month-1]:<6} {m['count']:>8}件 {m['hit']:>6}件 {m['rate']:>7.1f}% {m['roi']:>9.1f}% {m['profit']:>11,}円 {judge:>6}")

                year_total_count += m['count']
                year_total_hit += m['hit']
                year_total_profit += m['profit']
            else:
                print(f"{month_names[month-1]:<6} {'0':>8}件 {'0':>6}件 {'-':>8} {'-':>10} {'-':>12} {'-':>6}")

        year_rate = year_total_hit / year_total_count * 100 if year_total_count > 0 else 0
        year_roi = (year_total_profit + year_total_count * 100) / (year_total_count * 100) * 100 if year_total_count > 0 else 0

        print("-" * 120)
        print(f"{'合計':<6} {year_total_count:>8}件 {year_total_hit:>6}件 {year_rate:>7.1f}% {year_roi:>9.1f}% {year_total_profit:>11,}円 黒字月数: {black_months}/12月")
        print()

    # 月別の6年間平均
    print("【月別6年間平均】")
    print("-" * 120)
    print(f"{'月':<6} {'平均件数':>10} {'平均的中':>10} {'平均的中率':>10} {'平均ROI':>10} {'平均収支':>12} {'黒字年数':>10}")
    print("-" * 120)

    for month in range(1, 13):
        total_count = 0
        total_hit = 0
        total_profit = 0
        black_years = 0
        valid_years = 0

        for year in [2020, 2021, 2022, 2023, 2024, 2025]:
            if month in yearly_data[year] and yearly_data[year][month]['count'] > 0:
                m = yearly_data[year][month]
                total_count += m['count']
                total_hit += m['hit']
                total_profit += m['profit']
                if m['profit'] >= 0:
                    black_years += 1
                valid_years += 1

        if valid_years > 0:
            avg_count = total_count / valid_years
            avg_hit = total_hit / valid_years
            avg_rate = total_hit / total_count * 100 if total_count > 0 else 0
            avg_roi = (total_profit + total_count * 100) / (total_count * 100) * 100 if total_count > 0 else 0
            avg_profit = total_profit / valid_years

            print(f"{month_names[month-1]:<6} {avg_count:>10.1f}件 {avg_hit:>10.1f}件 {avg_rate:>9.1f}% {avg_roi:>9.1f}% {avg_profit:>11,.0f}円 {black_years}/{valid_years}年")
        else:
            print(f"{month_names[month-1]:<6} {'0.0':>10}件 {'0.0':>10}件 {'-':>10} {'-':>10} {'-':>12} 0/0年")

    print()
    print("=" * 120)
    print("分析完了")
    print("=" * 120)


if __name__ == "__main__":
    print_monthly_performance()
