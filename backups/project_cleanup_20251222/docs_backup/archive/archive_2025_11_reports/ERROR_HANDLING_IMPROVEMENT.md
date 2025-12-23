# エラーハンドリング改善

**実施日**: 2025年11月3日
**対象ファイル**: `ui/components/model_training.py`

---

## 改善内容

### 改善前

```python
except Exception as e:
    st.error(f"❌ エラーが発生しました: {e}")
    import traceback
    st.code(traceback.format_exc())
```

**問題点**:
- エラーメッセージが単純すぎる
- トレースバックが常に展開されて表示される（画面が見づらい）
- トラブルシューティングのヒントがない
- コンテキスト情報がない

---

### 改善後

#### 1. ヘルパー関数の追加

```python
def display_error_with_traceback(error: Exception, context: str = ""):
    """
    エラーメッセージとトレースバックを表示

    Args:
        error: 発生した例外
        context: エラーの文脈情報
    """
    st.error(f"❌ エラーが発生しました{': ' + context if context else ''}")

    # エラー詳細をエキスパンダーで表示
    with st.expander("🔍 エラー詳細を表示", expanded=False):
        st.markdown(f"**エラータイプ**: `{type(error).__name__}`")
        st.markdown(f"**エラーメッセージ**: {str(error)}")

        st.markdown("---")
        st.markdown("**トレースバック:**")

        # トレースバックを整形して表示
        tb_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        st.code(tb_str, language="python")

        # トラブルシューティングのヒント
        st.markdown("---")
        st.markdown("**💡 トラブルシューティングのヒント:**")

        if "No module named" in str(error):
            st.info("モジュールが見つかりません。必要なライブラリがインストールされているか確認してください。")
        elif "does not exist" in str(error) or "No such file" in str(error):
            st.info("ファイルまたはテーブルが見つかりません。データベースが正しく初期化されているか確認してください。")
        elif "no such column" in str(error):
            st.info("データベースのカラムが見つかりません。テーブル構造を確認してください。")
        elif "out of memory" in str(error).lower():
            st.info("メモリ不足です。データサイズを減らすか、メモリを増やしてください。")
        else:
            st.info("エラーの詳細を確認し、適切な対処を行ってください。")
```

#### 2. 使用方法

```python
except Exception as e:
    display_error_with_traceback(e, "モデル学習処理中")
```

---

## 改善点の詳細

### 1. ユーザビリティ向上

#### エラー情報の階層化
- **第1レベル（常時表示）**: エラー発生の通知とコンテキスト
  ```
  ❌ エラーが発生しました: モデル学習処理中
  ```

- **第2レベル（エキスパンダー内）**: 詳細情報
  - エラータイプ
  - エラーメッセージ
  - トレースバック
  - トラブルシューティングのヒント

#### メリット
- 画面が見やすくなる（デフォルトで折り畳まれている）
- 必要な人だけ詳細を確認できる
- 一般ユーザーは混乱しない

---

### 2. デバッグ情報の充実

#### 表示内容
1. **エラータイプ**: `ValueError`, `KeyError` など
2. **エラーメッセージ**: 例外オブジェクトのメッセージ
3. **完全なトレースバック**: ファイル名、行番号、スタックトレース
4. **コンテキスト情報**: どの処理中にエラーが発生したか

#### メリット
- エラーの原因特定が容易
- 開発者への報告がしやすい
- デバッグ時間の短縮

---

### 3. トラブルシューティングガイド

エラーメッセージに基づいて、自動的にヒントを表示:

| エラーパターン | ヒント |
|--------------|--------|
| `No module named` | ライブラリのインストール確認 |
| `does not exist` / `No such file` | ファイル・テーブルの存在確認 |
| `no such column` | データベーススキーマの確認 |
| `out of memory` | データサイズ削減、メモリ増量 |

#### メリット
- 初心者でも対処しやすい
- サポート負荷の軽減
- 自己解決率の向上

---

### 4. コンテキスト情報

各エラーハンドリングで適切なコンテキストを設定:

```python
# モデル学習時
display_error_with_traceback(e, "モデル学習処理中")

# Stage1学習時
display_error_with_traceback(e, "Stage1モデル学習中")

# 確率校正時
display_error_with_traceback(e, "確率校正処理中")
```

#### メリット
- エラーがどの処理で発生したか即座に判別
- 複数のタブがある場合でも混乱しない

---

## 適用箇所

### model_training.py 内
1. **モデル学習タブ** (`render_model_training_tab()`)
   - コンテキスト: "モデル学習処理中"

2. **Stage1学習タブ** (`render_stage1_training_tab()`)
   - コンテキスト: "Stage1モデル学習中"

3. **確率校正タブ** (`render_probability_calibration_tab()`)
   - コンテキスト: "確率校正処理中"（2箇所）

---

## 今後の展開

### 他のファイルへの適用
この改善されたエラーハンドリングは、他のUIコンポーネントにも適用可能:

- `ui/components/venue_strategy.py`
- `ui/components/backtest.py`
- `ui/components/betting_recommendation.py`
- `ui/components/data_export.py`

### 推奨される実装手順
1. `display_error_with_traceback()` を共通ユーティリティに移動
   ```python
   # 新規ファイル: ui/utils/error_handling.py
   ```

2. 各コンポーネントからインポート
   ```python
   from ui.utils.error_handling import display_error_with_traceback
   ```

3. 既存のエラーハンドリングを置き換え

---

## ベストプラクティス

### エラーハンドリングの原則

1. **ユーザーフレンドリー**
   - 技術的すぎる情報を最初から見せない
   - 必要な人だけ詳細を確認できる構造

2. **デバッグ可能**
   - 完全なトレースバックを保持
   - エラーの再現に必要な情報をすべて含める

3. **アクション可能**
   - 「何が問題か」だけでなく「どうすればいいか」を示す
   - トラブルシューティングのヒントを提供

4. **コンテキスト重視**
   - どの処理中にエラーが発生したかを明記
   - ユーザーの操作と紐付けやすくする

---

## サンプル出力

### ユーザーに表示される内容

#### 第1レベル（常時表示）
```
❌ エラーが発生しました: Stage1モデル学習中
🔍 エラー詳細を表示 ▶
```

#### 第2レベル（エキスパンダー展開時）
```
エラータイプ: ValueError
エラーメッセージ: Training data is empty. Cannot train model with 0 samples.

---
トレースバック:
Traceback (most recent call last):
  File "ui/components/model_training.py", line 485, in render_stage1_training_tab
    trainer.train(X_train, y_train)
  File "src/ml/race_selector.py", line 142, in train
    raise ValueError("Training data is empty. Cannot train model with 0 samples.")
ValueError: Training data is empty. Cannot train model with 0 samples.

---
💡 トラブルシューティングのヒント:
ℹ️ エラーの詳細を確認し、適切な対処を行ってください。
```

---

## まとめ

この改善により、以下が達成されました:

1. ✅ **ユーザビリティ向上** - エキスパンダーで情報階層化
2. ✅ **デバッグ効率化** - 完全なトレースバック表示
3. ✅ **自己解決支援** - トラブルシューティングヒント自動表示
4. ✅ **コード品質向上** - DRY原則に従ったヘルパー関数化
5. ✅ **保守性向上** - 一貫したエラーハンドリングパターン

---

**作成者**: Claude
**最終更新**: 2025年11月3日
