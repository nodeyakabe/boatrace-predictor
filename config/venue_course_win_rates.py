# -*- coding: utf-8 -*-
"""
コース×会場期待勝率テーブル

自動生成: generate_venue_course_win_rate_table.py
データ期間: 2020年以降
エントリー数: 144
最小レース数: 100レース

使い方:
    from config.venue_course_win_rates import get_venue_course_win_rate

    win_rate = get_venue_course_win_rate(venue_code='01', course=1)
"""

# 会場×コース別勝率テーブル
# 構造: {venue_code: {course: {'win_rate': float, 'total_races': int, 'first_count': int}}}
VENUE_COURSE_WIN_RATES = {
    "01": {
        "1": {
            "win_rate": 0.5721,
            "total_races": 2786,
            "first_count": 1594
        },
        "2": {
            "win_rate": 0.1096,
            "total_races": 2783,
            "first_count": 305
        },
        "3": {
            "win_rate": 0.1263,
            "total_races": 2779,
            "first_count": 351
        },
        "4": {
            "win_rate": 0.1149,
            "total_races": 2785,
            "first_count": 320
        },
        "5": {
            "win_rate": 0.0664,
            "total_races": 2770,
            "first_count": 184
        },
        "6": {
            "win_rate": 0.0199,
            "total_races": 2766,
            "first_count": 55
        }
    },
    "02": {
        "1": {
            "win_rate": 0.4589,
            "total_races": 3057,
            "first_count": 1403
        },
        "2": {
            "win_rate": 0.148,
            "total_races": 3074,
            "first_count": 455
        },
        "3": {
            "win_rate": 0.1612,
            "total_races": 3058,
            "first_count": 493
        },
        "4": {
            "win_rate": 0.1422,
            "total_races": 3067,
            "first_count": 436
        },
        "5": {
            "win_rate": 0.0733,
            "total_races": 3070,
            "first_count": 225
        },
        "6": {
            "win_rate": 0.0285,
            "total_races": 3053,
            "first_count": 87
        }
    },
    "03": {
        "1": {
            "win_rate": 0.4823,
            "total_races": 2486,
            "first_count": 1199
        },
        "2": {
            "win_rate": 0.1754,
            "total_races": 2491,
            "first_count": 437
        },
        "3": {
            "win_rate": 0.1393,
            "total_races": 2484,
            "first_count": 346
        },
        "4": {
            "win_rate": 0.1246,
            "total_races": 2505,
            "first_count": 312
        },
        "5": {
            "win_rate": 0.0689,
            "total_races": 2497,
            "first_count": 172
        },
        "6": {
            "win_rate": 0.0256,
            "total_races": 2496,
            "first_count": 64
        }
    },
    "04": {
        "1": {
            "win_rate": 0.4758,
            "total_races": 2436,
            "first_count": 1159
        },
        "2": {
            "win_rate": 0.1682,
            "total_races": 2450,
            "first_count": 412
        },
        "3": {
            "win_rate": 0.1392,
            "total_races": 2436,
            "first_count": 339
        },
        "4": {
            "win_rate": 0.1221,
            "total_races": 2449,
            "first_count": 299
        },
        "5": {
            "win_rate": 0.0788,
            "total_races": 2448,
            "first_count": 193
        },
        "6": {
            "win_rate": 0.0301,
            "total_races": 2456,
            "first_count": 74
        }
    },
    "05": {
        "1": {
            "win_rate": 0.5427,
            "total_races": 2626,
            "first_count": 1425
        },
        "2": {
            "win_rate": 0.1492,
            "total_races": 2634,
            "first_count": 393
        },
        "3": {
            "win_rate": 0.1217,
            "total_races": 2629,
            "first_count": 320
        },
        "4": {
            "win_rate": 0.113,
            "total_races": 2628,
            "first_count": 297
        },
        "5": {
            "win_rate": 0.063,
            "total_races": 2620,
            "first_count": 165
        },
        "6": {
            "win_rate": 0.0202,
            "total_races": 2619,
            "first_count": 53
        }
    },
    "06": {
        "1": {
            "win_rate": 0.5819,
            "total_races": 2777,
            "first_count": 1616
        },
        "2": {
            "win_rate": 0.1297,
            "total_races": 2760,
            "first_count": 358
        },
        "3": {
            "win_rate": 0.1195,
            "total_races": 2769,
            "first_count": 331
        },
        "4": {
            "win_rate": 0.0969,
            "total_races": 2765,
            "first_count": 268
        },
        "5": {
            "win_rate": 0.0639,
            "total_races": 2768,
            "first_count": 177
        },
        "6": {
            "win_rate": 0.0166,
            "total_races": 2765,
            "first_count": 46
        }
    },
    "07": {
        "1": {
            "win_rate": 0.6071,
            "total_races": 2606,
            "first_count": 1582
        },
        "2": {
            "win_rate": 0.1015,
            "total_races": 2601,
            "first_count": 264
        },
        "3": {
            "win_rate": 0.1193,
            "total_races": 2599,
            "first_count": 310
        },
        "4": {
            "win_rate": 0.1155,
            "total_races": 2605,
            "first_count": 301
        },
        "5": {
            "win_rate": 0.0533,
            "total_races": 2589,
            "first_count": 138
        },
        "6": {
            "win_rate": 0.0131,
            "total_races": 2595,
            "first_count": 34
        }
    },
    "08": {
        "1": {
            "win_rate": 0.61,
            "total_races": 3082,
            "first_count": 1880
        },
        "2": {
            "win_rate": 0.124,
            "total_races": 3088,
            "first_count": 383
        },
        "3": {
            "win_rate": 0.0982,
            "total_races": 3086,
            "first_count": 303
        },
        "4": {
            "win_rate": 0.0991,
            "total_races": 3088,
            "first_count": 306
        },
        "5": {
            "win_rate": 0.0676,
            "total_races": 3077,
            "first_count": 208
        },
        "6": {
            "win_rate": 0.0114,
            "total_races": 3079,
            "first_count": 35
        }
    },
    "09": {
        "1": {
            "win_rate": 0.6396,
            "total_races": 2578,
            "first_count": 1649
        },
        "2": {
            "win_rate": 0.1184,
            "total_races": 2584,
            "first_count": 306
        },
        "3": {
            "win_rate": 0.0989,
            "total_races": 2578,
            "first_count": 255
        },
        "4": {
            "win_rate": 0.0837,
            "total_races": 2581,
            "first_count": 216
        },
        "5": {
            "win_rate": 0.0536,
            "total_races": 2577,
            "first_count": 138
        },
        "6": {
            "win_rate": 0.0159,
            "total_races": 2571,
            "first_count": 41
        }
    },
    "10": {
        "1": {
            "win_rate": 0.595,
            "total_races": 2684,
            "first_count": 1597
        },
        "2": {
            "win_rate": 0.136,
            "total_races": 2705,
            "first_count": 368
        },
        "3": {
            "win_rate": 0.1359,
            "total_races": 2701,
            "first_count": 367
        },
        "4": {
            "win_rate": 0.082,
            "total_races": 2708,
            "first_count": 222
        },
        "5": {
            "win_rate": 0.0511,
            "total_races": 2701,
            "first_count": 138
        },
        "6": {
            "win_rate": 0.0156,
            "total_races": 2693,
            "first_count": 42
        }
    },
    "11": {
        "1": {
            "win_rate": 0.6228,
            "total_races": 2264,
            "first_count": 1410
        },
        "2": {
            "win_rate": 0.122,
            "total_races": 2262,
            "first_count": 276
        },
        "3": {
            "win_rate": 0.1122,
            "total_races": 2255,
            "first_count": 253
        },
        "4": {
            "win_rate": 0.0896,
            "total_races": 2254,
            "first_count": 202
        },
        "5": {
            "win_rate": 0.0476,
            "total_races": 2249,
            "first_count": 107
        },
        "6": {
            "win_rate": 0.0142,
            "total_races": 2258,
            "first_count": 32
        }
    },
    "12": {
        "1": {
            "win_rate": 0.6394,
            "total_races": 2299,
            "first_count": 1470
        },
        "2": {
            "win_rate": 0.1186,
            "total_races": 2276,
            "first_count": 270
        },
        "3": {
            "win_rate": 0.1069,
            "total_races": 2283,
            "first_count": 244
        },
        "4": {
            "win_rate": 0.0903,
            "total_races": 2269,
            "first_count": 205
        },
        "5": {
            "win_rate": 0.0472,
            "total_races": 2268,
            "first_count": 107
        },
        "6": {
            "win_rate": 0.0106,
            "total_races": 2269,
            "first_count": 24
        }
    },
    "13": {
        "1": {
            "win_rate": 0.6496,
            "total_races": 1998,
            "first_count": 1298
        },
        "2": {
            "win_rate": 0.091,
            "total_races": 1999,
            "first_count": 182
        },
        "3": {
            "win_rate": 0.1089,
            "total_races": 1993,
            "first_count": 217
        },
        "4": {
            "win_rate": 0.0932,
            "total_races": 1984,
            "first_count": 185
        },
        "5": {
            "win_rate": 0.0515,
            "total_races": 1982,
            "first_count": 102
        },
        "6": {
            "win_rate": 0.0135,
            "total_races": 1994,
            "first_count": 27
        }
    },
    "14": {
        "1": {
            "win_rate": 0.5321,
            "total_races": 2646,
            "first_count": 1408
        },
        "2": {
            "win_rate": 0.1477,
            "total_races": 2654,
            "first_count": 392
        },
        "3": {
            "win_rate": 0.1323,
            "total_races": 2645,
            "first_count": 350
        },
        "4": {
            "win_rate": 0.1128,
            "total_races": 2642,
            "first_count": 298
        },
        "5": {
            "win_rate": 0.0712,
            "total_races": 2656,
            "first_count": 189
        },
        "6": {
            "win_rate": 0.0174,
            "total_races": 2639,
            "first_count": 46
        }
    },
    "15": {
        "1": {
            "win_rate": 0.6306,
            "total_races": 2569,
            "first_count": 1620
        },
        "2": {
            "win_rate": 0.1257,
            "total_races": 2570,
            "first_count": 323
        },
        "3": {
            "win_rate": 0.0988,
            "total_races": 2562,
            "first_count": 253
        },
        "4": {
            "win_rate": 0.0888,
            "total_races": 2579,
            "first_count": 229
        },
        "5": {
            "win_rate": 0.0485,
            "total_races": 2556,
            "first_count": 124
        },
        "6": {
            "win_rate": 0.0176,
            "total_races": 2563,
            "first_count": 45
        }
    },
    "16": {
        "1": {
            "win_rate": 0.6376,
            "total_races": 2431,
            "first_count": 1550
        },
        "2": {
            "win_rate": 0.108,
            "total_races": 2435,
            "first_count": 263
        },
        "3": {
            "win_rate": 0.0929,
            "total_races": 2422,
            "first_count": 225
        },
        "4": {
            "win_rate": 0.0978,
            "total_races": 2433,
            "first_count": 238
        },
        "5": {
            "win_rate": 0.0562,
            "total_races": 2418,
            "first_count": 136
        },
        "6": {
            "win_rate": 0.0169,
            "total_races": 2423,
            "first_count": 41
        }
    },
    "17": {
        "1": {
            "win_rate": 0.6554,
            "total_races": 2554,
            "first_count": 1674
        },
        "2": {
            "win_rate": 0.0934,
            "total_races": 2548,
            "first_count": 238
        },
        "3": {
            "win_rate": 0.0998,
            "total_races": 2554,
            "first_count": 255
        },
        "4": {
            "win_rate": 0.0804,
            "total_races": 2549,
            "first_count": 205
        },
        "5": {
            "win_rate": 0.0597,
            "total_races": 2548,
            "first_count": 152
        },
        "6": {
            "win_rate": 0.0224,
            "total_races": 2541,
            "first_count": 57
        }
    },
    "18": {
        "1": {
            "win_rate": 0.7065,
            "total_races": 2504,
            "first_count": 1769
        },
        "2": {
            "win_rate": 0.1058,
            "total_races": 2505,
            "first_count": 265
        },
        "3": {
            "win_rate": 0.074,
            "total_races": 2485,
            "first_count": 184
        },
        "4": {
            "win_rate": 0.0733,
            "total_races": 2496,
            "first_count": 183
        },
        "5": {
            "win_rate": 0.0389,
            "total_races": 2491,
            "first_count": 97
        },
        "6": {
            "win_rate": 0.0088,
            "total_races": 2487,
            "first_count": 22
        }
    },
    "19": {
        "1": {
            "win_rate": 0.6589,
            "total_races": 2562,
            "first_count": 1688
        },
        "2": {
            "win_rate": 0.0989,
            "total_races": 2557,
            "first_count": 253
        },
        "3": {
            "win_rate": 0.0899,
            "total_races": 2548,
            "first_count": 229
        },
        "4": {
            "win_rate": 0.0857,
            "total_races": 2556,
            "first_count": 219
        },
        "5": {
            "win_rate": 0.0529,
            "total_races": 2554,
            "first_count": 135
        },
        "6": {
            "win_rate": 0.0208,
            "total_races": 2546,
            "first_count": 53
        }
    },
    "20": {
        "1": {
            "win_rate": 0.5941,
            "total_races": 2555,
            "first_count": 1518
        },
        "2": {
            "win_rate": 0.1347,
            "total_races": 2546,
            "first_count": 343
        },
        "3": {
            "win_rate": 0.1005,
            "total_races": 2557,
            "first_count": 257
        },
        "4": {
            "win_rate": 0.1033,
            "total_races": 2545,
            "first_count": 263
        },
        "5": {
            "win_rate": 0.0569,
            "total_races": 2548,
            "first_count": 145
        },
        "6": {
            "win_rate": 0.0196,
            "total_races": 2550,
            "first_count": 50
        }
    },
    "21": {
        "1": {
            "win_rate": 0.6366,
            "total_races": 2573,
            "first_count": 1638
        },
        "2": {
            "win_rate": 0.1067,
            "total_races": 2568,
            "first_count": 274
        },
        "3": {
            "win_rate": 0.1066,
            "total_races": 2562,
            "first_count": 273
        },
        "4": {
            "win_rate": 0.0999,
            "total_races": 2562,
            "first_count": 256
        },
        "5": {
            "win_rate": 0.0474,
            "total_races": 2553,
            "first_count": 121
        },
        "6": {
            "win_rate": 0.0137,
            "total_races": 2557,
            "first_count": 35
        }
    },
    "22": {
        "1": {
            "win_rate": 0.5895,
            "total_races": 2507,
            "first_count": 1478
        },
        "2": {
            "win_rate": 0.15,
            "total_races": 2520,
            "first_count": 378
        },
        "3": {
            "win_rate": 0.1467,
            "total_races": 2509,
            "first_count": 368
        },
        "4": {
            "win_rate": 0.0815,
            "total_races": 2516,
            "first_count": 205
        },
        "5": {
            "win_rate": 0.0362,
            "total_races": 2511,
            "first_count": 91
        },
        "6": {
            "win_rate": 0.012,
            "total_races": 2507,
            "first_count": 30
        }
    },
    "23": {
        "1": {
            "win_rate": 0.5785,
            "total_races": 2572,
            "first_count": 1488
        },
        "2": {
            "win_rate": 0.1384,
            "total_races": 2579,
            "first_count": 357
        },
        "3": {
            "win_rate": 0.1161,
            "total_races": 2576,
            "first_count": 299
        },
        "4": {
            "win_rate": 0.1014,
            "total_races": 2573,
            "first_count": 261
        },
        "5": {
            "win_rate": 0.0583,
            "total_races": 2574,
            "first_count": 150
        },
        "6": {
            "win_rate": 0.0195,
            "total_races": 2568,
            "first_count": 50
        }
    },
    "24": {
        "1": {
            "win_rate": 0.6814,
            "total_races": 2778,
            "first_count": 1893
        },
        "2": {
            "win_rate": 0.1122,
            "total_races": 2771,
            "first_count": 311
        },
        "3": {
            "win_rate": 0.0943,
            "total_races": 2777,
            "first_count": 262
        },
        "4": {
            "win_rate": 0.066,
            "total_races": 2771,
            "first_count": 183
        },
        "5": {
            "win_rate": 0.0456,
            "total_races": 2763,
            "first_count": 126
        },
        "6": {
            "win_rate": 0.0127,
            "total_races": 2758,
            "first_count": 35
        }
    }
}


def get_venue_course_win_rate(venue_code: str, course: int, default: float = 0.167) -> float:
    """
    会場・コース別の期待勝率を取得

    Args:
        venue_code: 会場コード（'01'-'24'）
        course: コース番号（1-6）
        default: データがない場合のデフォルト値（1/6 = 0.167）

    Returns:
        期待勝率（0.0-1.0）
    """
    venue_data = VENUE_COURSE_WIN_RATES.get(venue_code, {})
    # courseは整数だがテーブルのキーは文字列なので変換
    course_data = venue_data.get(str(course), {})
    return course_data.get('win_rate', default)


def get_venue_course_stats(venue_code: str, course: int) -> dict:
    """
    会場・コース別の詳細統計を取得

    Args:
        venue_code: 会場コード（'01'-'24'）
        course: コース番号（1-6）

    Returns:
        {'win_rate': float, 'total_races': int, 'first_count': int} or None
    """
    venue_data = VENUE_COURSE_WIN_RATES.get(venue_code, {})
    # courseは整数だがテーブルのキーは文字列なので変換
    return venue_data.get(str(course))


# 会場名マッピング
VENUE_NAMES = {
    "01": "桐生",
    "02": "戸田",
    "03": "江戸川",
    "04": "平和島",
    "05": "多摩川",
    "06": "浜名湖",
    "07": "蒲郡",
    "08": "常滑",
    "09": "津",
    "10": "三国",
    "11": "びわこ",
    "12": "住之江",
    "13": "尼崎",
    "14": "鳴門",
    "15": "丸亀",
    "16": "児島",
    "17": "宮島",
    "18": "徳山",
    "19": "下関",
    "20": "若松",
    "21": "芦屋",
    "22": "福岡",
    "23": "唐津",
    "24": "大村"
}
