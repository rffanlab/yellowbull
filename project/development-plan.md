# YellowBull `setup` 命令 — 开发计划

## 总览

| 项目 | 内容 |
|------|------|
| **功能** | `yellowbull setup` 交互式初始化命令 |
| **涉及模块** | cli, config, storage |
| **新增文件** | 2 个（setup.py、test_setup.py） |
| **修改文件** | 3 个（main.py、settings.py、__init__.py） |

---

## 阶段拆解

### Phase P0 — 核心功能（非交互模式 + .env 生成 + 数据初始化）

> 最小可用版本：支持 `--non-interactive` 参数，完成配置写入和数据目录/数据库初始化。

| 任务 ID | 描述 | 文件 | 工作量 |
|---------|------|------|--------|
| P0-T1 | 创建 `cli/setup.py`，定义 Click command + 所有 CLI 选项 | `src/yellowbull/cli/setup.py` | 小 |
| P0-T2 | 实现 `_generate_env()` — 将配置 dict 写入 `.env` 文件 | `src/yellowbull/cli/setup.py` | 小 |
| P0-T3 | 实现 `_init_data_dirs()` + `_init_database()` — 同步包装异步数据库初始化 | `src/yellowbull/cli/setup.py` | 中 |
| P0-T4 | 实现 `_gitignore_add_env()` — 追加 `.env` 到 `.gitignore` | `src/yellowbull/cli/setup.py` | 小 |
| P0-T5 | 实现 `--non-interactive` 模式主流程（参数校验 → .env → 数据初始化） | `src/yellowbull/cli/setup.py` | 中 |
| P0-T6 | 在 `cli/main.py` 注册 setup 命令入口 | `src/yellowbull/cli/main.py` | 小 |
| P0-T7 | Settings 新增 `export_env()` / `from_dict()` 辅助方法 | `src/yellowbull/config/settings.py` | 小 |

**验收标准：**
- [ ] `yellowbull setup --non-interactive --provider openai --model gpt-4o --api-key sk-test` 执行成功
- [ ] `.env` 文件正确生成，包含所有配置项
- [ ] `./data/` 目录创建，SQLite 数据库初始化完成（WAL 模式 + 建表）
- [ ] `.gitignore` 已追加 `.env`

---

### Phase P1 — 交互式引导

> 用户友好的交互体验：逐步引导配置 LLM、执行参数、工具选择。

| 任务 ID | 描述 | 文件 | 工作量 |
|---------|------|------|--------|
| P1-T1 | 实现 `_check_environment()` — Python 版本 + 依赖检测 | `src/yellowbull/cli/setup.py` | 小 |
| P1-T2 | 实现 `_interactive_llm_setup()` — 提供商选择 + Model/API Key/Base URL 输入 | `src/yellowbull/cli/setup.py` | 中 |
| P1-T3 | 实现 `_interactive_exec_setup()` — 执行参数引导（超时/步骤/重试） | `src/yellowbull/cli/setup.py` | 小 |
| P1-T4 | 实现 `_interactive_tool_setup()` — 工具多选 + Shell 安全模式确认 | `src/yellowbull/cli/setup.py` | 中 |
| P1-T5 | 实现交互式主流程编排（6步引导 → 汇总 → .env → 数据初始化） | `src/yellowbull/cli/setup.py` | 大 |
| P1-T6 | Rich Panel/Progress 美化输出（Banner、步骤进度、摘要表格） | `src/yellowbull/cli/setup.py` | 小 |

**验收标准：**
- [ ] `yellowbull setup` 进入交互模式，按步骤引导完成配置
- [ ] LLM API Key 输入时隐藏回显
- [ ] 所有选项支持 Enter 使用默认值
- [ ] Ollama 提供商自动填充 base_url = `http://localhost:11434`
- [ ] 最终打印配置摘要表格

---

### Phase P2 — LLM 连接测试

> 初始化完成后验证 LLM 连通性。

| 任务 ID | 描述 | 文件 | 工作量 |
|---------|------|------|--------|
| P2-T1 | 实现 `_test_llm_connection()` — 发送简短 chat 请求验证 API Key + Model | `src/yellowbull/cli/setup.py` | 中 |
| P2-T2 | 集成到主流程末尾（可选，用户可跳过） | `src/yellowbull/cli/setup.py` | 小 |

**验收标准：**
- [ ] LLM 连接成功时显示 ✓ + 响应摘要
- [ ] 连接失败时显示 ✗ + 排查建议（API Key 无效 / Model 不存在 / 网络问题）
- [ ] 用户可选择跳过测试

---

### Phase P3 — 辅助功能

> `--show-config`、`--init-data-only`、已有 `.env` 覆盖保护。

| 任务 ID | 描述 | 文件 | 工作量 |
|---------|------|------|--------|
| P3-T1 | 实现 `--show-config` — 加载当前配置并打印表格后退出 | `src/yellowbull/cli/setup.py` | 小 |
| P3-T2 | 实现 `--init-data-only` — 跳过 LLM 配置，仅初始化数据目录和数据库 | `src/yellowbull/cli/setup.py` | 小 |
| P3-T3 | `.env` 覆盖保护：已有文件时提示确认，`--force` 直接覆盖 | `src/yellowbull/cli/setup.py` | 小 |

**验收标准：**
- [ ] `yellowbull setup --show-config` 打印当前生效配置
- [ ] `yellowbull setup --init-data-only` 仅初始化数据，不碰 LLM
- [ ] 已有 `.env` + 无 `--force` → 提示确认覆盖
- [ ] 已有 `.env` + `--force` → 直接覆盖

---

## 执行顺序

```
P0-T1 → P0-T2 → P0-T3 → P0-T4 → P0-T5 → P0-T6 → P0-T7
   ↓ (P0 验收通过)
P1-T1 → P1-T2 → P1-T3 → P1-T4 → P1-T5 → P1-T6
   ↓ (P1 验收通过)
P2-T1 → P2-T2
   ↓ (P2 验收通过)
P3-T1 → P3-T2 → P3-T3
```

---

## 文件变更清单

| 文件 | 操作 | Phase |
|------|------|-------|
| `src/yellowbull/cli/setup.py` | **[NEW]** setup 命令全部实现 | P0-P3 |
| `src/yellowbull/cli/main.py` | 添加 `@cli.command()` 注册 setup | P0 |
| `src/yellowbull/config/settings.py` | 新增 `export_env()` / `from_dict()` | P0 |
| `tests/unit/test_setup.py` | **[NEW]** setup 命令单元测试 | P0-P3 |
