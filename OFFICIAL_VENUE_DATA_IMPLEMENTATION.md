# 公式会場データ取得機能 - 実装完了報告

**実施日**: 2025年11月3日
**所要時間**: 約30分

---

## 📋 実施内容サマリー

BOAT RACE公式サイトから全24会場の詳細データを取得し、データベースに保存する機能を実装しました。

### 実装したファイル

| ファイル | 役割 | 行数 |
|---------|------|------|
| [src/scraper/official_venue_scraper.py](src/scraper/official_venue_scraper.py) | 公式サイトスクレイピング | 280行 |
| [src/database/venue_data.py](src/database/venue_data.py) | DB保存・取得処理 | 300行 |
| [fetch_venue_data.py](fetch_venue_data.py) | 実行スクリプト | 100行 |

**合計**: 約680行の新規コード

---

## 🎯 取得可能なデータ

### 会場マスタデータ

BOAT RACE公式サイト（https://www.boatrace.jp/owpc/pc/data/stadium?jcd={01-24}）から以下のデータを取得：

```python
{
    'venue_code': '01',           # 会場コード（'01'〜'24'）
    'venue_name': '桐生',          # 会場名
    'water_type': '淡水',          # 水質（淡水/海水/汽水）
    'tidal_range': 'なし',         # 干満差
    'motor_type': '減音',          # モーター種別
    'course_1_win_rate': 47.6,    # 1コース1着率（%）
    'course_2_win_rate': 15.2,    # 2コース1着率（%）
    'course_3_win_rate': 12.1,    # 3コース1着率（%）
    'course_4_win_rate': 10.3,    # 4コース1着率（%）
    'course_5_win_rate': 8.5,     # 5コース1着率（%）
    'course_6_win_rate': 6.3,     # 6コース1着率（%）
    'record_time': '1.42.8',      # レコードタイム
    'record_holder': '石田章央',   # 記録保持者
    'record_date': '2004/10/27',  # 記録樹立日
    'characteristics': '...'      # 会場特性（説明文）
}
```

### 全24会場一覧

| コード | 会場名 | コード | 会場名 | コード | 会場名 | コード | 会場名 |
|--------|--------|--------|--------|--------|--------|--------|--------|
| 01 | 桐生 | 07 | 蒲郡 | 13 | 尼崎 | 19 | 下関 |
| 02 | 戸田 | 08 | 常滑 | 14 | 鳴門 | 20 | 若松 |
| 03 | 江戸川 | 09 | 津 | 15 | 丸亀 | 21 | 芦屋 |
| 04 | 平和島 | 10 | 三国 | 16 | 児島 | 22 | 福岡 |
| 05 | 多摩川 | 11 | びわこ | 17 | 宮島 | 23 | 唐津 |
| 06 | 浜名湖 | 12 | 住之江 | 18 | 徳山 | 24 | 大村 |

---

## 🗄️ データベース設計

### テーブル: `venue_data`

```sql
CREATE TABLE venue_data (
    venue_code TEXT PRIMARY KEY,      -- '01'〜'24'
    venue_name TEXT NOT NULL,          -- '桐生', '戸田', ...
    water_type TEXT,                    -- '淡水', '海水', '汽水'
    tidal_range TEXT,                   -- '干満差あり' or 'なし'
    motor_type TEXT,                    -- モーター種別
    course_1_win_rate REAL,             -- 1コース1着率（%）
    course_2_win_rate REAL,             -- 2コース1着率（%）
    course_3_win_rate REAL,             -- 3コース1着率（%）
    course_4_win_rate REAL,             -- 4コース1着率（%）
    course_5_win_rate REAL,             -- 5コース1着率（%）
    course_6_win_rate REAL,             -- 6コース1着率（%）
    record_time TEXT,                   -- レコード時間（例: '1.42.8'）
    record_holder TEXT,                 -- レコードホルダー名
    record_date TEXT,                   -- レコード日付（例: '2004/10/27'）
    characteristics TEXT,               -- 水面特性の説明文
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 最終更新日時
);
```

**主キー**: `venue_code`（'01'〜'24'）
**更新方式**: UPSERT（INSERT OR REPLACE）

---

## 🚀 使い方

### 1. データ取得・保存

```bash
# 全24会場のデータを取得してDBに保存
python fetch_venue_data.py
```

**実行内容**:
1. BOAT RACE公式サイトから各会場データを取得（2秒間隔）
2. データベースに保存（UPSERT）
3. 取得結果のサマリー表示（1コース勝率TOP5/BOTTOM5）

**所要時間**: 約1分（24会場 × 2秒 + 処理時間）

### 2. データ取得（Python API）

#### 特定会場のデータ取得

```python
from src.database.venue_data import VenueDataManager
from config.settings import DATABASE_PATH

manager = VenueDataManager(DATABASE_PATH)

# 桐生（01）のデータを取得
kiryu_data = manager.get_venue_data('01')

print(f"会場名: {kiryu_data['venue_name']}")
print(f"水質: {kiryu_data['water_type']}")
print(f"1コース勝率: {kiryu_data['course_1_win_rate']}%")
```

#### 全会場のコース別勝率を取得

```python
# 全会場のコース別勝率
win_rates = manager.get_venue_win_rates()

# {'01': [47.6, 15.2, 12.1, 10.3, 8.5, 6.3], '02': [...], ...}
for venue_code, rates in win_rates.items():
    venue_name = manager.get_venue_data(venue_code)['venue_name']
    print(f"{venue_name}: 1コース{rates[0]:.1f}%")
```

### 3. スクレイピング単体テスト

```bash
# 桐生（01）のデータのみ取得してテスト
python -c "
from src.scraper.official_venue_scraper import OfficialVenueScraper

scraper = OfficialVenueScraper()
data = scraper.fetch_venue_data('01')
print(data)
scraper.close()
"
```

---

## 📊 活用例

### 1. 予測モデルへの統合

会場別の1コース勝率を特徴量として活用：

```python
# feature_generator.py に追加

def add_venue_features(self, race_data, venue_code):
    """会場特性を特徴量として追加"""
    from src.database.venue_data import VenueDataManager
    from config.settings import DATABASE_PATH

    manager = VenueDataManager(DATABASE_PATH)
    venue_info = manager.get_venue_data(venue_code)

    # 特徴量として追加
    race_data['venue_course1_win_rate'] = venue_info['course_1_win_rate']
    race_data['venue_course2_win_rate'] = venue_info['course_2_win_rate']
    # ...

    return race_data
```

### 2. 会場別の補正係数計算

```python
def calculate_venue_adjustment(venue_code, course):
    """会場・コース別の補正係数を計算"""
    manager = VenueDataManager(DATABASE_PATH)
    venue_data = manager.get_venue_data(venue_code)

    # 全会場平均との差を補正係数に
    all_avg = 16.67  # 1コース平均勝率（1/6 = 16.67%）
    venue_win_rate = venue_data[f'course_{course}_win_rate']

    adjustment = venue_win_rate / all_avg
    return adjustment
```

### 3. UI統合（会場データ表示タブ）

```python
# ui/app.py に追加

def render_venue_data_tab():
    """会場データ表示タブ"""
    st.subheader("🏟️ 会場データ")

    manager = VenueDataManager(DATABASE_PATH)
    all_venues = manager.get_all_venues()

    # 会場選択
    venue_names = [v['venue_name'] for v in all_venues]
    selected = st.selectbox("会場を選択", venue_names)

    # 選択された会場のデータ表示
    venue_data = next(v for v in all_venues if v['venue_name'] == selected)

    st.markdown(f"### {venue_data['venue_name']} ボートレース場")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("水質", venue_data['water_type'])
    with col2:
        st.metric("干満差", venue_data['tidal_range'])
    with col3:
        st.metric("レコード", venue_data['record_time'])

    # コース別勝率グラフ
    import plotly.graph_objects as go

    fig = go.Figure(data=[
        go.Bar(
            x=['1コース', '2コース', '3コース', '4コース', '5コース', '6コース'],
            y=[
                venue_data['course_1_win_rate'],
                venue_data['course_2_win_rate'],
                venue_data['course_3_win_rate'],
                venue_data['course_4_win_rate'],
                venue_data['course_5_win_rate'],
                venue_data['course_6_win_rate']
            ]
        )
    ])
    fig.update_layout(title="コース別1着率")
    st.plotly_chart(fig)
```

---

## ✅ 動作確認

### 確認項目

- [x] スクレイパーが正常にデータ取得（桐生テスト成功）
- [x] データベーステーブル作成成功
- [x] データ保存・取得API動作確認
- [x] 全24会場のデータ構造確認（WebFetch使用）
- [x] UPSERT動作確認（重複データ更新）

### テスト結果

```bash
$ python src/scraper/official_venue_scraper.py

【テスト1: 桐生（01）のデータ取得】
  取得中: 桐生 (https://www.boatrace.jp/owpc/pc/data/stadium?jcd=01)
  ✓ 成功

取得データ:
  venue_code: 01
  venue_name: 桐生
  water_type: 淡水
  tidal_range: なし
  motor_type: 減音
  course_1_win_rate: 47.6
  course_2_win_rate: 15.2
  ...
```

---

## 📈 期待される効果

### 1. 予測精度の向上

- **会場特性の反映**: 1コース勝率が高い会場では内枠有利に補正
- **データドリブン**: 経験則ではなく、公式データに基づく予測
- **特徴量追加**: 予測モデルに新たな情報源を提供

### 2. ユーザー体験の向上

- **会場情報の可視化**: UI上で各会場の特性を確認可能
- **レース選択の支援**: 会場別の傾向を見て購入判断が可能
- **透明性の向上**: データの根拠が明確

### 3. データ管理の効率化

- **自動更新**: `fetch_venue_data.py`で定期実行可能
- **バージョン管理**: `updated_at`カラムで更新履歴を追跡
- **中央管理**: 会場データを一元管理

---

## 🔄 今後の改善案

### 短期（1週間）

- [ ] **UI統合**: 会場データ表示タブの追加
- [ ] **予測モデル統合**: feature_generator.pyに会場特徴量追加
- [ ] **データ更新スケジューラー**: 月1回自動更新

### 中期（2-3週間）

- [ ] **会場別分析機能**: 会場ごとの傾向分析UI
- [ ] **補正係数の自動計算**: 予測時に会場補正を自動適用
- [ ] **季節別データの取得**: 春夏秋冬別のコース勝率も取得

### 長期（1-2ヶ月）

- [ ] **追加データの取得**: 風向き、水面図の詳細データ
- [ ] **機械学習への統合**: 会場データを学習に活用
- [ ] **リアルタイム更新**: レース当日の会場コンディション取得

---

## 🔗 関連ドキュメント

- [REMAINING_TASKS.md](REMAINING_TASKS.md) - 残タスク一覧（タスク#8完了）
- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md) - システム仕様書
- [SCRAPER_CONSOLIDATION_COMPLETED.md](SCRAPER_CONSOLIDATION_COMPLETED.md) - スクレイパー整理報告

---

## 📝 まとめ

### 実施内容

- ✅ 公式会場データスクレイパーの実装（280行）
- ✅ データベース管理モジュールの実装（300行）
- ✅ データ取得・保存スクリプトの実装（100行）
- ✅ テーブル設計・API設計の完了

### 取得可能データ

- 全24会場のマスタデータ
- コース別1着率（1〜6コース）
- 水質・干満差・モーター種別
- レコード情報（タイム・記録者・日付）

### 効果

- 予測精度向上のための新たな特徴量源
- データドリブンな会場分析の基盤
- ユーザーへの会場情報提供機能の実装準備完了

---

**作成者**: Claude
**最終更新**: 2025年11月3日
**ステータス**: 実装完了（UI統合は今後の課題）
