# Rufflecopter — reversing an AVM2 "HTTP server" inside a Flash emulator

**FAUST CTF 2026 · Attack/Defense · service `rufflecopter` (tcp/35244) · Rust + Ruffle + PostgREST**

> Team **qiyu** (FAUST team number 980). This is the hardest target of the four and the one
> where we produced the **most understanding and the least score** (0 offense points).
> The negative result is the interesting part, and it is stated honestly in §9.

---

## English abstract

`rufflecopter` is a Rust HTTP server that embeds **Ruffle** (a Flash emulator) and runs a
single SWF, `server.swf`. Inside that SWF is, of all things, **an HTTP server written in
ActionScript 3** that routes requests to a PostgREST instance on the internal Docker network.
Reversing it therefore meant reversing AVM2 bytecode, not x86.

We built a small AVM2 disassembler and worked from the bytecode. Findings:

1. **Routing is 2-D proximity collision, not a table lookup.** Every frame,
   `travel()` calls `testPlanet(planet)` for each planet:

   ```
   dx = Spaceship.x - planet.x ;  dy = Spaceship.y - planet.y
   r1 = Spaceship.width / 4 * 0   = 0          ← identically zero
   r2 = planet.width / 2 + 1      = 8.5 px
   if (dx*dx + dy*dy) < r2*r2:
       if name not in hits:
           hits.push(name); Spaceship.x = planet.x; Spaceship.y = planet.y
           Spaceship.fuel = 100; dispatchEvent("hitstart")   ← the only gate lives here
   ```

   The requested `(method, path)` pair is turned into a **flight angle**; the ship flies and
   whichever planet it collides with decides the handler. `r1` is dead code multiplied by
   zero, so collision depends purely on the planet's own radius.

2. **The gate is a planet, not a middleware.** `method 22 handle_check_planet_hit` is the
   *only* authentication gate; `method 23 handle_site_planet_hit` (which serves `/receipts`)
   performs **no authorization of its own**. Reach the site planet without touching a check
   planet and the session check is simply bypassed.

3. **`receiptcode` is a three-plane QR steganogram, fully decoded.** The receipt is a
   percent-encoded BMP built by XOR-adding three QR codes into a blank base image:

   ```
   image = qr_base_image                       # 4698-byte percent-encoded BMP
   qrencode_add(image, 1, qrencode(DATES))     # bit 0
   qrencode_add(image, 2, qrencode(PILOT))     # bit 1
   qrencode_add(image, 4, qrencode(COMMENTS))  # bit 2  ← the flag lives here

   qrencode_add(image, bit, stream):
       for i in range(1079):
           if (stream[i >> 3] >> (7 - i % 8)) & 1:
               image[Q[i]] ^= bit
   ```

   So `(receiptcode[p] ^ BASE[p]) & 7` yields all three planes at once, and because writes
   are sequential with **no QR zigzag interleaving** there is no Reed–Solomon to run — plain
   string arithmetic suffices. We recovered the 1079 module indices `Q` and the 4698-byte
   base image, and validated the index set by set-subtraction against 60 observed samples.
   The checker plants the flag in the `comments` field of `POST /rent`.

4. **The 50 planet coordinates are not where you would look for them.** They are not in the
   ABC constant pool and not in any method body — they live in **`PlaceObject3` transform
   matrices on the SWF main timeline.** Every planet's bounding box is 2560×2560 twips
   (128×128 px).

5. **A 42-px gap exists, and it is enough to skip the gate.** At column `x = 195`,
   `check_0` covers `y ∈ [140.0, 157.0]` and `check_1` covers `y ∈ [199.0, 216.0]`, leaving a
   traversable corridor `y ∈ (157.0, 199.0)` — **42.0 px wide**. From the ship's start
   `(10.0, 166.9)` any heading between **−3.1° and +9.8°** threads it.

6. **Two gate-bypassing routes were found by an exhaustive trajectory simulator** — and
   neither of them can read the flag:

   | method | path | trajectory |
   |---|---|---|
   | **POST** | **`/login`** | `method_0 → location_1 → version_9 → header_9 → content_9 → post_login` |
   | **POST** | **`/register`** | `method_0 → location_1 → version_10 → header_10 → content_10 → post_register` |

   `method 18 handle_location_planet_hit` is a hard-coded **(path → angle) table**, and
   `/receipts` is pinned to **60°**. From `location_1 (70, 227.5)` that heading immediately
   flies off the planet grid (max `y` is 247.5) and never reaches the site column, fuel or not.

**Final conclusion.** There is no cross-user read primitive — but **not** for the reason we
first believed. It is not that you must pass the gate. It is that **the path is used both to
select the page to render and to select the flight angle, and the same table binds the two**.
The combinations that bypass the gate (`/login`, `/register`) are exactly the public pages that
need no session; the one that needs a session (`/receipts`) is exactly the one whose angle is
unusable. That is a designed duality, not a coincidence.

---

## 1. 服务形态

```
Rust HTTP server (tcp/35244)  →  内嵌 Ruffle (Flash 模拟器)  →  server.swf
                                                              ↓
                                                    PostgREST (http://postgrest:3000)
                                                    （仅 Docker 内网可达）
```

**这就是这道题的题眼**：不是"Rust 服务 + 一个 Flash 前端"，而是
**整个 HTTP 服务端逻辑都写在 SWF 里**。Rust 只做两件事：跑模拟器、把请求喂进去。

所以常规 Web 套路（翻 JS、找路由表、看框架中间件）全部失效 ——
**只能读 ActionScript 3 编译出的 AVM2 字节码**。

### 路由清单

```
/  /index.html  /garage  /login  /register  /logout  /rent  /receipts  /favicon.ico
```

---

## 2. 方法论：自写 AVM2 反汇编器

现成工具对这道题帮助有限（SWF 里的 ABC 块需要自己定位、method body 与静态 trait 要分开处理），
所以我们写了一个 AVM2 反汇编器（见 [`exploits/`](../exploits/) 里的工具链记录）。

**踩到的第一个坑**：第一版只 dump 了 method body，结果星球坐标死活找不到。
原因是**类级静态变量（trait）不在任何方法体里** —— 它们挂在 `InstanceInfo` / `ClassInfo`
的 trait 列表上。

> 教训：AVM2 里"代码"和"数据"是两套结构。只反汇编方法体会漏掉全部静态数据。

---

## 3. 路由机制 = 2D 空间邻近碰撞

从 `travel()` 和 `testPlanet()` 逆出的完整逻辑：

```
travel():  每帧 for each planet in this.planets: testPlanet(planet)

testPlanet(planet):
    dx = Spaceship.x - planet.x
    dy = Spaceship.y - planet.y
    r1 = Spaceship.width / 4 * 0          ← 恒等于 0（死代码）
    r2 = planet.width / 2 + 1 = 8.5px
    if (dx*dx + dy*dy) < r2*r2:
        if planet.name not in hits:
            hits.push(planet.name)
            Spaceship.x = planet.x        ← 瞬移到星球圆心
            Spaceship.y = planet.y
            Spaceship.fuel = 100
            dispatchEvent("hitstart")     ← 门禁只在这里触发
        else:
            dispatchEvent("hitcontinue")
    else:
        if planet.name in hits:
            hits.remove(planet.name)
            dispatchEvent("hitend")
```

三个要点：

1. **`r1 = Spaceship.width/4*0` 恒为 0** —— 一个看似要做圆-圆碰撞的半径项被乘了 0。
   碰撞完全由 `r2 = planet.width/2 + 1 = 8.5px` 决定。
2. **命中后飞船瞬移到星球圆心**，这决定了航线是"圆心→圆心"的**多段折线**，
   不是一条直线 —— 后面算弹道时必须按分段重算。
3. **`hitstart` 只在首次进入某星球时派发**（`hits` 数组去重），
   门禁挂在这个事件上。

---

## 4. 门禁的真实位置

| method | 名字 | 作用 |
|---|---|---|
| 18 | `handle_location_planet_hit` | **路径 → 角度** 表（决定往哪飞） |
| 22 | `handle_check_planet_hit` | **唯一的鉴权门禁** |
| 23 | `handle_site_planet_hit` | 渲染站点页（`/receipts`），**自身没有任何鉴权** |

**这是本题最重要的一个反直觉结论**：

> 鉴权不在 `/receipts` 这个**处理器**里，而在**到达它的航线上**。

也就是说，"能不能读 receipts"被建模成了"飞船能不能飞到这个星球"，而不是
"这个 handler 有没有检查 session"。**把授权编码进几何路径** —— 从设计角度这很妙，
但它也意味着**只要找到一条绕过 check 星球的航线，授权就被整个跳过了**。

---

## 5. `receiptcode` 解码器：三平面 QR 隐写

`GET /receipts` 会渲染 pilot 名、日期，以及原始的 `receiptcode`
（一个百分号编码的 BMP）。从 SWF 的 method 50（receipt 构造函数）逆出机制：

```
image = qr_base_image                       # 4698 字节：空白 BMP 的百分号编码字符串
qrencode_add(image, 1, qrencode(载荷A))     # 低 3 位的 bit0
qrencode_add(image, 2, qrencode(载荷B))     # bit1
qrencode_add(image, 4, qrencode(载荷C))     # bit2

qrencode_add(image, bit, stream):
    for i in range(1079):
        if (stream[i >> 3] >> (7 - i % 8)) & 1:
            image[Q[i]] ^= bit
```

**三个 QR 码被按位叠加进同一张图**：`1 / 2 / 4` 是三个不相交的位平面。

于是解码极其干净：

```python
d = [(ord(receiptcode[p]) ^ ord(BASE[p])) & 7 for p in Q]   # 一次拿到三个平面
bits_plane_k = [(v >> k) & 1 for v in d][4:]                # 跳过 4 位 mode 头
text = pack_msb_first(bits_plane_k)
```

### 三个工程要点

**① 不需要跑 Reed-Solomon。**
`qrencode_add` 是**按序逐位写入**、没有 QR 标准的 zigzag 交织，
所以位流直接就是数据 —— 纯 Python 字符串运算即可，不需要完整 QR 解码器。

**② 1079 个模块下标 `Q` 是逆出来的，并用集合运算自证。**
拿 60 个真实样本，取"变化位置的集合"，减去我们恢复的下标集合 —— 差集为空。
**这是可验证的推导，不是拟合。**

**③ 4698 字节的 `qr_base_image` 在 SWF 偏移 103623。**
它是一张空白 BMP 的百分号编码形式，直接内嵌在 SWF 里。

### 三个平面各是什么

| 平面 | bit | 内容 |
|---|---|---|
| A | 1 | 起止日期 |
| B | 2 | pilot 名 |
| C | 4 | **`comments` ← checker 把 flag 放这里** |

**checker 把 flag 种在 `POST /rent` 的 `comments` 字段**，所以旗子就在"属于某个
每轮随机用户名"的那条 rent 的 receipt 图里。

解码器已完整交付并验证：[`exploits/_receipt_decode.py`](../exploits/_receipt_decode.py)
（自包含：内嵌 1079 个下标 + 4698 字节 base）。

---

## 6. 50 个星球坐标藏在哪

**不在 ABC 常量池，也不在任何方法体里。**

它们在 **SWF 主时间轴的 `PlaceObject3` 变换矩阵**里 —— 也就是说，
星球的"位置"是 Flash 显示列表的**布局数据**，不是 ActionScript 的**代码数据**。

每个星球的包围盒都是 **2560×2560 twips = 128×128 px**（twips = 1/20 px）。

> 这是第二个方法论教训：**SWF 里"程序状态"可以存在于时间轴/显示列表里。**
> 只读 ABC 块会永远找不到这些常量。

---

## 7. 几何结论：存在一条 42px 的缝隙

用真实坐标算出每个 check 星球的覆盖区间后：

```
x = 195 这一列上：
    check_0 覆盖 y ∈ [140.0, 157.0]
    check_1 覆盖 y ∈ [199.0, 216.0]
    → 可穿行缝隙 y ∈ (157.0, 199.0)，宽 42.0px

飞船起点 (10.0, 166.9)
→ 角度落在 −3.1° ~ +9.8° 即可穿过
```

**门禁在几何上是可绕的** —— 这直接推翻了我们早期"必须经过 check 星球"的假设。

---

## 8. 弹道模拟器：找到两条绕过门禁的航线

因为航线是**多段折线**（每撞一个星球就瞬移到其圆心、后续处理器会改写角度），
直线推导不够用。我们把全部运动学常量写成一个模拟器
（按 SWF 每帧 10px 步进、含穿透效应），穷举 `(method, path)` 组合，得到两条
**完全不经过任何 check 星球**的航线：

| method | path | 命中序列 | 目标星球 |
|---|---|---|---|
| **POST** | **`/login`** | `method_0 → location_1 → version_9 → header_9 → content_9` | `planet_post_login` |
| **POST** | **`/register`** | `method_0 → location_1 → version_10 → header_10 → content_10` | `planet_post_register` |

**两条都成功绕过了 `handle_check_planet_hit`。**

---

## 9. 为什么最终仍然读不到旗子（诚实的否定结论）

这两条航线到达的是 `planet_post_login` / `planet_post_register`，
**而我们要的是 `/receipts`。**

问题出在 `method 18 handle_location_planet_hit` —— 那张 **路径 → 角度** 表：

> **`/receipts` 被硬编码映射到 60°。**

从 `location_1 (70, 227.5)` 沿 60° 出发，飞船**立刻飞出星球网格**
（网格最大 `y = 247.5`），燃料耗尽也够不到 site 列。

### 核心结论

> **路径既是"渲染哪个页面"的输入，又是"用哪个角度飞"的输入，两者被同一张表绑死。**

能绕门禁的组合（`/login`、`/register`）恰好都是**不需要 session 的公开页面**；
需要 session 的 `/receipts` 恰好角度不可用。

**这个对偶是设计出来的，不是巧合。**

### 我们修正了自己的结论

我们**早期**的结论是"无跨用户读取原语，因为必须经过 check 星球"。
**这个理由后来被我们自己的几何分析推翻了**（42px 缝隙 + 两条绕过航线）。

**最终结论仍然成立，但理由完全不同**：不是"必经门禁"，而是**"路径与角度绑定"**。

> 我特意保留这个修正过程，因为它比结论本身更有价值：
> **一个正确的结论配一个错误的理由，等于没有理解。**

### 顺便否掉的常规套路

| 尝试 | 结果 |
|---|---|
| PostgREST 操作符注入（`?user=eq.` 之类） | ❌ SWF 的 `sanitize()` 只保留 `[0-9A-Za-z_]` |
| IDOR（拿别人的 user cookie 读 receipts） | ❌ session 门禁比对的是 **cookie 原始值**与 DB 行，必须有合法 `(token, user)` 对 |
| 直接构造请求跳过飞行 | ❌ 路由就是飞行本身，没有旁路 |

---

## 10. 设计启示（我认为这才是这道题最值得带走的东西）

这道题做了一个很聪明的设计实验：**把授权决策编码进空间几何**，而不是写成中间件。

- **优点**：攻击者不能靠"找漏掉鉴权的 handler"来突破 —— 因为鉴权根本不在 handler 里。
  我们花了很久才意识到该去打**航线**而不是打**路由**。
- **代价**：授权一旦依赖几何，就退化成**导航问题**；而几何是可以用数学穷举的。
  42px 的缝隙就是穷举出来的。
- **真正的兜底**：最后真正救场的不是门禁，而是**"路径与角度共用一张表"这个耦合** ——
  它让"能绕过的"和"有用的"两个集合不相交。

**但这是一种脆弱的、事后看来才成立的安全性。** 如果哪位出题人多给一条
`(POST, /receipts)` 的角度映射，或者把 `/receipts` 的 60° 改成可用角度，
整道题当场崩塌 —— 而这个改动在几何上完全没有痕迹。

---

## 11. 修复建议（如果这是一个真实系统）

| # | 问题 | 修法 |
|---|---|---|
| 1 | 授权挂在"到达路径"而非处理器上 | 授权必须是**每个处理器自己的、默认拒绝的**属性；不要在导航层做访问控制 |
| 2 | `handle_site_planet_hit` 自身无鉴权 | `/(receipts)` 必须自己校验 session，不能依赖"到达它"隐含了检查 |
| 3 | `r1 = width/4*0` 死代码 | 无功能影响，但这类残留常量会让逆向者误判碰撞模型 —— 该删 |
| 4 | 路径同时驱动渲染与导航 | 解耦"选页面"与"算角度"，不要让一个输入承担两种安全语义 |
| 5 | `sanitize()` 是唯一防线 | 白名单方向正确，但它是**正确性**保证，不该被当作**授权**保证 |
| 6 | receipt 里三平面叠加 | 隐写不是加密。三平面叠加只是编码，`^3` 一次异或就全出来 —— 不要把它当成机密性措施 |

第 6 条特别值得说：**这个"隐写"不提供任何机密性**。
三平面共用低 3 位，逆运算是一行代码。它混淆的是"肉眼看图"，不是"攻击者读数据"。

---

## 12. 说明

- 本文结论全部来自**阅读 `server.swf` 的 AVM2 字节码**，没有靠猜。
- 逆向产物（完整反汇编、坐标 JSON）当时在比赛靶机上，**该靶机已于赛后清理**；
  但 `_receipt_decode.py` 是**自包含**的（内嵌 1079 个下标 + 4698 字节 base），
  不依赖任何被删文件即可复现解码。
- **这篇的服务我们没有拿到任何进攻分** —— 交付的是完整的逆向理解和一个
  可复现的否定结论。我认为这比含糊的"打不动"有价值。
- 比赛已于 2026-09-26 21:00 UTC 结束；本文按赛后 writeup 惯例公开。
