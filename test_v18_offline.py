#!/usr/bin/env python3
"""Multi-Layer Infra Tracker v1.8 のオフラインテスト (v1.7 回帰テストを含む)。

ネットワークは一切使わない。依存ライブラリ (networkx / matplotlib / requests) は
sys.modules に最小スタブを入れて差し替え、対象モジュールをファイルから読み込む。
セッションと live_resolve は各テストでフェイクに差し替える。
"""

import importlib.util
import pathlib
import sys
import types

HERE = pathlib.Path(__file__).resolve().parent


# ---------- 依存ライブラリの最小スタブ ----------
class _FakeNodes:
    def __init__(self, graph):
        self._g = graph

    def __call__(self, data=False):
        if data:
            return [(n, a) for n, a in self._g._nodes.items()]
        return list(self._g._nodes)

    def __getitem__(self, n):
        return self._g._nodes[n]

    def __iter__(self):
        return iter(self._g._nodes)

    def __contains__(self, n):
        return n in self._g._nodes


class _FakeGraph:
    def __init__(self):
        self._nodes = {}
        self._adj = {}

    @property
    def nodes(self):
        return _FakeNodes(self)

    def add_node(self, n, **attrs):
        self._nodes.setdefault(n, {}).update(attrs)
        self._adj.setdefault(n, set())

    def add_edge(self, u, v):
        self.add_node(u)
        self.add_node(v)
        self._adj[u].add(v)
        self._adj[v].add(u)

    def neighbors(self, n):
        return iter(self._adj.get(n, ()))

    def edges(self):
        seen = []
        for u, vs in self._adj.items():
            for v in vs:
                if (v, u) not in seen:
                    seen.append((u, v))
        return seen

    def __contains__(self, n):
        return n in self._nodes

    def __iter__(self):
        return iter(self._nodes)


def _install_stubs():
    nx = types.ModuleType("networkx")
    nx.Graph = _FakeGraph
    nx.draw = lambda *a, **k: None
    nx.spring_layout = lambda *a, **k: {}
    nx.connected_components = lambda g: []
    sys.modules["networkx"] = nx

    mpl = types.ModuleType("matplotlib")
    mpl.use = lambda *a, **k: None
    plt = types.ModuleType("matplotlib.pyplot")
    plt.figure = lambda *a, **k: None
    plt.title = lambda *a, **k: None
    plt.savefig = lambda *a, **k: None
    plt.close = lambda *a, **k: None
    sys.modules["matplotlib"] = mpl
    sys.modules["matplotlib.pyplot"] = plt

    req = types.ModuleType("requests")

    class _Session:
        def __init__(self):
            self.headers = {}
            self.auth = None

        def get(self, *a, **k):
            raise AssertionError("offline test: real HTTP must not be called")

    class _RequestException(Exception):
        pass

    req.Session = _Session
    req.RequestException = _RequestException
    sys.modules["requests"] = req


_install_stubs()

spec = importlib.util.spec_from_file_location("tracker_v18", HERE / "tracker_v1.8.py")
tracker_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracker_mod)
InfraTracker = tracker_mod.InfraTracker


# ---------- フェイク応答 ----------
class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", content_type="application/json"):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.headers = {"Content-Type": content_type}

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, response):
        self._response = response
        self.headers = {}
        self.auth = None

    def get(self, url, timeout=None):
        return self._response


def make_tracker():
    return InfraTracker("example.com", probe=False)


def build_cluster(t, domains, ips, ip_infos, profiles=None):
    for d in domains:
        t.graph.add_node(d, type="domain", color="pink")
    for ip in ips:
        t.graph.add_node(ip, type="ip", color="lightgreen")
    for d in domains:
        for ip in ips:
            t.graph.add_edge(d, ip)
    t.ip_info_cache.update(ip_infos)
    if profiles:
        t.header_profiles.update(profiles)
    return set(domains) | set(ips)


# ---------- テスト ----------
def test_ct_certificates_per_certificate():
    t = make_tracker()
    entries = [
        {"id": 111, "issuer_name": "CA One", "issuer_ca_id": 11,
         "common_name": "example.com",
         "name_value": "example.com\nshared.example.org\n*.wild.example.com\nfoo.sni.example.com",
         "not_before": "2026-01-01T00:00:00", "not_after": "2027-01-01T00:00:00"},
        {"id": 222, "issuer_name": "CA Two", "issuer_ca_id": 22,
         "common_name": "example.com",
         "name_value": "example.com\nimg.example.com",
         "not_before": "2026-02-01T00:00:00", "not_after": "2027-02-01T00:00:00"},
    ]
    t.plain_session = FakeSession(FakeResponse(200, json_data=entries))
    names = t.get_ct_logs("example.com")
    # 名前の和集合は従来どおり (ワイルドカードとノイズ名は除外)
    assert names == ["example.com", "img.example.com", "shared.example.org"], names
    # 証明書単位に分かれ、発行者が保持される
    assert len(t.ct_certificates) == 2, t.ct_certificates
    c1, c2 = t.ct_certificates
    assert c1["id"] == 111 and c1["issuer_name"] == "CA One" and c1["issuer_ca_id"] == 11
    assert c1["common_name"] == "example.com"
    assert c1["names"] == ["example.com", "shared.example.org"], c1["names"]
    assert c1["not_before"] == "2026-01-01T00:00:00" and c1["not_after"] == "2027-01-01T00:00:00"
    assert c2["id"] == 222 and c2["issuer_name"] == "CA Two"
    assert c2["names"] == ["example.com", "img.example.com"], c2["names"]


def test_score_pattern1_cloudflare_13():
    t = make_tracker()
    ips = ["104.21.5.10", "172.67.100.10"]
    infos = {ip: {"org": "AS13335 Cloudflare, Inc.", "_is_cloud": True} for ip in ips}
    cluster = build_cluster(t, ["example.com", "img.example.com"], ips, infos)
    result = t.calculate_relevance_score(cluster)
    assert result["score"] == 13, result


def test_score_pattern2_78():
    t = make_tracker()
    ips = ["203.0.113.10", "203.0.113.11"]
    infos = {ip: {"org": "AS64500 Example Hosting Inc", "_is_cloud": False} for ip in ips}
    profiles = {
        "example.com@203.0.113.10": {"server": "nginx/1.18.0", "powered": "Unknown",
                                      "cookies": ["custom_sess_id"], "status": 200,
                                      "proto": "https", "location": None,
                                      "host": "example.com", "ip": "203.0.113.10"},
        "old-bbs.example.org@203.0.113.11": {"server": "nginx/1.18.0", "powered": "Unknown",
                                             "cookies": ["custom_sess_id"], "status": 200,
                                             "proto": "https", "location": None,
                                             "host": "old-bbs.example.org", "ip": "203.0.113.11"},
    }
    cluster = build_cluster(t, ["example.com", "old-bbs.example.org"], ips, infos, profiles)
    result = t.calculate_relevance_score(cluster)
    assert result["score"] == 78, result


def test_score_partial_ipinfo_no_ip_points():
    t = make_tracker()
    ips = ["203.0.113.10", "203.0.113.11"]
    # 片方は取得失敗(None)、もう片方は org が空 → どちらも「そろっていない」
    infos = {"203.0.113.10": None,
             "203.0.113.11": {"org": "", "_is_cloud": False}}
    profiles = {
        "example.com@203.0.113.10": {"server": "nginx/1.18.0", "powered": "Unknown",
                                      "cookies": ["custom_sess_id"], "status": 200,
                                      "proto": "https", "location": None,
                                      "host": "example.com", "ip": "203.0.113.10"},
        "old-bbs.example.org@203.0.113.11": {"server": "nginx/1.18.0", "powered": "Unknown",
                                             "cookies": ["custom_sess_id"], "status": 200,
                                             "proto": "https", "location": None,
                                             "host": "old-bbs.example.org", "ip": "203.0.113.11"},
    }
    cluster = build_cluster(t, ["example.com", "old-bbs.example.org"], ips, infos, profiles)
    result = t.calculate_relevance_score(cluster)
    # IP由来は0点、ヘッダー由来 (Server +15, Cookie +30) のみ
    assert result["score"] == 45, result
    assert any("IP由来の加点なし" in r for r in result["reasons"]), result["reasons"]


def test_fallback_when_pdns_empty_but_available():
    t = make_tracker()
    t.pdns_available = True
    t.get_pdns = lambda indicator: []
    called = {}

    def fake_live(domain):
        called["domain"] = domain
        return {"8.8.8.8": 1234567890}

    t.live_resolve = fake_live
    found = t.resolve_domain_to_ips("example.com")
    assert called.get("domain") == "example.com", called
    assert found == {"8.8.8.8": 1234567890}, found
    # live 由来は first = last = その時刻
    assert t.ip_first_seen.get("8.8.8.8") == 1234567890, t.ip_first_seen


def test_ip_first_seen_from_time_first():
    t = make_tracker()
    t.pdns_available = True
    records = [
        {"rrtype": "A", "rdata": "8.8.4.4", "time_first": 1000, "time_last": 2000},
        {"rrtype": "A", "rdata": "8.8.4.4", "time_first": 500, "time_last": 3000},
        {"rrtype": "A", "rdata": "8.8.8.8", "time_first": 0, "time_last": 4000},
    ]
    t.get_pdns = lambda indicator: records
    t.live_resolve = lambda domain: {}
    found = t.resolve_domain_to_ips("example.com")
    assert found["8.8.4.4"] == 3000, found  # last は最大値
    assert t.ip_first_seen["8.8.4.4"] == 500, t.ip_first_seen  # first は最小値
    assert t.ip_first_seen["8.8.8.8"] == 0, t.ip_first_seen  # 不明は0のまま
    # 0=不明の後に 0でない値が来たら、そちらを採用する
    t._note_first_seen("8.8.8.8", 700)
    assert t.ip_first_seen["8.8.8.8"] == 700
    t._note_first_seen("8.8.8.8", 300)
    assert t.ip_first_seen["8.8.8.8"] == 300


def test_pdns_403_is_auth_failure_and_429_is_not():
    t = make_tracker()
    t.pdns_available = True
    t.pdns_session = FakeSession(FakeResponse(403))
    assert t.get_pdns("example.com") == []
    assert t.pdns_available is False

    t2 = make_tracker()
    t2.pdns_available = True
    t2.pdns_session = FakeSession(FakeResponse(429))
    assert t2.get_pdns("example.com") == []
    assert t2.pdns_available is True  # 429 は認証失敗として扱わない


def test_report_contains_new_fields():
    import json as _json
    import tempfile
    import os
    t = make_tracker()
    t.ct_certificates = [{"id": 1, "issuer_name": "CA One", "issuer_ca_id": 1,
                          "common_name": "example.com", "names": ["example.com"],
                          "not_before": None, "not_after": None}]
    t.ip_first_seen = {"8.8.8.8": 123}
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "report.json")
        t.save_report([], filename=path)
        with open(path, encoding="utf-8") as f:
            report = _json.load(f)
    assert report["certificates"] == t.ct_certificates, report.keys()
    assert report["ip_first_seen"] == {"8.8.8.8": 123}


# ---------- v1.8 の新規テスト ----------
class SeqSession:
    """呼ぶたびに用意した応答を順に返す (例外オブジェクトは送出する)。"""

    def __init__(self, items):
        self._items = list(items)
        self.headers = {}
        self.auth = None
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        item = self._items.pop(0) if len(self._items) > 1 else self._items[0]
        if isinstance(item, Exception):
            raise item
        return item


CT_ENTRIES = [
    {"id": 333, "issuer_name": "CA Three", "issuer_ca_id": 33,
     "common_name": "example.com",
     "name_value": "example.com\nimg.example.com",
     "not_before": "2026-03-01T00:00:00", "not_after": "2027-03-01T00:00:00"},
]


def test_ct_retry_then_success():
    tracker_mod.CT_RETRY_WAITS = (0, 0)  # 待機を差し替えて速くする
    t = make_tracker()
    session = SeqSession([FakeResponse(502), FakeResponse(502),
                          FakeResponse(200, json_data=CT_ENTRIES)])
    t.plain_session = session
    names = t.get_ct_logs("example.com")
    assert session.calls == 3, session.calls
    assert names == ["example.com", "img.example.com"], names
    assert len(t.ct_certificates) == 1, t.ct_certificates
    assert t.ct_certificates[0]["issuer_name"] == "CA Three"


def test_ct_all_failures_return_empty():
    tracker_mod.CT_RETRY_WAITS = (0, 0)
    t = make_tracker()
    session = SeqSession([FakeResponse(502)])
    t.plain_session = session
    assert t.get_ct_logs("example.com") == []
    assert session.calls == tracker_mod.CT_MAX_ATTEMPTS, session.calls
    assert t.ct_certificates == []


def test_ct_retry_on_connection_error():
    tracker_mod.CT_RETRY_WAITS = (0, 0)
    t = make_tracker()
    req_exc = tracker_mod.requests.RequestException("boom")
    session = SeqSession([req_exc, FakeResponse(200, json_data=CT_ENTRIES)])
    t.plain_session = session
    names = t.get_ct_logs("example.com")
    assert session.calls == 2, session.calls
    assert names == ["example.com", "img.example.com"], names


def test_dropped_non_global_live_and_report():
    import json as _json
    import tempfile
    import os
    t = make_tracker()
    t.pdns_available = False
    t.live_resolve = lambda domain: {"198.18.32.78": 111, "198.18.0.9": 222}
    found = t.resolve_domain_to_ips("example.com")
    assert found == {}, found
    assert t.dropped_non_global == {"example.com": 2}, t.dropped_non_global
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "report.json")
        t.save_report([], filename=path)
        with open(path, encoding="utf-8") as f:
            report = _json.load(f)
    assert report["dropped_non_global"] == {"example.com": 2}
    assert report["pdns_available"] is False


def test_dropped_non_global_pdns_records():
    t = make_tracker()
    t.pdns_available = True
    records = [
        {"rrtype": "A", "rdata": "10.0.0.1", "time_first": 100, "time_last": 200},
        {"rrtype": "A", "rdata": "10.0.0.1", "time_first": 100, "time_last": 300},
        {"rrtype": "A", "rdata": "8.8.8.8", "time_first": 100, "time_last": 200},
        {"rrtype": "A", "rdata": "not-an-ip", "time_first": 0, "time_last": 0},
    ]
    t.get_pdns = lambda indicator: records
    called = {}
    t.live_resolve = lambda domain: called.setdefault("live", True) or {}
    found = t.resolve_domain_to_ips("example.com")
    assert found == {"8.8.8.8": 200}, found
    # 重複した 10.0.0.1 は1件として数え、壊れた rdata は数えない
    assert t.dropped_non_global == {"example.com": 1}, t.dropped_non_global
    assert "live" not in called  # 公開IPが得られたのでフォールバックしない


def test_display_results_shows_pdns_unused_note():
    import contextlib
    import io
    t = make_tracker()
    t.pdns_available = False
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        t.display_results([])
    assert "pDNS履歴は未使用です" in buf.getvalue(), buf.getvalue()

    # クラスターがある場合の最後にも出る
    ips = ["104.21.5.10", "172.67.100.10"]
    infos = {ip: {"org": "AS13335 Cloudflare, Inc.", "_is_cloud": True} for ip in ips}
    cluster = build_cluster(t, ["example.com", "img.example.com"], ips, infos)
    result = t.calculate_relevance_score(cluster)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        t.display_results([(0, cluster, result)])
    assert "pDNS履歴は未使用です" in buf.getvalue(), buf.getvalue()

    # pDNSが使える場合は出ない
    t2 = make_tracker()
    t2.pdns_available = True
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        t2.display_results([])
    assert "pDNS履歴は未使用です" not in buf.getvalue(), buf.getvalue()


TESTS = [
    test_ct_certificates_per_certificate,
    test_score_pattern1_cloudflare_13,
    test_score_pattern2_78,
    test_score_partial_ipinfo_no_ip_points,
    test_fallback_when_pdns_empty_but_available,
    test_ip_first_seen_from_time_first,
    test_pdns_403_is_auth_failure_and_429_is_not,
    test_report_contains_new_fields,
    # v1.8 新規
    test_ct_retry_then_success,
    test_ct_all_failures_return_empty,
    test_ct_retry_on_connection_error,
    test_dropped_non_global_live_and_report,
    test_dropped_non_global_pdns_records,
    test_display_results_shows_pdns_unused_note,
]

if __name__ == "__main__":
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
