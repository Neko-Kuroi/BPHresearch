# 🌸 インフラ調査ガイド 完全版 (Multi-Layer Infra Tracker)

> **⚠️ 調査を始める前の確認(必須)**
> このガイドは、**教育・学習、または明確な許可を得たインフラの調査**を目的としています。第三者のサーバーへの無許可な能動的スキャンや、過度な負荷をかける行為は避けてください。調査の目的と倫理的な境界線を、常に意識してください。

このガイドの目的は、**防弾ホスティングなどに置かれ、CDN等の裏に隠れた掲示板などのサイトについて、そのオリジン（本来のサーバーと関連インフラ）を、防御的な調査として推測していく**ことです。前提とするツールは `tracker_v1.11.py` で、その全文は末尾の「付録: ツール本体のコード」に収録してあります。この文書だけで、考え方から実行、結論の書き方までが完結します。

## 目次

- ステップ1: 何をするために調査するのか
- ステップ2: 準備
- ステップ3: 実行コマンド
- ステップ4: 結果の読み方
- ステップ5: 可視化マップの見方
- ステップ6: 安全に、責任を持って使うために
- ステップ7: 実践の流れ（全体像）
- ステップ8: 調査メモと受動調査
- ステップ9: 候補を絞る（候補表を作る）
- ステップ10: 候補を1つずつ確かめる
- ステップ11: 結論の書き方
- 運営者側の解説
- 付録A: スコアの配点一覧
- 付録B: ツールの既知の制限
- 付録C: うまくいかないときの見方
- まとめ
- 付録: ツール本体のコード

---

## 🎯 ステップ1: 何をするために調査するのか

Webサイトは、DDoS対策として **Cloudflare などのCDN** を使ったり、サーバー移転のときに **ドメインやIPアドレスを変えたり** します。
そのため、単に「同じIPアドレスを使っている」だけでは、「たまたま同じ共有サーバーを借りている別の人」なのか、「同じ管理者がインフラを共有している」なのかを区別できません。

このツールは、複数の視点(レイヤー)を組み合わせて、「偶然の一致(ノイズ)」を減らし、「つながりの手がかり」を浮かび上がらせるために使います。

| 視点(レイヤー) | 具体的な調査内容 | 証拠としての強さと注意点 |
| :--- | :--- | :--- |
| **① 過去の足跡(pDNS)** | 過去にどのIPアドレスを使っていたかの履歴 | **中**。CDN導入前の本来のサーバーIPや、移転ルートの手がかりになる。共有ホスティングの可能性があるので、期間の確認が重要。 |
| **② 証明書(CTログ)** | どのドメインが同じSSL証明書(SAN)に載っているか | **強(条件付き)**。**別の登録ドメイン**が同じ証明書に載っていれば強い手がかり。同じ登録ドメインのサブドメイン同士が共有するのは当然なので、証拠としては弱い。 |
| **③ サーバーの癖(HTTP)** | サーバーが返すCookie名やソフトウェアのバージョン | **弱〜中**。独自の名前が一致すれば「同じソフト・設定を使っている可能性」を示すが、掲示板ソフトなどの**既定値**なら、別人でも一致する。 |

> **※ 重要**: ツールのスコアの配点は、上の「証拠の強さ」と一致しません。たとえば、ツールはCTログ自体には加点せず(関連ドメインの候補集めにだけ使う)、固有Cookieに最大の配点(+30)を与えます。最終判断は、スコアの数字だけでなく、理由欄の内容と、この強さの表を照らし合わせて、人間が行ってください。

---

## 🛠️ ステップ2: 準備

### 1. Python
- **必要なもの**: Python 3.9 以上
- **やること**:
  ```bash
  pip install requests networkx matplotlib
  ```
  (v1.11でも `pandas` は不要です)

### 2. CIRCL pDNS のアカウント(推奨)
- **必要なもの**: [CIRCL LU](https://www.circl.lu/services/passive-dns/) のアカウント
- **注意**: 申請から承認まで、数日かかることがあります。認証情報がない場合は、次のコマンドから `--user` と `--password` を外して実行してください。その場合、ツールは現在のDNS解決だけを材料にするので、**過去の足跡は見えません**。

### 3. 調査対象のドメイン
- 例: `example.com`

---

## 🚀 ステップ3: 実行コマンド

調査の基本は、**受動的な調査を優先し、能動的な調査は最小限にする**ことです。

### 推奨 A: まず受動調査のみ

```bash
python tracker_v1.11.py --domain example.com --user YOUR_USER --password YOUR_PASS --no-probe
```

- **`--no-probe` の意味**: 対象サーバーへのHTTP接続をしません。
- ただし、次の通信は発生します。
  - 対象ドメインの現在のDNS解決(pDNSが使えない場合。対象の権威DNSに問い合わせが届くことがあります)
  - CIRCL、crt.sh、ipinfo.io といった第三者サービスへの問い合わせ(調べているドメインとIPが送られます)

### 推奨 B: 自動のHTTP接続を含む調査

```bash
python tracker_v1.11.py --domain example.com --user YOUR_USER --password YOUR_PASS --recent-days 90
```

- **ツールの動き**: v1.11は、見つかったクラスターから**最大30件ほど**のIPに、自動でHTTP接続を試みます(CDNのIPも含みます)。
- **`--recent-days 90` の意味**: 直近90日以内に観測されたIPにだけ接続します。何年も前に別の人へ割り当てられたIPへ、誤ってアクセスするリスクを**減らします**(なくしはしません)。
- **より限定的に調べたい場合**: ツールの自動接続の代わりに、候補IPだけに1回、手動で接続します。
  ```bash
  curl -sI --resolve example.com:443:<候補IP> https://example.com/ -k
  ```

- **crt.sh の再試行**: crt.sh が一時的に応答しない場合、ツールは間隔を空けて最大3回まで再試行します。それでも取得できない場合は、その旨を表示して、CTログなしで処理を進めます。

### 注意

- **Windows**: コマンドプロンプトやPowerShellでは、行末の `\` が使えません。コマンドは1行で書いてください。
- **パスワード**: ユーザー名とパスワードは、環境変数 `CIRCL_USER` / `CIRCL_PASSWORD` でも指定できます（コマンドライン引数が優先されます）。コマンドラインに直接書くとシェルの履歴に残るので、環境変数での指定を推奨します。

---

## 📖 ステップ4: 結果の読み方

出力は、対象の環境によって大きく2つのパターンに分かれます。

なお、CIRCL認証がない場合は、結果表示の最後に「pDNS履歴は未使用です。現在のDNS解決のみが材料で、過去の姿は見えていません」という趣旨の1行が必ず出ます。`report.json` の `pdns_available` でも、pDNSが使えたかどうかを確認できます。

### パターン1: Cloudflare等のCDNの背後にある場合(よくあるケース)

`--no-probe` で実行したときの画面表示:

```text
  動的閾値: 40.0点 (上位35%の境界、下限40)

🌫️  [低関連度: 13点] クラスター #1: example.com, img.example.com
```

低関連度のクラスターは、**画面には1行しか出ません**。理由は `report.json` を開いて確認します。

```json
"reasons": [
  "クラウド/CDN IPのみ(ノイズ注意) (+3)",
  "全IPが同一ASN/Org: AS13335 Cloudflare, Inc. (+10)",
  "ヘッダー比較に使えるドメインが0件のみ(比較不可)"
]
```

- **わかること**: CDNの共有IPを使っているため、「同一運営者の証拠」にはなりません。
- **注意(ツールの癖)**: 「全IPが同一ASN/Org」の +10 は、CDNのIPを共有しているだけでも付きます。CDNの背後では、この加点を運営者の根拠として扱わないでください。
- **次の一手**: ツール単体では拾いきれない情報を、手動で補います。
  - プロキシしていないサブドメインのA、MX、SPFの `ip4:`
  - Censys / Shodan での、証明書やfaviconの検索
  - pDNSで、CDN導入前のIPが見つかったか
  - CTログで、Cloudflareが発行した証明書ではなく、**他のCAが発行した証明書**に、**別の登録ドメイン**が含まれているか


### パターン2: CDNを使わず、独自のインフラを共有している場合

> **※ 架空の例です。** 以下の `198.51.100.x` は文書用の予約IP範囲です。ツールの `is_global` のチェックで除外されるため、この出力は実際には再現できません。ツールの動きを説明するための例です。
> また、Cookie一致とServer一致は、**HTTP接続をしたとき(推奨B)だけ**出ます。`--no-probe` では、この2行(+45点)が出ず、33点で低関連度になります。

推奨Bで実行した場合の例:

```text
  動的閾値: 78.0点 (上位35%の境界、下限40)

🔥 [高関連度: 78点] クラスター #1
   ドメイン: example.com, old-bbs.example.org
   IP: 198.51.100.10, 198.51.100.11
   ✔️  非クラウドIPを共有: 2個 (+15)
   ✔️  全IPが同一サブネット (+8)
   ✔️  全IPが同一ASN/Org: AS64500 Example Hosting Inc (+10)
   ✔️  Server完全一致(バージョン付き): nginx/1.18.0 (+15)
   ✔️  固有Cookie名が一致: custom_sess_id (+30)
```

- **わかること**: 複数の手がかり(非クラウドIPの共有、同じホスティング事業者、独自の名前のCookieの一致)が重なっています。
- **注意**:
  - スコアは「確率」ではありません。
  - 閾値は相対的な値です。クラスターが1つしかなければ、閾値はそのクラスター自身のスコアと40の大きい方(この例では78.0点)になります。
  - これは「同一運営者の可能性がある」という**手がかり**であり、確定した証拠ではありません。
  - `Server` のバージョン一致は、同じOSのパッケージ版であれば、誰でも同じになります。

---

## 🗺️ ステップ5: 可視化マップ(`infra_map.png`)の見方

- 🔵 **水色の丸**: 調査の起点のドメイン
- 🩷 **ピンクの丸**: CTログなどから見つかり、IPが解決できた名前(同じ登録ドメインのサブドメインも含みます)
- 🟢 **緑色の丸**: IPアドレス

**⚠️ 注意**: 1つの緑の丸(IP)に多数のドメインがつながる大きな星型は、Cloudflareなどの共有CDNを使っている場合の、典型的な**ノイズ**です。見た目の密集度では判断せず、`report.json` の理由欄(`reasons`)を確認してください。

---

## ⚠️ ステップ6: 安全に、責任を持って使うために

1. **出力は「手がかり」であり「証拠」ではない**
   Cookie名の一致は、同じ掲示板ソフトの既定値を使っている別人でも起きます。Serverのバージョン一致も、同じOSのパッケージ版なら、誰でも同じになります。
2. **結論には「信頼度」を書く**
   「確定」「可能性が高い(独立した根拠が3つ以上)」「可能性あり(1〜2の手がかり)」のように確度を示し、「誤検知の可能性(共有ホスティング、既定値の一致、古いIPの流用など)」を必ず添えます。
3. **実名の取り扱い**
   調査結果を外部と共有するときは、実在のドメインやIPアドレスを、`example.com` や `192.0.2.x` などに置き換えてください。

---

## 🎯 ステップ7: 実践の流れ（全体像）

実践は、次の5つの段に分けて進めます。段を飛ばさないことが大事です。

1. **メモを作る**（何を確かめるのかを先に書く）
2. **受動調査で候補を出す**（ツールはここまで）
3. **候補を絞る**（時期と出どころで候補表を作る）
4. **候補を1つずつ確かめる**（能動的な確認は最小限に）
5. **結論を書く**（信頼度と、誤検知の可能性と、分からないことをセットで）

ツールがやってくれるのは主に段2までです。段3以降が、ステップ9〜11の担当です。

---

## 📝 ステップ8: 調査メモと受動調査

### 1. 始める前にメモを作る

調査を始める前に、次の5つをメモに書きます。後から「何を調べていたのか」が曖昧になるのを防ぐためです。

- 対象ドメイン
- 観測を始めた日時
- 仮説（例： 「この掲示板はCDNの裏にオリジンがあり、過去には素のIPで運用されていたのではないか」）
- 許可の範囲（受動のみか、候補への1回の確認接続まで含むか）
- 終わりの条件（候補が尽きたら終わる、など）

### 2. 受動調査を実行し、出力を残す

```bash
python tracker_v1.11.py --domain example.com --user YOUR_USER --password YOUR_PASS --no-probe
```

- 実行したら、出力されたレポート（`report_YYYYMMDD_HHMMSS.json`）と地図（`infra_map_YYYYMMDD_HHMMSS.png`）が、その回の控えになります。出力ファイル名には実行日時が入るので、再実行しても前の回のファイルが上書きされることはありません。
- 画面で低関連度と出たクラスターも捨てません。低関連度の理由は画面には1行しか出ず、`report.json` の `reasons` にだけ残ります。実践では、むしろ低関連度の中に「CDNの裏側」を示す手がかりが残ることがあります。

### 3. report.json から拾うもの

実践で主に使うのは、次の項目です。

| 項目 | 見ること |
|:--- |:--- |
| `clusters[].reasons` | スコアの理由。点数そのものより、こちらを先に読む |
| `clusters[].ips` | 候補になり得るIPの一覧 |
| `ip_last_seen` | 各IPが最後に観測された時刻（epoch）。時期の判断に使う |
| `ip_first_seen` | 各IPが最初に観測された時刻（epoch）。pDNSの `time_first` 由来で、0は不明。現在のDNS解決で得たIPは、初出＝最終観測＝解決した時刻になる |
| `certificates` | 証明書ごとの記録。発行者（`issuer_name`）、その証明書に載った名前の組（`names`）、有効期間が入る。証明書の判断はこの単位で行う |
| `dropped_non_global` | ドメインごとに、非公開/予約IPのため除外した解決結果の件数。IPが0件のときに、解決自体ができなかったのか、除外されたのかを切り分ける |
| `pdns_available` | CIRCL pDNS が使えたかどうか。`false` の回は、過去の履歴が見えていない |
| `ip_info` | ASN/Org と、クラウド判定（`_is_cloud`）。取得できなかったIPは `null`（判定不能） |
| `header_profiles` | probeした場合のみ。Server、X-Powered-By、Cookie名 |

---

## 🔍 ステップ9: 候補を絞る（候補表を作る）

候補IPを並べた表を作り、1つずつ次の物差しで見ます。**物差しに合わない候補は、早めに落とします。**

### 物差し1： 時期

- そのIPは、CDNを入れ始めた**前**の時期に現れているか。pDNSの履歴で、CDNのIPに切り替わる前に使われていたIPは、オリジンの候補として残します。
- 逆に、何年も前に一度だけ現れて、その後ずっと別の用途に見えるIPは、割り当てが変わった可能性が高いので落とします。
- 「最初に現れた時期」は、`report.json` の `ip_first_seen` で確認できます（pDNSの `time_first` 由来）。`ip_last_seen`（最後に観測された時刻）と並べて、「いつからいつまで使われていたか」の幅で見ます。ただし `ip_first_seen` が 0 のIPは初出が不明です。また、現在のDNS解決で得たIPは初出＝最終観測＝解決した時刻になるので、履歴としての初出ではありません。

### 物差し2： プロキシされていない名前

CDNを通していないサブドメインは、オリジンを直接指していることがあります。

```bash
dig +short A example.com
dig +short A mail.example.com
dig +short MX example.com
dig +short TXT example.com
```

- MX の宛先や、TXT（SPF）に書かれた `ip4:` の範囲に、候補IPやその近くのIPが含まれていないかを見ます。
- これはツールが集めていない情報です。手動で補います。

### 物差し3： 証明書（1枚ずつ見る）

ツールは証明書を**証明書単位で保持**し、`report.json` の `certificates` に、証明書ごとの発行者（`issuer_name`）と、その証明書に載った名前の組（`names`）が入ります（候補集めに使う名前の和集合も、併せて返します）。判断は、この証明書の単位で行います。各証明書について、次の2つを見ます。

- 発行者がCDN事業者ではないか
- 同じ証明書に、**別の登録ドメイン**が載っていないか

この2つが揃った証明書は強い手がかりです。最終確認として、もとの crt.sh の画面で証明書を開き直すこと自体は省略しません。

### 物差し4： ネットワーク

- 候補IPの ASN/Org が、CDN事業者ではないか。
- ただし、同一ASN・同一サブネット・非クラウドという3つは、元をたどれば同じIP情報です。次のステップ10の数え方でも、**まとめて1系統**として数えます。

候補表の例（架空の例です。IPは文書用の予約範囲を使っています）:

| 候補IP | 時期 | 素の名前 | 証明書 | ネットワーク | 残す／落とす |
|:--- |:--- |:--- |:--- |:--- |:--- |
| 203.0.113.10 | CDN導入前に継続して出現 | MXの宛先と同じ | 別ドメインと共有（他CA発行） | 非クラウド | 残す |
| 203.0.113.99 | 5年前に1回だけ | なし | なし | 非クラウド | 落とす（割り当て変更の疑い） |
| CDNのIP | 現在 | ― | ― | クラウド | 落とす（表側のIP） |

---

## 🌐 ステップ10: 候補を1つずつ確かめる

候補が残ったら、確かめるのは**候補1つにつき1回**を原則にします。ツールの自動probe（推奨B）の代わりに、手動で1回だけ接続し、表側（CDN経由）の応答と比べます。

```bash
curl -sk -o /dev/null -D - --resolve example.com:443:203.0.113.10 https://example.com/
```

- `-D -` で応答ヘッダーだけを表示し、本文はファイルに保存しません（`-o /dev/null`）。
- 比べるもの： ステータス、Server、Set-Cookie の名前、リダイレクト先。
- **合わなかったら、その候補は落として終わりにします。** 合わない候補に対して、ポートやパスを変えて試し続けることはしません。それは調査ではなくスキャンになります。
- 証明書の検証を切っている（`-k`）のは、候補IPにドメイン名で接続する都合です。表示された内容を「本物」と断定する根拠にはならない点に注意します。

なお、ガイド本文の推奨B（ツールの自動probe）は、最大30組の（ドメイン, IP）に対して、https が失敗すれば http も試す動きをします。実践で細かく確かめたいときは、自動probeではなく、この手動1回を基本にします。

---

## ✍️ ステップ11: 結論の書き方

### 根拠の数え方

根拠は、点数ではなく**出どころの系統**で数えます。系統は次の4つです。

1. **DNS履歴**（時期を含む pDNS の形）
2. **証明書**（証明書の単位で確認したもの）
3. **HTTPの癖**（Server、Cookie名などの一致）
4. **ネットワーク**（ASN、サブネット、非クラウドかどうかは、まとめてこの1系統）

同じIP情報から出た項目を、系統をまたいで二重に数えないことが、過大評価を防ぐ要点です。

### 信頼度の段階

| 表現 | 目安 |
|:--- |:--- |
| 確定 | 使わない。インフラの外側からの観測だけで「確定」とは書かない |
| 可能性が高い | 独立した系統が3つ以上そろい、誤検知の説明でも対抗できない |
| 可能性あり | 系統が1〜2つ。候補として残るが、言い切れない |
| 候補のみ | 時期やネットワークだけなど、弱い一致だけ |
| 不明 | 候補が残らなかった、または表側の情報しか得られなかった |

### 結論文の雛形

```text
対象： example.com
結論： オリジンとみられる候補は 203.0.113.10 で、信頼度は「可能性あり」。
根拠（系統別）：
- DNS履歴： CDN導入前の時期に、このIPが継続して使われていた
- 証明書： 他CA発行の1枚に、別の登録ドメインと一緒に載っていた
誤検知の可能性：
- 共有ホスティングであれば、別の運営者のサイトでも同じ形になり得る
- IPの割り当てが時期の途中で変わっている可能性を、完全には排除できない
分からないこと：
- 現在も同じサーバーがオリジンとして使われているかは、外側からは確認できない
観測日時： 2026-11-26
```

### 通しの例（架空の例です）

CDNの裏にある掲示板 `example.com` を調べた、という設定の例です。IPは文書用の予約範囲で、実際の出力ではありません。

1. 受動調査では、クラスターは13点で低関連度でした。理由は「クラウド/CDN IPのみ (+3)」「全IPが同一ASN/Org (+10)」「ヘッダー比較に使えるドメインが0件」で、表側がCDNであることしか分かりません。
2. 候補表を作ると、pDNSの履歴に、CDN導入前の時期だけ現れるIPが1つ残りました。MXの宛先も同じIPを指していました。
3. 証明書を1枚ずつ見ると、そのIPの時期に発行された他CAの証明書に、別の登録ドメインが一緒に載っていました。
4. 候補への手動の確認接続では、ステータスとServerは表側と合いましたが、Cookie名は確認できませんでした。
5. 結論は、雛形を使って「可能性あり」と書きました。系統は DNS履歴と証明書の2つで、3つには届かないため「可能性が高い」とは書かない、という判断です。

この例のように、**「言い切れない」で終わるのが普通の終わり方**です。言い切れないことを、そのまま書くのが結論の書き方です。

---

---

# 運営者側の解説

ここでは、隠す側（＝守る側）が何を考え、どういう手順でサイトを公開しているのかを、防御側・運営側の視点で整理します。調査する側が「なぜ見えないのか」を理解するための章です。仕組みを知ることは、調査の結果を正しく読むためにも、自分のサイトを守る側に回るときにも役立ちます。

## 1. 運営者は何を守っているのか（思惑）

特定のサイトの運営者の考えを外から断定することはできません。ただ、CDNの裏に実サーバーを置く運営者には、一般に次のような理由があるとされています。

- **DDoSや攻撃から実サーバーを守る**： 実サーバーのIPが知られると、CDNを素通りして直接攻撃されてしまいます。IPを表に出さないこと自体が、防御の第一段です。
- **攻撃の的をCDNに肩代わりさせる**： 表側の応答はCDNが受け持ちます。大量のアクセスや攻撃は、まずCDNが吸収します。
- **サーバー移転や事業者変更を外に見せない**： 実サーバーを引っ越しても、CDNの中の向き先を変えるだけです。外から見える姿（CDNのIP）は変わらないので、移転のタイミングや移転先を推測されにくくなります。
- **苦情や削除要請の矛先を分散する**： 問い合わせや要請は、まず表側（CDN事業者やドメイン登録側）に届きます。実サーバーの置き場所に直接届くわけではありません。
- **運営者の身元や、利用しているホスティング事業者を推測されにくくする**： 実サーバーのIPが分かると、そのIPの持ち主（事業者）や、同じIP・同じネットワークにある他のサイトから、運営の素性に近づけてしまうことがあります。IPを隠すことは、その入口を閉じることでもあります。

調査する側から見ると、これらはすべて「手がかりを出さない理由」として働きます。逆に言えば、手がかりが出てくるのは、運営者がこれらの守りを**うっかり破った**ときがほとんどです。

## 2. 掲示板プログラムが出来てから公開までの流れ

掲示板プログラムを書き上げた運営者が、公開までに何をするのかを、順番に並べます。各ステップに「調査側から見ると何が見える／見えないか」を添えます。

**ステップ1： サーバーを借りて土台を入れる**
VPSや専用サーバーを契約し、OSと土台（Webサーバー、データベース、実行環境）を入れます。この時点でサーバーには本当のIPアドレスが付いています。
- 調査側から見ると： まだ何も見えません。ドメインと結びついていないIPは、無数にあるIPの1つにすぎません。

**ステップ2： プログラムを置き、IP直打ちで動作確認する**
プログラムをサーバーに置き、IPアドレスで直接アクセスして、書き込みや表示が動くかを確かめます。この段階は非公開の作業です。
- 調査側から見ると： 見えません。名前（ドメイン）を通していない作業は、DNSにも証明書にも記録が残りません。

**ステップ3： ドメインを取り、登録情報はプライバシー保護にする**
サイトの名前（ドメイン）を登録します。登録者の情報は、公開されないプライバシー保護つきにするのが普通です。
- 調査側から見ると： ドメインの存在と登録時期は分かりますが、登録者そのものは見えません。

**ステップ4： 公開前にCloudflareへドメインを預け、名前サーバーを切り替える**
Cloudflareにドメインを登録し、名前サーバーをCloudflareのものに切り替えます。肝は、**公開より先に**これを済ませることです。最初からCDNの裏で始めるわけです。
- 調査側から見ると： 名前サーバーがCDN事業者のものであることは見えます。ただし「CDN導入前の姿」は存在しないので、pDNSの履歴にも導入前のIPは現れません。

**ステップ5： DNSの名前を作り、実IPへ向けつつプロキシ有効にする**
Cloudflareの管理画面で、本体とサブドメインの名前を作り、それぞれ実サーバーのIPに向けます。ただし「プロキシ有効」の設定にします。
- 調査側から見ると： 名前を引いて返るのはCDNのIPだけです。実IPはCloudflareの中だけの情報で、外には出ません。

**ステップ6： 証明書はワイルドカードでまとめる**
HTTPS用の証明書を用意します。名前ごとにバラバラの証明書を取るのではなく、ワイルドカード（*.ドメイン）でまとめます。
- 調査側から見ると： CTログに出るのはワイルドカードと本体の名前だけで、サブドメインの名前や、他のドメインとの組み合わせは出てきません。

**ステップ7： 実サーバーはCloudflareからの接続だけを通すよう、ファイアウォールで閉じる**
実サーバー側で「CDNからの接続だけ通し、それ以外は拒否」する設定にします。
- 調査側から見ると： たとえ候補IPが浮かんでも、直接接続して確かめることができません。ステップ10の「候補への確認接続」が通らない理由の1つです。

**ステップ8： メールサーバーを立てない。管理用やテスト用の別名を作らない**
メールは立てない（立てるなら別の場所にする）ことにし、`direct`、`cpanel` のような管理用の名前や、テスト用のサブドメインも作りません。作ったものは消します。
- 調査側から見ると： MXやSPFからIPが漏れる口が無く、プロキシされていない名前も無いので、物差し2（ステップ9）が使えません。

**ステップ9： 公開と運用**
告知して公開し、あとは普通に運営します。プログラムの更新はサーバーに直接入って行います。サーバーを移転するときは、Cloudflareの中の向き先を変えるだけです。
- 調査側から見ると： 外から見える姿は公開初日からほぼ変わりません。移転しても表側は同じなので、変化として観測できません。

まとめると、肝は2つだけです。**「公開の初日からCDNの裏にいる」**ことと、**「裏を通さない名前やサービスを1つも作らない」**こと。残りは普通のサイト運営と変わりません。

## 3. 漏れ口の対照表

ステップ1のレイヤー表（調査側の手がかり）と、運営側のふさぎ方を、左右に並べます。

| 調査側の手がかり | 運営側のふさぎ方 |
| :--- | :--- |
| pDNSの履歴（CDN導入前のIP） | 公開初日からCDNの裏にいる。CDN導入前の期間そのものを作らない |
| CTログで、別の登録ドメインが同じ証明書に載っている | ワイルドカード証明書でまとめる。用途ごとの別証明書を取らない |
| MX・SPFに書かれたIP | メールを置かない。置くなら実サーバーとは別のサーバーにする |
| プロキシされていないサブドメイン（管理用・テスト用など） | そういう名前を作らない。作ったら消す |
| HTTPの癖（Serverヘッダー、Cookie名） | 表側はCDNが応答するので、実サーバーのヘッダーは表に出ない |
| 候補IPへの直接接続による確認 | 実サーバーはCloudflare以外からの接続を拒否する |

調査側の手がかりは、右側のふさぎ方が破れた場所に対応しています。逆に、右側が全部守られていれば、左側は全部空振りになります。

## 4. 「分からない」が正しい結論になる場合

このツールも含めて、インフラ調査の手がかりは、主に**「うっかり漏れたもの」を拾う仕組み**です。導入前の履歴、メールの記録、別名の指すIP、証明書の組み合わせ――どれも、運営側が何かを表に出してしまったときにだけ生まれます。

ですから、漏れが無ければ、候補は出ません。それはツールの失敗でも、手順の不足でもありません。**「受動の範囲では手がかり無し」という、調査結果の1つ**です。ステップ11の信頼度の段階で言えば「不明」に当たりますが、「不明」と正しく書けることは、根拠のない候補を並べるより、ずっと価値のある結論です。

---

## 📚 付録A: スコアの配点一覧

本文では例の中に散らばっていた配点を、ここに集めます。いずれも**クラスター単位**の加点で、ドメイン同士が直接同じIPを共有していなくても、IPを介してつながったクラスター全体に付きます。

**IP由来の加点（非クラウド、クラウドのみ、同一サブネット、同一ASN/Org の4つ）は、クラスター内の全IPについて `org` を含む ipinfo 情報がそろった場合にだけ付きます。** 1つでも取得できていないIPや、`org` が空のIPがある場合は、IP由来の加点を一切行わず、理由欄に「IP由来の加点なし」と残ります。ヘッダー由来の加点（Server、Cookie、X-Powered-By）は、この条件とは無関係に付きます。

| 条件 | 点数 | 補足 |
|:--- |:--- |:--- |
| 非クラウドIPがある | +15 | 全IPの `org` がそろった場合のみ（上の条件） |
| クラウド/CDN IPのみ | +3 | 上と同時には付かない。全IPの `org` がそろった場合のみ |
| 全IPが同一サブネット（IPv4は /24、IPv6は /48） | +8 | 全IPの `org` がそろった場合のみ |
| 全IPが同一ASN/Org | +10 | 同上。CDNのIPだけでも付くので、CDNの裏では根拠にしない |
| Server が完全一致し、バージョンを含む | +15 | 異なるIPから得た応答同士の比較の場合のみ。例： `nginx/1.18.0` |
| Server が完全一致（汎用値） | +3 | 異なるIPから得た応答同士の比較の場合のみ。例： バージョンのない値 |
| 固有Cookie名が一致 | +30 | 異なるIPから得た応答同士の比較の場合のみ。汎用Cookie名（次項）は判定から**除外**される |
| X-Powered-By が完全一致し、バージョンを含む | +8 | 異なるIPから得た応答同士の比較の場合のみ。バージョンのない一致は 0点 |

- 汎用Cookie名として除外される例： `PHPSESSID`、`JSESSIONID`、`sessionid`、`csrftoken`、Cloudflare や AWS のロードバランサーが付ける名前、など。フレームワークやCDNの既定値は、別人でも一致するためです。
- ヘッダーの比較に使えるドメインが2つ未満の場合、ヘッダー由来の加点は一切付きません（理由欄に「比較不可」と残ります）。
- 動的閾値： `max(40, スコアの65パーセンタイル)`。クラスターが1つだけなら、そのクラスター自身のスコアと40の大きい方になります。

## ⚠️ 付録B: ツールの既知の制限

判断を誤らないよう、ツールの側の限界を集めておきます。ここに挙げるのは、現在のツールの制限です。

1. **CTのノイズ除外は「名前」に対してだけ**： `cloudflaressl.com`、`sni.`、`cloudflare-dns` を含む名前を落とす仕組みで、CDN事業者が発行した証明書そのものを、発行者で除外する仕組みではありません。証明書の発行者は `report.json` の `certificates` で確認できますが、除外の判定には使われていません。
2. **自動probeの件数**： 最大30なのは（ドメイン, IP）の組の数で、1組ごとに https、失敗すれば http と試すため、接続の試行は最大60回です。同じIPが複数のドメインで重なって選ばれることもあります。1クラスターからは最大6ドメインまでで、ドメインが1つだけのクラスターは probe の対象外です。
3. **登録ドメインの判定は、内蔵の短いリストによる**： `co.jp`、`co.uk` など一部の2段サフィックスだけを特別扱いします。それ以外の共有サフィックス配下では、登録ドメインの切り分けがずれることがあります。
4. **probe の対象は「最近のIP」のみ**： pDNSの最終観測時刻が `--recent-days`（既定90日）より古いIPには接続しません。最終観測時刻が取れなかったIP（時刻が0）も、結果として対象外になります。
5. **ヘッダーの一致は、異なるIP同士の比較でのみ加点される**： Server、Cookie、X-Powered-By の一致による加点は、異なるIPから得た応答同士を比べた場合にだけ付きます。全ドメインの応答が同一IPからしか得られなかったクラスターでは、値が一致しても加点されず、理由欄にその旨が表示されます。同じサーバーが答えた一致を、独立した根拠として二重に数えないための仕様です。

## 🛠️ 付録C: うまくいかないときの見方

| 画面や結果の様子 | 考えられること | 次の一手 |
|:--- |:--- |:--- |
| 「CIRCL認証エラー: pDNSを無効化し…」と出る | 認証が401または403で弾かれた。以降は現在のDNS解決だけが材料になる | 認証情報を確かめる。急がないなら、認証なしの結果として扱い、その旨をメモに残す |
| pDNSを使っているのに候補IPが出ない | ツールは、pDNSで公開A/AAAAが得られなければ、理由によらず現在のDNS解決へフォールバックします。それでも出ない場合は、現在のDNSでも公開IPが引けなかったということです | crt.sh 側の名前が取れているかを見る。取れていなければ、今回は受動情報が薄い回として記録する |
| 「非公開/予約IPのため除外した解決結果がN件あります」と出る／IPが0件になる | 実行環境のリゾルバが fake-IP（198.18.x 等）を返していて、解決結果が全部除外された可能性があります。除外した件数は、その場で警告として表示され、`report.json` の `dropped_non_global` にも残ります | その回のツールの結果は材料不足として扱い、DoH（DNS over HTTPS）等で実際のA/AAAAレコードを別途確認して、候補表の材料にする |
| 「crt.sh が 502。再試行します」と出る／「CTログが取得できませんでした」と出る | crt.sh が混雑している、または一時的にエラーを返しています。ツールは間隔を空けて最大3回まで自動で再試行します | 再試行で取れればそのまま進む。3回でも駄目なら、その回はCTなしとして記録し、時間を置いてから再実行する |
| ipinfo のレートリミット表示が出る | 一部のIPが判定不能になっている | その回のネットワーク系統の根拠は弱いものとして扱い、結論の信頼度を下げる |
| 複数ドメインのクラスターができない | 対象がCDNの共有IPだけでつながっている、または候補の名前が解決できなかった | スコアで判断せず、ステップ9の候補表（時期・素の名前・証明書）へ進む |
| probe の結果が全部ステータス0 | https／http とも接続できなかった。古いIP、フィルタリング、候補違いのいずれか | 候補表に戻って時期の物差しを確かめる。接続方法を変えて試し続けない |
| 地図が大きな星型になる | CDNの共有IPに多数の名前がつながっている典型的な形 | 見た目で判断せず、`report.json` の理由欄に戻る |

---

---

## 🌸 まとめ

核心は、**単一の情報源を信じ込まず、複数の独立した根拠(履歴、証明書、設定の癖)を重ねて、ノイズを減らし、確からしさを見積もる**という考え方です。

ツールの仕事は候補を出すところまでで、そこから先は、候補を時期と出どころで絞り、最小限の確認をして、言い切れる範囲だけを信頼度つきで書くのが調査の進め方です。ツールの出力はそのまま信じず、「なぜこのスコアになったのか」「ほかに誤検知の原因はないか」を確かめることが、質の高い調査につながります。分からないことが残るのは失敗ではなく、外側からの観測では普通の結果です。

---

# 付録: ツール本体のコード

以下は `tracker_v1.11.py` の全文です。

```python
#!/usr/bin/env python3
"""
Multi-Layer Infra Tracker v1.11
pDNS + CT + HTTP Headers + ASN による関連性分析(防御・調査目的)

v1.11 の変更点 (外部レビューで残っていた小さい問題5件への対応):
  - crt.sh の応答の形への耐性: JSONが配列でない (辞書など) 場合は「想定外の応答」
    として再試行の対象にし、例外で落ちない。リスト内の辞書でない要素も飛ばす
  - CTの名前の形の確認: ホスト名の形をしていない名前 (メールアドレス風、空白や
    "_" を含むもの等) は、候補にも証明書の名前一覧にも入れない
  - pDNS の 404・429 の扱い: 404 は「記録なし」として警告せず空を返す。
    429 は間隔を空けて最大 PDNS_MAX_ATTEMPTS 回まで再試行する
  - 出力ファイル名に日時を入れる: 既定名は report_YYYYMMDD_HHMMSS.json と
    infra_map_YYYYMMDD_HHMMSS.png (実行開始時刻ベース、2ファイルで同じ日時文字列)
  - 環境変数対応: CIRCL のユーザー名・パスワードを環境変数 CIRCL_USER /
    CIRCL_PASSWORD からも読めるようにした (コマンドライン引数が優先)

v1.10 の変更点:
  - ヘッダー由来の加点は、異なるIPから得たプロファイル同士の比較でのみ行う:
    各ドメインのプロファイルに「どのIPで得たか」を保持し、Server /
    X-Powered-By / 固有Cookie の各加点は、出どころのIPが異なるドメインの組の
    間で一致した場合にだけ付ける。全ドメインの応答が同一IPからしか得られなかった
    場合はヘッダー加点を行わず、理由にその旨を残す。同じサーバーが答えた一致を
    独立した根拠として数えないため (IP由来の加点・閾値・その他の挙動は不変)

v1.9 の変更点 (外部レビューで実在を確認した指摘への対応):
  - CNAMEの多段追跡: pDNSのCNAMEチェーンを最大 MAX_CNAME_DEPTH 段までたどり、
    2段以上の先のA/AAAAも取得する。訪問済み集合で循環を防ぎ、上限・循環で
    打ち切った場合はその旨を表示する
  - orgs 判定の簡略化: 冗長だった `len(orgs | {None}) == 2` を削除 (挙動不変)
  - probe のIP選定を時刻順に: 最近の候補IPから ip_last_seen が最も新しいものを
    選ぶ (同点の場合はIP文字列の昇順で決定論的に選ぶ)
  - get_pdns の構造整理: 冗長な `status_code == 200` 判定を外した (挙動不変)
  - 配点の定数化: calculate_relevance_score の加算値を SCORE_* 定数に集約
    (スコアの値と理由文の文面は v1.8 と同一)
  - probe_headers の SSL コンテキストに、証明書を検証しないことの意味を
    注記するコメントを追加 (挙動不変)

v1.8 の変更点 (実地テストで見つかった課題への対応):
  - crt.sh への再試行: HTTPエラー (429・5xx等)、想定外の応答、接続例外の場合は
    間隔を空けて最大3回まで試す (待機は CT_RETRY_WAITS、既定 5秒→10秒)
  - 非公開/予約IPの除外を可視化: is_global でないために除外した解決結果を
    ドメインごとに数えて警告し、report.json の "dropped_non_global" に出す。
    fake-IP を返すリゾルバの環境で「IP 0件」の理由が分かるようにするため
  - pDNS未使用の明示: CIRCL認証が使えない場合は、結果表示の最後に
    「pDNS履歴は未使用で、過去の姿は見えていない」旨を必ず出す。
    report.json にも "pdns_available" を出す

v1.7 の変更点 (実践編にコード側を合わせたもの):
  - CTを証明書単位で保持: 名前の和集合の返却は従来どおり維持しつつ、証明書ごとの
    発行者・名前の組を self.ct_certificates に保持し、report.json の "certificates" に出す
  - pDNSフォールバックの拡張: 401/403 を認証失敗として扱い、その他の非200は警告する。
    pDNSで公開A/AAAAが得られなかった場合は理由によらず現在のDNS解決へフォールバックする
  - 初出時刻の保持: CIRCLレコードの time_first から self.ip_first_seen を保持し、
    report.json の "ip_first_seen" に出す (live解決由来は first=last=現在時刻)
  - ipinfo加点の厳密化: IP由来の加点は、クラスター内の全IPについて org を含む
    ipinfo情報がそろった場合にだけ行う。そろわない場合はIP由来の加点を一切しない

v1.5 レビューからの主な変更:
  - 認証情報の分離: CIRCL用セッションと調査対象用セッションを分け、Basic認証を対象へ送らない
  - 非公開IP・予約IPを除外 (ipaddress.is_global)
  - 古いIPには能動接続しない (--recent-days)
  - SNI=ドメイン名のまま指定IPへ接続 (Hostヘッダーだけでなく SNI も正しく送る)
  - リダイレクトを追わない / IPv6対応 / 本文は読まない
  - 「異なるドメイン × 1IPずつ」の決定論的サンプリング
  - 汎用Cookie/Serverは低配点、バージョン付きや固有値は高配点
  - ipinfo失敗は「判定不能」として扱い、加点しない
  - pDNS認証失敗を検出したら以降のpDNSを止め、現在のDNS解決へフォールバック
  - 出力の決定論化 (ソート)、pandas依存を削除

注意: 能動的なHTTP接続を伴う。自己管理下、または調査許可のあるインフラにのみ使うこと。
      --no-probe で受動情報(pDNS/CT/ASN)のみの実行ができる。
"""

import argparse
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import requests

# --- 設定 ---
CIRCL_PDNS_URL = "https://www.circl.lu/pdns/query/"
CRT_SH_URL = "https://crt.sh/?q={}&output=json"
USER_AGENT = "InfraTracker/1.11"
CT_MAX_ATTEMPTS = 3            # v1.8: crt.sh への最大試行回数
CT_RETRY_WAITS = (5, 10)       # v1.8: crt.sh 再試行の待機秒 (試行の合間)
PDNS_MAX_ATTEMPTS = 3          # v1.11: pDNS の 429 への最大試行回数
PDNS_RETRY_WAITS = (5, 10)     # v1.11: pDNS 再試行の待機秒 (試行の合間)
REQUEST_TIMEOUT = 15
PROBE_TIMEOUT = 8
MAX_CT_DOMAINS = 30
MAX_HTTP_CHECKS = 30
MAX_DOMAINS_PER_CLUSTER = 6
MAX_CNAME_DEPTH = 5            # v1.9: pDNSでたどるCNAMEチェーンの最大段数
DEFAULT_RECENT_DAYS = 90

# v1.9: 関連性スコアの配点 (calculate_relevance_score で使用。理由文にも同じ値を出す)
SCORE_NON_CLOUD_SHARED = 15    # 非クラウドIPを共有
SCORE_CLOUD_ONLY = 3           # クラウド/CDN IPのみ
SCORE_SAME_SUBNET = 8          # 全IPが同一サブネット
SCORE_SAME_ORG = 10            # 全IPが同一ASN/Org
SCORE_SERVER_VERSIONED = 15    # Server完全一致 (バージョン付き)
SCORE_SERVER_GENERIC = 3       # Server一致 (汎用値)
SCORE_UNIQUE_COOKIE = 30       # 固有Cookie名が一致
SCORE_POWERED_VERSIONED = 8    # X-Powered-By完全一致 (バージョン付き)

# v1.11: CTから集めた名前がホスト名の形かどうかを見るための単純な判定。
# ラベルは英数字とハイフン (先頭・末尾は英数字)、少なくとも1つのドットを含むこと。
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

PUBLIC_SUFFIX_2 = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "net.uk",
    "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp",
    "com.au", "net.au", "org.au", "gov.au", "edu.au",
    "co.nz", "org.nz", "net.nz",
    "com.br", "org.br", "net.br",
}

CLOUD_KEYWORDS = [
    "cloudflare", "amazon", "google", "fastly",
    "akamai", "microsoft", "incapsula", "cdn",
]

# 共有証明書・CDN由来のノイズ名
CT_NOISE_SUBSTRINGS = ("cloudflaressl.com", "sni.", "cloudflare-dns")

# フレームワーク/CDNの既定値 → 運営者の癖としては弱い
GENERIC_COOKIES = {
    "phpsessid", "jsessionid", "asp.net_sessionid", "csrftoken", "xsrf-token",
    "__cf_bm", "_cfuvid", "__cfduid", "awsalb", "awsalbcors", "awsalbtg",
    "laravel_session", "connect.sid", "sessionid", "ci_session",
}


def is_versioned(value: str) -> bool:
    """'nginx/1.18.0' のようにバージョンを含む値か。"""
    return "/" in value and any(c.isdigit() for c in value.split("/", 1)[1])


def resolve_circl_credentials(user=None, password=None):
    """CIRCL認証情報の解決 (v1.11): コマンドライン引数を優先し、無ければ環境変数を見る。"""
    return (user or os.environ.get("CIRCL_USER"),
            password or os.environ.get("CIRCL_PASSWORD"))


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """指定IPへ接続しつつ、SNIにはドメイン名を載せる。"""

    def __init__(self, host, ip, **kw):
        super().__init__(host, **kw)
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, ip, **kw):
        super().__init__(host, **kw)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class InfraTracker:
    def __init__(self, target_domain, username=None, password=None,
                 recent_days=DEFAULT_RECENT_DAYS, probe=True):
        self.target = target_domain.lower().strip()
        self.recent_days = recent_days
        self.probe = probe
        # v1.11: 出力ファイル名に使う実行開始時刻 (report と map で同じ文字列を使う)
        self.run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.graph = nx.Graph()

        # 認証はpDNS専用セッションにのみ付与する
        self.pdns_session = requests.Session()
        self.pdns_session.headers["User-Agent"] = USER_AGENT
        if username and password:
            self.pdns_session.auth = (username, password)
        self.pdns_available = bool(username and password)

        # crt.sh / ipinfo など認証不要の通信用
        self.plain_session = requests.Session()
        self.plain_session.headers["User-Agent"] = USER_AGENT

        self.ip_info_cache = {}       # ip -> dict | None(取得失敗)
        self.ip_last_seen = {}        # ip -> epoch
        self.ip_first_seen = {}       # ip -> epoch (v1.7: time_first 由来、0=不明)
        self.ct_certificates = []     # 証明書ごとの dict (v1.7)
        self.dropped_non_global = {}  # domain -> 除外した非公開/予約IPの件数 (v1.8)
        self.header_profiles = {}     # "domain@ip" -> dict
        self._lock = threading.Lock()
        self._warned_pdns = False

    # ---------- IP ユーティリティ ----------
    @staticmethod
    def is_public_ip(value: str) -> bool:
        try:
            return ipaddress.ip_address(value).is_global
        except ValueError:
            return False

    def is_recent(self, ip: str) -> bool:
        seen = self.ip_last_seen.get(ip)
        if seen is None:
            return False
        return (time.time() - seen) <= self.recent_days * 86400

    # ---------- Layer 1: DNS ----------
    def get_pdns(self, indicator: str) -> list:
        if not self.pdns_available:
            return []
        records = []
        # v1.11: 404 は「記録なし」として警告せず空を返し、429 は間隔を空けて
        # 最大 PDNS_MAX_ATTEMPTS 回まで再試行する。401/403 と他の非200は従来どおり。
        for attempt in range(1, PDNS_MAX_ATTEMPTS + 1):
            try:
                res = self.pdns_session.get(f"{CIRCL_PDNS_URL}{indicator}", timeout=REQUEST_TIMEOUT)
            except requests.RequestException as e:
                print(f"  ⚠️  pDNS接続エラー ({indicator}): {e}")
                return []
            if res.status_code in (401, 403):
                with self._lock:
                    self.pdns_available = False
                    if not self._warned_pdns:
                        self._warned_pdns = True
                        print("  ⚠️  CIRCL認証エラー: pDNSを無効化し、現在のDNS解決へ切り替える")
                return []
            if res.status_code == 404:
                return []
            if res.status_code == 429:
                if attempt < PDNS_MAX_ATTEMPTS:
                    print(f"  ⚠️  pDNS が 429 (レート制限)。再試行します ({attempt}/{PDNS_MAX_ATTEMPTS})")
                    wait = PDNS_RETRY_WAITS[min(attempt - 1, len(PDNS_RETRY_WAITS) - 1)]
                    if wait:
                        time.sleep(wait)
                    continue
                print(f"  ⚠️  pDNSがレート制限のため取得できませんでした (indicator={indicator}、{PDNS_MAX_ATTEMPTS}回試行)")
                return []
            if res.status_code != 200:
                print(f"  ⚠️  pDNSが想定外の応答 (indicator={indicator}, status={res.status_code})")
                return []
            for line in res.text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            break
        return [r for r in records if r.get("rrtype") in ("A", "AAAA", "CNAME")]

    def live_resolve(self, domain: str) -> dict:
        """pDNSが使えない場合の現在のA/AAAA解決。"""
        out = {}
        try:
            for info in socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP):
                out[info[4][0]] = int(time.time())
        except socket.gaierror:
            pass
        return out

    def _note_first_seen(self, ip: str, first: int):
        """ip_first_seen を更新する。0=不明は、0でない値が来たらそちらを採用する。

        resolve_domain_to_ips は並列に呼ばれるため、更新はロックで守る。
        """
        with self._lock:
            cur = self.ip_first_seen.get(ip)
            if cur is None:
                self.ip_first_seen[ip] = first
            elif cur == 0 and first != 0:
                self.ip_first_seen[ip] = first
            elif first != 0:
                self.ip_first_seen[ip] = min(cur, first)

    def resolve_domain_to_ips(self, domain: str) -> dict:
        """ip -> last_seen(epoch)。公開IPのみ返す。

        CNAMEはチェーンを最大 MAX_CNAME_DEPTH 段までたどる (v1.9で多段化)。
        訪問済みの名前は再訪しないため、CNAMEの循環でも無限ループにならない。
        上限・循環で打ち切った場合はその旨を表示する。

        v1.7: あわせて time_first から ip_first_seen を保持する。
        pDNSで公開A/AAAAが1つも得られなかった場合は、理由によらず
        現在のDNS解決(live_resolve)へフォールバックする。
        """
        found = {}
        dropped = set()  # v1.8: is_global でないために除外したアドレス (重複は1件)

        def note_dropped(value):
            # IPアドレスとして解釈できる値だけを数える (壊れた rdata は数えない)
            try:
                addr = ipaddress.ip_address(value)
            except ValueError:
                return
            if not addr.is_global:
                dropped.add(value)

        def absorb(records):
            cnames = set()
            for r in records:
                rtype, rdata = r.get("rrtype"), r.get("rdata", "")
                if rtype in ("A", "AAAA"):
                    if self.is_public_ip(rdata):
                        try:
                            last = int(r.get("time_last") or 0)
                        except (TypeError, ValueError):
                            last = 0
                        try:
                            first = int(r.get("time_first") or 0)
                        except (TypeError, ValueError):
                            first = 0
                        found[rdata] = max(found.get(rdata, 0), last)
                        self._note_first_seen(rdata, first)
                    else:
                        note_dropped(rdata)
                elif rtype == "CNAME":
                    cnames.add(rdata.rstrip("."))
            return cnames

        if self.pdns_available:
            # v1.9: CNAMEチェーンを多段にたどる。visited で循環を防ぐ。
            visited = {domain}
            frontier = absorb(self.get_pdns(domain))
            depth = 0
            while frontier:
                pending = sorted(frontier - visited)
                if not pending:
                    print(f"  ⚠️  {domain}: CNAMEが循環しているため追跡を打ち切り")
                    break
                if depth >= MAX_CNAME_DEPTH:
                    print(f"  ⚠️  {domain}: CNAMEの追跡が上限{MAX_CNAME_DEPTH}段に"
                          "達したため打ち切り")
                    break
                depth += 1
                next_names = set()
                for cname in pending:
                    visited.add(cname)
                    next_names |= absorb(self.get_pdns(cname))
                frontier = next_names
        if not found:
            for ip, ts in self.live_resolve(domain).items():
                if self.is_public_ip(ip):
                    found[ip] = ts
                    self._note_first_seen(ip, ts)
                else:
                    note_dropped(ip)
        if dropped:
            # v1.8: 除外したことが分かるよう、件数を記録して警告する
            with self._lock:
                self.dropped_non_global[domain] = len(dropped)
            print(f"  ⚠️  {domain}: 非公開/予約IPのため除外した解決結果が{len(dropped)}件あります")
        return found

    # ---------- Layer 2: CT ----------
    @staticmethod
    def get_registered_domain(domain: str) -> str:
        parts = domain.lower().split(".")
        if len(parts) >= 3 and ".".join(parts[-2:]) in PUBLIC_SUFFIX_2:
            return ".".join(parts[-3:])
        return ".".join(parts[-2:]) if len(parts) >= 2 else domain

    def get_ct_logs(self, domain: str) -> list:
        reg = self.get_registered_domain(domain)
        print(f"  📜 [CT] 証明書履歴を調査: {reg}")
        # v1.8: crt.sh の一時的なエラー (429・5xx、想定外の応答、接続例外) では
        # 間隔を空けて最大 CT_MAX_ATTEMPTS 回まで試す。
        reason = "不明なエラー"
        for attempt in range(1, CT_MAX_ATTEMPTS + 1):
            entries = None
            try:
                res = self.plain_session.get(CRT_SH_URL.format(f"%.{reg}"), timeout=30)
                if res.status_code == 200 and "json" in res.headers.get("Content-Type", ""):
                    data = res.json()  # JSONでなければ ValueError → 再試行対象
                    if isinstance(data, list):
                        entries = data
                    else:
                        # v1.11: 配列でないJSON (辞書など) も想定外の応答として再試行する
                        reason = "想定外の応答 (JSONが配列ではない)"
                elif res.status_code == 200:
                    reason = "想定外の応答 (JSONではない)"
                else:
                    reason = f"{res.status_code}"
            except ValueError:
                # res.json() の失敗 (requests の JSONDecodeError は ValueError の子孫)
                reason = "想定外の応答 (JSONとして読めない)"
            except requests.RequestException as e:
                reason = f"接続エラー ({e})"
            if entries is not None:
                names = set()
                certificates = []
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue  # v1.11: 辞書でない要素は飛ばす (落ちないように)
                    cert_names = set()
                    for name in entry.get("name_value", "").split("\n"):
                        name = name.strip().lower()
                        if (name and not name.startswith("*")
                                and not any(n in name for n in CT_NOISE_SUBSTRINGS)
                                and HOSTNAME_RE.match(name)):  # v1.11: ホスト名の形だけを通す
                            cert_names.add(name)
                    names |= cert_names
                    # v1.7: 証明書(エントリ)単位でも保持する。1エントリにつき1 dict。
                    certificates.append({
                        "id": entry.get("id"),
                        "issuer_name": entry.get("issuer_name"),
                        "issuer_ca_id": entry.get("issuer_ca_id"),
                        "common_name": entry.get("common_name"),
                        "names": sorted(cert_names),
                        "not_before": entry.get("not_before"),
                        "not_after": entry.get("not_after"),
                    })
                self.ct_certificates.extend(certificates)
                return sorted(names)
            if attempt < CT_MAX_ATTEMPTS:
                wait = CT_RETRY_WAITS[min(attempt - 1, len(CT_RETRY_WAITS) - 1)]
                print(f"  ⚠️  crt.sh が {reason}。再試行します ({attempt}/{CT_MAX_ATTEMPTS})")
                if wait:
                    time.sleep(wait)
            else:
                print(f"  ⚠️  CTログが取得できませんでした ({reason}、{CT_MAX_ATTEMPTS}回試行)")
        return []

    def pick_ct_domains(self, names: list) -> list:
        """決定論的に選ぶ: 別の登録ドメイン(SAN共有)を優先し、残りをアルファベット順。"""
        own = self.get_registered_domain(self.target)
        others = [n for n in names if n != self.target and self.get_registered_domain(n) != own]
        same = [n for n in names if n != self.target and self.get_registered_domain(n) == own]
        return (others + same)[:MAX_CT_DOMAINS]

    # ---------- Layer 3: HTTP ----------
    def probe_headers(self, domain: str, ip: str) -> dict:
        """ipへ接続し、SNI/Hostにdomainを使う。リダイレクトは追わず、本文は読まない。"""
        empty = {"server": "Unknown", "powered": "Unknown", "cookies": [],
                 "status": 0, "proto": None, "location": None, "host": domain, "ip": ip}
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # 調査用途: 自己署名証明書も観測対象
        # 証明書を検証しないため、観測結果は「そのIPが名乗る姿」であって本人確認ではない

        for proto in ("https", "http"):
            conn = None
            try:
                if proto == "https":
                    conn = PinnedHTTPSConnection(domain, ip, timeout=PROBE_TIMEOUT, context=ctx)
                else:
                    conn = PinnedHTTPConnection(domain, ip, timeout=PROBE_TIMEOUT)
                conn.request("GET", "/", headers={"Host": domain, "User-Agent": USER_AGENT,
                                                  "Connection": "close"})
                resp = conn.getresponse()
                headers = resp.getheaders()  # 同名ヘッダーも個別に保持される
                cookies = sorted({
                    v.split("=", 1)[0].strip()
                    for k, v in headers if k.lower() == "set-cookie" and "=" in v
                })
                return {
                    "server": resp.getheader("Server") or "Unknown",
                    "powered": resp.getheader("X-Powered-By") or "Unknown",
                    "cookies": cookies,
                    "status": resp.status,
                    "proto": proto,
                    "location": resp.getheader("Location"),
                    "host": domain,
                    "ip": ip,
                }
            except (OSError, http.client.HTTPException, ssl.SSLError):
                continue
            finally:
                if conn is not None:
                    conn.close()
        return empty

    # ---------- ASN ----------
    def fetch_ip_info(self, ip: str):
        """成功: dict、失敗: None(判定不能)。"""
        try:
            res = self.plain_session.get(f"https://ipinfo.io/{ip}/json", timeout=10)
            if res.status_code == 200:
                data = res.json()
                org = (data.get("org") or "").lower()
                data["_is_cloud"] = any(k in org for k in CLOUD_KEYWORDS)
                return data
            if res.status_code == 429:
                print(f"  ⚠️  ipinfo.io レートリミット (IP: {ip}) → 判定不能として扱う")
        except (requests.RequestException, ValueError):
            pass
        return None

    @staticmethod
    def subnet_of(ip: str) -> str:
        addr = ipaddress.ip_address(ip)
        prefix = 24 if addr.version == 4 else 48
        return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))

    # ---------- スコアリング ----------
    def calculate_relevance_score(self, cluster) -> dict:
        domains = sorted(n for n in cluster if self.graph.nodes[n]["type"] == "domain")
        ips = sorted(n for n in cluster if self.graph.nodes[n]["type"] == "ip")
        if len(domains) < 2:
            return {"score": 0, "reasons": []}

        score, reasons = 0, []

        # --- IP/ASN: v1.7では、全IPについて org を含む情報がそろった場合にだけ加点する ---
        # org が空の情報は「取れていない」として扱う。そろわない場合はIP由来の加点を一切しない。
        known = {ip: self.ip_info_cache.get(ip) for ip in ips}
        missing = [ip for ip in ips
                   if not known[ip] or not known[ip].get("org")]
        if missing:
            reasons.append(
                f"IP由来の加点なし: orgを含むASN情報がそろっていないIPが{len(missing)}個あるため、"
                "IP由来の加点は行わない")
            known = {}
        if known:
            non_cloud = [ip for ip, d in known.items() if not d["_is_cloud"]]
            cloud = [ip for ip, d in known.items() if d["_is_cloud"]]
            if non_cloud:
                score += SCORE_NON_CLOUD_SHARED
                reasons.append(f"非クラウドIPを共有: {len(non_cloud)}個 (+{SCORE_NON_CLOUD_SHARED})")
            elif cloud:
                score += SCORE_CLOUD_ONLY
                reasons.append(f"クラウド/CDN IPのみ(ノイズ注意) (+{SCORE_CLOUD_ONLY})")

            if len(known) >= 2:
                if len({self.subnet_of(ip) for ip in known}) == 1:
                    score += SCORE_SAME_SUBNET
                    reasons.append(f"全IPが同一サブネット (+{SCORE_SAME_SUBNET})")
                orgs = {d.get("org") for d in known.values() if d.get("org")}
                if len(orgs) == 1:
                    score += SCORE_SAME_ORG
                    reasons.append(f"全IPが同一ASN/Org: {next(iter(orgs))} (+{SCORE_SAME_ORG})")

        # --- HTTPヘッダー: 異なるドメイン間で比較 ---
        # v1.10: プロファイルは「どのIPで得たか」と一緒に保持し、加点は
        # 出どころのIPが異なるドメインの組の間での一致に限る。同じIPが答えた
        # 応答同士の一致は、同じサーバーが答えただけであり、独立した根拠として
        # 数えない (結論を書くときの「同じIP由来の根拠は二重に数えない」と揃える)。
        by_domain = {}   # domain -> (応答を得たIP, プロファイル)
        for d in domains:
            for ip in ips:
                p = self.header_profiles.get(f"{d}@{ip}")
                if p and p["status"] > 0:
                    by_domain.setdefault(d, (ip, p))
        if len(by_domain) >= 2:
            # ドメイン名順に並べ、組の作り方と値の選び方を決定論的にする
            ordered = [by_domain[d] for d in sorted(by_domain)]
            source_ips = {ip for ip, _ in ordered}
            if len(source_ips) < 2:
                only_ip = next(iter(source_ips))
                reasons.append(
                    f"ヘッダー比較: 全ドメインの応答が同一IP ({only_ip}) からのため、"
                    "一致は加点しない")
            else:
                def cross_ip_value(key, usable):
                    """key の値のうち、異なる2つ以上のIPから得られているものを返す。

                    返す値は、ドメイン名順に最初に現れるものに固定する。
                    """
                    by_value = {}
                    for ip, p in ordered:
                        if usable(p[key]):
                            by_value.setdefault(p[key], set()).add(ip)
                    for _, p in ordered:
                        if usable(p[key]) and len(by_value.get(p[key], ())) >= 2:
                            return p[key]
                    return None

                server = cross_ip_value("server", lambda v: v != "Unknown")
                if server is not None:
                    if is_versioned(server):
                        score += SCORE_SERVER_VERSIONED
                        reasons.append(f"Server完全一致(バージョン付き): {server} (+{SCORE_SERVER_VERSIONED})")
                    else:
                        score += SCORE_SERVER_GENERIC
                        reasons.append(f"Server一致(汎用値): {server} (+{SCORE_SERVER_GENERIC})")

                # 固有Cookie: 異なるIPの組ごとに共通名を求め、その和集合で判定する
                common_cookies = set()
                for i in range(len(ordered)):
                    for j in range(i + 1, len(ordered)):
                        if ordered[i][0] == ordered[j][0]:
                            continue
                        a = {c for c in ordered[i][1]["cookies"]
                             if c.lower() not in GENERIC_COOKIES}
                        b = {c for c in ordered[j][1]["cookies"]
                             if c.lower() not in GENERIC_COOKIES}
                        common_cookies |= a & b
                if common_cookies:
                    score += SCORE_UNIQUE_COOKIE
                    reasons.append(f"固有Cookie名が一致: {', '.join(sorted(common_cookies))} (+{SCORE_UNIQUE_COOKIE})")

                powered = cross_ip_value(
                    "powered", lambda v: v != "Unknown" and is_versioned(v))
                if powered is not None:
                    score += SCORE_POWERED_VERSIONED
                    reasons.append(f"X-Powered-By完全一致(バージョン付き): {powered} (+{SCORE_POWERED_VERSIONED})")
        else:
            reasons.append(f"ヘッダー比較に使えるドメインが{len(by_domain)}件のみ(比較不可)")

        return {"score": score, "reasons": reasons}

    # ---------- 出力 ----------
    def draw_graph(self, filename=None):
        if filename is None:
            # v1.11: 既定名は実行開始時刻入りにし、再実行で上書きされないようにする
            filename = f"infra_map_{self.run_stamp}.png"
        plt.figure(figsize=(16, 12))
        pos = nx.spring_layout(self.graph, k=0.9, iterations=60, seed=42)
        nodes = list(self.graph.nodes())
        nx.draw(self.graph, pos, nodelist=nodes, with_labels=True,
                node_color=[self.graph.nodes[n]["color"] for n in nodes],
                node_size=1400, font_size=8, font_weight="bold",
                edge_color="gray", linewidths=1.5, alpha=0.95)
        plt.title(f"Infrastructure Map: {self.target}", fontsize=16)
        plt.savefig(filename, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  ✅ '{filename}' を保存")

    def save_report(self, scored, filename=None):
        if filename is None:
            # v1.11: 既定名は実行開始時刻入りにし、再実行で上書きされないようにする
            filename = f"report_{self.run_stamp}.json"
        report = {
            "target": self.target,
            "timestamp": datetime.now().isoformat(),
            "recent_days": self.recent_days,
            "probe_enabled": self.probe,
            "nodes": [{"id": n, **a} for n, a in self.graph.nodes(data=True)],
            "edges": [{"source": u, "target": v} for u, v in self.graph.edges()],
            "ip_info": self.ip_info_cache,
            "ip_last_seen": self.ip_last_seen,
            "ip_first_seen": self.ip_first_seen,
            "certificates": self.ct_certificates,
            "dropped_non_global": self.dropped_non_global,
            "pdns_available": self.pdns_available,
            "header_profiles": self.header_profiles,
            "clusters": [
                {"id": i + 1,
                 "domains": sorted(n for n in c if self.graph.nodes[n]["type"] == "domain"),
                 "ips": sorted(n for n in c if self.graph.nodes[n]["type"] == "ip"),
                 "score": s["score"], "reasons": s["reasons"]}
                for i, c, s in scored
            ],
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  💾 '{filename}' を保存")

    @staticmethod
    def percentile(values, q):
        s = sorted(values)
        if not s:
            return 0
        k = (len(s) - 1) * q
        lo, hi = int(k), min(int(k) + 1, len(s) - 1)
        return s[lo] + (s[hi] - s[lo]) * (k - lo)

    # v1.8: pDNS未使用のときは、結果表示の最後に必ずこの1行を出す
    PDNS_UNUSED_NOTE = ("  ℹ️  pDNS履歴は未使用です。現在のDNS解決のみが材料で、"
                        "過去の姿は見えていません (CIRCL認証で改善する可能性あり)")

    def display_results(self, scored):
        print("\n" + "=" * 70)
        print(" 分析結果 (Relevance Scoring v1.11)")
        print("=" * 70)
        if not scored:
            print("\n  複数ドメインを含むクラスターは見つからなかった。")
            if not self.pdns_available:
                print(self.PDNS_UNUSED_NOTE)
            return

        threshold = max(40, self.percentile([s["score"] for _, _, s in scored], 0.65))
        print(f"\n  動的閾値: {threshold:.1f}点 (上位35%の境界、下限40)\n")
        found = False
        for i, cluster, s in scored:
            domains = sorted(n for n in cluster if self.graph.nodes[n]["type"] == "domain")
            ips = sorted(n for n in cluster if self.graph.nodes[n]["type"] == "ip")
            if s["score"] >= threshold:
                found = True
                print(f"🔥 [高関連度: {s['score']}点] クラスター #{i + 1}")
                print(f"   ドメイン: {', '.join(domains)}")
                print(f"   IP: {', '.join(ips)}")
                for r in s["reasons"]:
                    print(f"   ✔️  {r}")
                print()
            else:
                print(f"🌫️  [低関連度: {s['score']}点] クラスター #{i + 1}: "
                      f"{', '.join(domains[:5])}{'...' if len(domains) > 5 else ''}")
        if not found:
            print("\n  高関連度クラスターなし (CDN/共有ホスティングのノイズが支配的な可能性)")
        print("\n  ※ スコアは手がかりであり、同一運営者の証明ではない。")
        if not self.pdns_available:
            print(self.PDNS_UNUSED_NOTE)

    # ---------- メイン ----------
    def build_probe_tasks(self, clusters):
        """各クラスターから『異なるドメイン × 1つの最近の公開IP』を決定論的に選ぶ。"""
        tasks = []
        for cluster in sorted(clusters, key=lambda c: (-len(c), sorted(c)[0])):
            domains = sorted(n for n in cluster if self.graph.nodes[n]["type"] == "domain")
            if len(domains) < 2:
                continue
            picked = 0
            for d in domains:
                if picked >= MAX_DOMAINS_PER_CLUSTER:
                    break
                cand = [ip for ip in self.graph.neighbors(d) if self.is_recent(ip)]
                if cand:
                    # v1.9: 最も新しく観測されたIPを選ぶ (同点ならIP文字列の昇順で決定論的に)
                    best = min(cand, key=lambda ip: (-self.ip_last_seen.get(ip, 0), ip))
                    tasks.append((d, best))
                    picked += 1
        return tasks[:MAX_HTTP_CHECKS]

    def run_analysis(self):
        print(f"\n追跡開始: {self.target}\n")
        if not self.pdns_available:
            print("  ℹ️  CIRCL認証なし: pDNSは使わず、現在のDNS解決で代替する\n")

        self.graph.add_node(self.target, type="domain", color="lightblue")
        names = self.get_ct_logs(self.target)
        print(f"  [+] CTログから {len(names)} 件の名前\n")
        candidates = [self.target] + self.pick_ct_domains(names)

        def add_result(domain, ips):
            if not ips:
                return
            if domain not in self.graph:
                self.graph.add_node(domain, type="domain", color="pink")
            for ip, seen in ips.items():
                self.graph.add_node(ip, type="ip", color="lightgreen")
                self.graph.add_edge(domain, ip)
                self.ip_last_seen[ip] = max(self.ip_last_seen.get(ip, 0), seen)

        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = {ex.submit(self.resolve_domain_to_ips, d): d for d in candidates}
            results = {}
            for f in as_completed(futs):
                try:
                    results[futs[f]] = f.result()
                except Exception as e:
                    print(f"  ⚠️  {futs[f]}: {e}")
        for d in candidates:  # 決定論的な順で反映
            add_result(d, results.get(d))

        all_ips = sorted(n for n, a in self.graph.nodes(data=True) if a["type"] == "ip")
        print(f"\n  🌍 {len(all_ips)} 個のIPのASN情報を取得")
        with ThreadPoolExecutor(max_workers=2) as ex:
            for ip, info in zip(all_ips, ex.map(self.fetch_ip_info, all_ips)):
                self.ip_info_cache[ip] = info

        clusters = list(nx.connected_components(self.graph))

        if self.probe:
            tasks = self.build_probe_tasks(clusters)
            print(f"\n  🌐 HTTPヘッダー調査: {len(tasks)} 件 (直近{self.recent_days}日内のIPのみ)")
            with ThreadPoolExecutor(max_workers=3) as ex:
                futs = {ex.submit(self.probe_headers, d, ip): (d, ip) for d, ip in tasks}
                for f in as_completed(futs):
                    d, ip = futs[f]
                    try:
                        self.header_profiles[f"{d}@{ip}"] = f.result()
                    except Exception:
                        pass
        else:
            print("\n  --no-probe: 能動的なHTTP接続は行わない")

        scored = []
        for i, c in enumerate(clusters):
            if sum(1 for n in c if self.graph.nodes[n]["type"] == "domain") >= 2:
                scored.append((i, c, self.calculate_relevance_score(c)))

        self.display_results(scored)
        self.draw_graph()
        self.save_report(scored)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Multi-Layer Infra Tracker v1.11")
    ap.add_argument("--domain", required=True, help="調査対象のドメイン")
    ap.add_argument("--user", help="CIRCL pDNS ユーザー名 (環境変数 CIRCL_USER でも指定可)")
    ap.add_argument("--password", help="CIRCL pDNS パスワード (環境変数 CIRCL_PASSWORD でも指定可)")
    ap.add_argument("--recent-days", type=int, default=DEFAULT_RECENT_DAYS,
                    help="能動接続の対象とするIPの最終観測からの日数 (既定: 90)")
    ap.add_argument("--no-probe", action="store_true", help="HTTP接続を行わない(受動情報のみ)")
    args = ap.parse_args()

    # v1.11: 引数が無ければ環境変数 CIRCL_USER / CIRCL_PASSWORD を使う (引数が優先)
    circl_user, circl_password = resolve_circl_credentials(args.user, args.password)
    InfraTracker(args.domain, circl_user, circl_password,
                 recent_days=args.recent_days, probe=not args.no_probe).run_analysis()
```
