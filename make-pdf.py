#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown -> PDF，用 Edge headless 打印。

仓库里所有文档都是 Markdown；这个脚本把它们变成可以直接发出去的 PDF。
没有 pandoc，所以自带一个够用的转换器（标题 / 表格 / 围栏代码 / 引用 / 列表 /
分隔线 / 粗体 / 行内代码 / 链接）。

用法:
    python make-pdf.py PORTFOLIO.md            # -> PORTFOLIO.pdf
    python make-pdf.py EVIDENCE.md out.pdf     # 指定输出名
"""
import html
import os
import re
import subprocess
import sys

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = """
@page { size: A4 portrait; margin: 14mm 13mm; }
body { font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
       font-size: 9.4pt; line-height: 1.62; color: #1f2328; margin: 0; }
h1 { font-size: 19pt; margin: 0 0 4mm; padding-bottom: 2mm;
     border-bottom: 2px solid #1a73e8; }
h2 { font-size: 13.5pt; margin: 7mm 0 2.5mm; padding-left: 2.5mm;
     border-left: 4px solid #1a73e8; page-break-after: avoid; }
h3 { font-size: 11pt; margin: 5mm 0 2mm; color: #174ea6; page-break-after: avoid; }
p { margin: 0 0 2.4mm; }
ul, ol { margin: 0 0 2.6mm; padding-left: 6mm; }
li { margin-bottom: 1mm; }
hr { border: none; border-top: 1px solid #dadce0; margin: 5mm 0; }
code { font-family: Consolas, "Cascadia Mono", monospace; font-size: 8.4pt;
       background: #f1f3f4; padding: 0.2mm 1mm; border-radius: 1mm; }
pre { background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 1.5mm;
      padding: 2.5mm 3mm; overflow-x: auto; page-break-inside: avoid;
      margin: 0 0 3mm; }
pre code { background: none; padding: 0; font-size: 8pt; line-height: 1.45; }
table { border-collapse: collapse; width: 100%; margin: 0 0 3.5mm;
        page-break-inside: avoid; font-size: 8.6pt; }
th { background: #1f2328; color: #fff; text-align: left; font-weight: 600;
     padding: 1.6mm 2mm; }
td { border-bottom: 1px solid #e6e8ea; padding: 1.5mm 2mm; vertical-align: top; }
tbody tr:nth-child(even) { background: #fafbfc; }
blockquote { margin: 0 0 3mm; padding: 2mm 3mm; background: #fff8e1;
             border-left: 3px solid #f9ab00; }
blockquote p { margin: 0 0 1.5mm; }
blockquote p:last-child { margin-bottom: 0; }
a { color: #1a73e8; text-decoration: none; word-break: break-all; }
strong { color: #0b1b33; }
"""


def inline(text):
    out = html.escape(text, quote=False)
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    out = re.sub(r"`([^`]+)`", stash, out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"<(https?://[^>]+)>", r'<a href="\1">\1</a>', out)
    for i, c in enumerate(codes):
        out = out.replace(f"\x00{i}\x00", f"<code>{html.escape(c)}</code>")
    return out


def convert(md):
    lines = md.split("\n")
    out, i, n = [], 0, len(md.split("\n"))
    while i < n:
        line = lines[i]

        if line.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            continue

        if line.startswith("|") and i + 1 < n and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            header = [c.strip() for c in line.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            t = ["<table><thead><tr>"]
            t += [f"<th>{inline(h)}</th>" for h in header]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>")
            i += 1
            continue

        if re.match(r"^-{3,}\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            out.append(f"<blockquote><p>{inline(' '.join(x for x in buf if x))}</p></blockquote>")
            continue

        if re.match(r"^[-*]\s+", line):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i]):
                items.append(inline(re.sub(r"^[-*]\s+", "", lines[i])))
                i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue

        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i]):
                items.append(inline(re.sub(r"^\d+\.\s+", "", lines[i])))
                i += 1
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>")
            continue

        if not line.strip():
            i += 1
            continue

        buf = []
        while i < n and lines[i].strip() and not re.match(
                r"^(#{1,6}\s|[-*]\s|\d+\.\s|>|\||```|-{3,}\s*$)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")

    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".pdf"

    edge = next((p for p in EDGE_CANDIDATES if os.path.exists(p)), None)
    if not edge:
        sys.exit("找不到 Edge；本脚本依赖 Edge headless 打印。")

    body = convert(open(src, encoding="utf-8").read())
    tmp = os.path.splitext(dst)[0] + "._tmp.html"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
                 f'<title>{html.escape(os.path.basename(src))}</title>'
                 f'<style>{CSS}</style></head><body>{body}</body></html>')

    if os.path.exists(dst):
        os.remove(dst)
    subprocess.run([
        edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw", "--virtual-time-budget=30000",
        f"--print-to-pdf={os.path.abspath(dst)}",
        "file:///" + os.path.abspath(tmp).replace("\\", "/"),
    ], capture_output=True)

    if not os.path.exists(dst):
        sys.exit("打印失败")
    raw = open(dst, "rb").read()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", raw))
    print(f"{src} -> {dst}  ({len(raw)} bytes, {pages} pages)")
    os.remove(tmp)


if __name__ == "__main__":
    main()
