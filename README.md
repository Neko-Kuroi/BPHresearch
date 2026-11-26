# 🌸 Infrastructure Investigation Guide — Complete Edition (Multi-Layer Infra Tracker)

> **⚠️ Before you begin (required reading)**
> This guide is intended for **education and learning, or for investigating infrastructure with explicit permission**. Do not perform unauthorized active scanning of third-party servers, and do not place excessive load on them. Always keep the purpose of your investigation and its ethical boundaries in mind.

The purpose of this guide is to **infer, as a defensive investigation, the origin (the real server and related infrastructure) of sites such as bulletin boards that are placed on bulletproof hosting or similar services and hidden behind a CDN or the like**. The tool it assumes is `tracker_v1.10.py`, whose full source code is included at the end of this document, in "Appendix: Full Source Code of the Tool." This document alone covers everything from the underlying ideas, through running the tool, to how to write up your conclusions.

## Contents

- Step 1: What are we investigating, and why?
- Step 2: Preparation
- Step 3: Running the tool
- Step 4: How to read the results
- Step 5: How to read the visualization map
- Step 6: Using the tool safely and responsibly
- Step 7: The practical workflow (overview)
- Step 8: Investigation notes and passive investigation
- Step 9: Narrowing down the candidates (building a candidate table)
- Step 10: Verifying candidates one at a time
- Step 11: How to write the conclusion
- The operator's side
- Appendix A: Score table
- Appendix B: Known limitations of the tool
- Appendix C: When things do not work
- Summary
- Appendix: Full Source Code of the Tool

---

## 🎯 Step 1: What are we investigating, and why?

Websites use **CDNs such as Cloudflare** to defend against DDoS attacks, and they **change domains and IP addresses** when they move servers.
Because of that, the mere fact that two sites "use the same IP address" does not tell you whether they are "strangers who happen to rent the same shared server" or "infrastructure shared by the same administrator."

This tool combines several viewpoints (layers) to reduce "coincidental matches (noise)" and to surface "clues to a connection."

| Viewpoint (layer) | What is actually examined | Strength as evidence, and cautions |
| :--- | :--- | :--- |
| **① Past footprints (passive DNS)** | The history of which IP addresses were used in the past | **Medium.** Can reveal the original server IP from before the CDN was introduced, and clues about migration paths. Shared hosting is possible, so checking the time period matters. |
| **② Certificates (CT logs)** | Which domains appear on the same SSL certificate (SAN) | **Strong (conditionally).** If a **different registered domain** appears on the same certificate, that is a strong clue. Subdomains of the same registered domain sharing a certificate is only natural, so that is weak as evidence. |
| **③ Server habits (HTTP)** | Cookie names and software versions returned by the server | **Weak to medium.** A match on a distinctive name suggests "the same software and configuration may be in use," but if it is a **default value** of bulletin board software or the like, different people will match too. |

> **Note:** The tool's scoring does not match the "strength as evidence" above. For example, the tool gives no points for CT logs themselves (it uses them only to gather candidate related domains), and it gives the largest score (+30) to a distinctive cookie match. The final judgment must be made by a human, weighing not just the score but also the reasons given, against this table of strengths.

---

## 🛠️ Step 2: Preparation

### 1. Python
- **What you need**: Python 3.9 or later
- **What to do**:
  ```bash
  pip install requests networkx matplotlib
  ```
  (`pandas` is not needed, in v1.10 either)

### 2. A CIRCL passive DNS account (recommended)
- **What you need**: An account with [CIRCL LU](https://www.circl.lu/services/passive-dns/)
- **Note**: Approval can take several days after you apply. If you have no credentials, run the commands below without `--user` and `--password`. In that case the tool works only from current DNS resolution, so **past footprints will not be visible**.

### 3. The domain to investigate
- Example: `example.com`

---

## 🚀 Step 3: Running the tool

The basic principle is to **prefer passive investigation, and keep active investigation to a minimum**.

### Recommended A: Passive investigation only, first

```bash
python tracker_v1.10.py --domain example.com --user YOUR_USER --password YOUR_PASS --no-probe
```

- **What `--no-probe` means**: The tool makes no HTTP connections to the target server.
- However, the following traffic does occur.
  - Current DNS resolution of the target domain (when passive DNS is unavailable; queries may reach the target's authoritative DNS servers)
  - Queries to third-party services such as CIRCL, crt.sh, and ipinfo.io (the domain and IPs you are investigating are sent to them)

### Recommended B: Investigation including automatic HTTP connections

```bash
python tracker_v1.10.py --domain example.com --user YOUR_USER --password YOUR_PASS --recent-days 90
```

- **What the tool does**: v1.10 automatically tries HTTP connections to **up to about 30** of the IPs in the clusters it finds (including CDN IPs).
- **What `--recent-days 90` means**: It connects only to IPs observed within the last 90 days. This **reduces** (but does not eliminate) the risk of accidentally accessing an IP that was reassigned to someone else years ago.
- **If you want to investigate more narrowly**: Instead of the tool's automatic connections, connect manually, just once, to a candidate IP only.
  ```bash
  curl -sI --resolve example.com:443:<candidate IP> https://example.com/ -k
  ```

- **Retries against crt.sh**: If crt.sh does not respond temporarily, the tool retries up to 3 times, with pauses in between. If it still cannot retrieve the data, it says so and continues processing without CT logs.

### Notes

- **Windows**: In Command Prompt and PowerShell, a trailing `\` cannot be used for line continuation. Write each command on a single line.
- **Passwords**: v1.10 does not support environment variables either. Be aware that if you write the password directly on the command line, it will remain in your shell history.

---

## 📖 Step 4: How to read the results

The output falls into two broad patterns, depending on the target's environment.

Note: if you have no CIRCL credentials, the results always end with a line to the effect of "passive DNS history was not used; only current DNS resolution is available as material, and the past is not visible." (The tool prints this line in Japanese.) You can also check whether passive DNS was available in `pdns_available` in `report.json`.

### Pattern 1: Behind a CDN such as Cloudflare (the common case)

What the screen shows when run with `--no-probe` (the tool's output is in Japanese):

```text
  動的閾値: 40.0点 (上位35%の境界、下限40)

🌫️  [低関連度: 13点] クラスター #1: example.com, img.example.com
```

(In English: "Dynamic threshold: 40.0 points (the top-35% boundary, floor 40)" and "Low relevance: 13 points, Cluster #1.")

Low-relevance clusters are shown as **only a single line on screen**. To see the reasons, open `report.json`.

```json
"reasons": [
  "クラウド/CDN IPのみ(ノイズ注意) (+3)",
  "全IPが同一ASN/Org: AS13335 Cloudflare, Inc. (+10)",
  "ヘッダー比較に使えるドメインが0件のみ(比較不可)"
]
```

(In English: "Cloud/CDN IPs only (noise warning) (+3)"; "All IPs in the same ASN/Org: AS13335 Cloudflare, Inc. (+10)"; "0 domains available for header comparison (cannot compare).")

- **What you can tell**: Because shared CDN IPs are in use, this is not "evidence of the same operator."
- **Caution (a quirk of the tool)**: The +10 for "all IPs in the same ASN/Org" is awarded even when it is merely CDN IPs being shared. Behind a CDN, do not treat this bonus as grounds concerning the operator.
- **Next move**: Fill in, manually, what the tool alone cannot pick up.
  - The A, MX, and SPF `ip4:` records of subdomains that are not proxied
  - Searching Censys / Shodan by certificate or favicon
  - Whether passive DNS shows an IP from before the CDN was introduced
  - In the CT logs, whether a certificate **issued by a CA other than Cloudflare** includes a **different registered domain**


### Pattern 2: Not using a CDN, sharing its own infrastructure

> **Note: this is a fictional example.** The `198.51.100.x` addresses below are from an IP range reserved for documentation. The tool's `is_global` check excludes them, so this output cannot actually be reproduced. It is an example to explain how the tool behaves.
> Also, the cookie match and Server match lines appear **only when HTTP connections are made (Recommended B)**. With `--no-probe`, those two lines (+45 points) do not appear, and the cluster is low relevance at 33 points.

An example of a run under Recommended B (the tool's output is in Japanese):

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

(In English: "High relevance: 78 points"; "Shared non-cloud IPs: 2 (+15)"; "All IPs in the same subnet (+8)"; "All IPs in the same ASN/Org (+10)"; "Server exact match (with version): nginx/1.18.0 (+15)"; "Distinctive cookie name match: custom_sess_id (+30).")

- **What you can tell**: Several clues overlap (sharing non-cloud IPs, the same hosting provider, a match on a cookie with a distinctive name).
- **Cautions**:
  - The score is not a "probability."
  - The threshold is a relative value. If there is only one cluster, the threshold is the larger of that cluster's own score and 40 (78.0 points in this example).
  - This is a **clue** that "the same operator is possible," not conclusive evidence.
  - A match on a `Server` version will be the same for anyone using the same OS package build.

---

## 🗺️ Step 5: How to read the visualization map (`infra_map.png`)

- 🔵 **Light-blue circles**: The domain where the investigation started
- 🩷 **Pink circles**: Names found in CT logs and the like whose IPs could be resolved (including subdomains of the same registered domain)
- 🟢 **Green circles**: IP addresses

**⚠️ Caution**: A large star shape, with many domains connected to a single green circle (IP), is typical **noise** when a shared CDN such as Cloudflare is in use. Do not judge by how dense the picture looks; check the reasons (`reasons`) in `report.json`.

---

## ⚠️ Step 6: Using the tool safely and responsibly

1. **The output is "clues," not "evidence"**
   A cookie name match can happen between different people who use the same bulletin board software with its default values. A `Server` version match is likewise the same for anyone on the same OS package build.
2. **Write a confidence level in your conclusion**
   Indicate the degree of certainty — for example "confirmed," "likely (three or more independent grounds)," "possible (one or two clues)" — and always attach the "possibility of a false positive (shared hosting, matching defaults, an old IP being reused, and so on)."
3. **Handling real names**
   When you share investigation results externally, replace real domains and IP addresses with things like `example.com` or `192.0.2.x`.

---

## 🎯 Step 7: The practical workflow (overview)

In practice, proceed in the following five stages. What matters is not to skip stages.

1. **Write notes** (write down, in advance, what you are trying to establish)
2. **Surface candidates with passive investigation** (this is as far as the tool goes)
3. **Narrow down the candidates** (build a candidate table using timing and sources)
4. **Verify the candidates one at a time** (keep active verification to a minimum)
5. **Write the conclusion** (confidence, the possibility of a false positive, and what you do not know, as a set)

The tool does most of the work up to stage 2. Stages 3 onward are what Steps 9–11 cover.

---

## 📝 Step 8: Investigation notes and passive investigation

### 1. Write notes before you start

Before starting an investigation, write the following five things in your notes. This prevents "what was I investigating, again?" from becoming vague later.

- The target domain
- The date and time you started observing
- Your hypothesis (for example: "This bulletin board may have an origin behind a CDN, and may once have been operated on a bare IP")
- The scope of permission (passive only, or including one verification connection to a candidate)
- The stopping conditions (for example: stop when the candidates run out)

### 2. Run the passive investigation and keep the output

```bash
python tracker_v1.10.py --domain example.com --user YOUR_USER --password YOUR_PASS --no-probe
```

- Once you have run it, save copies of `report.json` and `infra_map.png` under dated names (for example, `report_20261126_1730.json`) before they are overwritten. The tool's output file names are fixed, and rerunning it overwrites them.
- Do not throw away clusters that show as low relevance on screen, either. The reasons for a low-relevance cluster appear as only one line on screen, and remain only in `reasons` in `report.json`. In practice, clues pointing "behind the CDN" sometimes remain precisely among the low-relevance results.

### 3. What to pick out of report.json

In practice, the following fields are the ones mainly used.

| Field | What to look at |
|:--- |:--- |
| `clusters[].reasons` | The reasons for the score. Read these before the score itself |
| `clusters[].ips` | The list of IPs that could become candidates |
| `ip_last_seen` | The time each IP was last observed (epoch). Used to judge timing |
| `ip_first_seen` | The time each IP was first observed (epoch). Derived from `time_first` in passive DNS; 0 means unknown. For an IP obtained by current DNS resolution, first seen = last seen = the time it was resolved |
| `certificates` | One record per certificate: the issuer (`issuer_name`), the set of names on that certificate (`names`), and the validity period. Judge certificates in this unit |
| `dropped_non_global` | For each domain, the number of resolution results that were excluded as non-public / reserved IPs. When the IP count is 0, this lets you tell whether resolution itself failed, or the results were excluded |
| `pdns_available` | Whether CIRCL passive DNS was available. On a run where this is `false`, the past history was not visible |
| `ip_info` | The ASN/Org and the cloud determination (`_is_cloud`). An IP that could not be retrieved is `null` (cannot be determined) |
| `header_profiles` | Only when probing was done. Server, X-Powered-By, cookie names |

---

## 🔍 Step 9: Narrowing down the candidates (building a candidate table)

Build a table of candidate IPs, and look at each one with the following criteria. **Drop candidates that do not meet a criterion early.**

### Criterion 1: Timing

- Does the IP appear in the period **before** the CDN was introduced? An IP that passive DNS history shows was in use before the switch to CDN IPs stays as an origin candidate.
- Conversely, an IP that appeared only once, years ago, and looks to have been used for something else ever since is likely to have been reassigned, so drop it.
- You can check "when it first appeared" in `ip_first_seen` in `report.json` (derived from `time_first` in passive DNS). Look at it alongside `ip_last_seen` (the time it was last observed), as the span "from when to when was it in use." However, an IP whose `ip_first_seen` is 0 has an unknown first appearance. Also, for an IP obtained by current DNS resolution, first seen = last seen = the time of resolution, so it is not a first appearance in the historical sense.

### Criterion 2: Names that are not proxied

A subdomain that does not go through the CDN may point directly at the origin.

```bash
dig +short A example.com
dig +short A mail.example.com
dig +short MX example.com
dig +short TXT example.com
```

- Check whether the MX destination, or the `ip4:` ranges written in TXT (SPF) records, include a candidate IP or one near it.
- This is information the tool does not collect. Fill it in manually.

### Criterion 3: Certificates (look at them one at a time)

The tool **keeps certificates per certificate**, and `certificates` in `report.json` contains, for each certificate, its issuer (`issuer_name`) and the set of names on that certificate (`names`) (it also returns the union of names used for candidate gathering). Make your judgments in this per-certificate unit. For each certificate, look at the following two things.

- Is the issuer not a CDN provider?
- Does the same certificate include a **different registered domain**?

A certificate where both hold is a strong clue. As a final check, do not skip reopening the certificate on the crt.sh site itself.

### Criterion 4: Network

- Is the candidate IP's ASN/Org not a CDN provider?
- However, "same ASN," "same subnet," and "non-cloud" all trace back to the same IP information. In the counting in Step 10 below, count them together as **one category**.

An example candidate table (a fictional example; the IPs are from the range reserved for documentation):

| Candidate IP | Timing | Bare name | Certificate | Network | Keep / drop |
|:--- |:--- |:--- |:--- |:--- |:--- |
| 203.0.113.10 | Appeared continuously before the CDN was introduced | Same as the MX destination | Shared with another domain (issued by another CA) | Non-cloud | Keep |
| 203.0.113.99 | Only once, 5 years ago | None | None | Non-cloud | Drop (suspected reassignment) |
| A CDN IP | Current | — | — | Cloud | Drop (a public-facing IP) |

---

## 🌐 Step 10: Verifying candidates one at a time

Once candidates remain, the principle is to verify **once per candidate**. Instead of the tool's automatic probing (Recommended B), connect manually just once, and compare with the public-facing response (via the CDN).

```bash
curl -sk -o /dev/null -D - --resolve example.com:443:203.0.113.10 https://example.com/
```

- `-D -` shows only the response headers, and the body is not saved to a file (`-o /dev/null`).
- What to compare: the status, Server, the names in Set-Cookie, and the redirect destination.
- **If it does not match, drop that candidate and be done.** Do not keep trying a non-matching candidate with different ports or paths. That stops being investigation and becomes scanning.
- Certificate verification is disabled (`-k`) because we are connecting to a candidate IP by domain name. Note that what is displayed cannot, on that account, be treated as grounds for declaring it "the real thing."

Incidentally, Recommended B in the main text (the tool's automatic probing) tries up to 30 (domain, IP) pairs, falling back to http if https fails. When you want to verify carefully in practice, use this single manual connection as the basis, not automatic probing.

---

## ✍️ Step 11: How to write the conclusion

### How to count the grounds

Count the grounds not by points, but by **the category they come from**. There are four categories.

1. **DNS history** (the shape of passive DNS, including timing)
2. **Certificates** (confirmed per certificate)
3. **HTTP habits** (matches in Server, cookie names, and the like)
4. **Network** (ASN, subnet, and whether it is non-cloud — all together, this one category)

Not double-counting items that come from the same IP information across categories is the key to avoiding overestimation.

### Confidence levels

| Wording | Guideline |
|:--- |:--- |
| Confirmed | Do not use it. Observations from outside the infrastructure alone never justify writing "confirmed" |
| Likely | Three or more independent categories line up, and a false-positive explanation cannot compete |
| Possible | One or two categories. It remains a candidate, but you cannot state it flatly |
| Candidate only | Only weak matches, such as timing or network alone |
| Unknown | No candidate remained, or only public-facing information could be obtained |

### A template for the conclusion

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

(This template is the format the investigation notes use. In English: Target / Conclusion — the candidate believed to be the origin is 203.0.113.10, confidence "possible" / Grounds by category — DNS history: this IP was in continuous use in the period before the CDN was introduced; Certificate: it appeared, together with a different registered domain, on one certificate issued by another CA / Possibility of a false positive — on shared hosting, another operator's site could take the same shape; a mid-period change of IP assignment cannot be completely ruled out / What is not known — whether the same server is still used as the origin cannot be confirmed from outside / Date and time of observation: 2026-11-26.)

### A worked example (a fictional example)

This is an example set up as: a bulletin board `example.com` behind a CDN was investigated. The IPs are from the range reserved for documentation, and this is not actual output.

1. In the passive investigation, the cluster was low relevance at 13 points. The reasons were "cloud/CDN IPs only (+3)," "all IPs in the same ASN/Org (+10)," and "0 domains available for header comparison," so all that could be told was that the public-facing side is a CDN.
2. Building a candidate table, one IP remained in the passive DNS history that appears only in the period before the CDN was introduced. The MX destination also pointed at the same IP.
3. Looking at the certificates one at a time, a certificate from another CA, issued in that IP's period, had a different registered domain on it together with this one.
4. In the manual verification connection to the candidate, the status and Server matched the public-facing side, but the cookie names could not be confirmed.
5. The conclusion was written using the template, as "possible." The categories were two — DNS history and certificates — and since that does not reach three, the judgment was not to write "likely."

As in this example, **ending with "cannot say for sure" is the ordinary way for an investigation to end**. Writing, as-is, that you cannot say for sure is how a conclusion is written.

---

---

# The operator's side

This chapter organizes, from the defender's / operator's point of view, what the side doing the hiding (= the side doing the protecting) is thinking, and in what order of steps it publishes a site. It is a chapter for the investigating side to understand "why can we not see it?" Knowing how the mechanism works is useful both for reading investigation results correctly, and for when you are on the side protecting your own site.

## 1. What is the operator protecting? (Motives)

You cannot state, from outside, what a specific site's operator is thinking. That said, operators who place the real server behind a CDN are generally understood to have reasons such as the following.

- **Protecting the real server from DDoS and attacks**: If the real server's IP becomes known, it can be attacked directly, bypassing the CDN. Not exposing the IP is itself the first line of defense.
- **Having the CDN take the brunt of attacks**: The public-facing side's responses are handled by the CDN. Large volumes of access and attacks are absorbed by the CDN first.
- **Not showing server migrations or provider changes to the outside**: Even if the real server moves, all that changes is the destination inside the CDN. The appearance from outside (the CDN's IPs) does not change, so the timing of a migration, and where it went, are harder to infer.
- **Spreading out the target of complaints and takedown requests**: Inquiries and requests arrive first at the public-facing side (the CDN provider, or the domain registration side). They do not arrive directly at the place where the real server sits.
- **Making the operator's identity, and the hosting provider they use, harder to infer**: If the real server's IP becomes known, the owner of that IP (the provider), and other sites on the same IP or the same network, can lead closer to who is running the site. Hiding the IP closes that entrance, too.

Seen from the investigating side, all of these work as "reasons no clues are given out." Put the other way: clues emerge mostly when the operator has **carelessly broken** one of these protections.

## 2. From a finished bulletin board program to going live

Here is, in order, what an operator who has finished writing a bulletin board program does before going live. Each step has a note on "what the investigating side can and cannot see."

**Step 1: Rent a server and set up the foundations**
Rent a VPS or a dedicated server, and install the OS and the foundations (web server, database, runtime environment). At this point, the server has its real IP address.
- Seen from the investigating side: Nothing is visible yet. An IP not tied to a domain is just one of countless IPs.

**Step 2: Place the program, and test it by hitting the IP directly**
Place the program on the server, access it directly by IP address, and check that posting and display work. This stage is private work.
- Seen from the investigating side: Not visible. Work that does not go through a name (domain) leaves no record in DNS or in certificates.

**Step 3: Register a domain, with privacy protection on the registration information**
Register the site's name (domain). It is normal to use privacy protection so that the registrant's information is not published.
- Seen from the investigating side: The domain's existence and registration date are visible, but the registrant themselves is not.

**Step 4: Before going live, entrust the domain to Cloudflare and switch the name servers**
Register the domain with Cloudflare and switch the name servers to Cloudflare's. The key is to finish this **before going live**. In other words, the site starts out behind the CDN from the very beginning.
- Seen from the investigating side: That the name servers belong to a CDN provider is visible. But because there is no "before the CDN was introduced," no pre-CDN IP appears in the passive DNS history either.

**Step 5: Create the DNS names, point them at the real IP, and enable the proxy**
In Cloudflare's dashboard, create the names for the apex and the subdomains, and point each at the real server's IP. But set them to "proxy enabled."
- Seen from the investigating side: Resolving a name returns only CDN IPs. The real IP is information that exists only inside Cloudflare, and does not get out.

**Step 6: Consolidate certificates into a wildcard**
Prepare the certificates for HTTPS. Rather than taking separate certificates name by name, consolidate them into a wildcard (*.domain).
- Seen from the investigating side: What appears in CT logs is only the wildcard and the apex name; subdomain names, and combinations with other domains, do not come out.

**Step 7: Close the real server with a firewall so that it accepts connections only from Cloudflare**
On the real server's side, set it to "pass connections from the CDN only, and refuse everything else."
- Seen from the investigating side: Even if a candidate IP surfaces, you cannot connect to it directly to verify it. This is one of the reasons the "verification connection to a candidate" in Step 10 may not go through.

**Step 8: Do not run a mail server. Do not create separate names for administration or testing**
Decide not to run mail (or, if you do, put it somewhere else), and do not create administrative names such as `direct` or `cpanel`, or subdomains for testing, either. Delete any you did create.
- Seen from the investigating side: There is no opening for IPs to leak from MX or SPF, and no names that are not proxied, so Criterion 2 (Step 9) cannot be used.

**Step 9: Going live, and operation**
Announce the site, go live, and operate it normally from then on. Program updates are done by logging into the server directly. When the server is migrated, all that changes is the destination inside Cloudflare.
- Seen from the investigating side: The appearance from outside barely changes from the first day of going live. Even after a migration, the public-facing side is the same, so it cannot be observed as a change.

To sum up, there are only two keys. **"Being behind the CDN from the first day of going live,"** and **"not creating a single name or service that reaches the origin behind the CDN directly."** The rest is no different from running an ordinary site.

## 3. A side-by-side table of leak openings

Here are Step 1's layer table (the investigating side's clues) and the operator's ways of closing them, side by side.

| The investigating side's clue | The operator's way of closing it |
| :--- | :--- |
| Passive DNS history (the IP from before the CDN was introduced) | Be behind the CDN from the first day of going live. Do not create a pre-CDN period at all |
| In CT logs, a different registered domain on the same certificate | Consolidate into a wildcard certificate. Do not take separate certificates per purpose |
| IPs written in MX / SPF | Do not host mail. If you do, use a different server from the real server |
| Subdomains that are not proxied (for administration, testing, etc.) | Do not create such names. If you created one, delete it |
| HTTP habits (Server header, cookie names) | The public-facing side is answered by the CDN, so the real server's headers do not reach the public-facing side |
| Verification by connecting directly to a candidate IP | The real server refuses connections from anywhere other than Cloudflare |

The investigating side's clues correspond to the places where the right-hand side's closures have been broken. Conversely, if the right-hand side is fully upheld, the left-hand side all comes up empty.

## 4. When "we don't know" is the correct conclusion

The clues in infrastructure investigation, this tool included, are mostly a mechanism for **picking up things that leaked carelessly**. A pre-introduction history, mail records, the IP a separate name points to, a combination on a certificate — each of these is born only when the operator's side has exposed something on the public-facing side.

So if there are no leaks, no candidates come out. That is neither a failure of the tool nor a shortcoming of the procedure. It is **one legitimate investigation result: "no clues within the passive scope."** In terms of Step 11's confidence levels, it corresponds to "unknown" — and being able to write "unknown" correctly is a far more valuable conclusion than lining up candidates with no grounds.

---

## 📚 Appendix A: Score table

The scores that were scattered through examples in the main text are collected here. All of them are points **per cluster**: even if domains do not directly share the same IP with each other, the points apply to the whole cluster connected through IPs.

**The IP-derived points (the four: non-cloud, cloud-only, same subnet, same ASN/Org) are awarded only when ipinfo information including `org` is available for every IP in the cluster.** If even one IP could not be retrieved, or has an empty `org`, no IP-derived points are awarded at all, and the reasons note "no IP-derived points." The header-derived points (Server, Cookie, X-Powered-By) are awarded regardless of this condition.

| Condition | Points | Notes |
|:--- |:--- |:--- |
| There is a non-cloud IP | +15 | Only when every IP's `org` is available (the condition above) |
| Cloud/CDN IPs only | +3 | Not awarded together with the above. Only when every IP's `org` is available |
| All IPs in the same subnet (/24 for IPv4, /48 for IPv6) | +8 | Only when every IP's `org` is available |
| All IPs in the same ASN/Org | +10 | Same as above. It is awarded for CDN IPs alone, so behind a CDN, do not use it as grounds |
| Server exact match, including a version | +15 | Only when comparing responses obtained from different IPs. Example: `nginx/1.18.0` |
| Server exact match (generic value) | +3 | Only when comparing responses obtained from different IPs. Example: a value with no version |
| Distinctive cookie name match | +30 | Only when comparing responses obtained from different IPs. Generic cookie names (next item) are **excluded** from the determination |
| X-Powered-By exact match, including a version | +8 | Only when comparing responses obtained from different IPs. A match without a version is 0 points |

- Examples of generic cookie names that are excluded: `PHPSESSID`, `JSESSIONID`, `sessionid`, `csrftoken`, names set by Cloudflare or AWS load balancers, and so on. This is because default values of frameworks and CDNs match between different people too.
- If fewer than 2 domains are available for header comparison, no header-derived points are awarded at all (the reasons note "cannot compare").
- The dynamic threshold: `max(40, the 65th percentile of the scores)`. If there is only one cluster, it is the larger of that cluster's own score and 40.

## ⚠️ Appendix B: Known limitations of the tool

To avoid misjudging, the tool's own limits are collected here. What follows are the limitations of the current tool.

1. **CT noise exclusion applies only to "names"**: It is a mechanism that drops names containing `cloudflaressl.com`, `sni.`, or `cloudflare-dns`; it is not a mechanism that excludes, by issuer, certificates themselves issued by a CDN provider. A certificate's issuer can be checked in `certificates` in `report.json`, but it is not used in the exclusion determination.
2. **The number of automatic probes**: The maximum of 30 is the number of (domain, IP) pairs; for each pair it tries https, and http if that fails, so connection attempts are up to 60. The same IP may also be selected repeatedly across several domains. At most 6 domains are taken from one cluster, and a cluster with only one domain is outside the scope of probing.
3. **Registered-domain determination uses a short built-in list**: Only some two-level suffixes, such as `co.jp` and `co.uk`, are treated specially. Under other shared suffixes, the registered-domain split can be off.
4. **Probing covers only "recent IPs"**: It does not connect to an IP whose last-observed time in passive DNS is older than `--recent-days` (default 90 days). An IP whose last-observed time could not be obtained (time 0) also ends up out of scope.
5. **Header matches are scored only between different IPs**: Points for a Server, cookie, or X-Powered-By match are awarded only when the match is between responses obtained from different IPs. In a cluster where every domain's response was obtained from a single IP, no points are awarded even if the values match, and the reasons state that. This is by design, so that a match answered by the same server is not double-counted as independent grounds.

## 🛠️ Appendix C: When things do not work

| What the screen or results look like | What may be going on | Next move |
|:--- |:--- |:--- |
| "CIRCL認証エラー: pDNSを無効化し…" appears (in English: "CIRCL authentication error: disabling passive DNS…") | The credentials were rejected with 401 or 403. From then on, only current DNS resolution is material | Check the credentials. If there is no hurry, treat the run as a no-credentials result, and note that in your notes |
| Passive DNS is in use, yet no candidate IPs come out | If passive DNS yields no public A/AAAA records, the tool falls back to current DNS resolution regardless of the reason. If nothing comes out even then, it means no public IP could be resolved in current DNS either | Look at whether names were retrieved from crt.sh. If they were not, record this as a run where the passive information was thin |
| "非公開/予約IPのため除外した解決結果がN件あります" appears (in English: "There are N resolution results excluded as non-public / reserved IPs") / the IP count becomes 0 | The resolver in your execution environment may be returning fake IPs (such as 198.18.x), and every resolution result was excluded. The number excluded is shown as a warning on the spot, and also remains in `dropped_non_global` in `report.json` | Treat that run's tool results as insufficient material, check the actual A/AAAA records separately via DoH (DNS over HTTPS) or the like, and use them as material for the candidate table |
| "crt.sh が 502。再試行します" appears (in English: "crt.sh returned 502. Retrying") / "CTログが取得できませんでした" appears (in English: "Could not retrieve CT logs") | crt.sh is busy, or temporarily returning errors. The tool automatically retries up to 3 times, with pauses in between | If a retry succeeds, proceed as-is. If it fails even after 3 tries, record that run as one without CT, and rerun after waiting a while |
| An ipinfo rate-limit message appears | Some IPs have become impossible to determine | Treat that run's grounds in the network category as weak, and lower the confidence of the conclusion |
| Clusters across multiple domains do not form | The target is connected only through shared CDN IPs, or candidate names could not be resolved | Do not judge by score; move on to Step 9's candidate table (timing, bare names, certificates) |
| All probe results have status 0 | Neither https nor http could connect. An old IP, filtering, or the wrong candidate | Return to the candidate table and check the timing criterion. Do not keep trying with different connection methods |
| The map becomes a large star shape | The typical shape when many names are connected to a shared CDN IP | Do not judge by appearance; return to the reasons in `report.json` |

---

---

## 🌸 Summary

The core idea is: **do not trust a single source of information; layer multiple independent grounds (history, certificates, configuration habits), reduce noise, and estimate how likely something is**.

The tool's job ends at surfacing candidates. From there, an investigation proceeds by narrowing candidates down by timing and source, verifying with the minimum of checks, and writing — with a confidence level attached — only what can actually be stated. Do not take the tool's output at face value; checking "why did this score come out?" and "is there another possible cause of a false positive?" is what leads to a high-quality investigation. It is not a failure for things to remain unknown; from observations made from outside, that is an ordinary result.

---

# Appendix: Full Source Code of the Tool

The full text of `tracker_v1.10.py` follows. The code is reproduced as-is; comments in the code are in Japanese.

```python
#!/usr/bin/env python3
"""
Multi-Layer Infra Tracker v1.10
pDNS + CT + HTTP Headers + ASN による関連性分析(防御・調査目的)

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
USER_AGENT = "InfraTracker/1.10"
CT_MAX_ATTEMPTS = 3            # v1.8: crt.sh への最大試行回数
CT_RETRY_WAITS = (5, 10)       # v1.8: crt.sh 再試行の待機秒 (試行の合間)
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
        try:
            res = self.pdns_session.get(f"{CIRCL_PDNS_URL}{indicator}", timeout=REQUEST_TIMEOUT)
            if res.status_code in (401, 403):
                with self._lock:
                    self.pdns_available = False
                    if not self._warned_pdns:
                        self._warned_pdns = True
                        print("  ⚠️  CIRCL認証エラー: pDNSを無効化し、現在のDNS解決へ切り替える")
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
        except requests.RequestException as e:
            print(f"  ⚠️  pDNS接続エラー ({indicator}): {e}")
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
                    entries = res.json()  # JSONでなければ ValueError → 再試行対象
                    reason = "想定外の応答"
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
                    cert_names = set()
                    for name in entry.get("name_value", "").split("\n"):
                        name = name.strip().lower()
                        if (name and not name.startswith("*")
                                and not any(n in name for n in CT_NOISE_SUBSTRINGS)):
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
    def draw_graph(self, filename="infra_map.png"):
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

    def save_report(self, scored, filename="report.json"):
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
        print(" 分析結果 (Relevance Scoring v1.10)")
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
    ap = argparse.ArgumentParser(description="Multi-Layer Infra Tracker v1.10")
    ap.add_argument("--domain", required=True, help="調査対象のドメイン")
    ap.add_argument("--user", help="CIRCL pDNS ユーザー名")
    ap.add_argument("--password", help="CIRCL pDNS パスワード")
    ap.add_argument("--recent-days", type=int, default=DEFAULT_RECENT_DAYS,
                    help="能動接続の対象とするIPの最終観測からの日数 (既定: 90)")
    ap.add_argument("--no-probe", action="store_true", help="HTTP接続を行わない(受動情報のみ)")
    args = ap.parse_args()

    InfraTracker(args.domain, args.user, args.password,
                 recent_days=args.recent_days, probe=not args.no_probe).run_analysis()
```
