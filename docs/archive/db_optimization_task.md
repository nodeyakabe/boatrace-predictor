# DB接続最適化タスク

**作成日**: 2025-12-03
**優先度**: 高
**種別**: パフォーマンス改善（既存システム全体）

---

## 概要

予測システム全体で発生しているDB接続問題を解決し、処理速度を**90%改善**する。

---

## 現状の問題

### パフォーマンス

- **1レースあたり32秒**
- **100レースで53分**（期待: 2-3分）
- **DB接続が99.5%の時間を消費**

### 根本原因

各Analyzerクラスが個別にDB接続を作成・破棄している:

```python
# 現状の実装（全Analyzerで共通）
def _fetch_one(self, query, params):
    conn = sqlite3.connect(self.db_path)  # 毎回新規接続
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()  # 毎回切断
    return result
```

**1レースで98回の接続/切断**が発生:
- RacerAnalyzer: 25回
- MotorAnalyzer: 13回
- EntryPredictionModel: 6回
- その他Analyzers: 54回

---

## 影響範囲

### ❌ 新機能だけの問題ではない

✅ **予測システム全体**の根本的な問題:

1. **日常的な予測生成**
   - UIでのレース予測（毎回32秒）
   - バッチ予測

2. **全ての既存機能**
   - 基本スコア計算
   - 選手/モーター分析
   - 決まり手/グレード適性
   - 拡張スコア
   - dynamic_integration
   - entry_prediction_model
   - beforeinfo統合
   - 潮位補正
   - etc.

3. **影響を受けるファイル**（10+ファイル）
   ```
   src/analysis/racer_analyzer.py
   src/analysis/motor_analyzer.py
   src/analysis/kimarite_scorer.py
   src/analysis/grade_scorer.py
   src/analysis/extended_scorer.py
   src/analysis/entry_prediction_model.py
   src/analysis/beforeinfo_scorer.py
   src/analysis/compound_buff_system.py
   src/prediction/rule_based_engine.py
   src/analysis/tide_adjuster.py
   etc.
   ```

---

## 解決策

### Phase 1: DB接続プールの統合

**既に実装済み**のDB接続プール（[src/utils/db_connection_pool.py](../src/utils/db_connection_pool.py)）を各Analyzerで使用する。

#### 実装方針

各Analyzerの`_connect()`メソッドを変更:

```python
# 変更前
def _connect(self):
    return sqlite3.connect(self.db_path)

# 変更後
from src.utils.db_connection_pool import get_connection

def _connect(self):
    return get_connection(self.db_path)
```

#### 変更が必要なメソッド（例: racer_analyzer.py）

- `_connect()`: 1箇所
- `_fetch_all()`: 接続の閉じ方を変更
- `_fetch_one()`: 接続の閉じ方を変更

**注意**: 接続プールでは`conn.close()`を呼ばない（再利用のため）

```python
# 変更前
def _fetch_one(self, query, params):
    conn = self._connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()  # ← これを削除
    return result

# 変更後
def _fetch_one(self, query, params):
    conn = self._connect()  # プールから取得
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchone()
    cursor.close()  # カーソルのみ閉じる
    return result
```

#### 作業量

- **影響ファイル**: 10+ファイル
- **変更メソッド**: 100+個
- **所要時間**: 3-5時間
- **テスト**: 各Analyzerの動作確認

---

## 期待される効果

### パフォーマンス改善

| 項目 | 現在 | Phase 1後 | 改善率 |
|------|------|-----------|--------|
| 1レース | 32秒 | 3-5秒 | **90%削減** |
| 100レース | 53分 | 5-8分 | **90%削減** |
| UIでの予測 | 遅い | 快適 | **体感大幅向上** |

### ユーザー体験の向上

- ✅ UIでの予測生成が即座に完了
- ✅ バックテストが実用的な時間で完了
- ✅ A/Bテストが現実的に実施可能
- ✅ 日々の予測生成がストレスフリー

---

## 実装手順

### Step 1: テスト環境での確認

1. racer_analyzer.pyのみ変更
2. 1レーステストで効果確認（32秒 → 数秒を確認）
3. 問題なければ次へ

### Step 2: 全Analyzerに適用

各ファイルで同じ変更を適用:
- `_connect()`メソッドの変更
- `_fetch_all()`/`_fetch_one()`の変更
- `conn.close()`の削除

### Step 3: 統合テスト

1. 1レーステスト実行
2. 100レーステスト実行
3. 精度に影響がないことを確認
4. 速度改善を確認

### Step 4: 本番適用

feature_flags.pyで段階的に有効化（必要に応じて）

---

## リスクとリスク軽減策

### リスク

| リスク | 影響度 | 対策 |
|--------|--------|------|
| 接続プールのバグ | 中 | 十分なテスト |
| マルチスレッド問題 | 低 | threading.localで対応済み |
| 既存機能への影響 | 低 | 精度テストで確認 |

### リスク軽減策

1. **段階的実装**: 1ファイルずつ変更・テスト
2. **バックアップ**: 変更前にコミット
3. **ロールバック計画**: Gitで元に戻せる状態を維持
4. **精度検証**: 変更前後で予測結果が同じことを確認

---

## 関連ドキュメント

- [パフォーマンス最適化計画](performance_optimization_plan.md)
- [最適化調査結果](../temp/optimization_findings.md)
- [DB接続プール実装](../src/utils/db_connection_pool.py)

---

## 補足: なぜ別タスクにするのか

### 影響範囲の広さ

- 新機能だけでなく**既存システム全体**に影響
- 10+ファイル、100+メソッドの変更
- 慎重なテストが必要

### 作業の性質

- 新機能開発とは別の「既存システムの改善」
- パフォーマンス問題は既に存在していた
- 新機能追加で**問題が顕在化**しただけ

### 実装のタイミング

- 新機能の動作確認を優先
- DB最適化は独立したタスクとして実施
- 精度に影響しない純粋な効率化

---

## 次のステップ

1. ✅ この資料を確認
2. ⏳ 新機能のテスト・検証を完了
3. ⏳ 別途、DB最適化タスクとして着手
4. ⏳ 段階的に実装・テスト・統合

---

**まとめ**: DB接続最適化は予測システム全体の根本的な問題を解決する重要なタスク。新機能とは独立して、慎重に実装すべき。
