# UI改善機能ガイド

## 概要

予測精度改善機能がUIに統合されました。ユーザーは以下の場所で改善機能を確認・活用できます。

**実装日**: 2025-11-25
**対応UI**: Streamlit Web UI

---

## UIでの改善機能の表示場所

### 1. レース詳細画面（🎯 AI予測タブ）

**場所**: `レース予想` → `レース一覧・推奨` → レース選択 → `🎯 AI予測`タブ

**表示内容**:
- **⚙️ 適用された改善機能** セクション
  - 🔧 Laplace平滑化の効果（展開式）
  - 🔒 1着固定ルールの判定（展開式）

#### Laplace平滑化の効果

予測結果のすぐ下に表示されます。

```
🔧 Laplace平滑化の効果 ▼

○艇に平滑化を適用

| 艇番 | 選手 | 元の勝率 | 平滑化後 | 差分 |
|------|------|----------|----------|------|
|  1   | 山田 | 55.0%   | 55.4%   | +0.4% |
|  4   | 鈴木 |  0.0%   | 33.3%   | +33.3% |
|  5   | 田中 | 10.0%   | 21.4%   | +11.4% |

💡 データ不足の艇ほど大きく補正されます
```

#### 1着固定ルールの判定

```
🔒 1着固定ルールの判定 ▼

✅ 1着固定条件を満たしています
理由: 勝率・データ充実度が基準を満たす

推定勝率: 58.5%
データ充実度: 75

💰 この1号艇は鉄板です！
```

または

```
❌ 1着固定条件を満たしていません
理由: データ充実度不足

推定勝率: 57.2%
データ充実度: 45
```

---

### 2. 設定・管理タブ（📈 予測精度改善）

**場所**: `設定・管理` → `予測精度改善`

**表示内容**:
- 10項目の改善機能の詳細説明
- 各機能の有効/無効状態
- パラメータ設定値
- 効果の説明

#### タブ構成

```
📈 予測精度改善機能

[💡 即効性改善] [🔧 中長期改善] [📊 評価指標]

■ 即効性改善タブ
- 改善1: Laplace平滑化
- 改善2: 1着固定ルール
- 改善3: 信頼度Eフィルタ
- 改善4: 評価指標

■ 中長期改善タブ
- 改善5: 進入予想
- 改善6: 潮位補正
- 改善7: DBインデックス最適化
- 改善8: モーターEWMA
- 改善9: 展示データスクレイピング
- 改善10: 確率較正

■ 評価指標タブ
- Brier Score
- Log Loss
- ECE (Expected Calibration Error)
- 信頼度別的中率
```

#### 設定パネル

各改善機能の現在の設定が表示されます:

```
⚙️ 改善機能の設定

【即効性改善】              【中長期改善】

🔧 Laplace平滑化           📈 モーターEWMA
状態: ✅ 有効                状態: ❌ 無効
alpha値: 2.0                alpha値: 0.3
外枠のゼロ化問題を解決        直近の調子を重視

🔒 1着固定ルール            🌊 潮位補正
状態: ✅ 有効                状態: ✅ 有効
閾値: 0.55                  8会場の潮位影響を補正
最小データ充実度: 60
高勝率1号艇を1着固定

🚫 信頼度Eフィルタ          📊 確率較正
状態: ✅ 有効                状態: ❌ 無効
除外: E判定                  予測確率を実績に合わせて調整
最小表示レベル: D
低信頼度予測を除外
```

---

## 改善機能の設定変更方法

### 設定ファイルの場所

```
config/prediction_improvements.json
```

### 設定例

#### Laplace平滑化のalpha値を変更

```json
{
  "laplace_smoothing": {
    "enabled": true,
    "alpha": 3.0  // 2.0 → 3.0 に変更（より保守的）
  }
}
```

#### 1着固定ルールの閾値を変更

```json
{
  "first_place_lock": {
    "enabled": true,
    "win_rate_threshold": 0.60,  // 0.55 → 0.60 に変更（より厳格）
    "min_data_completeness": 70  // 60 → 70 に変更
  }
}
```

#### モーターEWMAを有効化

```json
{
  "motor_ewma": {
    "enabled": true,  // false → true に変更
    "alpha": 0.3
  }
}
```

### 設定変更後の反映

1. 設定ファイルを保存
2. 新しい予測を生成（`python generate_one_date.py 2025-11-XX`）
3. UIで結果を確認

---

## 改善機能のバッジ（将来実装予定）

予測結果の各艇に、適用された改善機能のバッジを表示する予定:

```
🥇 1号艇  山田太郎
スコア: 58.5  信頼度: A

🔧 平滑化  🔒 1着固定  📊 較正済
```

**バッジの種類**:
- 🔧 平滑化: Laplace平滑化が適用
- 🔒 1着固定: 1着固定ルールに該当
- 📊 較正済: 確率較正が適用
- 📈 EWMA: モーターEWMAが適用

---

## トラブルシューティング

### エラー: "No module named 'src.analysis.smoothing'"

**原因**: 改善機能のモジュールがインポートできない

**解決策**:
1. プロジェクトルートに移動
2. Pythonパスを確認
3. 必要に応じて `sys.path` を追加

### 改善機能が表示されない

**原因**: 設定ファイルが読み込めない、または改善機能が無効

**解決策**:
1. `config/prediction_improvements.json` の存在を確認
2. JSON形式が正しいか確認
3. `enabled: true` になっているか確認

### 平滑化の効果が表示されない

**原因**: 予測結果に `smoothing_applied` フラグがない

**解決策**:
1. 予測を再生成（`python generate_one_date.py`）
2. `src/analysis/statistics_calculator.py` で平滑化が統合されているか確認
3. `config/prediction_improvements.json` で `laplace_smoothing.enabled: true` を確認

---

## UIコンポーネントのファイル構成

```
ui/
  ├── app.py                              # メインアプリ（改善機能メニュー追加）
  └── components/
      ├── improvements_display.py         # 改善機能表示コンポーネント（新規）
      ├── unified_race_detail.py          # レース詳細（改善情報追加）
      └── unified_race_list.py            # レース一覧
```

### 主要コンポーネント

#### `improvements_display.py`

改善機能の表示を担当する新規コンポーネント:

- `render_improvement_badges()`: バッジ生成
- `render_improvement_panel()`: 設定パネル表示
- `render_smoothing_details()`: 平滑化詳細表示
- `render_first_place_lock_details()`: 1着固定詳細表示
- `render_motor_ewma_details()`: モーターEWMA詳細表示
- `render_confidence_filter_info()`: 信頼度フィルタ情報表示
- `render_improvements_summary_page()`: サマリーページ（設定・管理タブ用）

#### `unified_race_detail.py` (修正)

レース詳細画面に改善情報セクションを追加:

```python
# 改善機能の効果を表示
st.markdown("### ⚙️ 適用された改善機能")

with st.expander("🔧 Laplace平滑化の効果", expanded=False):
    render_smoothing_details(predictions)

with st.expander("🔒 1着固定ルールの判定", expanded=False):
    render_first_place_lock_details(predictions)
```

#### `app.py` (修正)

設定・管理タブのメニューに「予測精度改善」を追加:

```python
settings_mode = st.selectbox(
    "管理内容を選択",
    ["予測精度改善", "システム設定", "データ管理", "法則管理", "システム監視"]
)

if settings_mode == "予測精度改善":
    from ui.components.improvements_display import render_improvements_summary_page
    render_improvements_summary_page()
```

---

## 今後の拡張予定

### 1. リアルタイム設定変更

UIから直接設定を変更できる機能:

```python
# 設定変更UI（イメージ）
st.slider("Laplace平滑化 alpha値", 1.0, 5.0, 2.0)
st.slider("1着固定閾値", 0.50, 0.70, 0.55)
if st.button("設定を保存"):
    save_config()
    st.success("設定を保存しました")
```

### 2. 改善機能の効果グラフ

改善前後の予測精度を可視化:

```python
# 効果グラフ（イメージ）
import plotly.graph_objects as go

fig = go.Figure()
fig.add_trace(go.Bar(name='改善前', x=['1着的中率', 'Brier Score'], y=[0.45, 0.25]))
fig.add_trace(go.Bar(name='改善後', x=['1着的中率', 'Brier Score'], y=[0.52, 0.18]))
st.plotly_chart(fig)
```

### 3. A/Bテスト機能

改善機能のON/OFF比較:

```python
# A/Bテスト（イメージ）
st.subheader("A/Bテスト結果")

col1, col2 = st.columns(2)
with col1:
    st.metric("改善機能OFF", "的中率 45%")
with col2:
    st.metric("改善機能ON", "的中率 52%", delta="+7%")
```

---

## まとめ

予測精度改善機能がUIに統合され、ユーザーは以下を確認できるようになりました:

1. **レース詳細画面**: 各予測への改善適用状況
2. **設定・管理画面**: 全改善機能の状態と設定

これにより、改善機能の効果を視覚的に理解し、運用時の判断材料として活用できます。
