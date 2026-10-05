# 参与证明 / Proof of participation

FAUST CTF 2026 · team **qiyu** · FAUST team number **980** · rank **67 / 502** · **10,752.81** pts

本文档回答一个问题：**如果以后有人要我证明"我确实参加了这场比赛"，我拿什么给他看？**

---

## 一句话结论

不要依赖任何单一来源。**最可靠的是"官方数据 + 独立第三方时间戳"这个组合** ——
而它现在已经被固化下来了（见下面的快照链接）。

---

## 证据链（按证明力排序）

### ① 官方原始数据 + 第三方时间戳 ← 最硬

主办方发布的**冻结记分板原始 JSON**，被 Internet Archive 独立存档：

```
https://web.archive.org/web/20261005161102id_/https://2026.faustctf.net/competition/scoreboard.json
快照时间：2026-10-05 16:11:02 UTC
```

里面可以查到：

```json
{"rank": 67, "id": 185, "name": "qiyu", "total": 10752.812338558753}
```

**为什么这条最硬**：数据出自主办方（不是我们自己写的），存档出自第三方（不是我们能改的），
两者叠加后**不依赖任何当事方的自述**。

**可复核性**：本仓库 `data/scoreboard-full.json` 与上述存档副本**字节完全相同**：

```
SHA256  673b0b475c6a07928f8645ce437a3c74c9bb129b8d7d23588c0a9d7f8433c98f
大小    366,467 B
```

也就是说：任何人下载存档 → 算 SHA256 → 与上面的值比对 → 就能确认
"这个仓库里的数据没有被事后篡改"。

### ② CTFtime 官方记录

```
Event 快照   https://web.archive.org/web/20260929080911/https://ctftime.org/event/3312
Team  快照   https://web.archive.org/web/20261005160954/https://ctftime.org/team/449998
队号 页面    https://ctftime.org/team/449998   （event id 3312）
```

队伍页上写明：**FAUST CTF 2026 · Place 67 · CTF Points 10752.8123 · Rating 15.167**。

### ③ 队伍成员关联 ← **目前缺这一环**

CTFtime 上队伍 `qiyu` 的 "Team members" **现在一个成员都没有**：

> There is no registered members of this team. Click on "I'm in the team" - be the first.

这意味着第 ① ② 条证明的是**队伍**拿到了第 67 名，但**没有任何公开记录把"队伍"和"某个自然人"连起来**。

**这是整条证据链上唯一的缺口**，而且只能由你自己补：

1. 登录 <https://ctftime.org/>
2. 打开 <https://ctftime.org/team/449998>
3. 点 **"I'm in the team"**
4. 然后重新跑 `archive-evidence.ps1`，把带成员名单的页面再存一次

> ⚠ 要说清楚：CTFtime 的加入是**自述性**的（点一下就加入，不验证）。
> 所以它把"人 ↔ 队伍"连了起来，但强度**低于**第 ① ② 条。这是社区惯例，不是身份认证。

### ④ 自己的公开产出

**推荐引用"内容固定"的快照**（commit 不可变，快照永不过期）：

```
仓库树   https://web.archive.org/web/20261005162246/https://github.com/nnn493368-max/faust-ctf-2026-writeups/tree/65e44ebe81a83cb08eb3fb858740ee056a747ee3
本文档   https://web.archive.org/web/20261005162322/https://github.com/nnn493368-max/faust-ctf-2026-writeups/blob/65e44ebe81a83cb08eb3fb858740ee056a747ee3/EVIDENCE.md
仓库     https://github.com/nnn493368-max/faust-ctf-2026-writeups
```

三篇 writeup（IMC 三漏洞链 / Lamp TeX 头注入 / Rufflecopter AVM2 逆向）+ 能跑的 exploit 代码。

**它证明什么**：你**不是旁观者** —— 这些技术细节必须真的打过、读过源码/字节码才写得出来，
而且代码是可复现、可复核的。提交时间戳也在。

**它证明不了什么**：单靠一个仓库，无法排除"别人写完挂你名下"。所以它是**佐证**，不是主证。

> **为什么引用 commit URL 而不是分支 URL**：分支（`/tree/main`）的内容会随每次 push 变化，
> 而 Internet Archive 对同一 URL 有**去重窗口** —— 短时间内不会重抓，于是"分支快照"永远
> 落后一两个提交。commit URL 的内容是不可变的，不存在这个问题。
> 实测过：push 之后立刻重存 `/tree/main`，返回的仍是 push 之前的旧快照。

### ⑤ 主办方注册记录 ← 需要时去找

FAUST CTF 的报名是以**队伍名 + 密码**做的（我方 = 队号 980），主办方手里有注册时的邮箱记录。
如果需要**权威的个人关联**，这是唯一途径：

```
orga@faustctf.net
```

> ⚠ 我没有你的报名邮箱，这条得你自己核。写信时直接说明队号 980 / 队名 qiyu，
> 请求确认注册信息即可 —— 比赛已结束，这类请求是合理的。

---

## 这些东西会一直留着吗？

诚实回答：**没有"永远"这回事**，不同来源的寿命差很多。

| 来源 | 预期寿命 | 说明 |
|---|---|---|
| **Internet Archive 快照** | 很长 | 第三方，独立于主办方和我们；已存的快照基本不会消失。**这就是我现在抢先做快照的原因** |
| CTFtime | 长，但无承诺 | 2012 年运营至今，历史成绩一般长期保留；但它是志愿者站点，没有 SLA |
| GitHub 仓库 | 长 | 只要账号在就一直在；也可随时 clone 到本地/别处 |
| **官方站 `2026.faustctf.net`** | **通常赛后一段时间会下线** | ⚠ **不要依赖它**。现在还是 200，但从现在起就要假设它会消失 |
| 本地 PDF / JSON | 取决于你的备份 | 自持，最可控但最容易被自己弄丢 |

**结论**：官方站是最可能先消失的，而它恰恰是原始数据来源 —— 所以
**"趁它还在，把数据抓下来 + 提交给第三方存档"这件事，越早做越值**。已经做完了。

---

## 怎么用这份文档

有人问"你怎么证明参加过"，就发他这一段：

> FAUST CTF 2026，队伍 qiyu（FAUST 队号 980），第 67 / 502 名，总分 10,752.81。
> 官方冻结数据的第三方存档：<快照链接>；CTFtime 记录：<team/449998>；
> 我发布的赛后技术分析：<仓库>。

**顺序很重要 —— 先给第三方存档，再给自己的东西。** 先给自述性材料会削弱可信度。

---

## 待办

- [ ] **加入 CTFtime 队伍 449998**（补上"人 ↔ 队伍"这一环）
- [ ] 跑 `archive-evidence.ps1` 重新存档，让成员名单进快照
- [ ] （可选）把本仓库 clone 到第二块硬盘 / 私有备份
- [ ] （可选，需要权威个人证明时）邮件联系 orga@faustctf.net

---

## 维护记录

| 日期 | 动作 |
|---|---|
| 2026-10-05 | 首次固化：存档官方 scoreboard.json、CTFtime 队伍页、本仓库页；核对本地副本与存档字节一致 |
