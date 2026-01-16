# データ収集ドキュメント体系

**最終更新**: 2026-01-15

---

## 📚 ドキュメント一覧

### 1. [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md)
**対象**: Claude Codeの完全リファレンス

**内容**:
- クイックリファレンス（よくあるタスクと対応スクリプト）
- シナリオ別ガイド（初回セットアップ、日次更新、補完等）
- 推奨スクリプト一覧
- トラブルシューティング
- CSV収集方式の詳細

**こんな時に**:
- 「データ収集して」と依頼された時
- どのスクリプトを使うべきか迷った時
- トラブルが起きた時

---

### 2. [DATA_COLLECTION_SCRIPTS_CATALOG.md](DATA_COLLECTION_SCRIPTS_CATALOG.md)
**対象**: 全44スクリプトの完全カタログ

**内容**:
- 推奨スクリプト（現役17個）
- 旧版・非推奨（アーカイブ候補27個）
- スクリプト詳細仕様
- 整理方針

**こんな時に**:
- スクリプトの詳細仕様を確認したい時
- 重複スクリプトを整理したい時
- 旧版と新版の違いを確認したい時

---

### 3. [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md)
**対象**: CSV経由データ収集の詳細

**内容**:
- CSV方式の利点
- 使用方法（3ステップ）
- 不整合防止の仕組み
- パフォーマンス目安
- 推奨ワークフロー

**こんな時に**:
- 大量データを収集する時（DB負荷回避）
- 長時間収集中も他の作業をしたい時
- データ整合性を保証したい時

---

### 4. [VENUE_SPECIFIC_DATA_COLLECTION.md](VENUE_SPECIFIC_DATA_COLLECTION.md)
**対象**: 競艇場独自データの調査結果

**内容**:
- 各競艇場の公式サイトから収集可能な独自データ
- 優先度評価（潮汐表、気象データ、前検タイム等）
- 調査状況（4/24競艇場完了）
- 次のステップ

**こんな時に**:
- 公式API以外のデータを追加したい時
- 予測精度向上のため独自データを検討したい時
- 競艇場別の特性データを収集したい時

---

## 🎯 使い分けガイド

### 状況別おすすめドキュメント

| 状況 | ドキュメント |
|------|-------------|
| データ収集タスクを依頼された | [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) |
| どのスクリプトを使うか迷っている | [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) → クイックリファレンス |
| スクリプトの詳細仕様を知りたい | [DATA_COLLECTION_SCRIPTS_CATALOG.md](DATA_COLLECTION_SCRIPTS_CATALOG.md) |
| 大量データを収集したい | [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md) |
| DB負荷を回避したい | [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md) |
| 競艇場独自データを検討 | [VENUE_SPECIFIC_DATA_COLLECTION.md](VENUE_SPECIFIC_DATA_COLLECTION.md) |
| 旧版スクリプトを整理したい | [DATA_COLLECTION_SCRIPTS_CATALOG.md](DATA_COLLECTION_SCRIPTS_CATALOG.md) → 整理方針 |

---

## 🚀 クイックスタート

### よくある依頼と対応

#### 1. 「過去全データを収集して」

```bash
python scripts/data_collection/auto_fetch_2020_2025.py
```

**詳細**: [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) → シナリオ1

---

#### 2. 「2024年のデータが欲しい」

```bash
python scripts/data_collection/fetch_historical_data_parallel.py \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --workers 12
```

**詳細**: [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) → クイックリファレンス

---

#### 3. 「大量データをDB負荷なしで収集したい」

```bash
# ステップ1: CSV収集
python scripts/data_collection/fetch_to_csv_parallel_improved.py \
  --start 2020-01-01 \
  --end 2020-12-31 \
  --output data/csv/2020

# ステップ2: 検証
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020 \
  --dry-run

# ステップ3: DB投入
python scripts/maintenance/bulk_insert_from_csv.py \
  --input data/csv/2020
```

**詳細**: [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md)

---

#### 4. 「決まり手データが抜けている」

```bash
python scripts/data_collection/補完_決まり手データ_改善版.py
```

**詳細**: [DATA_COLLECTION_MASTER.md](DATA_COLLECTION_MASTER.md) → シナリオ4

---

## 📊 スクリプト選択チャート

```
データ収集タスク
    │
    ├─ 過去全データ（2020-2025）？
    │   └─ Yes → auto_fetch_2020_2025.py
    │
    ├─ 特定期間のみ？
    │   ├─ 少量（1ヶ月以内） → fetch_historical_data_parallel.py
    │   └─ 大量（複数月以上） → fetch_to_csv_parallel_improved.py
    │
    ├─ データ補完？
    │   ├─ 決まり手 → 補完_決まり手データ_改善版.py
    │   ├─ レース詳細 → 補完_レース詳細データ_改善版v4.py
    │   ├─ 払戻金 → 補完_払戻金データ.py
    │   └─ 気象データ → fill_missing_weather_data.py
    │
    ├─ オッズ収集？
    │   ├─ 3連単 → fetch_odds_parallel_safe.py
    │   └─ 2連単 → fetch_exacta_odds.py
    │
    └─ 日次更新？
        └─ fetch_today_beforeinfo.py
```

---

## ⚠️ 重要な注意事項

### 1. 旧版スクリプトは使わない

以下のスクリプトは改善版が存在するため使用禁止:

- `fetch_historical_data.py` → **使用: fetch_historical_data_parallel.py**
- `collect_beforeinfo_2020_2023.py` → **使用: collect_beforeinfo_2020_2023_optimized.py**
- `fetch_to_csv_parallel.py` → **使用: fetch_to_csv_parallel_improved.py**
- `補完_決まり手データ_シンプル版.py` → **使用: 補完_決まり手データ_改善版.py**

**詳細**: [DATA_COLLECTION_SCRIPTS_CATALOG.md](DATA_COLLECTION_SCRIPTS_CATALOG.md) → 旧版・非推奨

---

### 2. 大量データはCSV方式必須

**理由**:
- DB負荷なし
- 他の作業と並行可能
- 50タスクごとに自動保存（途中で止まってもデータ残る）

**詳細**: [CSV_DATA_COLLECTION_GUIDE.md](CSV_DATA_COLLECTION_GUIDE.md)

---

### 3. 並列化を活用

**推奨ワーカー数**: 8-12

```bash
--workers 12
```

---

## 🔄 データ収集フロー全体図

```
【初回セットアップ】
  ↓
auto_fetch_2020_2025.py（15-25時間）
  ↓
補完スクリプト実行
  ├─ 補完_決まり手データ_改善版.py
  ├─ 補完_レース詳細データ_改善版v4.py
  └─ fill_missing_weather_data.py
  ↓
統計指標生成
  └─ build_indicator_stats.py --year 2020～2025
  ↓
【セットアップ完了】

【日次運用】
  ↓
fetch_today_beforeinfo.py（毎日）
  ↓
update_racer_master.py（月次）
  ↓
【運用継続】
```

---

## 📝 CLAUDE.md との連携

[CLAUDE.md](../../CLAUDE.md) の「データ収集タスク」セクションに以下が追加されています:

- クイックリファレンス
- 基本原則
- 詳細ドキュメントへのリンク

Claude Codeは必要に応じてこれらのドキュメントを参照します。

---

## 🆕 今後の拡張予定

### 1. 競艇場独自データの収集

**現状**: 調査済み 4/24競艇場

**次のステップ**:
- 残り20競艇場の調査
- 優先度高データ（潮汐表、気象データ）の収集スクリプト実装

**詳細**: [VENUE_SPECIFIC_DATA_COLLECTION.md](VENUE_SPECIFIC_DATA_COLLECTION.md)

---

### 2. スクリプトアーカイブ化

**現状**: 44スクリプトすべてが scripts/data_collection/ に混在

**提案**:
```
scripts/data_collection/
├── (推奨17スクリプトのみ残す)
└── archive/
    ├── deprecated/     # 旧版（非推奨）
    └── year_specific/  # 特定年度専用
```

**詳細**: [DATA_COLLECTION_SCRIPTS_CATALOG.md](DATA_COLLECTION_SCRIPTS_CATALOG.md) → 整理方針

---

## まとめ

データ収集を効率的に進めるため、以下の体系が整備されました:

1. **マスターガイド** - すべてのタスクに対応
2. **スクリプトカタログ** - 全44スクリプトの分類と推奨
3. **CSV方式ガイド** - 大量データ収集の詳細
4. **競艇場独自データ** - 今後の拡張方針

Claude Codeはこれらのドキュメントを活用して、過去の知見を効率的に利用できるようになりました。

---

**関連ファイル**:
- [CLAUDE.md](../../CLAUDE.md) - プロジェクト設定
- [docs/guides/](.) - 各種ガイド

**最終更新**: 2026-01-15
