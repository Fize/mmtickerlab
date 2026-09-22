# 版本与 ClawHub 发布规则

项目使用 SemVer，但大版本只用于 Skill 的根本性重构。

- **补丁版本**：只修复 bug、校验错误、兼容性问题或文档错误，不改变能力和输出契约。
- **次版本**：增加向后兼容的新功能或数据模块。
- **大版本**：重做 Skill 核心架构，或改变核心输入、输出、调用协议，使旧调用方无法兼容。

项目版本记录在 [`VERSION`](VERSION)，各 Skill 的 ClawHub 版本和 slug 记录在 [`skill-versions.json`](skill-versions.json)。`SKILL.md` 保持 Agent Skills 元数据格式；发布版本通过 ClawHub CLI 的 `--version` 指定，避免注册表把功能变更自动递增为补丁版本。

当前这批改造属于向后兼容的功能增加与数据源重构，发布版本为 `1.1.1`。已改动的 Skill 发布 `1.1.1`，未改动的 `sim-trade` 保持 `1.0.0`。

发布前先检查版本：

```bash
python3 scripts/check_versions.py --tag v1.1.1
```

然后只发布本次改动过的 Skill，并显式传入对应版本：

```bash
clawhub skill publish ./market \
  --slug @fize/market \
  --version 1.1.1 \
  --tags latest \
  --changelog "引入 yfinance 海外主力源与毫秒级极速容灾，剔除问财依赖"
```

ClawHub 会保留旧版本；`latest` 只移动到新发布版本。不要复用已发布的版本号，也不要让未改动的 Skill 因项目整体发版而虚增版本。
