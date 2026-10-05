# FAUST CTF 2026 — writeups & exploits (team `qiyu`)

**Attack/Defense · 502 teams · 8 hours · 4 services · 2026-09-26**

| | |
|---|---|
| **Final rank** | **67 / 502** (top 13.3%, beat 86.7% of the field) |
| **Total score** | **10,752.81** |
| Offense | 6,737.16 |
| Defense | −5,069.72 |
| SLA | 9,085.37 |
| FAUST team number | **980** (used for the `fd66:666:980::2` addressing) |
| Scoreboard `id` | 185 (official `scoreboard.json` internal key — a *different* numbering; do not conflate) |
| CTFtime | [team/449998](https://ctftime.org/team/449998) · event [3312](https://ctftime.org/event/3312) |

This repository is the technical record of the four services we attacked. Everything in it
was derived by **reading the provided sources and bytecode**, not by fuzzing, and every
negative result is stated as a negative result.

> **Verifying these results:** [`EVIDENCE.md`](EVIDENCE.md) documents the full chain of
> evidence — the organizers' frozen `scoreboard.json` (with a third-party Internet Archive
> snapshot and a SHA256 anyone can check), the CTFtime record, and what each source does and
> does not prove. `archive-evidence.ps1` re-freezes those public pages on demand.
>
> **Short on time?** [`PORTFOLIO.md`](PORTFOLIO.md) ([PDF](PORTFOLIO.pdf)) is a two-minute
> summary of this work aimed at a reviewer: results, deliverables, the three technical
> highlights, and the engineering boundaries.

---

## The writeups

| Service | Topic | Score impact |
|---|---|---|
| **[IMC](writeups/imc.md)** | Three chained bugs → full cross-tenant flag read (SQLite double-quote fallback · `catch` without `return` · missing NULL guard) + a LIKE-pattern oracle | **6,726.31 / 6,737.16 of our offense (99.8%)** |
| **[Lamp](writeups/lamp.md)** | Unauthenticated arbitrary file read via TeX header macro injection (`Path:` overrides `\httpPath` **after** the traversal check) | 0 — verified primitive, no enumeration path |
| **[Rufflecopter](writeups/rufflecopter.md)** | Full AVM2 reverse of an HTTP server written in ActionScript: 2-D collision routing, a three-plane QR steganogram decoder, and why the gate bypass we found still can't read the flag | 0 — complete understanding, no primitive |

Each writeup is **full Chinese with an English abstract**.

### Bonus: Alf (1986, Flask) — heap leak primitive

Not written up in full, but the exploit ships in [`exploits/alf.py`](exploits/alf.py).

A custom `translate` library (`libparser.so`) expands `r` in place into `"rr"` and **forgets
the trailing NUL**, so the output constructor `sprintf(out+len, "%s%s", sep, node->buffer)`
reads past the buffer into an adjacent freed heap chunk. `POST /translate_text` needs no
authentication, so `base64("r.")` comes back as `base64("rr" + residual heap)` — an
unauthenticated heap disclosure. The substitution table is `t→d T→D p→b P→B k→g K→G r→rr`,
which makes the leak invertible enough to reconstruct exact flags locally.

The reason this service scored almost nothing for us (10.8 pts) is a targeting problem rather
than a bug problem: **Alf's `flag_id` is `User.id`, not `Translation.id`** — all 12 published
flag ids resolved to rows in the `user` table and none in `translation`, and the service has no
route that queries by translation id. So the checker must validate by reading
`/translation_history` as that user, which we never managed to do at scale.

---

## Repository layout

```
writeups/        imc.md · lamp.md · rufflecopter.md          (中文全文 + English abstract)
exploits/        imc.py · lamp.py · rufflecopter.py · alf.py
                 _receipt_decode.py                          (self-contained Rufflecopter decoder)
data/            scoreboard-full.json · scoreboard-full.csv   (official final snapshot, tick 159)
```

`exploits/*.py` are the actual modules that ran, with the farm passing each one a target
address and the officially published flag ids. They share a tiny interface:

```python
NAME  = "imc"                 # service name
PORTS = [8080]                # port on the target
def run(target, flag_ids, timeout) -> list[str]:   # returns FAUST_... tokens
```

`data/` is the organizers' own public final snapshot (`/competition/scoreboard.json`), kept
here so the numbers in these writeups stay checkable. Note the team-number caveat above.

---

## Attack/Defense context

A few things that shaped every decision above, in case you are reading this as a
first Attack/Defense post-mortem:

- **One WireGuard peer per team.** The tunnel to the game network can only be held by one
  machine at a time, so every exploit in this repo runs *from the vulnbox itself*. Bringing up
  a second tunnel would have taken all four of our own services off the network.
- **Flags expire.** They are valid for 5 ticks (a tick is 3 minutes), so firing stale flags at
  the submission server just burns submissions. `teams.json` publishes the *current*
  flag-store ids per team, and the IMC exploit uses that as a fast path instead of scanning.
- **Rounds have to fit inside a tick.** Our first orchestrator settings took 357–380 s per
  round, which is longer than a tick — we could never catch up. Going from 8 to 24 workers
  brought a round to 127–132 s and tripled the unique-flag rate (6.0/min → 18.8/min).
- **SLA is not free.** Dropping a service costs more than most flags are worth; we lost ~270
  SLA to a stale `docker-proxy` forward and had to add a watchdog that restarts containers
  when the game address stops answering.

---

## 中文说明

本仓库是 `qiyu` 队在 FAUST CTF 2026（Attack/Defense，502 支队）中对四个服务的技术记录。
**所有结论都来自阅读比赛提供的源码/字节码，不是黑盒爆破**；所有否定结论都如实写成否定结论。

三篇 writeup 均为**中文全文 + English abstract**：

- **IMC** —— 三个漏洞串联成完整的跨租户读旗原语。这也是我们 6,737.16 进攻分里 **6,726.31 分的来源（99.8%）**。
  三个 bug 分别是：SQLite 双引号标识符回退（`SET crew = "age"` 实际是列引用）、
  `update.neko` 的 `catch` 缺 `return`（邀请校验被穿透）、
  `fetch.neko` 的 SPACESHIP 过滤缺 `null` 守卫（`null == null` 为真，一条 FETCH 拿走全部旗船）。
  另有一个基于 `LIKE` 未转义 `_` 的差分预言机用于低成本枚举。
- **Lamp** —— 无认证任意文件读取。请求头名会被用来定义宏，于是 `Path:` 覆盖了内部
  `\httpPath`；而 `..` 检查跑在解析请求头**之前**，只作用于请求行，检查的是"稍后会被覆盖的值"。
  原语在真实靶机上验证成功，但 checker 用户名是每队随机的 16 位 hex，
  四条枚举路径全部证伪（其中 NUL 截断会打崩服务，**我们主动放弃**）。
- **Rufflecopter** —— 完整的 AVM2 逆向。这个服务的 HTTP 服务端逻辑整个写在 SWF 里，
  路由机制是"飞船 2D 邻近碰撞星球"，鉴权是其中一个星球而不是中间件。
  我们做出了三平面 QR 叠加的 receipt 解码器、50 个星球坐标（藏在 SWF 主时间轴而非 ABC 常量池）、
  并用弹道模拟器找到两条绕过门禁的航线 —— **但最终仍读不到旗子**，
  因为路径同时驱动"渲染哪个页面"和"用哪个角度飞"，`/receipts` 被硬编码在 60°。
  **这篇没有拿到任何分数，交付的是一个可复现的否定结论。**

另附 **Alf** 的堆泄露原语（代码见 `exploits/alf.py`，未单独成文）。

---

## License

Code: MIT ([`LICENSE`](LICENSE)). Writeups / prose: CC BY 4.0.

The challenge services, their sources and the flag format belong to the FAUST CTF
organizers (FAU Security Team, Friedrich-Alexander-Universität Erlangen-Nürnberg).
No other team's private data, credentials or keys appear anywhere in this repository.
