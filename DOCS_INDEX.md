# 📚 BoatRace システムドキュメント総合インデックス

**最終更新**: 2025-11-19

---

## 🚀 クイックスタート（初回はここから）

| 優先度 | ドキュメント | 説明 |
|--------|------------|------|
| 1 | [START_HERE.md](START_HERE.md) | 初回セットアップ |
| 2 | [起動方法.txt](起動方法.txt) | UIアプリの起動 |
| 3 | [SYSTEM_OVERVIEW_FINAL.md](SYSTEM_OVERVIEW_FINAL.md) | システム全体像 |

---

## 📕 最新の改善計画

| ドキュメント | 状態 | 説明 |
|------------|------|------|
| [改善点_1118.md](改善点_1118.md) | ✅ 実装完了 | 最優先改善項目（pit_number、条件付きモデル等） |
| [IMPROVEMENT_PLAN_20251117.md](IMPROVEMENT_PLAN_20251117.md) | 📋 計画 | Phase 1-3 改善計画 |
| [仕様改善点_20251114.txt](仕様改善点_20251114.txt) | ✅ 実装済 | AI向け改善仕様書 |
| [改善アドバイス20251103.txt](改善アドバイス20251103.txt) | ✅ 実装済 | 初期改善アドバイス |

---

## 📗 主要ガイド

### データ収集
| ドキュメント | 説明 |
|------------|------|
| [COMPREHENSIVE_DATA_COLLECTION_README.md](COMPREHENSIVE_DATA_COLLECTION_README.md) | データ収集総合ガイド |
| [DATA_COLLECTION_GUIDE.md](DATA_COLLECTION_GUIDE.md) | 基本データ収集 |
| [DATA_FILLING_GUIDE.md](DATA_FILLING_GUIDE.md) | データ補充 |
| [DAILY_COLLECTION_SETUP.md](DAILY_COLLECTION_SETUP.md) | 日次自動収集 |

### 実装・UI
| ドキュメント | 説明 |
|------------|------|
| [UI_INTEGRATION_GUIDE.md](UI_INTEGRATION_GUIDE.md) | UI統合ガイド |
| [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) | 実装ガイド |
| [README_SCRIPTS.md](README_SCRIPTS.md) | スクリプト説明 |

---

## ⚠️ アーカイブ対象（docs/archive へ移動推奨）

### 復元作業関連（2025-11-13 完了済）
- 復元作業報告_20251113.md
- 機能比較レポート_復元版vs破損版.md
- 欠落機能と復元計画.md
- 復元完了_*.md / .txt
- PROJECT_BUG_REPORT_20251113.md
- CRITICAL_DISCOVERY_20251113.md

### 重複クイックスタート
- README_QUICK_START.md
- QUICK_START_GUIDE.md
- QUICK_START.md
- NEXT_SESSION_QUICKSTART.md

### デバッグ出力（削除可能）
- test_output.txt, st_debug_output.txt, table3_output.txt 等

---

## 🎯 ドキュメント体系

```
BoatRace/
├── 📖 作業ガイド（必読）
│   ├── README_WORK_GUIDE.md        ← スタート地点
│   ├── WORK_CHECKLIST.md           ← 作業前に必ず確認
│   └── SYSTEM_CONSTRAINTS.md       ← 絶対に守るべき制約
│
├── 🧪 品質保証
│   ├── QUALITY_ASSURANCE.md        ← 対策の全体像
│   ├── TESTING_GUIDE.md            ← テスト実行方法
│   ├── tests/
│   │   ├── test_integration.py    ← 統合テスト
│   │   └── test_core_logic.py     ← ユニットテスト
│   └── src/validation/
│       └── data_validator.py       ← データ検証モジュール
│
├── 📊 システム仕様
│   └── SYSTEM_LOGIC_ANALYSIS.md    ← ロジック詳細
│
└── 🚀 実行スクリプト
    └── run_tests.py                ← テスト実行
```

---

## 🚨 作業開始前に必ず確認するドキュメント（優先度順）

### 1️⃣ [README_WORK_GUIDE.md](README_WORK_GUIDE.md)
**最初に開くファイル**

**内容**:
- すべてのドキュメントへのクイックリンク
- 状況別ガイド（DB操作、計算ロジック変更など）
- クイックコマンド集

**いつ見る**: 作業開始時、困ったとき

---

### 2️⃣ [WORK_CHECKLIST.md](WORK_CHECKLIST.md)
**作業前のチェックリスト**

**内容**:
- ✅ 作業開始前の必須確認事項
- ✅ 影響範囲の特定方法
- ✅ データ整合性の確認
- ✅ テスト計画の策定
- ✅ 作業完了後のチェック

**いつ見る**: 毎回の作業前

**重要度**: ⭐⭐⭐（最重要）

---

### 3️⃣ [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md)
**システムの制約・ルール**

**内容**:
- データベース制約（外部キー、UNIQUE、値範囲）
- 計算ロジックの制約（確率、Kelly基準）
- 特徴量の値範囲
- 禁止事項リスト

**いつ見る**: DB操作、計算変更、特徴量追加の前

**重要度**: ⭐⭐⭐（最重要）

---

## 📖 参考ドキュメント

### [QUALITY_ASSURANCE.md](QUALITY_ASSURANCE.md)
**品質保証の全体像**

**内容**:
- 実装した対策の概要
- テストフレームワーク
- データ検証モジュール
- 開発ワークフロー

**いつ見る**: 品質方針を確認したいとき

**重要度**: ⭐⭐

---

### [TESTING_GUIDE.md](TESTING_GUIDE.md)
**テスト実行の詳細ガイド**

**内容**:
- テストの種類と実施タイミング
- テスト実行フロー
- データ検証の使い方
- よくある問題と対処法
- テスト追加ガイド

**いつ見る**: テスト追加時、テスト失敗時

**重要度**: ⭐⭐⭐

---

### [SYSTEM_LOGIC_ANALYSIS.md](SYSTEM_LOGIC_ANALYSIS.md)
**システムロジックの詳細**

**内容**:
- データ収集ロジック
- データベース設計
- 特徴量エンジニアリング
- 機械学習モデル
- 予測エンジン
- ベッティング戦略
- 主要アルゴリズム

**いつ見る**: システム全体の理解、複雑なロジック変更の前

**重要度**: ⭐⭐

---

## 🔧 実装ファイル

### テスト

#### [tests/test_integration.py](tests/test_integration.py)
**統合テスト**

**テスト内容**:
- データベース整合性（外部キー、6艇制約）
- 特徴量生成パイプライン
- 予測確率の合計検証
- Kelly基準計算
- AI解析用エクスポート機能

**実行方法**:
```bash
python -m pytest tests/test_integration.py -v
```

---

#### [tests/test_core_logic.py](tests/test_core_logic.py)
**ユニットテスト**

**テスト内容**:
- Kelly基準計算（正/負の期待値、エッジケース）
- 確率計算・正規化
- 特徴量の値範囲検証
- データ整合性（着順、決まり手）

**実行方法**:
```bash
python -m pytest tests/test_core_logic.py -v
```

---

### データ検証

#### [src/validation/data_validator.py](src/validation/data_validator.py)
**データ検証モジュール**

**機能**:
- スキーマ定義と検証
- データベース挿入前の自動検証
- 特徴量の妥当性チェック

**使用例**:
```python
from src.validation.data_validator import DataValidator

is_valid, errors = DataValidator.validate_race(race_data)
if not is_valid:
    for error in errors:
        print(f"エラー: {error}")
```

---

### 実行スクリプト

#### [run_tests.py](run_tests.py)
**テスト実行スクリプト**

**実行方法**:
```bash
python run_tests.py
```

**出力例**:
```
================================================================================
BoatRace システムテスト実行
実行日時: 2025-11-14 17:00:00
================================================================================
tests/test_core_logic.py::TestKellyCalculation::test_positive_expected_value PASSED
tests/test_integration.py::TestDataFlow::test_database_integrity PASSED
...
================================================================================
✅ 全テスト合格 (6 passed in 3.45s)
================================================================================
```

---

## 📊 ドキュメント比較表

| ドキュメント | 目的 | 対象読者 | 長さ | 重要度 | 更新頻度 |
|------------|------|---------|------|--------|---------|
| README_WORK_GUIDE.md | クイックリファレンス | 全員 | 中 | ⭐⭐⭐ | 低 |
| WORK_CHECKLIST.md | 作業前チェック | 開発者 | 中 | ⭐⭐⭐ | 低 |
| SYSTEM_CONSTRAINTS.md | 制約定義 | 開発者 | 長 | ⭐⭐⭐ | 低 |
| QUALITY_ASSURANCE.md | 品質方針 | 全員 | 短 | ⭐⭐ | 低 |
| TESTING_GUIDE.md | テスト詳細 | 開発者 | 中 | ⭐⭐⭐ | 中 |
| SYSTEM_LOGIC_ANALYSIS.md | ロジック詳細 | 開発者 | 長 | ⭐⭐ | 中 |

---

## 🎯 状況別おすすめドキュメント

### 初めての作業
1. [README_WORK_GUIDE.md](README_WORK_GUIDE.md)
2. [WORK_CHECKLIST.md](WORK_CHECKLIST.md)
3. [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md)

### データベース操作
1. [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) - データベース制約
2. [WORK_CHECKLIST.md](WORK_CHECKLIST.md) - データ整合性チェック
3. [data_validator.py](src/validation/data_validator.py) - 検証コード

### 計算ロジック変更
1. [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) - 計算ロジックの制約
2. [WORK_CHECKLIST.md](WORK_CHECKLIST.md) - 影響範囲特定
3. [test_core_logic.py](tests/test_core_logic.py) - テスト追加

### 特徴量追加
1. [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) - 特徴量の制約
2. [data_validator.py](src/validation/data_validator.py) - 検証ルール追加
3. [test_integration.py](tests/test_integration.py) - パイプラインテスト

### テスト失敗
1. [TESTING_GUIDE.md](TESTING_GUIDE.md) - よくある問題
2. [WORK_CHECKLIST.md](WORK_CHECKLIST.md) - 緊急時の対応

### システム理解
1. [SYSTEM_LOGIC_ANALYSIS.md](SYSTEM_LOGIC_ANALYSIS.md) - ロジック詳細
2. [README_WORK_GUIDE.md](README_WORK_GUIDE.md) - 全体像

---

## ⚡ クイックアクセス

### 最も重要な3つのコマンド

```bash
# 1. 全テスト実行
python run_tests.py

# 2. データベース整合性チェック
python -m pytest tests/test_integration.py::TestDataFlow::test_database_integrity -v

# 3. 計算ロジックチェック
python -m pytest tests/test_core_logic.py -v
```

### 最も重要な3つの検証

```python
# 1. レースデータ検証
from src.validation.data_validator import DataValidator
is_valid, errors = DataValidator.validate_race(race_data)

# 2. 特徴量検証
from src.validation.data_validator import FeatureValidator
is_valid, errors = FeatureValidator.validate_features(features_df)

# 3. 確率の合計チェック
assert abs(sum(probabilities) - 1.0) < 0.01
```

---

## 🔄 ドキュメント更新ガイド

### ドキュメントを更新すべきとき

| 変更内容 | 更新すべきドキュメント |
|---------|---------------------|
| 新しい制約を追加 | SYSTEM_CONSTRAINTS.md |
| 新しいテストを追加 | TESTING_GUIDE.md |
| 新しい機能を追加 | SYSTEM_LOGIC_ANALYSIS.md |
| 作業手順を変更 | WORK_CHECKLIST.md |
| 新しいドキュメントを追加 | README_WORK_GUIDE.md, DOCS_INDEX.md |

### 更新時のルール

1. **日付を更新**: `最終更新: YYYY-MM-DD`
2. **変更履歴を記録**: 大きな変更は記録
3. **整合性を保つ**: 関連ドキュメントも同時に更新

---

## 📞 サポート

### 質問・不明点がある場合

1. まず [README_WORK_GUIDE.md](README_WORK_GUIDE.md) を確認
2. 該当するドキュメントを読む
3. それでも解決しない場合は、テストログを確認

---

## 📝 印刷推奨ドキュメント

デスクに置いておくと便利：

1. [WORK_CHECKLIST.md](WORK_CHECKLIST.md)
2. [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) の「絶対に守るべき制約（TOP 5）」

---

**このファイルをブックマークして、作業前に必ず確認してください！**

---

**最終更新**: 2025-11-14
