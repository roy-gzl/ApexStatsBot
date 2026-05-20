# ApexStatsBot

ApexStatsBot は，Apex Legends の試合結果を Discord 上で記録し，セッション単位で統計を集計する Discord Bot です．

手入力の試合記録を CSV / JSON に保存する機能に加えて，Mozambique API を使った外部Apex情報の取得にも対応しています．

## 開発背景

Apex Legends を複数試合続けてプレイすると，その日の成績や負け方の傾向をあとから振り返りにくいという課題があります．

このBotでは，`/start` でセッションを開始した後，Botが表示するプルダウン式メニューから試合記録・キャラ変更・集計・終了を選択できます．DiscordのSlash Command，Select Menu，Modal，Buttonを組み合わせ，プレイ中でも入力しやすいUIを目指しました．

## 主な機能

### セッション記録

- `/setup` パネルボタンをチャンネルに設置（管理者用）
- `/panel` プルダウン式の操作パネルを表示
- `/start` 使用キャラを選択してセッション開始し，通常メニューを表示
- `/match` 1試合の結果を記録
- `/legend` セッション中の使用キャラを変更
- `/summary` 現在のセッション統計を表示
- `/end` 統計を表示してセッション終了
- `/reset` 現在のセッションの記録だけ削除
- `/export` 自分の `matches.csv` をDiscordに添付送信

### Mozambique API連携

- `/apex_set` Apexプロフィールをユーザーごとに保存
- `/apex_stats` プレイヤー統計を表示
- `/apex_map` 現在と次のマップローテーションを表示
- `/apex_predator` 各プラットフォームのプレデター到達RPを表示

### 試合修正

通常メニューの「試合を修正」から，現在のセッションの直近25試合を選択して内容を修正できます．レジェンド・死亡原因・順位・ダメージ・キル数をすべて変更可能です．

## 技術スタック

- Python 3.10+
- discord.py
- python-dotenv
- aiohttp
- CSV / JSON
- Mozambique API

SQLiteなどのDBは使わず，まずはローカルファイルでユーザーごとに独立して保存する構成にしています．

## ディレクトリ構成

```text
ApexStatsBot/
  bot.py              # Bot本体とSlash Command同期
  commands.py         # Slash Command定義（@bot.tree.command）
  views.py            # UIコンポーネント（View / Modal / Select / Button）
  helpers.py          # 共通ユーティリティ（状態チェック・行生成など）
  storage.py          # CSV / JSONの読み書きと集計処理
  constants.py        # キャラ・死亡原因・CSVカラム定義
  mozambique.py       # Mozambique APIクライアントと表示整形
  requirements.txt
  .env.example
  README.md
```

実行後，ユーザーデータは以下の形式で作成されます．

```text
data/
  users/
    <discord_user_id>/
      matches.csv
      session_state.json
      apex_profile.json
```

## 保存データ

このBotでは，試合履歴・現在のセッション状態・外部API用プロフィールを分けて保存しています．

- `matches.csv`: 追記型の試合履歴．あとから表計算ソフトやPythonで分析しやすい形式
- `session_state.json`: 現在進行中のセッション状態．Bot再起動後も `/match` を継続するための状態管理
- `apex_profile.json`: Mozambique APIで参照するApexプロフィール．毎回プレイヤー名を入力しなくてよくするための設定

### matches.csv

`matches.csv` は1試合につき1行を追記する履歴データです．`/summary` と `/end` では，このCSVから `current_session_id` と一致する行だけを抽出して集計します．

```csv
date,session_id,match_id,user_id,username,legend,death_cause,rank,damage,rp,kills,assists,knocks
```

| カラム | 説明 |
|---|---|
| `date` | 記録日時．Botが保存した時刻 |
| `session_id` | セッションID．例: `2026-05-18-001` |
| `match_id` | セッション内の試合ID．例: `2026-05-18-001-003` |
| `user_id` | DiscordユーザーID．ユーザー識別の主キー |
| `username` | 記録時点のDiscord表示名 |
| `legend` | その試合で使用したキャラ |
| `death_cause` | 選択された死亡原因 |
| `rank` | 順位．1〜20の整数 |
| `damage` | 与ダメージ．0以上の整数．現在の入力フォームでは使用せず `0` を保存 |
| `rp` | 獲得RP．マイナスも許可 | 
| `kills` | キル数．0以上の整数 |
| `assists` | 互換性維持用のカラム．現在の入力フォームでは使用せず `0` を保存 |
| `knocks` | 互換性維持用のカラム．現在の入力フォームでは使用せず `0` を保存 |

CSVに `username` も保存していますが，保存先や集計の基準には使っていません．Discordの表示名は変更されるため，ユーザー識別には常に `user_id` を使います．

### session_state.json

`session_state.json` は，ユーザーごとの「現在のセッション」を表す状態ファイルです．Botを停止してもこのファイルが残るため，再起動後もセッション継続状態を復元できます．

```json
{
  "user_id": "123456789012345678",
  "username": "user",
  "current_legend": "レイス",
  "current_session_id": "2026-01-01-001",
  "match_count": 3,
  "is_active": true
}
```

| フィールド | 説明 |
|---|---|
| `user_id` | DiscordユーザーID |
| `username` | 最後に状態を更新した時点のDiscord表示名 |
| `current_legend` | 現在選択中の使用キャラ．`/match` ではこの値を自動使用 |
| `current_session_id` | 現在のセッションID |
| `match_count` | 現在のセッションで記録した試合数 |
| `is_active` | セッション中なら `true`，`/end` 後は `false` |

`/start` を実行すると新しい `session_id` が作成され，`match_count` は0に戻ります．同じ日に複数回開始した場合は，`2026-05-18-001`，`2026-05-18-002` のように連番になります．

### apex_profile.json

`apex_profile.json` は，Mozambique APIでプレイヤー統計を取得するためのプロフィール設定です．`/apex_set` で保存され，`/apex_stats` 実行時に省略値として使われます．

```json
{
  "platform": "PC",
  "player_name": "PlayerName"
}
```

| フィールド | 説明 |
|---|---|
| `platform` | Mozambique APIに渡すプラットフォーム．`PC`, `PS4`, `X1`, `SWITCH` |
| `player_name` | Apexのプレイヤー名．PCの場合はOrigin / EAアカウント名 |

このファイルは手入力の試合履歴とは独立しています．外部APIのプロフィール設定を変更しても，過去の `matches.csv` には影響しません．

## セットアップ

### 1. リポジトリへ移動

```bash
cd ApexStatsBot
```

### 2. 仮想環境を作成

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. 依存関係をインストール

```bash
pip install -r requirements.txt
```

### 4. 環境変数を設定

```bash
cp .env.example .env
```

`.env` に以下を設定します．

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
MOZAMBIQUE_API_KEY=your_mozambique_api_key_here
DISCORD_GUILD_ID=your_test_server_id_here
```

### 5. Botを起動

```bash
python bot.py
```

起動時にSlash Commandを同期します．`DISCORD_GUILD_ID` を設定している場合は，指定したサーバーへ即時反映されるギルド同期を使います．未設定の場合はグローバル同期になります．

```text
Synced 12 guild slash commands.
```

## Discord Developer Portal設定

1. Discord Developer PortalでApplicationを作成
2. `Bot` ページでBotを作成
3. Bot Tokenを `.env` の `DISCORD_BOT_TOKEN` に設定
4. `OAuth2` -> `URL Generator` を開く
5. Scopesで `bot` と `applications.commands` を選択
6. Bot Permissionsで `Send Messages` と `Attach Files` を選択
7. 生成されたURLからBotをサーバーへ招待

## Mozambique API設定

Mozambique APIを使うには，Apex Legends API PortalでAPIキーを取得します．

```text
https://portal.apexlegendsapi.com/
```

取得したキーを `.env` に設定してください．

```env
MOZAMBIQUE_API_KEY=your_mozambique_api_key_here
```

PCプレイヤーはSteamでプレイしている場合でも，APIではOrigin / EAアカウント名が必要です．

## 開発用サーバーIDの設定

Slash Commandをすぐ反映したい場合は，Discordの開発者モードを有効にしてサーバーIDをコピーし，`.env` に設定します．

```env
DISCORD_GUILD_ID=123456789012345678
```

設定すると，Bot起動時にそのサーバーへギルド同期します．ポートフォリオ公開時に特定サーバーへ依存させたくない場合は，READMEではなく `.env` だけに実IDを入れてください．

## コマンド例

### セッション開始

```text
/start
```

使用キャラをプルダウンで選択するとセッションが開始され，通常メニューが表示されます．通常メニューや記録結果は `ephemeral` メッセージとして送信されるため，操作した本人にだけ表示されます．

通常メニューの選択肢：

- 試合を記録
- 試合を修正
- キャラ変更
- セッション統計
- セッション終了
- その他

基本操作はこの通常メニューから選択します．各処理が終わると，Botが再び通常メニューを表示します．セッション終了を選ぶまでこの流れを繰り返します．

セッションが進行中の状態でパネルボタンを押すと，「新しく開始」か「既存のセッションを継続」かを選択できます．

### その他メニュー

通常メニューで `その他` を選ぶと，以下の操作を選択できます．

- CSVエクスポート
- セッションリセット
- Apexプロフィール設定
- Apex統計
- マップローテ
- プレデターRP
- 通常メニューへ戻る

`/panel` を使うと，必要なタイミングで通常メニューだけを再表示できます．

### 試合結果を記録

```text
/match
```

1. 現在のレジェンドを確認（「そのまま」か「変更する」を選択）
2. 変更する場合はロール別プルダウンからレジェンドを選択
3. 死亡原因をプルダウンで選択
4. Modalで順位・ダメージ・キル数を入力

入力値に問題がある場合，再入力ボタン付きのエラーメッセージが表示されます．

記録完了後は「修正する」ボタンで内容を修正できます．

### 試合結果を修正

通常メニューの「試合を修正」から，現在のセッションの直近25試合をプルダウンで選択して修正できます．

1. 修正する試合を選択
2. レジェンドを確認（「そのまま」か「変更する」を選択）
3. 死亡原因をプルダウンで選択（現在の値が表示されます）
4. Modalで順位・ダメージ・キル数を入力（現在の値がプリフィルされます）

### セッション集計

```text
/summary
```

表示内容：

- 試合数
- 平均順位
- 平均ダメージ
- 平均キル
- キャラ別：試合数 / 平均DMG / K/D
- 死亡原因（多い順，1回以上のものをすべて表示）

### Mozambique API統計

```text
/apex_set platform: PC player_name: PlayerName
/apex_stats
/apex_map
/apex_predator
```

`/apex_stats` のKDは，APIレスポンスに死亡数が含まれる場合だけ計算します．取得できない場合は `KD：取得不可` と表示します．

マップローテーションやプレデター情報の表示には，API規約に合わせて `Data from apexlegendsstatus.com` を含めています．

## エラー処理

- `/match` 実行時にセッション未開始なら `/start` を案内
- 数値入力が不正な場合（整数以外・範囲外）は保存せずエラーメッセージと再入力ボタンを表示
- Discordのモーダルからは別のモーダルを直接開けない制約があるため，バリデーションエラー時はボタン経由で再入力させる方式
- Mozambique APIの `403`，`404`，`429` などをユーザー向けメッセージに変換
- CSVやJSONが存在しない場合は自動作成

## 今後の改善案

- Docker化
- グラフ画像の自動生成
- セッション履歴一覧コマンド
- GitHub ActionsによるLint / Test自動化
