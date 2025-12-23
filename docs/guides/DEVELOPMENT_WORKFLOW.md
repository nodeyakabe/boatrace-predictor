# 開発ワークフロー

**最終更新**: 2025-12-15
**ドキュメント管理者**: Claude Code

---

## 1. 機能追加・改善時の手順

### Step 1: 既存実装の確認（最重要）

```bash
# 類似機能がないか検索
grep -r "機能名" src/
grep -r "機能名" docs/

# 最近の変更履歴を確認
git log --oneline --all -20

# 関連ファイルの変更履歴
git log --oneline -- src/ml/
git log --oneline -- src/prediction/
```

**確認チェックリスト**:
- [ ] 同じ機能が別ファイルに実装されていないか
- [ ] 類似の改善が過去に行われていないか
- [ ] 関連ドキュメントを確認したか

### Step 2: 影響範囲の特定

```bash
# 依存関係を確認
grep -r "import.*対象モジュール" src/
grep -r "from.*対象モジュール" src/

# 呼び出し元を確認
grep -r "対象クラス\|対象関数" src/ scripts/ ui/
```

**影響範囲チェックリスト**:
- [ ] 変更するファイルをリストアップした
- [ ] 呼び出し元のファイルを特定した
- [ ] 設定ファイルへの影響を確認した

### Step 3: 実装

**コーディング規約**:
```python
# ファイルヘッダー
"""
モジュール名

改善内容（YYYY-MM-DD）:
- 変更点1
- 変更点2
"""

# 関数ドキュメント
def function_name(param1: Type1, param2: Type2) -> ReturnType:
    """
    関数の説明

    Args:
        param1: パラメータ1の説明
        param2: パラメータ2の説明

    Returns:
        戻り値の説明

    Example:
        >>> function_name(value1, value2)
        expected_result
    """
    pass
```

**ログ出力**:
```python
import logging
logger = logging.getLogger(__name__)

# 重要な処理の前後にログ
logger.info(f"処理開始: {param}")
logger.debug(f"中間結果: {intermediate}")
logger.info(f"処理完了: {result}")
```

### Step 4: テスト・検証

```bash
# ユニットテスト
python -m pytest tests/test_対象モジュール.py -v

# バックテスト（モデル変更時は必須）
python scripts/backtest_pattern_h_with_venue_course_adjustment.py

# 簡易動作確認
python -c "
from src.xxx import YYY
obj = YYY()
result = obj.method()
print(result)
"
```

**検証チェックリスト**:
- [ ] ユニットテストをパスした
- [ ] バックテストで性能低下がないことを確認した
- [ ] 既存機能のリグレッションテストをパスした

### Step 5: ドキュメント更新

更新すべきドキュメント:
- [ ] `docs/SYSTEM_ARCHITECTURE.md` - 構成変更時
- [ ] `docs/MODEL_MANAGEMENT.md` - モデル変更時
- [ ] `docs/PREDICTION_LOGIC.md` - 予測ロジック変更時
- [ ] `docs/残タスク一覧.md` - タスク完了時

---

## 2. モデル改善時の特別ルール

### 2.1 事前確認（必須）

```bash
# 1. 現在使用中のモデル確認
cat docs/MODEL_MANAGEMENT.md | head -50

# 2. 既存の改善実装確認
git log --grep="改善" --oneline | head -20
grep -r "改善\|Improvement" src/ml/ docs/

# 3. AUC基準値確認
python -c "
import json
with open('models/conditional_meta.json') as f:
    meta = json.load(f)
print('Stage2 AUC:', meta['metrics']['stage2']['cv_auc_mean'])
print('Stage3 AUC:', meta['metrics']['stage3']['cv_auc_mean'])
"

# 4. 現在の特徴量を確認
python -c "
import json
with open('models/conditional_meta.json') as f:
    meta = json.load(f)
for stage, feats in meta.get('feature_names', {}).items():
    print(f'{stage}: {len(feats)} features')
"
```

**確認チェックリスト**:
- [ ] 現在のAUC基準値を確認した（Stage2 >= 0.7423, Stage3 >= 0.6675）
- [ ] 類似の改善が既に実装されていないか確認した
- [ ] 特徴量の重複がないか確認した

### 2.2 改善実施フロー

```
[改善案]
    |
    v
[既存実装確認] --重複あり--> [中止]
    |
    | 重複なし
    v
[ブランチ作成]
    |
    v
[実装]
    |
    v
[AUC確認] --基準未達--> [改善案見直し]
    |
    | 基準達成
    v
[バックテスト] --性能低下--> [ロールバック]
    |
    | 性能維持/向上
    v
[ドキュメント更新]
    |
    v
[コミット・マージ]
```

### 2.3 AUC基準

| Stage | 最低基準 | 改善閾値 |
|-------|---------|---------|
| Stage2 | 0.7423 | +0.01 (0.7523) |
| Stage3 | 0.6675 | +0.01 (0.6775) |

**判定**:
- 基準未達 → 却下
- 基準達成、改善閾値未達 → バックテスト次第で適用検討
- 改善閾値達成 → 適用推奨

### 2.4 バックテスト基準

| 指標 | 最低基準 | 改善目標 |
|-----|---------|---------|
| 年間ROI | 100% | 129.9% |
| 年間収支 | +0円 | +67,570円 |
| 的中率 | 3.0% | 9.2% |

---

## 3. Git運用

### 3.1 ブランチ戦略

```
main (本番)
  |
  +-- feature/xxx-YYYYMMDD (機能追加)
  |
  +-- fix/xxx-YYYYMMDD (バグ修正)
  |
  +-- model/improvement-YYYYMMDD (モデル改善)
```

### 3.2 コミットメッセージ規約

```
<type>: <subject>

<body>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

**type**:
- `feat`: 新機能
- `fix`: バグ修正
- `model`: モデル改善
- `docs`: ドキュメント
- `refactor`: リファクタリング
- `test`: テスト追加

**例**:
```
model: Stage2モデルに相対特徴量追加

## 変更内容
- 1着艇との差分特徴量を追加
- コース位置関係特徴量を追加
- AUC Stage2: 0.7423 → 0.7523 (+1.0pt)

## 検証結果
- バックテストROI: 129.9% → 131.5%

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### 3.3 プッシュ手順

```bash
# 1. 変更確認
git status
git diff

# 2. ステージング
git add .

# 3. コミット
git commit -m "$(cat <<'EOF'
type: subject

詳細な説明

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"

# 4. プッシュ
git push origin main
```

---

## 4. チェックリスト

### 4.1 コミット前チェックリスト

- [ ] コードレビュー完了
- [ ] テスト全通過
- [ ] ドキュメント更新
- [ ] 変更内容をコミットメッセージに記載
- [ ] 機密情報（APIキー等）が含まれていないか確認

### 4.2 モデル更新前チェックリスト

- [ ] 既存モデルのAUCを確認
- [ ] 類似改善の重複確認
- [ ] 学習データ期間を決定
- [ ] CV設定を決定

### 4.3 モデル更新後チェックリスト

- [ ] AUCが基準を満たしている
- [ ] バックテストで性能低下なし
- [ ] 旧モデルをバックアップ
- [ ] メタ情報ファイルを更新
- [ ] MODEL_MANAGEMENT.md を更新

### 4.4 マージ前チェックリスト

- [ ] バックテスト実行
- [ ] 性能劣化なし確認
- [ ] レビュー承認
- [ ] 関連ドキュメント更新

---

## 5. 禁止事項

### 5.1 絶対に避けること

| 禁止事項 | 理由 | 代替策 |
|---------|------|-------|
| ドキュメント未更新でのコミット | 後で分からなくなる | 変更と同時にドキュメント更新 |
| テスト未実施でのマージ | バグ混入リスク | 必ずテスト実施 |
| 重複実装の作成 | 保守性低下、時間の無駄 | 既存実装を事前確認 |
| 既存機能の無断削除 | 依存関係破壊 | deprecation warningを出してから |
| AUC未確認でのモデル差し替え | 性能劣化リスク | 必ずAUC確認 |
| 旧モデルの削除 | ロールバック不可 | バックアップを残す |

### 5.2 Deprecation Warning の出し方

```python
import warnings

def old_function():
    warnings.warn(
        "old_function() は非推奨です。"
        "new_function() を使用してください。",
        DeprecationWarning,
        stacklevel=2
    )
    # 旧実装
```

---

## 6. 開発環境

### 6.1 推奨環境

- Python 3.10+
- SQLite 3
- Git 2.0+

### 6.2 依存パッケージ

```bash
pip install -r requirements.txt
```

主要パッケージ:
- pandas, numpy
- scikit-learn, xgboost, lightgbm
- streamlit
- optuna

### 6.3 開発用コマンド

```bash
# UI起動
cd ui && python -m streamlit run app.py

# バックテスト実行
python scripts/backtest_pattern_h_with_venue_course_adjustment.py

# モデル学習
python scripts/train_conditional_models.py

# 日次ベッティング分析
python scripts/run_daily_betting_pattern_h.py
```

---

## 7. トラブルシューティング

### 7.1 よくあるエラー

| エラー | 原因 | 解決策 |
|-------|------|-------|
| `ModuleNotFoundError` | パスが通っていない | `sys.path.insert(0, ...)` を追加 |
| `FileNotFoundError` | ファイルパスが違う | 絶対パスを使用 |
| `ValueError: features mismatch` | 特徴量の不一致 | メタ情報を確認 |

### 7.2 デバッグ方法

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# または
import pdb; pdb.set_trace()
```

---

## 関連ドキュメント

- [システムアーキテクチャ](SYSTEM_ARCHITECTURE.md)
- [モデル管理ガイド](MODEL_MANAGEMENT.md)
- [予測ロジック詳細](PREDICTION_LOGIC.md)
- [残タスク一覧](残タスク一覧.md)
