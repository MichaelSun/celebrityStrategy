# 核查已移除 guru 是否仍残留于报告/存档

## 背景

从 `TRACKED_GURUS` 移除某 guru（如帕布莱 Pabrai / 斯皮尔 Spier）后，脚本**新生成**的报告不再含该 guru。
但多数情况下用户看到的"还在报告里"来自**移除之前**生成的历史文件，而非当前报告。本脚本用于精确判断到底哪里还有残留。

## 关键陷阱：不要用子串搜索

移除 Pabrai 时，若用 `search_files(pattern="PI")` 或 `re.search("PI")`，会大量命中其他词：
- **Pinduoduo**（拼多多）→ 含 "pi"
- **Palantir**（PLTR）→ 含 "pi"
- **aq** 短码也会误中 "...aque..." 等

这会造成"还有 12 处命中"的误报。必须用**全词匹配**正则。

## 精确核查脚本

```python
from pathlib import Path

# 要核查的 guru 标识（按当前 TRACKED_GURUS 已移除者填写）
PAT = re.compile(r'(?i)(pabrai|spier|aquamarine|帕布莱|斯皮尔)')

# 1) 当前最新报告（应为 0 命中）
cur = Path('/Users/michael/Documents/GoogleAntigravity/celebrityStrategy/reports')
latest = sorted(cur.glob('celebrity_clone_*_V*.md'))[-1]   # 取最大版本
print("当前报告", latest.name, "命中:", PAT.findall(latest.read_text(errors='ignore')))

# 2) 所有 workspace 旧时间戳存档（可能含历史残留）
for f in sorted(cur.glob('celebrity_clone策略对比_*.md')):
    h = PAT.findall(f.read_text(errors='ignore'))
    if h:
        print("旧存档含残留:", f.name, len(h), "处")

# 3) Obsidian 目录（只读核查，不删除）
obs = Path('/Users/michael/Library/Mobile Documents/iCloud~md~obsidian/Documents/3.Investment/持仓参考')
for f in sorted(obs.glob('celebrity_clone*')):
    try:
        h = PAT.findall(f.read_text(errors='ignore'))
        if h:
            print("OBSIDIAN 含残留:", f.name, len(h), "处")
    except Exception as e:
        print(f.name, "读取失败:", e)
```

## 判读

- **当前报告 0 命中 + Obsidian 无残留** → 脚本已正确，用户看到的是旧文件或 iCloud 缓存未刷新。告知用户打开最新 `celebrity_clone_mm-dd-yyyy_季度_Vn.md`。
- **workspace 旧时间戳文件有残留** → 属历史存档，符合预期。按用户意愿决定是否清理（workspace 本地文件可删，不违反 Obsidian 只写不删规则）。
- **Obsidian 有残留** → 若来自旧同步，按"只写不删"硬规则，**覆盖但不删除**；如需更新直接 `cp` 新文件覆盖同名旧文件。
