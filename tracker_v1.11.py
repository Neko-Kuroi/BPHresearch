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
