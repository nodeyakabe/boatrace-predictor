# 🚀 START HERE - 作業を始める前に

**最終更新**: 2025-11-25

---

## ⚠️ 重要：最初に読むこと

このプロジェクトは複雑なシステムです。**デグレ・ロジック破綻を防ぐため**、必ず以下の手順に従ってください。

---

## 🔄 ステップ0: Gitで最新版を取得（必須）

### 作業開始前に必ず実行

```bash
# 最新版をGitHubから取得
git pull origin main
```

**理由**: 別PCで行った変更を反映するため、必ず最初にpullしてください。

---

## 📚 ステップ1: ドキュメントを開く

### 🎯 メインドキュメント（必ず確認）

**【今すぐ開く】**

1. **[README_WORK_GUIDE.md](README_WORK_GUIDE.md)** ← すべてのドキュメントへのリンク集
2. **[WORK_CHECKLIST.md](WORK_CHECKLIST.md)** ← 作業前の必須チェックリスト
3. **[SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md)** ← 絶対に守るべき制約

---

## ✅ ステップ2: 作業前チェックリスト

### 必ず確認する項目

```
□ WORK_CHECKLIST.md を開いた
□ 今回の作業に関連するドキュメントを読んだ
□ 影響範囲を特定した
□ データ整合性を確認した
□ テスト計画を立てた
```

---

## 🔧 ステップ3: 作業を開始

### データベース操作をする場合

```python
# 1. データ検証を追加
from src.validation.data_validator import DataValidator

is_valid, errors = DataValidator.validate_race(race_data)
if not is_valid:
    raise ValueError(f"検証エラー: {errors}")

# 2. データ挿入
cursor.execute("INSERT INTO races VALUES (...)")

# 3. テスト実行
python -m pytest tests/test_integration.py::TestDataFlow::test_database_integrity -v
```

### 計算ロジックを変更する場合

```python
# 1. 入力検証を追加
if value < 0 or value > 100:
    raise ValueError(f"値が範囲外: {value}")

# 2. 計算
result = calculate_something(value)

# 3. 出力検証
assert 0 <= result <= 1, f"計算結果が異常: {result}"

# 4. テスト実行
python -m pytest tests/test_core_logic.py -v
```

### 特徴量を追加する場合

```python
# 1. SYSTEM_CONSTRAINTS.md で値範囲を確認
# 2. data_validator.py に検証ルールを追加
ValidationRule('new_feature', float, min_value=0, max_value=100)

# 3. テスト追加
def test_new_feature():
    assert 0 <= new_feature <= 100

# 4. テスト実行
python -m pytest tests/test_integration.py::TestDataFlow::test_feature_generation_pipeline -v
```

---

## 🧪 ステップ4: テストを実行

### 全テスト実行（必須）

```bash
python run_tests.py
```

**期待結果**:
```
================================================================================
BoatRace システムテスト実行
================================================================================
tests/test_core_logic.py PASSED
tests/test_integration.py PASSED
...
================================================================================
✅ 全テスト合格
================================================================================
```

---

## 💾 ステップ5: コミット＆プッシュ（必須）

### テスト合格を確認してからコミット＆プッシュ

```bash
# 1. テスト実行
python run_tests.py

# 2. テスト合格を確認してコミット
git add .
git commit -m "機能追加（テスト済み）"

# 3. GitHubにプッシュ（必須）
git push origin main
```

**重要**: 作業完了後は**必ずプッシュ**してください。プッシュしないと別PCに変更が反映されません。

### プッシュ前の確認

```bash
# 変更内容を確認
git status

# コミット履歴を確認
git log --oneline -3
```

---

## 🚨 絶対に守るべきルール（TOP 5）

### 1. 1レース = 6艇
```python
assert len(entries) == 6, "1レースは6艇固定"
```

### 2. 確率の合計 = 1.0
```python
assert abs(sum(probabilities) - 1.0) < 0.01
```

### 3. Kelly分数 ≤ 0.2
```python
kelly_fraction = min(kelly_fraction, 0.2)
```

### 4. 外部キー制約を守る
```python
# 子レコード削除 → 親レコード削除
cursor.execute("DELETE FROM entries WHERE race_id = ?", (race_id,))
cursor.execute("DELETE FROM races WHERE id = ?", (race_id,))
```

### 5. 値の範囲を検証
```python
assert 1 <= pit_number <= 6
assert 0 <= win_rate <= 10
assert 0 <= probability <= 1
```

---

## 🆘 困ったときは

### テストが失敗した
→ [TESTING_GUIDE.md](TESTING_GUIDE.md) の「緊急時の対応」

### 制約が分からない
→ [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md)

### 何をすれば良いか分からない
→ [WORK_CHECKLIST.md](WORK_CHECKLIST.md)

---

## 📖 全ドキュメント一覧

詳細は **[DOCS_INDEX.md](DOCS_INDEX.md)** を参照

---

## ⚡ クイックコマンド

```bash
# 全テスト実行
python run_tests.py

# DB整合性チェック
python -m pytest tests/test_integration.py::TestDataFlow::test_database_integrity -v

# 計算ロジックチェック
python -m pytest tests/test_core_logic.py -v
```

---

## 🎯 作業フロー（まとめ）

```
1. git pull origin main（最新版取得）★必須★
   ↓
2. START_HERE.md を読む（今ここ）
   ↓
3. README_WORK_GUIDE.md でドキュメントを確認
   ↓
4. WORK_CHECKLIST.md で作業前チェック
   ↓
5. SYSTEM_CONSTRAINTS.md で制約確認
   ↓
6. コード変更
   ↓
7. データ検証コード追加
   ↓
8. テスト追加
   ↓
9. python run_tests.py
   ↓
10. ✅合格 → git commit
   ↓
11. git push origin main（GitHubに反映）★必須★
```

---

## 📝 Git運用の重要ポイント

### 必ず守るルール

```bash
# 【作業開始時】必ずpull
git pull origin main

# 【作業完了時】必ずpush
git add .
git commit -m "変更内容の説明"
git push origin main
```

### コンフリクト（競合）が発生したら

```bash
# 1. 現在の変更を退避
git stash

# 2. 最新版を取得
git pull origin main

# 3. 退避した変更を戻す
git stash pop

# 4. コンフリクトしたファイルを手動で修正
# （エディタでファイルを開いて、<<<<<<<, =======, >>>>>>> を削除）

# 5. 修正完了後、コミット＆プッシュ
git add .
git commit -m "Resolve conflict: 変更内容"
git push origin main
```

### Git設定の詳細

詳細は **[GIT_SETUP_GUIDE.md](GIT_SETUP_GUIDE.md)** を参照

---

## 📌 このファイルをブックマーク！

作業を始める前に、必ずこのファイルを確認してください。

**次のステップ**: [README_WORK_GUIDE.md](README_WORK_GUIDE.md) を開く

---

## 🔗 関連ドキュメント

- **[GIT_SETUP_GUIDE.md](GIT_SETUP_GUIDE.md)** - Git設定手順（別PC用）
- **[README_WORK_GUIDE.md](README_WORK_GUIDE.md)** - 全ドキュメントへのリンク集
- **[WORK_CHECKLIST.md](WORK_CHECKLIST.md)** - 作業前チェックリスト

---

**最終更新**: 2025-11-25
