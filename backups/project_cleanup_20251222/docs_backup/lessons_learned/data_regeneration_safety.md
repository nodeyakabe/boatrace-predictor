# データ再生成時の安全対策

## 2025-12-21 インシデント

### 発生した問題
- 予測データ再生成スクリプトで「全削除→順次再生成」の設計
- 途中で停止したため58,981件のデータが喪失
- 数時間分の作業が無駄に

### 原因
```python
# 危険なパターン
delete_existing_predictions(all_race_ids)  # 全削除
for race in all_races:
    regenerate(race)  # ← 途中停止でデータ喪失
```

### 再発防止策

#### パターン1: UPSERT方式（推奨）
```python
# 削除せずに上書き
for race in all_races:
    predictions = generate(race)
    upsert_predictions(race_id, predictions)  # INSERT OR REPLACE
```

#### パターン2: バッチ単位処理
```python
# 1日単位で削除→再生成
for date in dates:
    delete_predictions_for_date(date)
    regenerate_for_date(date)
    commit()  # 1日分完了を保証
```

#### パターン3: 新テーブル方式
```python
# 新テーブルに生成→完了後に入れ替え
create_temp_table()
for race in all_races:
    insert_to_temp(race)
rename_tables()  # アトミックに入れ替え
```

### 結論
- 大量データの再生成は「全削除先行」を絶対に避ける
- 進捗を保存できる設計にする
- バックアップを取ってから実行する
