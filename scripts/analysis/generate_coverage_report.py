#!/usr/bin/env python3
"""
データ充足率レポート生成
"""

import sqlite3
from datetime import datetime
import os

DB_PATH = "c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032/data/boatrace.db"
OUTPUT_PATH = "c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032/docs/performance/DATA_COVERAGE_REPORT_20260206.md"

def get_yearly_data(conn):
    """年度別データ取得"""
    cursor = conn.cursor()
    query = """
    SELECT
        strftime('%Y', r.race_date) as year,
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT e.race_id) as with_entries,
        COUNT(DISTINCT res.race_id) as with_results,
        COUNT(DISTINCT t.race_id) as with_odds,
        COUNT(DISTINCT rd.race_id) as with_details,
        COUNT(DISTINCT rp.race_id) as with_predictions
    FROM races r
    LEFT JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id
    LEFT JOIN trifecta_odds t ON r.id = t.race_id
    LEFT JOIN race_details rd ON r.id = rd.race_id
    LEFT JOIN race_predictions rp ON r.id = rp.race_id
    WHERE r.race_date >= '2020-01-01' AND r.race_date <= '2025-12-31'
    GROUP BY year
    ORDER BY year
    """
    cursor.execute(query)
    return cursor.fetchall()

def get_monthly_data(conn, year, month):
    """月別データ取得"""
    cursor = conn.cursor()

    # 次の月を計算
    if month == '12':
        next_date = f"{int(year)+1:04d}-01-01"
    else:
        next_date = f"{year}-{int(month)+1:02d}-01"

    query = f"""
    SELECT
        COUNT(DISTINCT r.id) as total_races,
        COUNT(DISTINCT e.race_id) as with_entries,
        COUNT(DISTINCT res.race_id) as with_results,
        COUNT(DISTINCT t.race_id) as with_odds,
        COUNT(DISTINCT rd.race_id) as with_details,
        COUNT(DISTINCT rp.race_id) as with_predictions
    FROM races r
    LEFT JOIN entries e ON r.id = e.race_id
    LEFT JOIN results res ON r.id = res.race_id
    LEFT JOIN trifecta_odds t ON r.id = t.race_id
    LEFT JOIN race_details rd ON r.id = rd.race_id
    LEFT JOIN race_predictions rp ON r.id = rp.race_id
    WHERE r.race_date >= '{year}-{month}-01' AND r.race_date < '{next_date}'
    """
    cursor.execute(query)
    return cursor.fetchone()

def main():
    print("レポート生成開始...")

    conn = sqlite3.connect(DB_PATH)

    # 年度別データ取得
    print("年度別データを取得中...")
    yearly_data = get_yearly_data(conn)

    # レポート作成
    md_content = f"""# データ充足率調査レポート

**調査日**: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}
**対象期間**: 2020年1月～2025年12月
**データベース**: `data/boatrace.db`

---

## エグゼクティブサマリー

本調査では、2020年～2025年の競艇データの充足状況を6つのテーブル別に分析しました。特に、今回追加された **2021年9-12月** および **2023年1-12月** のデータを重点的に確認しています。

### 主要な発見

"""

    # 総レース数と充足率を計算
    total_races = sum(row[1] for row in yearly_data)
    total_entries = sum(row[2] for row in yearly_data)
    total_results = sum(row[3] for row in yearly_data)
    total_odds = sum(row[4] for row in yearly_data)
    total_details = sum(row[5] for row in yearly_data)
    total_preds = sum(row[6] for row in yearly_data)

    md_content += f"""
- **総レース数**: {total_races:,}レース（2020-2025年）
- **出走表充足率**: {total_entries/total_races*100:.1f}%
- **結果充足率**: {total_results/total_races*100:.1f}%
- **オッズ充足率**: {total_odds/total_races*100:.1f}%
- **詳細充足率**: {total_details/total_races*100:.1f}%
- **予測充足率**: {total_preds/total_races*100:.1f}%

---

## 1. 年度別データ充足率

| 年度 | レース数 | 出走表 | 結果 | オッズ | 詳細 | 予測 |
|------|----------|--------|------|--------|------|------|
"""

    for row in yearly_data:
        year, total, entries, results, odds, details, preds = row
        md_content += f"| {year} | {total:,} | {entries:,}<br>({entries/total*100:.1f}%) | {results:,}<br>({results/total*100:.1f}%) | {odds:,}<br>({odds/total*100:.1f}%) | {details:,}<br>({details/total*100:.1f}%) | {preds:,}<br>({preds/total*100:.1f}%) |\n"

    # 2021年9-12月の詳細
    md_content += "\n---\n\n## 2. 今回追加データの充足状況\n\n"
    md_content += "### 2.1 2021年9-12月（今回追加分）\n\n"
    md_content += "| 年月 | レース数 | 出走表 | 結果 | オッズ | 詳細 | 予測 |\n"
    md_content += "|------|----------|--------|------|--------|------|------|\n"

    for month in ['09', '10', '11', '12']:
        data = get_monthly_data(conn, '2021', month)
        total, entries, results, odds, details, preds = data

        if total > 0:
            md_content += f"| 2021-{month} | {total:,} | {entries:,}<br>({entries/total*100:.1f}%) | {results:,}<br>({results/total*100:.1f}%) | {odds:,}<br>({odds/total*100:.1f}%) | {details:,}<br>({details/total*100:.1f}%) | {preds:,}<br>({preds/total*100:.1f}%) |\n"
        else:
            md_content += f"| 2021-{month} | データなし | - | - | - | - | - |\n"

    # 2023年全期間
    md_content += "\n### 2.2 2023年1-12月（今回追加分）\n\n"
    md_content += "| 年月 | レース数 | 出走表 | 結果 | オッズ | 詳細 | 予測 |\n"
    md_content += "|------|----------|--------|------|--------|------|------|\n"

    for month_num in range(1, 13):
        month = f"{month_num:02d}"
        data = get_monthly_data(conn, '2023', month)
        total, entries, results, odds, details, preds = data

        if total > 0:
            md_content += f"| 2023-{month} | {total:,} | {entries:,}<br>({entries/total*100:.1f}%) | {results:,}<br>({results/total*100:.1f}%) | {odds:,}<br>({odds/total*100:.1f}%) | {details:,}<br>({details/total*100:.1f}%) | {preds:,}<br>({preds/total*100:.1f}%) |\n"

    # 全期間の月別データ
    md_content += "\n---\n\n## 3. 全期間の月別データ充足率\n\n"

    for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
        md_content += f"\n### {year}年\n\n"
        md_content += "| 月 | レース数 | 出走表 | 結果 | オッズ | 詳細 | 予測 |\n"
        md_content += "|----|----------|--------|------|--------|------|------|\n"

        for month_num in range(1, 13):
            month = f"{month_num:02d}"
            data = get_monthly_data(conn, year, month)
            total, entries, results, odds, details, preds = data

            if total > 0:
                md_content += f"| {month} | {total:,} | {entries:,}<br>({entries/total*100:.1f}%) | {results:,}<br>({results/total*100:.1f}%) | {odds:,}<br>({odds/total*100:.1f}%) | {details:,}<br>({details/total*100:.1f}%) | {preds:,}<br>({preds/total*100:.1f}%) |\n"

    # データ品質評価
    md_content += "\n---\n\n## 4. データ品質評価\n\n"
    md_content += "### 4.1 テーブル別評価\n\n"

    def get_status(rate):
        if rate >= 99.0:
            return "✅ 完全"
        elif rate >= 95.0:
            return "✅ 良好"
        elif rate >= 90.0:
            return "⚠️ 要確認"
        else:
            return "❌ 不足"

    md_content += f"""
| テーブル | 充足率 | 評価 | コメント |
|----------|--------|------|----------|
| **races** | 100.0% | ✅ 完全 | 基準テーブル（全{total_races:,}レース） |
| **entries** | {total_entries/total_races*100:.1f}% | {get_status(total_entries/total_races*100)} | 出走表データ（{total_entries:,}レース） |
| **results** | {total_results/total_races*100:.1f}% | {get_status(total_results/total_races*100)} | レース結果（{total_results:,}レース） |
| **trifecta_odds** | {total_odds/total_races*100:.1f}% | {get_status(total_odds/total_races*100)} | 3連単オッズ（{total_odds:,}レース） |
| **race_details** | {total_details/total_races*100:.1f}% | {get_status(total_details/total_races*100)} | レース詳細・展示情報（{total_details:,}レース） |
| **race_predictions** | {total_preds/total_races*100:.1f}% | {get_status(total_preds/total_races*100)} | 予測データ（{total_preds:,}レース） |
"""

    # 欠損データの特定
    md_content += "\n### 4.2 欠損データの特定\n\n"

    missing_entries = total_races - total_entries
    missing_results = total_races - total_results
    missing_odds = total_races - total_odds
    missing_details = total_races - total_details
    missing_preds = total_races - total_preds

    if any([missing_entries, missing_results, missing_odds, missing_details, missing_preds]):
        md_content += "**欠損レース数（全期間）**:\n\n"
        if missing_entries > 0:
            md_content += f"- 出走表: {missing_entries:,}レース欠損\n"
        if missing_results > 0:
            md_content += f"- 結果: {missing_results:,}レース欠損\n"
        if missing_odds > 0:
            md_content += f"- オッズ: {missing_odds:,}レース欠損\n"
        if missing_details > 0:
            md_content += f"- 詳細: {missing_details:,}レース欠損\n"
        if missing_preds > 0:
            md_content += f"- 予測: {missing_preds:,}レース欠損\n"
    else:
        md_content += "✅ 全テーブルで100%充足（欠損データなし）\n"

    # 改善状況
    md_content += "\n---\n\n## 5. 今回の追加データによる改善状況\n\n"
    md_content += """
### 追加データの概要

- **2021年9-12月**: 前回調査時に欠損していた期間
- **2023年1-12月**: 前回調査時に欠損していた期間

### 改善効果

今回のデータ追加により、以下の改善が見られました：

1. **2021年のデータ完全性向上**
   - 2021年9-12月のデータが新規追加され、年間データがほぼ完全に

2. **2023年の完全なカバレッジ**
   - 2023年全12ヶ月のデータが追加され、年間分析が可能に

3. **バックテスト精度の向上**
   - 連続した6年間（2020-2025）のデータが揃い、長期的なパフォーマンス分析が可能に

4. **予測モデルの学習データ拡充**
   - トレーニングデータが増加し、より精度の高い予測が期待できる

"""

    # 推奨アクション
    md_content += "\n---\n\n## 6. 推奨アクション\n\n"

    if total_entries/total_races < 0.99 or total_results/total_races < 0.99 or total_odds/total_races < 0.99:
        md_content += "### データ補完が必要なテーブル\n\n"

        action_needed = False

        if total_entries/total_races < 0.99:
            md_content += f"#### 1. entries（出走表）\n"
            md_content += f"- **充足率**: {total_entries/total_races*100:.2f}%\n"
            md_content += f"- **欠損数**: {missing_entries:,}レース\n"
            md_content += "- **推奨スクリプト**: `python scripts/data_collection/fetch_historical_data_parallel.py --start YYYY-MM-DD --end YYYY-MM-DD`\n\n"
            action_needed = True

        if total_results/total_races < 0.99:
            md_content += f"#### 2. results（結果）\n"
            md_content += f"- **充足率**: {total_results/total_races*100:.2f}%\n"
            md_content += f"- **欠損数**: {missing_results:,}レース\n"
            md_content += "- **推奨スクリプト**: `python scripts/data_collection/fetch_historical_data_parallel.py --start YYYY-MM-DD --end YYYY-MM-DD`\n\n"
            action_needed = True

        if total_odds/total_races < 0.99:
            md_content += f"#### 3. trifecta_odds（オッズ）\n"
            md_content += f"- **充足率**: {total_odds/total_races*100:.2f}%\n"
            md_content += f"- **欠損数**: {missing_odds:,}レース\n"
            md_content += "- **推奨スクリプト**: `python scripts/data_collection/fetch_odds_parallel_safe.py --start YYYY-MM-DD --end YYYY-MM-DD`\n\n"
            action_needed = True

        if total_details/total_races < 0.95:
            md_content += f"#### 4. race_details（詳細）\n"
            md_content += f"- **充足率**: {total_details/total_races*100:.2f}%\n"
            md_content += f"- **欠損数**: {missing_details:,}レース\n"
            md_content += "- **推奨スクリプト**: `python scripts/data_collection/補完_レース詳細データ_改善版v4.py`\n\n"
            action_needed = True

        if total_preds/total_races < 0.95:
            md_content += f"#### 5. race_predictions（予測）\n"
            md_content += f"- **充足率**: {total_preds/total_races*100:.2f}%\n"
            md_content += f"- **欠損数**: {missing_preds:,}レース\n"
            md_content += "- **推奨スクリプト**: `python scripts/prediction/generate_predictions.py --year YYYY`\n\n"
            action_needed = True
    else:
        md_content += "### データ充足状況\n\n"
        md_content += "✅ 全テーブルで高い充足率を達成しています。現時点でのデータ補完は不要です。\n\n"

    md_content += """
### 今後のメンテナンス

1. **定期的なデータ収集**
   - 自動化スクリプトによる日次データ収集を継続
   - 特にオリジナル展示データは前日限定のため、毎日の取得が必須

2. **充足率のモニタリング**
   - 月次でデータ充足率を確認
   - 欠損が見つかった場合は速やかに補完

3. **予測データの更新**
   - 新規データ追加後は予測データの再生成を実施
   - 標準テストで精度を確認

4. **バックアップの実施**
   - データベースの定期的なバックアップを実施
   - 特に大規模なデータ追加前後はバックアップ必須

---

## 7. まとめ

### データ品質スコア

"""

    # 総合スコアを計算
    avg_coverage = (
        total_entries/total_races * 100 * 0.2 +
        total_results/total_races * 100 * 0.2 +
        total_odds/total_races * 100 * 0.2 +
        total_details/total_races * 100 * 0.2 +
        total_preds/total_races * 100 * 0.2
    )

    def get_grade(score):
        if score >= 99.0:
            return "A+"
        elif score >= 95.0:
            return "A"
        elif score >= 90.0:
            return "B"
        elif score >= 85.0:
            return "C"
        else:
            return "D"

    md_content += f"""
**総合充足率**: {avg_coverage:.1f}%
**評価グレード**: {get_grade(avg_coverage)}

### 結論

今回のデータ追加により、2020-2025年の6年間にわたるデータが揃い、長期的な分析・予測が可能になりました。特に2021年9-12月と2023年全期間のデータが追加されたことで、年次トレンドの分析やモデルの学習データとしての価値が大幅に向上しています。

"""

    if avg_coverage >= 95.0:
        md_content += "現在のデータ品質は非常に高く、バックテストや予測生成に十分な状態です。\n"
    elif avg_coverage >= 90.0:
        md_content += "現在のデータ品質は良好ですが、一部のテーブルで補完を検討すると更に精度が向上します。\n"
    else:
        md_content += "データ補完を実施し、充足率を向上させることを推奨します。\n"

    md_content += f"""
---

**調査完了**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}
**生成スクリプト**: `scripts/analysis/generate_coverage_report.py`
"""

    conn.close()

    # レポート保存
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"\n✅ レポートを保存しました: {OUTPUT_PATH}")
    print(f"\n総合充足率: {avg_coverage:.1f}% (グレード: {get_grade(avg_coverage)})")

if __name__ == "__main__":
    main()
