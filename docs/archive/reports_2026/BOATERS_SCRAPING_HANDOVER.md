# ボーターズスクレイピングシステム 引継ぎ資料

作成日: 2026-05-13  
プロジェクト: BoatRace_package_20251115_172032

---

## 1. 概要

**ボーターズ（boaters-boatrace.com）** はNext.js製の競艇AI予想サービス。全ページが `__NEXT_DATA__` にJSON埋め込みでデータを持つため、ブラウザを使わず `requests` のみでスクレイピング可能（ローカル実行ならIP規制なし）。

### できること
- 3連単買い目・的中確率・投資額・オッズを全グループ自動取得
- 展示タイム・ST・チルト・重量・風・波を取得
- レース結果（isHit）も取得済みの場合は自動判定
- Plackett-Luceモデルでボーターズのλ（選手強度）を逆算
- λと各指標（勝率・展示タイム・ST等）の相関分析

---

## 2. URLパターン

```
https://boaters-boatrace.com/race/{venue_slug}/{date}/{race}R/{page}
```

| ページ | 内容 |
|--------|------|
| `race-prediction?rf=pr_button` | 買い目・確率・グループ・結果 |
| `last-minute?last-minute-content=original-tenji` | 展示タイム・ST・風・波 |
| `race-result` | 結果のみ |
| `data` | 選手データ |

### 会場スラッグ一覧

| コード | スラッグ | 会場名 |
|:------:|---------|--------|
| 01 | kiryu | 桐生 |
| 02 | toda | 戸田 |
| 03 | edogawa | 江戸川 |
| 04 | heiwajima | 平和島 |
| 05 | tamagawa | 多摩川 |
| 06 | hamanako | 浜名湖 |
| 07 | gamagori | 蒲郡 |
| 08 | tokoname | 常滑 |
| 09 | tsu | 津 |
| 10 | mikuni | 三国 |
| 11 | biwako | びわこ |
| 12 | suminoe | 住之江 |
| 13 | amagasaki | 尼崎 |
| 14 | naruto | 鳴門 |
| 15 | marugame | 丸亀 |
| 16 | kojima | 児島 |
| 17 | miyajima | 宮島 |
| 18 | tokuyama | 徳山 |
| 19 | shimonoseki | 下関 |
| 20 | wakamatsu | 若松 |
| 21 | ashiya | 芦屋 |
| 22 | fukuoka | 福岡 |
| 23 | karatsu | 唐津 |
| 24 | omura | 大村 |

---

## 3. スクレイピングの実装

### コアロジック（`__NEXT_DATA__` 取得）

```python
import requests, re, json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}

def fetch_next_data(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=15)
    # 403はAnthropicサーバーのみブロック。ローカルPCからは200が返る
    assert r.status_code == 200, f"HTTP {r.status_code}"
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        r.text, re.DOTALL
    )
    return json.loads(m.group(1))["props"]["pageProps"]["initialApolloState"]
```

### 予想データ取得

```python
def get_ai_bets(venue_slug, date, race_num):
    """
    戻り値: {
        'manshu_rate': 5,          # AI万舟率(%)
        'aiBets': [...],           # 全買い目リスト
        'odds': {...},             # 全三連単オッズ (_3t123 形式)
        'hit_combination': '1-3-2' # 結果判明時のみ（未確定はNone）
    }
    """
    url = (f"https://boaters-boatrace.com/race/{venue_slug}/{date}/{race_num}R"
           f"/race-prediction?rf=pr_button")
    state = fetch_next_data(url)

    # ターゲットレースを特定
    race_obj = next(
        v for k, v in state.items()
        if k.startswith("CrawledRace:") and isinstance(v, dict)
        and v.get("round") == race_num and v.get("aiBets")
    )

    # オッズテーブル
    odds_ref = race_obj.get("odds", {}).get("__ref", "")
    odds_obj = state.get(odds_ref, {})

    # isHitから結果を逆算
    hit = next((b["kaime"] for b in race_obj["aiBets"] if b.get("isHit")), None)

    return {
        "manshu_rate": race_obj.get("manshuRatePercent", 0),
        "aiBets": race_obj["aiBets"],
        "odds": odds_obj,
        "hit_combination": hit,
    }
```

### aiBets のデータ構造

```python
# 1件のaiBet
{
    "__typename": "AiBet",
    "raceId": "2026-05-130801",
    "kaime": "1-3-2",      # 三連単組み合わせ
    "proba": 0.1201,       # 的中確率 (0〜1)
    "bet": 900,            # 投資額（円）
    "aiType": "Hit",       # グループ: Profitable/Hit/NewBalance/HighOdds
    "isHit": True,         # 的中フラグ（結果確定後）
    "isPikaichi": False    # 予想印の筆頭
}
```

### aiType（グループ）の意味

| aiType | 役割 | 特徴 |
|--------|------|------|
| Profitable | G1 本命EV重視 | 点数少ない・期待値重視。ROI最も高い傾向 |
| Hit | G2 的中重視 | 広め買い・的中率狙い |
| NewBalance | G3 バランス | G1/G2の中間 |
| HighOdds | G4 万舟狙い | 低確率高配当 |

### オッズキーのフォーマット

```python
# 例: 1-3-2 のオッズ
odds_obj["_3t132"]  # → 6.6

# 変換ルール
comb = "1-3-2"
key = "_3t" + comb.replace("-", "")  # → "_3t132"
```

### 展示データ取得

```python
def get_exhibition(venue_slug, date, race_num):
    """
    戻り値: {
        '1': {'time': 6.72, 'time_rank': 2, 'st': 0.07, 'st_rank': 1, 'tilt': 0},
        '2': {...}, ...
    }
    """
    url = (f"https://boaters-boatrace.com/race/{venue_slug}/{date}/{race_num}R"
           f"/last-minute?last-minute-content=original-tenji")
    state = fetch_next_data(url)

    exhibition = {}
    for k, v in state.items():
        if k.startswith("CrawledRaceBeforeRacer:") and isinstance(v, dict):
            bn = str(v["boatNumber"])
            exhibition[bn] = {
                "time":      v.get("tenjiTime"),       # 展示タイム
                "time_rank": v.get("tenjiRank"),        # 展示タイム順位
                "st":        v.get("startTenjiTime"),   # 展示ST
                "st_rank":   v.get("startTenjiRank"),   # 展示ST順位
                "tilt":      v.get("tilt"),              # チルト
            }

    # 風・波はBeforeInfoから
    bi_key = next((k for k in state if k.startswith("CrawledRaceBeforeInfo:")), None)
    bi = state.get(bi_key, {}) if bi_key else {}
    conditions = {
        "weather":        bi.get("weather"),
        "wind_speed":     bi.get("windSpeed"),
        "wind_direction": bi.get("windDirection"),
        "wave_height":    bi.get("waveHeight"),
    }
    return exhibition, conditions
```

---

## 4. 保存JSONスキーマ

保存先: `data/boaters_analysis/races/{YYYYMMDD}_{venue_code}_{race}R.json`

```json
{
  "race_info": {
    "date": "2026-05-13",
    "venue_code": "08",
    "venue_name": "常滑",
    "race_number": 1,
    "race_time": "08:40",
    "race_id": 1017546,
    "source": "scraped:tokoname",
    "boaters_ai_manshu_rate": 5
  },
  "entries": {
    "1": {"name": "浜先　　真範", "rank": "A1", "win_rate": 7.23,
          "local_win_rate": 6.50, "motor_2r": 45.0, "avg_st": 0.14}
  },
  "exhibition": {
    "1": {"time": 6.72, "time_rank": 2, "st": 0.07, "st_rank": 1, "tilt": 0}
  },
  "race_conditions": {
    "weather": "晴", "wind_speed": 3, "wind_direction": 11, "wave_height": 1
  },
  "boaters_groups": [
    {
      "group": 1,
      "group_name": "Profitable",
      "top_pick": [1, 2, 6],
      "total_amount": 2800,
      "bets": [
        {
          "combination": "1-2-6",
          "odds": 11.3,
          "amount": 1800,
          "payout": 20340,
          "probability": 6.77,
          "is_hit": false,
          "ai_type": "Profitable"
        }
      ]
    }
  ],
  "our_predictions": {
    "advance": {"1": {"score": 86.2, "rank": 1, "confidence": "B"}},
    "before_estimated": {},
    "purchase_triggered": false,
    "purchase_reason": "要確認"
  },
  "result": {
    "first_place": 1,
    "second_place": 3,
    "third_place": 2,
    "combination": "1-3-2",
    "trifecta_odds": 6.6,
    "our_advance_correct": false,
    "boaters_g1_correct": true,
    "boaters_g2_correct": false,
    "boaters_g3_correct": false,
    "boaters_had_combination": true,
    "boaters_combination_detail": "G2(900円)"
  },
  "analysis": {
    "lambda_estimated": {"1": 0.921, "2": 0.021, "3": 0.029,
                         "4": 0.011, "5": 0.004, "6": 0.014},
    "lambda_model_loss": 32.835,
    "correlations_with_lambda": {
      "win_rate": 0.751,
      "local_win_rate": 0.800,
      "motor_2r": -0.149,
      "exh_time_neg": 0.0,
      "exh_rank_neg": 0.0,
      "exh_st_neg": 0.0
    },
    "noted_at": "2026-05-13"
  }
}
```

---

## 5. 既存スクリプト一覧

| スクリプト | 役割 |
|-----------|------|
| `scripts/analysis/boaters_reverse_engineer.py` | メインツール（全機能統合） |
| `scripts/analysis/boaters_bulk_scrape.py` | DBスケジュール連携一括スクレイピング |

### boaters_reverse_engineer.py の使い方

```bash
# URLから自動スクレイピング（最推奨）
python scripts/analysis/boaters_reverse_engineer.py \
    --url "https://boaters-boatrace.com/race/tokoname/2026-05-13/1R/race-prediction"

# テキストファイルから手動登録
python scripts/analysis/boaters_reverse_engineer.py \
    --input "C:/path/to/file.txt" \
    --date 2026-05-13 --venue 08 --race 1

# 結果を後から追記
python scripts/analysis/boaters_reverse_engineer.py \
    --date 2026-05-13 --venue 08 --race 1 \
    --update-result 1-3-2

# 蓄積データ一覧
python scripts/analysis/boaters_reverse_engineer.py --list

# 累積相関分析（拡張版・7セクション出力）
python scripts/analysis/boaters_reverse_engineer.py --analyze
```

### boaters_bulk_scrape.py の使い方

```bash
# DB（boatrace.db）からレース候補を自動取得して1000件まで蓄積
python scripts/analysis/boaters_bulk_scrape.py
```

スクリプト先頭の定数で調整可能:
```python
TARGET      = 1000   # 目標総件数
BATCH_DELAY = 0.35   # リクエスト間隔（秒）
MAX_ERRORS  = 20     # 連続エラー上限
```

---

## 6. n=1000 分析結果サマリー（最新・2026-05-13）

### λ相関（Plackett-Luceモデルで逆算した選手強度との相関）

| 指標 | mean r | n | p値 | 判定 |
|------|:------:|:---:|:---:|:---:|
| 全国勝率 | +0.436 | 1000 | 0.0000 | *** 確定 |
| 会場勝率 | +0.292 | 1000 | 0.0000 | *** 確定 |
| 展示タイム（速い） | +0.250 | 999 | 0.0000 | *** 確定 |
| 展示TM順位（速い） | +0.246 | 999 | 0.0000 | *** 確定 |
| 展示ST（速い） | +0.095 | 999 | 0.0025 | ** 確定 |
| モーター2連率 | +0.057 | 936 | 0.0838 | n.s. |

**ボーターズロジック仮説（n=1000確定）**:
```
ボーターズ強度 ≈ コースバイアス
              × 選手力（全国勝率 r~0.44・会場勝率 r~0.29）
              × 展示タイム補正（r~0.25）
```
展示STは弱い寄与（r=0.095）。モーター2連率はほぼ無視。

### グループ別ROI（n=1000）

| グループ | 投資 | 払戻 | ROI | 的中含レース |
|---------|:---:|:---:|:---:|:---:|
| G1 Profitable | 1,877,900 | 1,713,480 | **91.2%** | 69件 |
| G2 Hit | 5,497,000 | 4,471,300 | 81.3% | 481件 |
| G3 NewBalance | 5,504,900 | 4,433,610 | 80.5% | 416件 |
| G4 HighOdds | 5,474,100 | 5,454,690 | **99.6%** | 123件 |
| **全体** | 18,373,200 | 16,079,020 | **87.5%** | - |

**注意**: G1が全グループ中最高ROIだが、いずれも100%未満（控除率を超えていない）。

### AI万舟率別ROI（n=1000）

| 万舟率 | 投資 | 払戻 | ROI |
|:------:|:---:|:---:|:---:|
| < 30% | 17,383,000 | 15,032,710 | 86.5% |
| **≥ 30%** | 990,200 | 1,046,310 | **105.7%** ← 注目 |

n=100時点の239.2%から収束し105.7%に落ち着いた。まだn=990件しかないが傾向として「高万舟率レースは回収率が高い」は支持される。n≥3000で実用判断を推奨。

### 的中率（n=1000）

| 指標 | 的中 | 的中率 |
|------|:---:|:---:|
| 本ツールadvance 3着内 | 66/1000 | 6.6% |
| G1 Profitable | 47/1000 | 4.7% |
| G2 Hit | 74/1000 | 7.4% |
| G3 NewBalance | 48/1000 | 4.8% |
| **いずれかに含む** | 582/1000 | **58.2%** |

### 1着コース分布（n=1000）

| コース | 件数 | 比率 |
|:------:|:---:|:---:|
| 1コース | 551 | 55.4% |
| 2コース | 135 | 13.6% |
| 3コース | 127 | 12.8% |
| 4コース | 91 | 9.1% |
| 5コース | 58 | 5.8% |
| 6コース | 33 | 3.3% |

### n=100 → n=1000 の変化

| 指標 | n=100 | n=1000 | 変化 |
|------|:-----:|:------:|:----:|
| G1 ROI | 115.3% | 91.2% | ↓ 収束 |
| G4 ROI | 96.9% | 99.6% | → 安定 |
| 万舟率≥30% ROI | 239.2% | 105.7% | ↓ 大幅収束 |
| 展示タイム r | +0.219* | +0.250*** | ↑ 有意確定 |
| 全体ROI | 95.0% | 87.5% | ↓ 収束 |

---

## 7. Opusによる統計的評価（2026-05-13）

### n=100評価（当初）
- **n=100で確定**: 全国勝率・会場勝率の正の相関
- **n=100では不十分**: 展示タイム・モーター・ST（多重比較補正後に脱落）
- **AI万舟率ROI239%は偶然と区別不能**: 95%CI推定 [60%, 450%]
- **推奨サンプル数**:
  - 1,000件 → 展示タイム確定・会場別層別分析・G1ROI再現性
  - 3,000件 → 万舟率ROI実用判断・多変量モデル

### n=1000評価（現時点）
- **展示タイム確定**: r=+0.250, p<0.001 (***) → Opusの予測通り確定
- **G1 ROI収束**: 115%→91%。全グループで100%未満が確定。ボーターズ単体では控除率以下
- **万舟率≥30% ROI=105.7%**: まだ信頼区間広い（n=99件）。傾向は支持されるが実用判断はn≥3000待ち
- **次の課題**: 会場別・コース別の層別分析（24会場は物理配置が全て異なるため全会場一括集計は注意）

---

## 8. 注意事項

1. **boaters-boatrace.comへのアクセス**: AnthropicサーバーからはHTTP403。ローカルPCから実行すること（WebFetchツールは使えない）
2. **リクエスト間隔**: 0.35秒以上を推奨。短すぎるとレート制限の可能性あり
3. **過去データのisHit**: レース結果が確定していれば `isHit: true` が付く。未来/当日レースは全て `isHit: false`
4. **展示データの有無**: レース前に取得した場合は展示なし。`last-minute` ページの `BeforeRacer` が空の場合あり
5. **会場コードの0埋め**: DBは `'01'`〜`'24'`、スラッグへの変換時は `.zfill(2)` で統一

---

## 9. 将来の拡張候補

- [ ] 会場別・コース別λ相関の層別分析（Opusが指摘した「全会場一括統計の誤り」対策）
- [ ] AI万舟率≥30% の追跡（n≥500件になってから判断）
- [ ] G1 Profitable の買い目だけ購入する戦略のROI追跡
- [ ] 多変量回帰でボーターズの重み係数を推定（n≥1,000件から）
- [ ] 本ツール予測スコアとボーターズλの差分分析（乖離が大きいレースの的中率）
