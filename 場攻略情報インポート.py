"""
ボーターズから抜粋した場攻略情報をデータベースにインポート
"""
import sqlite3
import sys
import io

# Windows環境でのUTF-8出力対応
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 場攻略情報（ボーターズから抜粋）
VENUE_STRATEGIES = {
    '01': {  # 桐生
        'name': '桐生',
        'water_type': '淡水',
        'key_features': [
            '標高124mと全24場で最も高い場所に位置し、気圧が低い',
            '気圧の低さが出足・行き足に影響し、ダッシュ勢が有利',
            'モーター性能や体重差による影響が出やすい',
            'ピットから２マークの距離が165mと長い'
        ],
        'course_tendency': 'ダッシュ有利',
        'kimarite_tendency': None,
        'wind_tendency': None,
        'tide_impact': False,
        'special_notes': '気圧・気温・湿度がモーターに影響し、個体差が大きく出やすい'
    },
    '02': {  # 戸田
        'name': '戸田',
        'water_type': '淡水',
        'key_features': [
            '日本で一番インが弱い',
            'コース幅102.5m、１マークのバック側70.5mと全国で一番狭い',
            '１マークはスタンド側に13m振られており、インは斜めに走る形で距離が長い',
            '風は比較的穏やかで無風状態が約３割'
        ],
        'course_tendency': 'イン不利、センター有利',
        'kimarite_tendency': 'まくり発生率トップクラス、差し・まくり差しはやや決まりにくい',
        'wind_tendency': '無風約30%',
        'tide_impact': False,
        'special_notes': '２マークも対岸側に振られており、逆転や決まり手「抜き」が多い'
    },
    '03': {  # 江戸川
        'name': '江戸川',
        'water_type': '海水',
        'key_features': [
            '全国で唯一河川をコースに利用',
            '潮位と川の流れが独特の水面を形成',
            '日本一の難水面（強風+潮流）',
            '１マークの振り幅が大きく、スタンド側約37mと全国上位の狭さ'
        ],
        'course_tendency': 'イン不利',
        'kimarite_tendency': '決まり手「抜き」比率は全国一',
        'wind_tendency': '5m以上の強風が吹く割合は全国でもトップクラス',
        'tide_impact': True,
        'special_notes': '潮の流れと風がぶつかると水面状況が悪化。荒水面時の逆転が多い'
    },
    '04': {  # 平和島
        'name': '平和島',
        'water_type': '海水',
        'key_features': [
            'スタンドから1マークまで約37mと日本一狭い',
            'コース幅の狭さによりインが窮屈',
            'バックの内側での伸びが強烈',
            '大外6枠が日本一強いレース場'
        ],
        'course_tendency': 'イン不利、バック内側伸び',
        'kimarite_tendency': '差しが決まりやすい',
        'wind_tendency': '夏場は追い風、冬場は向かい風',
        'tide_impact': True,
        'special_notes': '満潮はスロー勢有利、干潮はダッシュ勢のまくり有利'
    },
    '05': {  # 多摩川
        'name': '多摩川',
        'water_type': '淡水',
        'key_features': [
            '日本一の静水面（防風林に囲まれている）',
            '追い風が42%と多い',
            'ホーム側、バック側とも広い水面',
            'どのコースからでも全速で攻めこむことが可能'
        ],
        'course_tendency': '先手有利',
        'kimarite_tendency': None,
        'wind_tendency': '追い風42%、風速は緩やか',
        'tide_impact': False,
        'special_notes': 'スタートを決めて先手を取った選手が主導権を握る'
    },
    '06': {  # 浜名湖
        'name': '浜名湖',
        'water_type': '汽水',
        'key_features': [
            '淡水と海水が混ざった汽水で、水質が柔らかい',
            '競走水面の面積は日本一',
            '周囲に障害物がないため風の影響を受けやすい',
            '風速5m以上の割合は約30%'
        ],
        'course_tendency': 'スピード戦',
        'kimarite_tendency': '追い風でまくり、向かい風でまくり差し（通常と逆）',
        'wind_tendency': '強風が吹きやすい（5m以上約30%）',
        'tide_impact': False,
        'special_notes': '体重差やモーターの差が比較的出づらい'
    },
    '07': {  # 蒲郡
        'name': '蒲郡',
        'water_type': '汽水',
        'key_features': [
            '汽水だが潮の影響をほとんど受けない',
            'スタンドや防風壁などに風が遮られる静水面',
            '１マークのバック側が156.7mと全国一広い',
            '広くて水面が安定'
        ],
        'course_tendency': 'スピード戦',
        'kimarite_tendency': None,
        'wind_tendency': '強風が少ない静水面',
        'tide_impact': False,
        'special_notes': 'アウトから攻撃的な仕掛けもよく見られる'
    },
    '08': {  # 常滑
        'name': '常滑',
        'water_type': '海水',
        'key_features': [
            '競争水面全体は全国屈指の広さ',
            '広大な水面と柔らかい水質を生かしたスピード戦',
            '１マーク側の伊勢湾からの海風で向かい風が多い（約60%）',
            '水門を設けているのでレース中の水位変動は少ない'
        ],
        'course_tendency': 'スピード戦',
        'kimarite_tendency': None,
        'wind_tendency': '向かい風約60%、冬場は季節風で強風',
        'tide_impact': True,
        'special_notes': '満潮時はイン有利、干潮時はアウト有利'
    },
    '09': {  # 津
        'name': '津',
        'water_type': '汽水に近い淡水',
        'key_features': [
            '汽水に近い淡水で、体重差による影響が少ない',
            '比較的イン有利な水面レイアウト',
            '海に近いことや水面が南北にレイアウトされており風の影響が大きい',
            '水面が荒れやすい'
        ],
        'course_tendency': 'イン有利',
        'kimarite_tendency': '差し比率が高い（特に追い風時）',
        'wind_tendency': '夏は追い風、冬は向かい風',
        'tide_impact': False,
        'special_notes': 'イン１着率は24場中6位（2020年）'
    },
    '10': {  # 三国
        'name': '三国',
        'water_type': '淡水',
        'key_features': [
            'スタートライン上のコース幅は62mとトップクラスの広さ',
            'コース幅が広いためアウトの選手は１マークまでが遠い',
            '年間を通して追い風が多い',
            '内側３艇優位'
        ],
        'course_tendency': 'スロー有利、ダッシュ不利',
        'kimarite_tendency': 'まくりが少なく、差しが多い',
        'wind_tendency': '追い風が多い',
        'tide_impact': False,
        'special_notes': '4〜6コースの1着率やまくり決着率は全国でも下位'
    },
    '11': {  # びわこ
        'name': 'びわこ',
        'water_type': '淡水',
        'key_features': [
            '標高85mで全24場中2番目の高さのため気圧が低い',
            '2020年10月の第１ターンマーク移設によりインが強くなった',
            '琵琶湖特有のうねりが発生することがある',
            '春から夏にかけては波乱決着が多い傾向'
        ],
        'course_tendency': 'イン有利（改修後）',
        'kimarite_tendency': None,
        'wind_tendency': None,
        'tide_impact': False,
        'special_notes': '中間整備の効果が非常に大きい。水位が高いと不安定になる'
    },
    '12': {  # 住之江
        'name': '住之江',
        'water_type': '淡水',
        'key_features': [
            'センターポールからの振りが6mと振り幅が小さい',
            '約4割のレースが無風状態',
            'コンクリート護岸に囲まれており、引き波が返し波として残りやすい',
            '２マーク近辺で水面が荒れる'
        ],
        'course_tendency': 'イン有利',
        'kimarite_tendency': '２マークでの逆転が多い',
        'wind_tendency': '無風約40%、5m以上の強風は約5%',
        'tide_impact': False,
        'special_notes': '無風ではスリットが揃いやすく、イン勝率が上昇'
    },
    '13': {  # 尼崎
        'name': '尼崎',
        'water_type': '淡水',
        'key_features': [
            '２マークから１マークまで一直線に並び、ターンマークの振りがない唯一のレース場',
            '１マークホーム側は全国一の広さ',
            '向かい風が吹くことが多く、半分以上のレースを占める',
            '5m以上の強風が約30%'
        ],
        'course_tendency': 'イン有利',
        'kimarite_tendency': 'まくり差し・差しが決まりやすい',
        'wind_tendency': '向かい風が多い（50%以上）、強風約30%',
        'tide_impact': False,
        'special_notes': 'イン一着率24場中3位（2021年）'
    },
    '14': {  # 鳴門
        'name': '鳴門',
        'water_type': '海水',
        'key_features': [
            '潮流れが激しくて波もたちやすい',
            'コースが最も狭く、特に1マークへ向けて内側へ狭くなる',
            'バックストレッチの内側に伸びやすい「鳴門の花道」がある',
            '干潮に向かって潮の引いている時間帯が乗りやすい'
        ],
        'course_tendency': 'イン難しい',
        'kimarite_tendency': 'まくりが決まりやすい（差しよりも）',
        'wind_tendency': None,
        'tide_impact': True,
        'special_notes': 'コース取り次第でどのコースからでも勝利を狙える'
    },
    '15': {  # 丸亀
        'name': '丸亀',
        'water_type': '海水',
        'key_features': [
            '１マークの振りが比較的大きめで、センター全速戦が利きやすい',
            '瀬戸内海に面しているため常に風が吹いている（無風ゼロ）',
            '向かい風（55%）か左横風（18%）が多い',
            '潮の変化によってレース傾向が大きく変わる'
        ],
        'course_tendency': 'イン優勢だがセンター戦も利く',
        'kimarite_tendency': None,
        'wind_tendency': '向かい風55%、左横風18%、追い風24%',
        'tide_impact': True,
        'special_notes': '追い潮では1・2コース、向かい潮では3〜5コースの1着率が上昇'
    },
    '16': {  # 児島
        'name': '児島',
        'water_type': '海水',
        'key_features': [
            '水面レイアウトは平均的でクセが無い',
            '瀬戸内海に面した湾内に位置',
            '無風は約2%と少ないが、風速3m以内の緩やかな風が多い',
            '干潮時は水面が穏やか、満潮時は荒れやすい'
        ],
        'course_tendency': '平均的',
        'kimarite_tendency': 'まくりが決まりにくく、差し・まくり差し率が高い',
        'wind_tendency': '風速3m以内の緩やかな風が多い',
        'tide_impact': True,
        'special_notes': '追い風の満潮時は差しが決まりやすい'
    },
    '17': {  # 宮島
        'name': '宮島',
        'water_type': '海水',
        'key_features': [
            '１マークをスタンド側に振ってあり、センターから攻めに出やすい',
            'スタートの難所として知られる',
            '潮位差は最大で３mと大きい',
            '無風状態は年間で1割以下'
        ],
        'course_tendency': 'イン優勢（スタート難により）',
        'kimarite_tendency': 'まくり比率が高く、全国でも上位',
        'wind_tendency': '無風1割以下、前半と後半で風向き・風速が変わりやすい',
        'tide_impact': True,
        'special_notes': 'スタートが慎重になって横並びに揃いやすく、その結果インが優勢'
    },
    '18': {  # 徳山
        'name': '徳山',
        'water_type': '海水',
        'key_features': [
            'イン一着率は24場中2位',
            'インに有利な追い風・左横風が8割',
            '風速も1〜3mが多い',
            '潮位差は最大で3.5mと大きい'
        ],
        'course_tendency': 'イン有利',
        'kimarite_tendency': None,
        'wind_tendency': '追い風・左横風80%、風速1〜3mが多い',
        'tide_impact': True,
        'special_notes': 'イン優遇の番組構成。2〜6コースの1着率はワーストクラス'
    },
    '19': {  # 下関
        'name': '下関',
        'water_type': '海水',
        'key_features': [
            'ピットから２マークまでの距離が173mと全国で二番目に長い',
            '瀬戸内海に面しているが強風になることは少なめ',
            'レイアウトがイン優勢で、基本的には穏やかな静水面',
            '潮の影響も少ない'
        ],
        'course_tendency': 'イン有利',
        'kimarite_tendency': None,
        'wind_tendency': '常に風が吹いているが強風は少なめ',
        'tide_impact': True,
        'special_notes': '1コース1着率24場中5位（2021年）'
    },
    '20': {  # 若松
        'name': '若松',
        'water_type': '海水',
        'key_features': [
            'イン有利の水面レイアウト（センターポールからの振りは9m）',
            '満潮時は水面が高く不安定になる',
            '風が強まると潮の流れと合わさりスタートがバラつく',
            '水位の高い状態での追い風時に１マーク、向かい風時には２マークが荒れやすい'
        ],
        'course_tendency': 'イン有利',
        'kimarite_tendency': '決まり手「抜き」の比率が高い',
        'wind_tendency': None,
        'tide_impact': True,
        'special_notes': '満潮になると水面は高く不安定、スピードを落として回るインが有利'
    },
    '21': {  # 芦屋
        'name': '芦屋',
        'water_type': '淡水',
        'key_features': [
            '全国でもトップクラスの1コース1着率',
            '競争水面全体が広く、１マークのバック側も87mと十分な広さ',
            'バック側に葦が群生していることで引き波が消えやすい',
            '小高い丘に囲まれているため風の影響も軽減'
        ],
        'course_tendency': 'イン最強',
        'kimarite_tendency': None,
        'wind_tendency': '風の影響が軽減されている',
        'tide_impact': False,
        'special_notes': '1コース1着率24場中1位（2021年）。番組構成が大きく影響'
    },
    '22': {  # 福岡
        'name': '福岡',
        'water_type': '海水に近い汽水',
        'key_features': [
            '満潮時に海水と汽水が混ざり合ってうねりをあげる',
            '助走距離が180mと全国で最も短い',
            '24場唯一のバック側ピット',
            'うねりの発生、助走距離が短い、コース幅が広いなどアウト不利な要素が多い'
        ],
        'course_tendency': 'イン有利、アウト不利',
        'kimarite_tendency': None,
        'wind_tendency': None,
        'tide_impact': True,
        'special_notes': '潮の流れや風によって水面の状態が変わる特殊性。地元選手が有利'
    },
    '23': {  # 唐津
        'name': '唐津',
        'water_type': '淡水',
        'key_features': [
            'ピットから２マークの距離が日本一長い',
            '待機行動時間も1分50秒と他場より10秒長い',
            '風次第でレース傾向が変わるほど影響が大きい',
            '海に近いため無風状態は少なく、追い風が多い'
        ],
        'course_tendency': '差し・まくり差しが多い',
        'kimarite_tendency': '差し・まくり差しが多い。1コースの2着率は全国上位',
        'wind_tendency': '追い風が多い。午前は向かい風、午後は追い風と変化しやすい',
        'tide_impact': False,
        'special_notes': 'ピット離れで進入が変わることも比較的多い'
    },
    '24': {  # 大村
        'name': '大村',
        'water_type': '海水',
        'key_features': [
            'イン最強水面で、イン勝率は2014年から6年連続の1位',
            'イン優遇の番組編成',
            'コース幅が広く１マークの振りも比較的小さい',
            '防風ネットが追加設置され、さらにイン最強に'
        ],
        'course_tendency': 'イン最強',
        'kimarite_tendency': '逃げが決まりやすい',
        'wind_tendency': '2m以下の風速が増加（防風ネット効果）',
        'tide_impact': True,
        'special_notes': '風向きが変わりやすく安定しないためスタートを決めづらくインが強い'
    },
}


def create_venue_strategy_table():
    """場攻略情報テーブルを作成"""
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # テーブル作成
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS venue_strategies (
            venue_code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            water_type TEXT,
            course_tendency TEXT,
            kimarite_tendency TEXT,
            wind_tendency TEXT,
            tide_impact INTEGER,
            special_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 場攻略特徴テーブル（複数の特徴を格納）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS venue_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venue_code TEXT NOT NULL,
            feature TEXT NOT NULL,
            FOREIGN KEY (venue_code) REFERENCES venue_strategies(venue_code)
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ 場攻略情報テーブルを作成しました")


def import_venue_strategies():
    """場攻略情報をデータベースにインポート"""
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    imported_count = 0
    features_count = 0

    for venue_code, data in VENUE_STRATEGIES.items():
        # 既存データを削除
        cursor.execute('DELETE FROM venue_strategies WHERE venue_code = ?', (venue_code,))
        cursor.execute('DELETE FROM venue_features WHERE venue_code = ?', (venue_code,))

        # venue_strategiesにインサート
        cursor.execute('''
            INSERT INTO venue_strategies
            (venue_code, name, water_type, course_tendency, kimarite_tendency, wind_tendency, tide_impact, special_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            venue_code,
            data['name'],
            data['water_type'],
            data['course_tendency'],
            data['kimarite_tendency'],
            data['wind_tendency'],
            1 if data['tide_impact'] else 0,
            data['special_notes']
        ))

        # venue_featuresにインサート
        for feature in data['key_features']:
            cursor.execute('''
                INSERT INTO venue_features (venue_code, feature)
                VALUES (?, ?)
            ''', (venue_code, feature))
            features_count += 1

        imported_count += 1

    conn.commit()
    conn.close()

    print(f"✅ {imported_count}会場の場攻略情報をインポートしました")
    print(f"✅ {features_count}件の特徴を登録しました")


if __name__ == "__main__":
    print("=" * 80)
    print("場攻略情報インポート")
    print("=" * 80)
    print()

    # テーブル作成
    create_venue_strategy_table()

    # データインポート
    import_venue_strategies()

    print()
    print("=" * 80)
    print("完了")
    print("=" * 80)
