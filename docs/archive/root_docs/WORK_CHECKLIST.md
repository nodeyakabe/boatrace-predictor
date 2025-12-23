# 🔍 作業開始前チェックリスト

**重要**: コード修正・機能追加の前に必ずこのチェックリストを確認してください

---

## ✅ 作業開始前の必須確認事項

### 1. 📚 関連ドキュメントの確認

作業内容に応じて、以下のドキュメントを**必ず読む**：

| 作業内容 | 確認すべきドキュメント |
|---------|---------------------|
| **データベース操作** | [DATABASE_CONSTRAINTS.md](#) - テーブル制約・外部キー |
| **特徴量追加・修正** | [FEATURE_RULES.md](#) - 特徴量の値範囲・型定義 |
| **Kelly基準・確率計算** | [CALCULATION_RULES.md](#) - 計算式・検証ルール |
| **データエクスポート** | [SYSTEM_LOGIC_ANALYSIS.md](SYSTEM_LOGIC_ANALYSIS.md) - データフロー |
| **テスト追加** | [TESTING_GUIDE.md](TESTING_GUIDE.md) - テスト方針 |

### 2. 🎯 影響範囲の特定

以下の質問に答えて、影響範囲を明確にする：

- [ ] この変更はデータベーススキーマに影響しますか？
- [ ] 既存の計算ロジック（Kelly基準、確率計算）を変更しますか？
- [ ] 新しい特徴量を追加しますか？
- [ ] 既存の特徴量の値範囲を変更しますか？
- [ ] UIの表示内容を変更しますか？
- [ ] 外部API（スクレイピング）に影響しますか？

### 3. 🛡️ データ整合性の確認

データベースに関わる変更の場合：

- [ ] 外部キー制約は維持されていますか？
- [ ] 1レース = 6艇の制約は守られていますか？
- [ ] 必須カラムの値は必ず存在しますか？
- [ ] 値の範囲（pit_number: 1-6, rank: 1-6/F/L/K/S など）は正しいですか？

### 4. 🧪 テスト計画の策定

変更内容に応じたテストを計画：

- [ ] 新しいユニットテストが必要ですか？
- [ ] 既存のテストを修正する必要がありますか？
- [ ] 統合テストで確認すべき項目は何ですか？
- [ ] 手動テストで確認すべき項目は何ですか？

---

## 🚀 作業中の注意事項

### 計算ロジックの変更時

```python
# ❌ 悪い例：検証なしで計算
def calculate_something(value):
    result = value * 2
    return result

# ✅ 良い例：入力検証 + 範囲チェック
def calculate_something(value):
    # 入力検証
    if value is None or value < 0:
        raise ValueError(f"無効な値: {value}")

    result = value * 2

    # 結果検証
    if result < 0 or result > 100:
        raise ValueError(f"計算結果が範囲外: {result}")

    return result
```

### データベース操作時

```python
# ❌ 悪い例：検証なしで挿入
cursor.execute("INSERT INTO entries VALUES (?, ?)", (race_id, pit_number))

# ✅ 良い例：検証してから挿入
from src.validation.data_validator import DataValidator

entry_data = {
    'race_id': race_id,
    'pit_number': pit_number,
    'racer_name': racer_name,
    # ...
}

is_valid, errors = DataValidator.validate_entry(entry_data)
if not is_valid:
    for error in errors:
        print(f"検証エラー: {error}")
    return

cursor.execute("INSERT INTO entries VALUES (...)", entry_data)
```

### 特徴量の追加時

```python
# ✅ 必須手順
1. 値の範囲を定義
2. DataValidatorに検証ルールを追加
3. ユニットテストを作成
4. 既存の統合テストを実行
```

---

## 🔄 作業完了後のチェック

### 1. テストの実行

```bash
# 関連テストを実行
python -m pytest tests/test_XXX.py -v

# 全テストを実行
python run_tests.py
```

### 2. データ整合性の確認

```bash
# データベース整合性テストを実行
python -m pytest tests/test_integration.py::TestDataFlow::test_database_integrity -v
```

### 3. 手動動作確認

- [ ] UIで正常に動作するか確認
- [ ] エラーメッセージが適切か確認
- [ ] パフォーマンスに問題ないか確認

### 4. ドキュメントの更新

変更内容に応じて更新：

- [ ] 新しい制約を追加した → [DATABASE_CONSTRAINTS.md](#) を更新
- [ ] 新しい特徴量を追加した → [FEATURE_RULES.md](#) を更新
- [ ] 計算式を変更した → [CALCULATION_RULES.md](#) を更新
- [ ] 新しいテストを追加した → [TESTING_GUIDE.md](TESTING_GUIDE.md) を更新

---

## 🚨 緊急時の対応

### テストが失敗した場合

1. **エラーメッセージを確認**
   ```bash
   python -m pytest tests/ -v --tb=long
   ```

2. **変更を一時的に元に戻す**
   ```bash
   git stash
   python run_tests.py  # 元の状態でテスト
   git stash pop
   ```

3. **問題を特定して修正**
   - データ検証エラー → DataValidatorの設定を確認
   - 計算エラー → 値の範囲を確認
   - DB整合性エラー → 外部キー制約を確認

### データベースが壊れた場合

1. **バックアップから復元**
   ```bash
   copy data\boatrace_backup.db data\boatrace.db
   ```

2. **整合性チェック**
   ```bash
   python -m pytest tests/test_integration.py::TestDataFlow::test_database_integrity -v
   ```

---

## 📋 よくある間違いと対策

### ❌ 間違い1: テストなしでコミット

```bash
# 悪い例
git add .
git commit -m "機能追加"
```

```bash
# 良い例
python run_tests.py
# テスト合格を確認してから
git add .
git commit -m "機能追加（テスト済み）"
```

### ❌ 間違い2: 値の範囲を確認せずに変更

```python
# 悪い例：範囲チェックなし
pit_number = user_input

# 良い例：範囲チェック
pit_number = user_input
if not (1 <= pit_number <= 6):
    raise ValueError(f"pit_numberが範囲外: {pit_number}")
```

### ❌ 間違い3: ドキュメントを読まずに変更

**結果**: 既存の制約を壊してしまう

**対策**: このチェックリストを必ず確認！

---

## 🎯 まとめ

### 作業フロー（完全版）

```
1. このチェックリストを開く
   ↓
2. 関連ドキュメントを読む
   ↓
3. 影響範囲を特定
   ↓
4. データ整合性を確認
   ↓
5. テスト計画を立てる
   ↓
6. コード変更
   ↓
7. 関連テスト実行
   ↓
8. 全テスト実行
   ↓
9. 手動動作確認
   ↓
10. ドキュメント更新
   ↓
11. コミット
```

---

**最終更新**: 2025-11-14

**重要**: このチェックリストを守ることで、デグレ・ロジック破綻を防げます！
