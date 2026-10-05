# 发布指南 / Publishing guide

仓库内容已经写好并脱敏，可以直接发布。以下三步**需要你的凭据**，我（AI 助手）没有你的
GitHub / CTFtime / 博客账号，所以这三步必须由你执行。

---

## 0. 先做一次脱敏复查（建议每次都跑）

```powershell
cd C:\Users\qiyu\Documents\faust-ctf-2026-writeups
python preflight.py
```

`preflight.py` 会做四件事，任何一项不过就以非零码退出：

1. **脱敏扫描** —— 私钥块、VPN 内联凭据、Vulnbox 服务包口令、基础设施网段等
2. **成绩数字校验** —— README 里的每个数字都要和 `data/scoreboard-full.json` 对得上
3. **相对链接校验** —— `../exploits/...` 之类必须指向真实存在的文件
4. **编号一致性** —— 队号与记分板 `id` 不得混用

> 敏感模式只写在 `preflight.py` 里，脚本会跳过自身，所以正常情况下输出就是干净的 0 命中。
> 如果它报出命中，**先判断是不是误报**（例如文中解释性地提到某个字段名），再决定是否发布。

我在整理时**故意排除**了以下内容，请不要在后续提交里加回来：

| 排除项 | 原因 |
|---|---|
| `RUNBOOK.md` | 含 Vulnbox 服务包的 GPG 口令 |
| VPN 配置文件 | 含私钥 |
| `/etc/team-num`、靶机内网地址清单 | 运营细节，公开无意义 |
| 其他队伍的数据 | 只引用主办方公开的 `scoreboard.json` / `teams.json` |

---

## 1. GitHub

### 最快路径：一条命令

```powershell
cd C:\Users\qiyu\Documents\faust-ctf-2026-writeups
.\publish.ps1
```

`publish.ps1` 会依次做：定位 `gh` → 检查登录 → 确认 git 身份 → 跑 `preflight.py` 自检
→ 提交 → 建库 → 推送 → 打印 CTFtime 提交链接。

**前置条件只有一个**：先在自己终端里跑过一次 `gh auth login`。
没登录的话脚本会提示并退出（退出码 2），不会做任何破坏性操作。

常用变体：

```powershell
.\publish.ps1 -Private                             # 先建私有库自己看一眼
.\publish.ps1 -RepoName my-writeups                # 换仓库名
.\publish.ps1 -GitName "Alice" -GitEmail "a@b.c"   # 非交互指定身份
```

如果 PowerShell 拒绝执行脚本（报 `AuthorizationManager check failed` 或
`cannot be loaded because running scripts is disabled`），用这个绕过：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish.ps1
```

### 手工路径（等价的原始命令）

```powershell
cd C:\Users\qiyu\Documents\faust-ctf-2026-writeups

git config user.name  "你的名字"
git config user.email "你的邮箱"

python .\preflight.py            # 自检，必须通过

git add -A
git commit -m "FAUST CTF 2026 writeups: IMC bug chain, Lamp TeX header injection, Rufflecopter AVM2 reverse"

gh repo create faust-ctf-2026-writeups --public --source=. --remote=origin --push

# 或手工建库后：
# git remote add origin git@github.com:<你的用户名>/faust-ctf-2026-writeups.git
# git push -u origin main
```

> **踩过的坑（写在这里免得你重踩）**：
> 1. `gh` 装好后**当前终端**的 PATH 还是旧的，要**新开一个终端**才认得 `gh`。
> 2. 这个脚本必须保持**纯 ASCII**。Windows PowerShell 5.1 会把无 BOM 的 `.ps1`
>    按 ANSI 读，中文会乱码并把字符串引号弄坏 —— 第一版就是这么炸的。
> 3. 脚本里**不能**用 `$ErrorActionPreference='Stop'`：`gh` / `git` 会往 stderr
>    写进度，`Stop` 会把它当致命错误，**推送成功也会中止**。现在改成显式查
>    `$LASTEXITCODE`。

### 顺手开 GitHub Pages（强烈建议）

CTFtime 的 writeup 提交要的是一个**可点击的 URL**，Markdown 在 GitHub 上也能读，
但渲染过的页面更专业。最省事的做法：

1. 仓库 Settings → Pages → Source 选 `main` 分支的 `/`（根目录）或 `/docs`
2. 或者直接把 `writeups/*.md` 复制到 `docs/` 并加一个 `index.md`

> 如果不熟悉 Pages，**直接用 GitHub 上 Markdown 的 URL 提交给 CTFtime 也完全可以**，
> 例如 `https://github.com/<user>/faust-ctf-2026-writeups/blob/main/writeups/imc.md`
> —— 这是很多队伍的做法。

---

## 2. CTFtime

**FAUST CTF 2026 的 event id 是 `3312`**
（来源：<https://ctftime.org/team/449998> 的参赛记录里链到 `/event/3312`）。

流程：

1. 登录 <https://ctftime.org/>
2. 打开 <https://ctftime.org/writeup/add/>
3. 填写：
   - **Event**: FAUST CTF 2026 (`/event/3312`)
   - **Task / Title**: 建议一服务一条，例如
     - `IMC — three-bug chain to a cross-tenant flag read (FAUST CTF 2026)`
     - `Lamp — arbitrary file read via TeX header macro injection (FAUST CTF 2026)`
     - `Rufflecopter — reversing an AVM2 HTTP server (FAUST CTF 2026)`
   - **URL**: 上面的 GitHub（或 Pages）链接
   - **Language**: Chinese（我们是中文全文 + 英文摘要）
4. 本队账号：<https://ctftime.org/team/449998>

### 关于语言的一个提醒

CTFtime 的主要读者是国际社区。我们每篇都带 **English abstract**，但如果你希望拿到更好的
投票与引用，**建议至少把 IMC 那篇翻成完整英文**（它是三篇里技术密度最高、最有引用价值的）。

> 说明：CTFtime 的评分机制里 writeup 本身不计入比赛分数，它的价值是**公开可见度** ——
> 这正是你要的东西。

---

## 3. 个人博客（可选）

如果博客有 Markdown 支持（Hexo / Hugo / VitePress / WordPress 的 MD 插件），
`writeups/*.md` 可以直接贴。

三篇之间的内部链接是相对路径：

```
../exploits/imc.py
../exploits/_receipt_decode.py
```

贴到博客时记得把这类链接改成仓库的绝对 URL，否则会 404。发布前可以用：

```powershell
Select-String -Path .\writeups\*.md -Pattern '\]\(\.\./'
```

把它们统一替换成 `https://github.com/<user>/faust-ctf-2026-writeups/blob/main/...`。

---

## 4. 发布前的最后一遍自检

- [ ] 脱敏复查无命中
- [ ] `writeups/` 三篇内部链接（`../exploits/...`）在发布环境下可解析
- [ ] README 里的成绩数字与 `data/scoreboard-full.json` 一致
- [ ] 队号 `980` 与记分板 `id` `185` 没有被混用
      （README 已显式说明；`scoreboard-full.csv` 的列名是 `scoreboard_id`）
- [ ] 确认比赛已结束（2026-09-26 21:00 UTC）—— Attack/Defense 赛后发 writeup 是惯例
