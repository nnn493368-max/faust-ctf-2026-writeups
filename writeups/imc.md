# IMC — Interstellar Mission Control

**FAUST CTF 2026 · Attack/Defense · service `imc` (tcp/8080) · NekoVM + SQLite**

> Team **qiyu** (FAUST team number 980) — rank 67 / 502, 10,752.8 pts.
> This service produced **6,726 of our 6,737 offense points (99.8%)**.

---

## English abstract

`imc` is a NekoVM service speaking a raw line protocol on tcp/8080. It keeps its state in a
single SQLite database opened `STRICT` and builds every statement by string concatenation.

We recovered three defects from the `.neko` sources and chained them into a full
cross-tenant flag-read primitive. **No brute force and no fuzzing was involved** — all three
were read out of the code.

1. **SQLite double-quoted-token fallback.** `db.neko:updateById()` emits
   `UPDATE <table> SET <attr> = "<val>" WHERE id = <int>`. SQLite resolves a double-quoted
   token that happens to name a column of the target table as a **column reference**
   (its legacy MySQL-compatibility behaviour). `SET crew = "age"` therefore compiles to
   `crew = age`.

2. **Missing `return` in a `catch` block.** `update.neko`'s `BEINGS.crew` path is supposed to
   require an invitation. Passing the literal token `age` makes `$int("age") == 0`; there is no
   `CREWS` row 0, so reading `crew.invited` throws. The handler reports the error and then
   **falls through** to the update it was guarding.

Together, (1) + (2) let one single `UPDATE` descriptor set `BEINGS.age = N` *and*
`BEINGS.crew = "age"` (i.e. `crew = age = N`) in one shot, giving us **any crew id we want**
without an invitation. Because `STRICT` typing is satisfied by the integer column value, the
type system does not save the service here.

3. **Missing NULL guard in a fetch filter.** `fetch.neko`'s SPACESHIP filter is
   `being.crew == row.crew || being.id == row.janitor`, while the equivalent predicate in
   `update.neko` correctly starts with `being.crew != null`. Neko evaluates `null == null` as
   true, so a freshly created being (`crew IS NULL`) matches **every crew-less spaceship** —
   which is exactly how the checker plants its flag ships.

We also found a cheap **boolean oracle** to avoid brute forcing ids: `fetch.neko` answers
`RVJS|0|Not found` when the generated `WHERE` clause matched nothing, but returns a normal
`FETCH` message (carrying only the identity header) when rows *did* match and were then
rejected by the Neko filter. Since descriptor values become `<col> LIKE "<value>"` predicates
and `_` is an unescaped LIKE wildcard that the input whitelist happens to allow, that
difference is a **fixed-length pattern oracle**, so flag-bearing crew ids are enumerated
digit by digit.

Finally, `teams.json` publishes the live flag-store ids per team, so the production exploit
takes a fast path that targets the current flags directly instead of scanning for them.

**Impact:** reading `CREWS.equipment` and `SPACESHIPS.resources` for arbitrary tenants.
**Fix:** bind parameters instead of interpolating; add the missing `return`; add the missing
`!= null` guard; escape `%`/`_` in LIKE operands.

---

## 1. 服务形态

```
socat -6 tcp-l:8080,fork EXEC:"neko imc.n => 每个连接 fork 一个全新 NekoVM
```

`imc.neko` 全文只有 15 行，结构极简：

```neko
var stdin = file_stdin();
db.initDB()                                  // ← 每个连接都跑一次
$print("Welcome to Interstellar Mission Controll v67\n");   // 注意原文的拼写错误
while($not(file_eof(stdin))){
	parser.handleRequest();
}
```

**这一点对利用工程有直接影响**：`initDB()` 里有五条
`DELETE FROM <表> WHERE timestamp < unixepoch()-1200`（`db.neko:59-72`），
每个新连接都会重跑一遍并对同一个 SQLite 库加写锁。所以**多开连接是在替目标制造额外负载**，
规范的打法是**单连接复用到底**。

### 线路协议

请求（`mode` 必须是 `REQUEST`）：

```
TVNI|<num_lines>|<type>|<time>|<subject>|<mode>|
<num_lines> 行 payload，\n 分隔
```

payload 里两种记录：

| tag | 含义 |
|---|---|
| `SURI\|<id>\|<name>\|<auth>` | 身份 |
| `QkRS` | being（8 列） |
| `Q0RS` | crew（6 列） |
| `TVNE` | mission（9 列） |
| `U0RS` | spaceship（11 列） |

成功响应：`TVNI|<n>|FETCH|<date>|<subject>|RESPONSE|` + n 行。
错误响应走 `responder.sendMessage`：**`TVNI|<n>||<date>||RESPONSE|`** —— 注意
`type` 与 `subject` **两个字段是空的**，这正是后面那个预言机赖以区分成功/失败的特征。

`<date>` 用 `^%m^^%H^^%d^^%M^^%Y^` 格式化，所以字段里天然带 `^` 分隔符 ——
这也解释了为什么 `checkInput` 的白名单里会有 `^`（见下）。

### 输入白名单

`db.neko:11-24` 的 `checkInput()` 只允许：

```
[0-9A-Za-z]  /  _  +  空格  ^
```

**关键：它允许 `_`，但不允许 `%`、`"`、`'`、`-`。**

- 不允许 `"` → 没法闭合 `updateById` 里的双引号字符串（正面防住了经典 SQLi）
- 不允许 `%` → LIKE 里做不了"任意长度通配"
- **允许 `_`** → LIKE 的**单字符**通配符可用

这三条约束的净效果是：经典 SQLi 被堵死，但**定长模式匹配**是可行的。这就是预言机的基础。

---

## 2. 漏洞一：SQLite 双引号标识符回退

`db.neko:168-181`：

```neko
var updateById = function(table, id, attr, nval){
	var amalg = table+id+attr+nval;
	if($not(isColumnOf(table, attr))) return -1;     // attr 必须是真实列名
	if($not(checkInput(amalg))) return -2;           // 白名单过滤
	var sql = "UPDATE " + table + " SET " + attr + " = \"" + nval + "\" WHERE id = " + $int(id) + ";";
	...
}
```

`attr` 被 `isColumnOf` 限制成真实列名，`nval` 被白名单挡住引号 —— 表面看无懈可击。

**问题出在 SQLite 的一个兼容性行为上。** SQLite 为了兼容 MySQL 的坏习惯，
允许用**双引号**包裹字符串；但当一个双引号 token **恰好是当前查询里某个表的列名**时，
SQLite 会把它**优先解析为列引用**而不是字符串。所以：

```sql
UPDATE BEINGS SET crew = "age" WHERE id = 42;
-- 实际语义：crew = age     （列引用！）
```

这不是转义问题，是**语义歧义**：开发者以为在写字符串常量，数据库理解成了列引用。

**为什么这条特别致命**：`BEINGS` 是 `STRICT` 表，`crew INTEGER`。如果攻击者直接传
`crew = "age"` 当字符串，STRICT 会拒绝（`cannot store TEXT value in INTEGER column`）。
但经由双引号回退，实际赋值是**同行 `age` 列的整数值**，类型完全合法。**类型系统在这里帮不上忙，
反而因为"值是个合法整数"而放行。**

---

## 3. 漏洞二：`catch` 缺 `return`，邀请校验被穿透

`update.neko` 的 `UPDATE_SPEC`（`update.neko:9-26`）里，四个 subject 各自的授权谓词：

```neko
CREW =>      { ..., auth => function(being, row) {return being.id==row.captain}},
MISSION =>   { ..., auth => function(being, row) {return being.id==row.overseer || being.id==row.sponsor}},
SPACESHIP => { ..., auth => function(being, row) {return (being.crew!=null && being.crew==row.crew) || being.id == row.janitor}}
```

注意 SPACESHIP 这一行**有** `being.crew != null &&` 守卫 —— 记住这个对比，漏洞三就出在它对面。

然后 `update.neko:106-126` 是 `BEINGS.crew` 的加入团队校验：

```neko
if(spec.table == "BEINGS" && cols[i] == "crew"){
    try {
        var crew = db.getById("CREWS", $int(v));            // v = "age" → $int("age") == 0
        if($not(utils.strListContains(crew.invited, id))){  // crew 是 null → 读 .invited 抛异常
                resp.sendMessage(...); return -1;
        }
        var new_invites = utils.removeFromStrList(crew.invited, id);
        if((db.updateById("CREWS", $int(v), "invited", new_invites)) < 0) { ... }
    } catch e {
        resp.sendMessage(resp.addErrorMessage(null, 1, "Unable to join crew!"));
        /* ←←← 这里没有 return */
    }
}
if((db.updateById(spec.table, id, cols[i], v)) < 0) { ... }   // ← 异常后照样走到这
```

链条：

1. 攻击者把新 `crew` 值填成字面量 `age`
2. `$int("age") == 0`（Neko 的 `$int` 对非数字返回 0）
3. `db.getById("CREWS", 0)` 找不到 id=0 的行 → 返回 `null`
4. 读 `crew.invited`（在 null 上取字段）→ **抛异常**
5. 进 `catch`，发一条 `RVJS` 错误消息 —— **但没有 `return`**
6. 控制流**穿透**到第 123 行，执行它本该拦下的更新

**邀请校验被完全绕过**，而且攻击者还收到了两条消息（一条错误 + 一条成功），从响应里能直接看出穿透发生了。

---

## 4. 漏洞一 + 二 的组合：一条 descriptor 同时写两列

`update.neko:96-130` 按 `cols` 的**列顺序**遍历 descriptor：

```neko
BEING cols => $array("id","name","age","remaining_lives","affiliation","crew","diseases","skills")
```

`descriptor[i+1]` 对应 `cols[i]`，非空就更新一次 --- 也就是**一条 UPDATE 可以连续改多列**，
且 `age` 排在 `crew` 前面。

于是（下表是 exploit 里真实的字段构造，注意 `QkRS` 后面一共 8 个字段对应 `cols` 的 8 列）：

```
索引:    [0]   [1]    [2]  [3]     [4]  [5]  [6]   [7]  [8]
        QkRS | <我的id> | | <目标N> | | | age | |
对应列:        id      name  age    remain aff  crew  dis  skills
```

执行顺序：

1. `cols[2] = age` ← `N` → `UPDATE BEINGS SET age = N`
2. `cols[5] = crew` ← `"age"` → 走上面那条穿透链 → `UPDATE BEINGS SET crew = "age"` → **`crew = age = N`**

**结果：`being.crew` 可以被设成任意整数 N，不需要任何邀请。**

而 `age` 本身在创建 being 时就是攻击者可控的（`addBeing` 把它不加引号地拼进 SQL），
所以这个 N 可以任选 —— 也就是**可以顶替任何一个 crew id**。

### 拿到旗子

`fetch.neko` 的 CREW 过滤是 `being.id==row.captain || being.crew==row.id`。
既然我们能把自己伪装成任意 crew 的成员，就能直接 FETCH 到该 crew 的完整行，
其中 **`CREWS.equipment` 就是 flag 所在字段**。

---

## 5. 漏洞三：`fetch.neko` 过滤缺判空 → 一条 FETCH 拿走全部旗船

`fetch.neko:8-21`：

```neko
SPACESHIP => { table => "SPACESHIPS", tag => "U0RS",
    cols => $array("id","name","location","fuel","max_speed","tuv","manufacturer","crew","resources","capacity", "janitor"),
    filter => function(being, row) {return being.crew==row.crew || being.id==row.janitor}}
```

对比 `update.neko:25` 的同款谓词 —— 那边是
`(being.crew!=null && being.crew==row.crew) || being.id == row.janitor`，
**`fetch.neko` 少了 `being.crew != null &&`**。

**Neko 里 `null == null` 为真。**

新建的 being `crew IS NULL`，而 checker 放 flag 的那些飞船同样是 `crew IS NULL`。
两边都是 null → 谓词成立 → **一次 FETCH 返回全部旗船**。

`fetch.neko` 还要求 descriptor 里非空的字段才进 WHERE（`fetch.neko:81-90`），
所以只要送一个**全空 descriptor**，WHERE 子句为空，SQL 就是无过滤的
`SELECT <cols> FROM SPACESHIPS`，再由那个坏掉的 filter 把 flag 船全放过来。
**`SPACESHIPS.resources` 就是 flag 字段。**

> 复现时用 `U0RS` 后面跟 11 个 `|`（`"|" * 11`）来构造空 descriptor。

---

## 6. 漏洞三·续：「Not found」差分预言机

`fetch.neko:92-111` 的返回路径有一个微妙差别：

```neko
var rows = db.fetchByFields(spec.table, cols, whereCols, whereVals);
if($asize(rows) == 0){
    resp.sendMessage(resp.addErrorMessage(null, 0, "Not found"));   // → TVNI|n||date||RESPONSE| + RVJS
    return -1;
}
var out = $amake(0);
out = resp.addIdentityHeader(out, identity.id, identity.name, identity.auth);   // ← 先塞身份行
while(i < $asize(rows)){
    if(spec.filter(being, rows[i])){                              // ← 再按 Neko 过滤
        out = $aconcat(...);
    }
}
resp.sendResponse(out, "FETCH", ctx.header.request_subject);      // → TVNI|n|FETCH|...
```

- **WHERE 命中 0 行** → `RVJS|0|Not found`，且响应头 `type` 字段为**空**
- **WHERE 命中 ≥1 行、但全被 Neko 过滤掉** → 仍然是 `FETCH` 响应（body 里只有 `SURI`）

这个差别**与 Neko 层的 filter 无关**，只反映 SQL 层 `WHERE` 是否匹配。

再看 WHERE 是怎么拼的（`db.neko:216-222`）：

```neko
where = where + whereCols[i] + " LIKE \"" + whereVals[i] + "\"";
```

**`LIKE` 模式，而且没有转义 `_` 和 `%`。** 前面说过白名单禁 `%` 但**允许 `_`**，
于是 `_`（LIKE 的单字符通配）就成了攻击者的工具：

| 模式 | 含义 |
|---|---|
| `"___"` | id 的十进制文本**恰好 3 位** |
| `"1___"` | 3 位且以 1 开头 |
| `"12__"` | 3 位且以 12 开头 |

这是**定长模式**匹配（因为没有 `%`，必须把长度补齐），但对"逐位枚举整数 id"来说完全够用。

### 枚举套路

1. `_max_id_len`：用 `"_"*n` 探出 id 的最大位数
2. `_enumerate_flag_crews`：对每个长度做**逐位 DFS** —— 每位 0-9 各试一次，
   把命中的前缀带到下一位，模式用 `_` 补足原长度
3. `equipment` 字段同时用 `_FLAG_EQUIP` 限定：

```python
_FLAG_EQUIP = "^FAUST" + "_" * 33 + "^"      # 40 字符
```

即 `^FAUST_<32 个任意字符>^` —— 直接筛出"equipment 长得就像旗子"的 crew。
（`^` 是这套应用自己的字段分隔符。）

这样**不用爆破 id 空间**，几十次请求就能定位到承载 flag 的 crew。

---

## 7. 利用实现与工程细节

完整代码见 [`exploits/imc.py`](../exploits/imc.py)。几个值得说的点：

### 单连接复用

因为每个新连接都会 fork 新 VM 并重跑 `initDB()` 的五条 DELETE 扫描，
连接数是**要省着用的资源**。整个 run 只开一条 TCP 连接，
把 UPDATE/FETCH 成批写进去再一次读完。批量大小：

```python
_ORACLE_BATCH = 40      # 40 个预言机探测一次写出
_PROBE_BATCH  = 20      # 20 组 UPDATE+FETCH 一次写出
_MAX_REQUESTS = 900     # 单次运行自己给自己设的礼貌上限
```

### 响应计数不能只看 tag

一次探测会回两类消息（UPDATE 的判定 + FETCH 的结果），而"没找到"走的是
`type` 为空的错误消息 —— 所以不能简单按 tag 计数，
`_Session.read_probe_responses()` 专门处理这个大小写混合的计账。

### 用官方 `flag_ids` 走快速路径

`teams.json` 公开发布了**每个队当前的 flag-store id**。拿到它之后就不需要
先枚举再读，直接 `_extract()` 精确命中当轮的旗子：

```python
if pub:
    blob, _ = _fetch_spaceships(session, ident)   # 漏洞三：一把捞旗船
    found |= _flags(blob)
    found |= _extract(session, ident, pub, deadline)
    if found:
        return sorted(found)
```

**这同时解决了"打过期旗"的问题** —— 扫出来的历史 flag 提交回去只会得到
`Flag has expired`，白白消耗提交配额。

### 实测产出

配合该快速路径，单轮提交质量 `OK=141~166 / OLD=5~12`。
把编排器的 `MAX_WORKERS` 从 8 提到 24 后，单轮耗时 **357~380s → 127~132s**
（原先一轮超过一个 tick，永远追不上节奏），唯一旗速率 **6.0/分钟 → 18.8/分钟（3.1×）**。

---

## 8. 修复建议

按危害排序，每一条都能单独掐断链条：

| # | 位置 | 问题 | 修法 |
|---|---|---|---|
| 1 | `db.neko:updateById/updateByName/create*, fetchByFields` | 字符串拼 SQL | **全部改绑定参数**。注意"改用单引号"不是修复 —— SQLite 的双引号回退才是根因，但拼接本身就该消灭 |
| 2 | `update.neko:119-121` | `catch` 里缺 `return` | `catch` 必须 `return -1`；**任何"校验失败后继续执行"的控制流都是漏洞** |
| 3 | `fetch.neko:20` | 过滤缺 `being.crew != null` | 照抄 `update.neko:25` 的写法；更稳的是统一成共享的谓词函数 |
| 4 | `db.neko:220` | `LIKE` 的 `_`/`%` 未转义 | 转义操作数，或改用 `=` |
| 5 | 全表 | 越权判定散落在各处 | 把授权收敛到一处并**默认拒绝**；`fetch` 与 `update` 用同一份策略 |
| 6 | `db.neko:41-74` | 每连接跑 `initDB()` 的清理扫描 | 启动时做一次即可，不要放在 per-connection 路径上 |

第 2 条和第 3 条尤其值得强调：它们都不是"过滤不严"，而是**控制流写了但没生效** ——
一个 `catch` 少了 `return`，一个谓词少了半个条件。这类 bug 静态阅读代码比黑盒测试更容易发现。

---

## 9. 说明

- 本文所有结论都来自**阅读比赛提供的 `.neko` 源码**，不是黑盒爆破。
  源码清单：`db.neko` / `update.neko` / `fetch.neko` / `create.neko` / `parser.neko` /
  `responder.neko` / `utils.neko` / `imc.neko`。
- 比赛已于 2026-09-26 21:00 UTC 结束。本文按赛后 writeup 惯例公开。
- 文中不含任何其他队伍的数据、凭据或私有信息；引用的 `teams.json` / `scoreboard.json`
  均为主办方公开接口。
