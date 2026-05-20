from typing import TypedDict


class MatchRow(TypedDict):
    date: str
    session_id: str
    match_id: str
    user_id: str
    username: str
    legend: str
    death_cause: str
    rank: int
    damage: int

    kills: int
    assists: int
    knocks: int


LEGENDS_BY_ROLE = {
    "スカーミッシャー": ["アクセル", "アッシュ", "オクタン", "オルター", "ホライゾン", "レイス", "パスファインダー"],
    "アサルト": ["バリスティック", "バンガロール", "ヒューズ", "マッドマギー", "レヴナント"],
    "リコン": ["ヴァルキリー", "ヴァンテージ", "クリプト", "シア", "スパロー", "ブラッドハウンド"],
    "コントローラー": ["カタリスト", "コースティック", "ランパート", "ワットソン"],
    "サポート": ["コンジット", "ジブラルタル", "ニューキャッスル", "ライフライン", "ミラージュ", "ローバ"],
}

LEGENDS = [legend for legends in LEGENDS_BY_ROLE.values() for legend in legends]

DEATH_CAUSES = [
    "射線管理ミス",
    "孤立",
    "詰めすぎ",
    "エイム負け",
    "フォーカスずれ",
    "初動ファイト",
    "漁夫",
    "安置",
    "物資不足",
    "漁りすぎ",
    "アビリティ未使用",
    "不明",
]

CSV_FIELDS = [
    "date",
    "session_id",
    "match_id",
    "user_id",
    "username",
    "legend",
    "death_cause",
    "rank",
    "damage",

    "kills",
    "assists",
    "knocks",
]
