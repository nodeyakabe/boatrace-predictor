# wave_heightデータ品質問題の調査と修正スクリプト作成レポート

**作成日**: 2026-01-29
**対象**: データベース内のrace_conditionsテーブルのwave_height関連の3つの問題

---

## エグゼクティブサマリー

wave_height補完検証で発見された3つの重大なデータ品質問題について、詳細調査を実施し、それぞれの修正スクリプトを作成しました。

| 問題 | 影響範囲 | 優先度 | スクリプト | 状態 |
|------|---------|--------|-----------|------|
| **問題1: 2020年9月の異常な日付形式** | 3,000件 | **最優先** | `scripts/maintenance/fix_abnormal_dates_2020_09.py` | ✅ 作成完了 |
| **問題2: 2024年のwave_height欠損** | 805件 | 高 | `scripts/data_collection/補完_wave_height_2024.py` | ✅ 作成完了 |
| **問題3: 2020-2023年のrace_conditions未登録** | 5,534件 | 高 | `scripts/data_collection/補完_race_conditions_2020_2023.py` | ✅ 作成完了 |

**総影響レース数**: 9,339件

---

## 問題1: 2020年9月の異常な日付形式【最優先】

### 調査結果

#### 現状
- 2020年9月のレースデータが「YYYYMMDD」形式（例: `20200901`）で登録されている
- 正常な形式は「YYYY-MM-DD」（例: `2020-09-01`）
- **影響件数**: 3,000件

#### 形式別内訳
```
YYYY-MM-DD形式: 4,522件（正常）
YYYYMMDD形式:   3,000件（異常）
```

#### 日付別サンプル
```
20200901 -> 2020-09-01: 120件
20200902 -> 2020-09-02: 120件
20200903 -> 2020-09-03: 132件
20200904 -> 2020-09-04: 168件
...
```

#### race_conditions紐付け状況
- **重大な問題**: YYYYMMDD形式のレースにはrace_conditionsが1件も紐づいていない
- これは日付形式の不一致によりJOINが失敗しているため

#### 影響
1. これらのレースは予測対象から漏れる可能性がある
2. 統計分析で2020年9月のデータが欠落
3. 2020年の予測精度に影響

### 作成スクリプト

**パス**: `scripts/maintenance/fix_abnormal_dates_2020_09.py`

#### 機能
- YYYYMMDD形式をYYYY-MM-DD形式に一括変換
- トランザクション管理で安全に更新
- dry-runモード対応

#### 使用方法
```bash
# 確認のみ（推奨：まずこれを実行）
python scripts/maintenance/fix_abnormal_dates_2020_09.py --dry-run

# 実際に修正
python scripts/maintenance/fix_abnormal_dates_2020_09.py
```

#### 実行結果（dry-run）
```
異常な日付形式のレコード: 3000件

【修正対象のサンプル（先頭10件）】
  1. race_id=171303, 20200901 -> 2020-09-01 (会場01 R01)
  2. race_id=171304, 20200901 -> 2020-09-01 (会場01 R02)
  ...
```

---

## 問題2: 2024年のwave_height欠損

### 調査結果

#### 現状
- 2024年のrace_conditionsにwave_heightがNULLのレコードが存在
- **影響件数**: 805件

#### 会場別欠損件数
```
会場03（江戸川）: 297件
会場02（戸田）:   185件
会場01（桐生）:   168件
会場07（蒲郡）:    24件
会場22（福岡）:    24件
会場04（平和島）:  23件
会場09（津）:      22件
会場11（びわこ）:  22件
会場21（芦屋）:    12件
会場06（浜名湖）:   9件
会場15（丸亀）:     9件
会場05（多摩川）:   6件
会場08（常滑）:     4件
```

#### 具体的な欠損例
```
2024-01-07 会場15 R08-R12: 5レース
2024-02-26 会場06 R11-R12: 2レース
2024-02-26 会場09 R10-R12: 3レース
2024-03-08 会場15: 4レース
2024-03-18 複数会場で大量欠損
...
```

#### 影響
1. wave_heightは水面状態の重要な指標
2. 予測モデルの入力特徴量として使用される可能性
3. 805件は2024年全レースの約5%に相当

### 作成スクリプト

**パス**: `scripts/data_collection/補完_wave_height_2024.py`

#### 機能
- ResultScraperで公式サイトから波高データを再取得
- 既存race_conditionsのwave_heightフィールドのみを更新
- 並列処理で高速化（デフォルト8ワーカー）
- リトライ機能付き

#### 使用方法
```bash
# 2024年全体を補完（デフォルト）
python scripts/data_collection/補完_wave_height_2024.py

# dry-runで確認
python scripts/data_collection/補完_wave_height_2024.py --dry-run

# 期間指定
python scripts/data_collection/補完_wave_height_2024.py --start-date 2024-01-01 --end-date 2024-06-30

# 並列数指定
python scripts/data_collection/補完_wave_height_2024.py --workers 10
```

#### 注意事項
- 公式APIへのアクセスが必要（約805リクエスト）
- 所要時間: 約5-10分（並列数により変動）
- REQUEST_DELAYを遵守（デフォルト1秒）

---

## 問題3: 2020-2023年のrace_conditions未登録

### 調査結果

#### 現状
- racesテーブルにレコードはあるが、race_conditionsが紐づいていない
- **総影響件数**: 5,534件

#### 年度別内訳
```
2020年: 3,310件
2021年:   772件
2022年:   852件
2023年:   600件
```

#### 具体的な欠損例
```
2020-03-05 会場02 R07-R12: 6レース
2020-03-11 会場01 R12: 1レース
2020-03-16 会場01 R01-R12: 12レース（全レース）
2020-03-16 会場02 R06...: 複数レース
...
```

#### 影響
1. 環境条件データが完全に欠落
2. 予測モデルの入力として使用不可
3. 特に2020年のデータ品質が低い
4. バックテストの信頼性に影響

### 作成スクリプト

**パス**: `scripts/data_collection/補完_race_conditions_2020_2023.py`

#### 機能
- ResultScraperで公式サイトから環境条件データを取得
- race_conditionsテーブルに新規レコードを挿入
- 並列処理で高速化（デフォルト10ワーカー）
- リトライ機能付き

#### 使用方法
```bash
# 2020-2023年全体を補完（デフォルト）
python scripts/data_collection/補完_race_conditions_2020_2023.py

# dry-runで確認
python scripts/data_collection/補完_race_conditions_2020_2023.py --dry-run

# 特定年度を補完
python scripts/data_collection/補完_race_conditions_2020_2023.py --year 2020

# 期間指定
python scripts/data_collection/補完_race_conditions_2020_2023.py --start-date 2020-01-01 --end-date 2020-06-30

# 並列数指定
python scripts/data_collection/補完_race_conditions_2020_2023.py --workers 12
```

#### 注意事項
- 公式APIへのアクセスが必要（約5,534リクエスト）
- 所要時間: 約30-60分（並列数により変動）
- REQUEST_DELAYを遵守（デフォルト1秒）
- 2020年から順番に実行することを推奨

---

## 実行推奨順序

データ整合性を保つため、以下の順序で実行してください。

### ステップ1: 問題1の修正（最優先）

```bash
# 1. dry-runで確認
python scripts/maintenance/fix_abnormal_dates_2020_09.py --dry-run

# 2. 問題なければ実行
python scripts/maintenance/fix_abnormal_dates_2020_09.py

# 3. 検証
python -c "
import sqlite3
from config.settings import DATABASE_PATH
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()
cursor.execute(\"SELECT COUNT(*) FROM races WHERE race_date LIKE '202009__' AND race_date NOT LIKE '%-%'\")
print(f'残存異常形式: {cursor.fetchone()[0]}件')
conn.close()
"
```

**理由**: 日付形式が正しくないとJOINが失敗し、他の修正が無効化される可能性がある

### ステップ2: 問題3の修正（2020-2023年のrace_conditions）

```bash
# 年度別に実行することを推奨

# 2020年（最も件数が多い）
python scripts/data_collection/補完_race_conditions_2020_2023.py --year 2020

# 2021年
python scripts/data_collection/補完_race_conditions_2020_2023.py --year 2021

# 2022年
python scripts/data_collection/補完_race_conditions_2020_2023.py --year 2022

# 2023年
python scripts/data_collection/補完_race_conditions_2020_2023.py --year 2023
```

**理由**: race_conditionsレコードが存在しない状態では、wave_heightの更新ができない

### ステップ3: 問題2の修正（2024年のwave_height）

```bash
python scripts/data_collection/補完_wave_height_2024.py
```

**理由**: race_conditionsレコードが存在する前提で、wave_heightフィールドのみを更新する

---

## 共通仕様

### すべてのスクリプトに含まれる機能

1. **dry-runモード**
   - `--dry-run` フラグで確認のみ実行
   - 実際のDB更新は行わない

2. **進捗表示**
   - リアルタイムで処理状況を表示
   - 成功/失敗の件数
   - 処理速度と残り時間の推定

3. **エラーハンドリング**
   - 個別レースのエラーで全体を停止しない
   - エラー詳細をログ出力
   - トランザクション管理で安全性確保

4. **期間フィルター**
   - `--start-date` と `--end-date` で範囲指定可能
   - `--year` で年度指定可能（問題3のみ）

5. **並列処理**
   - `--workers` で並列数を調整可能
   - デフォルト値は適切に設定済み

---

## 検証コマンド

### 問題1の検証
```bash
# 異常な形式が残っていないか確認
python -c "
import sqlite3
from config.settings import DATABASE_PATH
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()
cursor.execute('''
    SELECT
        CASE
            WHEN race_date LIKE \"________\" AND race_date NOT LIKE \"%-%\" THEN \"YYYYMMDD\"
            WHEN race_date LIKE \"____-__-__\" THEN \"YYYY-MM-DD\"
            ELSE \"OTHER\"
        END as format_type,
        COUNT(*) as cnt
    FROM races
    WHERE race_date LIKE \"202009%\" OR race_date LIKE \"2020-09-%\"
    GROUP BY format_type
''')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]}件')
conn.close()
"
```

### 問題2の検証
```bash
# 2024年のwave_height欠損が残っていないか確認
python -c "
import sqlite3
from config.settings import DATABASE_PATH
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()
cursor.execute('''
    SELECT COUNT(*)
    FROM races r
    JOIN race_conditions rc ON r.id = rc.race_id
    WHERE rc.wave_height IS NULL
      AND r.race_date >= \"2024-01-01\"
      AND r.race_date < \"2025-01-01\"
''')
print(f'2024年の残存欠損: {cursor.fetchone()[0]}件')
conn.close()
"
```

### 問題3の検証
```bash
# 2020-2023年のrace_conditions未登録が残っていないか確認
python -c "
import sqlite3
from config.settings import DATABASE_PATH
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()
cursor.execute('''
    SELECT
        SUBSTR(r.race_date, 1, 4) as year,
        COUNT(*) as cnt
    FROM races r
    LEFT JOIN race_conditions rc ON r.id = rc.race_id
    WHERE rc.id IS NULL
      AND r.race_date >= \"2020-01-01\"
      AND r.race_date < \"2024-01-01\"
    GROUP BY year
    ORDER BY year
''')
results = cursor.fetchall()
if results:
    print('残存未登録:')
    for year, cnt in results:
        print(f'  {year}年: {cnt}件')
else:
    print('未登録なし - すべて補完されました')
conn.close()
"
```

---

## 今後の予防策

### 1. データ投入時の検証強化
- 日付形式の統一チェック
- 必須フィールド（wave_heightなど）の存在確認
- race_conditionsの自動関連付け

### 2. 定期的なデータ品質チェック
```bash
# 月次で実行する検証スクリプトの作成を推奨
python scripts/maintenance/check_data_quality.py
```

### 3. 新規データ収集スクリプトの改善
- race_conditionsを必ず同時に収集
- wave_heightの取得を必須化
- 日付形式の統一（YYYY-MM-DD固定）

---

## まとめ

### 実施項目
- ✅ 3つの問題の詳細調査完了
- ✅ 各問題に対する修正スクリプト作成
- ✅ dry-run動作確認完了
- ✅ 実行手順書作成

### 次のアクション
1. **問題1の即時実行**（最優先）
2. **問題3の段階的実行**（年度別）
3. **問題2の実行**（最後）
4. **検証コマンドで確認**
5. **データ品質チェックの定期化**

### 期待される効果
- 9,339件のデータ品質問題を解決
- 予測モデルの精度向上
- バックテストの信頼性向上
- 2020-2024年の一貫したデータ品質確保

---

**作成者**: Claude Code
**最終更新**: 2026-01-29
