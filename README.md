# ai-skills

跨设备统一管理与同步 **Codex**（`~/.codex/skills`）和 **Antigravity**（`~/.gemini/config/skills`）全局 AI Agent Skills 的轻量工具。

- **零第三方依赖**：仅依赖系统自带 Python 3 与 `git`。
- **稀疏按需拉取**：Git 来源使用 `--filter=blob:none` 与 `sparse-checkout`，大仓库也能只拉取目标技能子目录。
- **配置与状态分离**：`sources.json` 只保存声明式配置供 Git 托管；每台机器的同步版本号、时间与已安装列表写入本机 `~/.config/ai-skills/state.json`，执行 `update` 不会污染仓库工作区。
- **自动清理旧技能**：从 `sources.json` 移除某个来源或将其加入 `retiredSkills` 后，全量执行 `ai-skills update` 会自动删掉不再配置的旧技能目录。

## 新电脑一键初始化

```bash
gh repo clone ardenlab/ai-skills ~/.local/share/ai-skills
~/.local/share/ai-skills/install.sh --sync
```

> 如果新电脑之前已有独立的 `~/.config/ai-skills/sources.json`，`install.sh` 会在覆盖软链接前自动把旧状态迁移到 `state.json`，再由 `--sync` 同步最新技能并清理 `retiredSkills` 中声明的旧目录。

## 日常使用

```bash
ai-skills list                 # 查看目标目录数量与各来源同步状态
ai-skills check [source_id]    # 仅检查全部或指定来源是否有上游更新
ai-skills update [source_id]   # 拉取更新并同步到 Codex / Antigravity
```

## 多端同步工作流

1. 在任一设备编辑仓库中的 `sources.json`（增删来源或调整 `retiredSkills`）。
2. 提交并推送到 GitHub：
   ```bash
   git add sources.json && git commit -m "chore: update skills" && git push
   ```
3. 在其他设备拉取并一键同步：
   ```bash
   git -C ~/.local/share/ai-skills pull && ai-skills update
   ```

## `sources.json` 字段说明

| `type` | 说明 | 关键字段 |
| --- | --- | --- |
| `git-bundle` | 同步仓库下某目录内的全部子技能 | `repo`, `branch`, `subpath` |
| `git-dir` | 同步单个技能目录；可用 `targetSubpaths` 按客户端映射不同构建包 | `repo`, `branch`, `subpath` 或 `targetSubpaths`, `skillName` |
| `git-dirs` | 同步同一仓库内的多个指定子技能目录 | `repo`, `branch`, `subpaths` |
| `git-files` | 从仓库只检出指定文件组成技能 | `repo`, `branch`, `files`, `skillName` |
| `http-files` | 直接从 HTTP 基准地址拉取指定文件列表 | `baseUrl`, `files`, `skillName` |

可选附加字段：
- `retiredSkills`（顶层数组）：声明已下线需自动删除的技能名（例如 `["frontend-design"]`），方便尚未记录 `state.json` 的机器在首次 `--sync` 时一并清理旧目录。
- `postSync`（来源内命令数组）：当该来源发生新增或更新时，在安装目录内自动执行预热命令（例如 `["scripts/impeccable", "engine-probe"]`）。
