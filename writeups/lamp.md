# Lamp — arbitrary file read via TeX header macro injection

**FAUST CTF 2026 · Attack/Defense · service `lamp` (tcp/1337) · xelatex web "framework"**

> Team **qiyu** (FAUST team number 980). This primitive was **verified against real
> opponents' targets** but we never converted it into flags — the reason is documented
> honestly in §6.

---

## English abstract

`lamp` is a deliberately absurd "web framework" built out of a single LaTeX document.
`socat` hands every TCP connection to `entrypoint.sh`, which runs **one `xelatex
--shell-escape` compile per HTTP request**; the HTTP response body *is* xelatex's terminal
output.

`http.sty` implements the request parser. Its `\httpParseHeader` defines one macro per
request header, named after the header:

```tex
\expandafter\xdef\csname http\name\endcsname####1{\value}
```

So any `Xxx: <v>` header silently redefines `\httpXxx`. Two of those macros are
security-relevant: **`\httpStatic`** (via a `Static:` header) is used as a path prefix, and
**`\httpPath`** (via `Path:`) as the request path.

`\httpServe` runs in the order *request line → `..` check → header parsing → middleware
(auth → `httpTryServeStatic` → `httpRenderPage`)*. The traversal check therefore only ever
sees the path from the **request line**; a `..` smuggled through the `Path:` header is
parsed *after* the check and never re-validated.

`httpTryServeStatic` then does, for GET:

```tex
\IfFileExists{\httpStatic\httpPath{}}{ \httpSendFile{\httpStatic\httpPath{}} }{ ... }
```

With the default `\httpStatic = "/srv/www/"`, sending
`Path: ../../../storage/<name>.tex` resolves to `/storage/<name>.tex`, and `\httpSendFile`
executes `\immediate\write18{cat "..."}` — dumping the file straight into the response body.

**Result: authenticated-free arbitrary file read.** Confirmed on live targets reading
`/srv/main.tex` and `/etc/passwd`.

The flag is planted as a ship name in `/storage/<checker-username>.tex`:

```tex
\def \shipname {FAUST\Uchar95Q1RGLS32...\nFAUST\Uchar95...\n}
```

so `FAUST\Uchar95` → `FAUST_` recovers it — **if you know the filename**. The checker uses a
16-hex-character random username per team and we found no enumeration primitive in the
application (§6 lists the four we disproved, one of which we abandoned because it risked a
DoS). We therefore never scored from this service.

**Impact:** read any file the xelatex process can read, unauthenticated.
**Fix:** do not derive macro names from untrusted input; validate the resolved path after
concatenation, not before; drop `--shell-escape`.

---

## 1. 服务形态

```
socat -6 tcp-l:1337,fork EXEC:/entrypoint.sh
```

每次 HTTP 请求 = 一次 `xelatex --shell-escape` 编译。**响应体就是 xelatex 的 stdout**
（含警告、日志、错误），所以"读文件"这件事在输出里是裸的。
后端还有 mariadb + redis。

这是个"用 TeX 实现 Web 框架"的玩笑式设计，但它把 TeX 的几个特性组合成了真实的漏洞。

---

## 2. 漏洞：请求头名 → 宏名

`http.sty` 里解析请求头的核心是这一行：

```tex
\expandafter\xdef\csname http\name\endcsname####1{\value}
```

用人类话讲：**对每一个 `Name: value` 请求头，定义（或覆盖）一个叫 `\httpName` 的宏，
其展开结果就是那个 value。**

这是 TeX 的 `\csname...\endcsname` 动态构造控制序列的经典用法，问题在于
**`\name` 直接来自 attacker 控制的请求头名字**，没有任何白名单。

于是攻击者获得了"改写框架内部宏"的能力。其中两个恰好是安全敏感的：

| 请求头 | 被覆盖的宏 | 框架里的用途 |
|---|---|---|
| `Static: <v>` | `\httpStatic` | 静态文件名的**前缀**（默认 `/srv/www/`） |
| `Path: <v>` | `\httpPath` | **请求路径** |

---

## 3. 关键：`..` 检查与头部解析的**顺序**

`\httpServe` 的处理顺序是：

```
解析请求行  →  检查路径里有没有 ".."  →  解析请求头  →  中间件链
                                        (auth → httpTryServeStatic → httpRenderPage)
```

**目录穿越检查只作用于"请求行里的路径"，而它跑在"解析请求头"之前。**

这件事的后果不是"检查写得不好"，而是**检查作用于一个稍后会被覆盖的变量**：

```
GET / HTTP/1.1              ← 这里没有 ".."，检查通过
Path: ../../../storage/x.tex  ← 解析头时把 \httpPath 覆盖成带 ".." 的值
                             ← 再没有任何人重新检查
```

**这是本文里最值得记住的一点：校验必须作用于最终被使用的值，而不是它的早期快照。**

---

## 4. 从覆盖到文件读取

`httpTryServeStatic` 对 GET 请求做：

```tex
\IfFileExists{\httpStatic\httpPath{}}{
    \httpSendFile{\httpStatic\httpPath{}}     % 内部是 \immediate\write18{cat "<路径>"}
}{ ... }
```

默认 `\httpStatic = "/srv/www/"`，所以：

```
Path: ../../../storage/<name>.tex
→ /srv/www/../../../storage/<name>.tex   (即 /storage/<name>.tex)
→ \IfFileExists 为真
→ \httpSendFile → \write18{cat "..."}  → 文件原文进入响应体
```

### 真实靶机验证

```console
$ curl -s -H 'Path: ../main.tex'        "http://[fd66:666:45::2]:1337/"   → /srv/main.tex 全文
$ curl -s -H 'Path: ../../etc/passwd'   "http://[fd66:666:45::2]:1337/"   → passwd 全文
```

**无需认证。** 任意文件读取，只要 xelatex 进程读得到。

---

## 5. flag 的存放形式

checker 把 flag 当作"船名"注册，落盘在 `/storage/<checker用户名>.tex`：

```tex
\def \shipname {FAUST\Uchar95Q1RGLS32...\nFAUST\Uchar95...\n}
```

`\Uchar95` 就是 `_`（TeX 在 `\write` 时把下划线编码成 `\Uchar95` 以避免转义问题）。
**把 `FAUST\Uchar95` 还原成 `FAUST_` 就得到 flag。**

所以 exploit 的正则是：

```python
_RE_UCHAR_FLAG = re.compile(r"FAUST\\Uchar95([A-Za-z0-9/+]{32})")
_RE_RAW_FLAG   = re.compile(r"FAUST_" + r"([A-Za-z0-9/+]{32})")
```

---

## 6. 卡点（诚实说明）：无枚举原语

漏洞本身是"任意文件读"，但**文件名 = checker 随机生成的用户名**
（12 位随机字母数字，或 16 位 hex），且**每队独立随机**。

**没有用户名，就读不到那个文件。** 我们系统性地验证了四条可能的枚举路径，
**全部证伪**：

| # | 尝试 | 结果 |
|---|---|---|
| ① | 通过 shipname 做 TeX 注入 `\write18` | ❌ `\store` 把 `}` 转成 `\Uchar125`，展开后是 **catcode 12 的 `}`**，**不关闭分组** → 注入内容只作为文本存进宏体，**从不执行** |
| ② | Redis CRLF 协议注入 | ❌ `\StrLen` **把 CRLF 也算进长度**，长度自洽，构造不出协议错位 |
| ③ | NUL 字节截断 | ❌ 能让服务崩溃 —— **有 DoS 风险，我们主动放弃** |
| ④ | 换行截断 / 目录读取 | ❌ 不成立 |

另外两条相关的否定结论：

- `\IfFileExists` / `\httpSendFile` **不支持通配符**，传目录返回 false
- `cat` 的参数**永远在双引号里**，做不了 glob
- 唯一能执行 shell 的入口 `\input{|"cmd"}` 要求**文件名以 `|` 开头**，
  而应用里两个 `\input` 路径分别固定带 `/srv/pages/` 和 `/storage/` 前缀，
  并且 `\input` 在 `\edef` 上下文里还会**挂住等终端输入**，不能滥用

**还有一个对我们不利的发现**：`\immediate\write18{...}` 这类控制序列即使被
`^^5c` 走私进 SQL 输出，也只会被 `\edef`/`\xdef` **展开**而不会被**执行** ——
所以其他队伍此前留在 `components.type` 字段里的 payload 都是无效的。

> ⚠️ 第 ③ 条值得单独讲：我们发现 NUL 截断能让服务崩溃后**主动停手**。
> Attack/Defense 里的 DoS 既违反规则、又会被 SLA 扣分，而且在真实系统上
> "打得掉"不等于"利用得了"。**能崩不等于能用**，这条判断我认为是对的。

### 结果

Lamp 这条线**没有给我们带来任何进攻分**（该服务我方 `offense = 0.0`）。
我们交付的是一个**在真实靶机上验证过的任意文件读取原语**，
但没能把它接上"未知文件名"这个最后一公里。

**这个诚实的结论比假装成功有价值**：它把问题精确定位成
"需要一个 `/storage` 目录枚举原语"，而不是含糊的"Lamp 打不动"。

---

## 7. 修复建议

| # | 问题 | 修法 |
|---|---|---|
| 1 | 请求头名 → 宏名（`\csname http\name\endcsname`） | **绝不**用不可信输入构造控制序列名；改为白名单映射（只认已知的头） |
| 2 | 穿越检查跑在头部解析之前 | 校验**最终拼接后的绝对路径**（`\httpStatic\httpPath`），而不是请求行里的路径；用规范化后的路径做前缀比较，而不是查 `".."` 字符串 |
| 3 | `\write18{cat "...}` 直接吃拼接结果 | 去掉 `--shell-escape`；真要发静态文件就用 TeX 之外的一层 |
| 4 | 无认证即可 `httpTryServeStatic` | 静态服务路径应独立于请求驱动的路径解析，并限制在文档根内 |
| 5 | flag 以可预测形式落盘为 `.tex` | 这是 checker 侧设计，但也说明"文件名保密"被当成了安全边界 —— 不该依赖它 |

第 2 条是通用教训，值得从这道题里带出去：

> **验证要针对最终生效的值。** 先校验再覆盖，等价于没校验。

---

## 8. 说明

- 本文结论基于比赛提供的服务源码 + 在**真实对手靶机**上的实测（`/srv/main.tex`、`/etc/passwd`）。
- 四条枚举路径的否定结论均在真实靶机上验证，不是推测。
- 比赛已于 2026-09-26 21:00 UTC 结束；本文按赛后 writeup 惯例公开。
- 文中不含其他队伍的私有数据或凭据。
