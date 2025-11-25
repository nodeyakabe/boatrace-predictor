# テスト・検証ガイド

**目的**: デグレ・ロジック破綻を防ぐためのテスト戦略

---

## テストの種類

### 1. ユニットテスト (`tests/test_core_logic.py`)
**対象**: 個別関数・メソッドの動作確認

**実施タイミング**: コード変更後、毎回実行

**テスト項目**:
- Kelly基準計算の正確性
- 確率計算の妥当性
- 特徴量の値範囲チェック
- データ型の整合性

**実行方法**:
```bash
python -m pytest tests/test_core_logic.py -v
```

### 2. 統合テスト (`tests/test_integration.py`)
**対象**: モジュール間の連携動作確認

**実施タイミング**: 機能追加・修正後

**テスト項目**:
- データベース整合性（外部キー、6艇制約）
- 特徴量生成パイプライン
- 予測確率の合計（= 1.0）
- Kelly計算の妥当性
- エクスポート機能

**実行方法**:
```bash
python -m pytest tests/test_integration.py -v
```

### 3. 全テスト実行
```bash
python run_tests.py
```

---

## テスト実行フロー

### 日常的なワークフロー

```
[1] コード変更
    ↓
[2] 影響範囲の特定
    ↓
[3] 関連テストの実行
    ├─ Kelly基準変更 → test_core_logic.py の TestKellyCalculation
    ├─ 特徴量追加 → test_integration.py の test_feature_generation_pipeline
    └─ DB変更 → test_integration.py の test_database_integrity
    ↓
[4] 全テスト実行（リリース前）
    ↓
[5] テスト合格 → コミット
```

### リリース前チェックリスト

- [ ] 全ユニットテスト合格
- [ ] 全統合テスト合格
- [ ] データベース整合性確認
- [ ] 手動テスト（UI動作確認）
- [ ] バックアップ作成

---

## データ検証

### データ挿入前の検証

```python
from src.validation.data_validator import DataValidator

# レースデータの検証
race_data = {
    'venue_code': '07',
    'race_date': '2025-01-01',
    'race_number': 1,
}

is_valid, errors = DataValidator.validate_race(race_data)
if not is_valid:
    print("検証エラー:")
    for error in errors:
        print(f"  - {error}")
```

### 特徴量の検証

```python
from src.validation.data_validator import FeatureValidator

# 特徴量DataFrameの検証
is_valid, errors = FeatureValidator.validate_features(features_df)
if not is_valid:
    print("特徴量エラー:")
    for error in errors:
        print(f"  - {error}")
```

---

## 既知の問題と対処法

### 問題1: テストデータ不足

**症状**: `pytest.skip("テスト用データが存在しません")`

**対処法**:
1. データベースに最低1ヶ月分のデータを投入
2. テスト用のサンプルデータを作成

### 問題2: 浮動小数点誤差

**症状**: `assert 1.0000001 == 1.0` で失敗

**対処法**: `pytest.approx()` を使用
```python
assert value == pytest.approx(1.0, abs=1e-6)
```

### 問題3: データベースロック

**症状**: `sqlite3.OperationalError: database is locked`

**対処法**:
1. Streamlitアプリを停止
2. データベース接続を必ずcloseする

---

## テスト追加ガイド

### 新機能追加時のテスト作成

1. **ユニットテスト作成**
   ```python
   # tests/test_core_logic.py に追加
   class TestNewFeature:
       def test_basic_case(self):
           """基本ケースのテスト"""
           result = new_function(input_data)
           assert result == expected_value

       def test_edge_case(self):
           """エッジケースのテスト"""
           result = new_function(None)
           assert result == default_value
   ```

2. **統合テスト作成**
   ```python
   # tests/test_integration.py に追加
   def test_new_feature_integration(self):
       """新機能の統合テスト"""
       # データフロー全体を確認
       pass
   ```

3. **テスト実行**
   ```bash
   python -m pytest tests/test_core_logic.py::TestNewFeature -v
   ```

---

## CI/CD統合（将来的な拡張）

### GitHub Actions設定例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest
      - name: Run tests
        run: python run_tests.py
```

---

## よくある質問

### Q1: テストが遅い場合の対処法は？

**A**: 並列実行を有効化
```bash
python -m pytest tests/ -n auto
```
（`pytest-xdist` のインストールが必要）

### Q2: 特定のテストだけ実行したい

**A**: クラス・関数名を指定
```bash
python -m pytest tests/test_core_logic.py::TestKellyCalculation -v
```

### Q3: テストをスキップしたい

**A**: `@pytest.mark.skip` デコレータを使用
```python
@pytest.mark.skip(reason="API未実装")
def test_api_call():
    pass
```

---

## まとめ

### テストの重要性

1. **デグレ防止**: 既存機能が壊れていないことを保証
2. **仕様の明確化**: テストが仕様書の役割
3. **リファクタリングの安全性**: 安心してコード改善可能
4. **バグの早期発見**: 本番環境での問題を未然に防ぐ

### 推奨運用

- **毎日**: 修正後に関連テストを実行
- **週次**: 全テストを実行してレポート確認
- **リリース前**: 必ず全テスト合格を確認

---

**最終更新**: 2025-11-14
