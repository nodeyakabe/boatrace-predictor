# 📚 作業ガイド - クイックリファレンス

**目的**: 作業前に必要なドキュメントへ素早くアクセス

---

## 🚨 作業開始前に必ず確認

### 最重要：作業開始前チェックリスト
📄 **[WORK_CHECKLIST.md](WORK_CHECKLIST.md)**

**内容**:
- ✅ 作業前の必須確認事項
- ✅ 影響範囲の特定方法
- ✅ テスト計画の策定
- ✅ 作業完了後のチェック

**いつ見る**: すべての作業の前に

---

## 📖 主要ドキュメント一覧

### 1. システム制約・ルール
📄 **[SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md)**

**内容**:
- データベース制約（外部キー、UNIQUE、NOT NULL）
- 計算ロジックの制約（確率、Kelly基準）
- 特徴量の値範囲
- 禁止事項リスト

**いつ見る**: データベース操作、計算ロジック変更、特徴量追加の前

---

### 2. テスト実行ガイド
📄 **[TESTING_GUIDE.md](TESTING_GUIDE.md)**

**内容**:
- テストの種類と実施タイミング
- テスト実行方法
- データ検証の使い方
- よくある問題と対処法

**いつ見る**: テスト追加時、テスト失敗時

---

### 3. 品質保証の全体像
📄 **[QUALITY_ASSURANCE.md](QUALITY_ASSURANCE.md)**

**内容**:
- 実装した対策の概要
- テストフレームワークの説明
- データ検証モジュールの使い方
- 開発ワークフロー

**いつ見る**: 品質管理の方針を確認したいとき

---

### 4. システムロジック詳細
📄 **[SYSTEM_LOGIC_ANALYSIS.md](SYSTEM_LOGIC_ANALYSIS.md)**

**内容**:
- データ収集ロジック
- 特徴量エンジニアリング
- 機械学習モデル
- ベッティング戦略
- 主要アルゴリズム

**いつ見る**: システム全体の理解、ロジック変更の前

---

## 🎯 状況別ガイド

### データベースを操作する

1. 📄 [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) - データベース制約を確認
2. 📄 [WORK_CHECKLIST.md](WORK_CHECKLIST.md) - データ整合性チェック
3. データ検証コードを追加
   ```python
   from src.validation.data_validator import DataValidator
   is_valid, errors = DataValidator.validate_race(race_data)
   ```
4. テスト実行
   ```bash
   python -m pytest tests/test_integration.py::TestDataFlow::test_database_integrity -v
   ```

---

### 計算ロジックを変更する

1. 📄 [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) - 計算ロジックの制約を確認
2. 📄 [WORK_CHECKLIST.md](WORK_CHECKLIST.md) - 影響範囲を特定
3. ユニットテストを追加
   ```python
   # tests/test_core_logic.py に追加
   def test_new_calculation():
       result = new_function(input)
       assert result == expected
   ```
4. テスト実行
   ```bash
   python -m pytest tests/test_core_logic.py -v
   ```

---

### 特徴量を追加する

1. 📄 [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) - 特徴量の制約を確認
2. 値の範囲を定義
3. DataValidatorに検証ルールを追加
   ```python
   # src/validation/data_validator.py
   ValidationRule('new_feature', float, min_value=0, max_value=100)
   ```
4. ユニットテストを追加
5. テスト実行
   ```bash
   python -m pytest tests/test_integration.py::TestDataFlow::test_feature_generation_pipeline -v
   ```

---

### テストが失敗した

1. 📄 [TESTING_GUIDE.md](TESTING_GUIDE.md) - よくある問題を確認
2. エラーメッセージを詳細表示
   ```bash
   python -m pytest tests/ -v --tb=long
   ```
3. 変更を一時的に戻してテスト
   ```bash
   git stash
   python run_tests.py
   git stash pop
   ```

---

## ⚡ クイックコマンド

### テスト実行

```bash
# 全テスト実行
python run_tests.py

# 統合テストのみ
python -m pytest tests/test_integration.py -v

# コアロジックのみ
python -m pytest tests/test_core_logic.py -v

# 特定のテストクラス
python -m pytest tests/test_core_logic.py::TestKellyCalculation -v

# 特定のテスト関数
python -m pytest tests/test_core_logic.py::TestKellyCalculation::test_positive_expected_value -v
```

### データ検証

```python
from src.validation.data_validator import DataValidator, FeatureValidator

# レースデータ検証
is_valid, errors = DataValidator.validate_race(race_data)

# 特徴量検証
is_valid, errors = FeatureValidator.validate_features(features_df)
```

### データベース整合性チェック

```bash
python -m pytest tests/test_integration.py::TestDataFlow::test_database_integrity -v
```

---

## 📋 チェックリスト（印刷用）

```
作業前
□ WORK_CHECKLIST.md を確認
□ 関連ドキュメントを読む
□ 影響範囲を特定
□ テスト計画を立てる

作業中
□ データ検証を追加
□ 入力値の範囲をチェック
□ 計算結果の妥当性を確認

作業後
□ 関連テストを実行
□ 全テストを実行
□ 手動動作確認
□ ドキュメント更新
□ コミット
```

---

## 🆘 困ったときは

### テストが通らない
→ [TESTING_GUIDE.md](TESTING_GUIDE.md) の「緊急時の対応」

### 制約が分からない
→ [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) の該当セクション

### システムの動作が分からない
→ [SYSTEM_LOGIC_ANALYSIS.md](SYSTEM_LOGIC_ANALYSIS.md) で確認

### 何から始めれば良いか分からない
→ [WORK_CHECKLIST.md](WORK_CHECKLIST.md) の手順に従う

---

## 📊 ドキュメント一覧表

| ドキュメント | 用途 | 重要度 | 更新頻度 |
|------------|------|--------|---------|
| [WORK_CHECKLIST.md](WORK_CHECKLIST.md) | 作業前チェック | ⭐⭐⭐ | 低 |
| [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) | 制約確認 | ⭐⭐⭐ | 低 |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | テスト実行 | ⭐⭐⭐ | 中 |
| [QUALITY_ASSURANCE.md](QUALITY_ASSURANCE.md) | 品質方針 | ⭐⭐ | 低 |
| [SYSTEM_LOGIC_ANALYSIS.md](SYSTEM_LOGIC_ANALYSIS.md) | ロジック詳細 | ⭐⭐ | 中 |
| README_WORK_GUIDE.md (本ファイル) | クイックリファレンス | ⭐⭐⭐ | 低 |

---

## 🎯 推奨ワークフロー

### 新機能開発

```
1. WORK_CHECKLIST.md を開く
   ↓
2. SYSTEM_CONSTRAINTS.md で制約確認
   ↓
3. 実装
   ↓
4. データ検証コード追加
   ↓
5. ユニットテスト追加
   ↓
6. python run_tests.py
   ↓
7. 合格 → コミット
```

### バグ修正

```
1. WORK_CHECKLIST.md を開く
   ↓
2. テストを追加（バグ再現）
   ↓
3. 修正
   ↓
4. python run_tests.py
   ↓
5. 合格 → コミット
```

### リファクタリング

```
1. WORK_CHECKLIST.md を開く
   ↓
2. 既存テストがすべて通ることを確認
   ↓
3. リファクタリング
   ↓
4. python run_tests.py（すべて通ることを確認）
   ↓
5. 合格 → コミット
```

---

**最終更新**: 2025-11-14

**このファイルをブックマークしておくと便利です！**
