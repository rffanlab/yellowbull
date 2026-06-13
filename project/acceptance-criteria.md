# YellowBull `setup` 命令 — 验收标准

## 功能验收

### AC-01: 非交互模式初始化

| 项目 | 内容 |
|------|------|
| **前置条件** | 干净的目录，无 `.env`、无 `./data/` |
| **操作** | `yellowbull setup --non-interactive --provider openai --model gpt-4o --api-key sk-test123` |
| **预期结果** | |

- [ ] 退出码为 0
- [ ] `.env` 文件已生成，内容包含：
  - `YELLOWBULL_LLM_PROVIDER=openai`
  - `YELLOWBULL_LLM_MODEL=gpt-4o`
  - `YELLOWBULL_LLM_API_KEY=sk-test123`
- [ ] `./data/` 目录已创建
- [ ] `./data/yellowbull.db` 数据库文件存在，WAL 模式启用
- [ ] 数据库中 `experiences`、`experience_keywords`、`experience_tags` 表已创建
- [ ] `.gitignore` 包含 `.env`

---

### AC-02: 非交互模式参数校验

| 项目 | 内容 |
|------|------|
| **前置条件** | 任意环境 |
| **操作** | `yellowbull setup --non-interactive`（缺少必要参数） |
| **预期结果** | |

- [ ] 退出码非 0
- [ ] 错误信息提示缺少 `--provider`、`--model`、`--api-key`

---

### AC-03: Ollama 自动填充 Base URL

| 项目 | 内容 |
|------|------|
| **前置条件** | 任意环境 |
| **操作** | `yellowbull setup --non-interactive --provider ollama --model llama3 --api-key dummy` |
| **预期结果** | |

- [ ] `.env` 中 `YELLOWBULL_LLM_BASE_URL=http://localhost:11434`

---

### AC-04: .env 覆盖保护

| 项目 | 内容 |
|------|------|
| **前置条件** | 已存在 `.env` 文件（内容为 `OLD=value`） |
| **操作 A** | `yellowbull setup --non-interactive --provider openai --model gpt-4o --api-key sk-new`（无 `--force`） |
| **预期结果 A** | |

- [ ] 提示 `.env` 已存在，询问是否覆盖
- [ ] 非交互模式下拒绝执行或报错

---

| 项目 | 内容 |
|------|------|
| **前置条件** | 已存在 `.env` 文件（内容为 `OLD=value`） |
| **操作 B** | `yellowbull setup --non-interactive --provider openai --model gpt-4o --api-key sk-new --force` |
| **预期结果 B** | |

- [ ] 直接覆盖，`.env` 内容更新为新配置
- [ ] 旧内容 `OLD=value` 不存在

---

### AC-05: --init-data-only 模式

| 项目 | 内容 |
|------|------|
| **前置条件** | 干净的目录 |
| **操作** | `yellowbull setup --init-data-only` |
| **预期结果** | |

- [ ] `./data/` 目录已创建
- [ ] `./data/yellowbull.db` 数据库初始化完成
- [ ] `.env` 文件未生成（或仅包含数据相关配置）
- [ ] 不要求 LLM 参数

---

### AC-06: --show-config 模式

| 项目 | 内容 |
|------|------|
| **前置条件** | 已存在 `.env` 或环境变量已设置 |
| **操作** | `yellowbull setup --show-config` |
| **预期结果** | |

- [ ] 打印当前生效配置（Provider / Model / Tools / Database / Experience）
- [ ] 以表格形式展示
- [ ] 退出码为 0，不修改任何文件

---

### AC-07: Python 版本检测

| 项目 | 内容 |
|------|------|
| **前置条件** | Python < 3.10（模拟） |
| **操作** | `yellowbull setup` |
| **预期结果** | |

- [ ] 拒绝执行，提示 "Python >= 3.10 required"
- [ ] 退出码非 0

---

### AC-08: .gitignore 自动追加

| 项目 | 内容 |
|------|------|
| **前置条件** | `.gitignore` 不存在或存在但不包含 `.env` |
| **操作** | `yellowbull setup --non-interactive --provider openai --model gpt-4o --api-key sk-test` |
| **预期结果** | |

- [ ] `.gitignore` 文件存在且包含 `.env`
- [ ] 原有内容未被破坏（追加模式）

---

## 交互验收

### AC-09: 交互式引导流程

| 项目 | 内容 |
|------|------|
| **前置条件** | 干净目录 |
| **操作** | `yellowbull setup`（无参数，交互式） |
| **预期结果** | |

- [ ] 显示初始化向导 Banner
- [ ] 按步骤引导：环境检测 → LLM 配置 → 执行配置 → 工具配置 → 数据初始化 → 生成配置
- [ ] 每步显示进度 `[1/6]`、`[2/6]` ...
- [ ] API Key 输入时隐藏回显（显示 `●●●●●●●●`）
- [ ] 所有选项支持 Enter 使用默认值
- [ ] 最终打印配置摘要表格

---

### AC-10: LLM 连接测试

| 项目 | 内容 |
|------|------|
| **前置条件** | `.env` 已生成，API Key 有效 |
| **操作** | setup 完成后选择 "测试 LLM 连接" → `y` |
| **预期结果（成功）** | |

- [ ] 显示 ✓ 连接成功 + Model 名称

---

| 项目 | 内容 |
|------|------|
| **前置条件** | `.env` 已生成，API Key 无效 |
| **操作** | setup 完成后选择 "测试 LLM 连接" → `y` |
| **预期结果（失败）** | |

- [ ] 显示 ✗ 连接失败 + 排查建议
- [ ] 不阻止 setup 完成（仅警告）

---

## 边界/异常验收

### AC-11: 数据库路径自定义

| 项目 | 内容 |
|------|------|
| **前置条件** | 任意环境 |
| **操作** | `yellowbull setup --non-interactive --provider openai --model gpt-4o --api-key sk-test --db-path /tmp/test.db` |
| **预期结果** | |

- [ ] `/tmp/test.db` 创建成功
- [ ] `.env` 中 `YELLOWBULL_DATABASE_PATH=/tmp/test.db`

---

### AC-12: 工具列表自定义

| 项目 | 内容 |
|------|------|
| **前置条件** | 任意环境 |
| **操作** | `yellowbull setup --non-interactive --provider openai --model gpt-4o --api-key sk-test --tools file,shell` |
| **预期结果** | |

- [ ] `.env` 中 `YELLOWBULL_TOOLS_ALLOWED=file,shell`

---

### AC-13: 重复执行幂等性

| 项目 | 内容 |
|------|------|
| **前置条件** | 已完成一次 setup（`.env` + `./data/` 存在） |
| **操作** | `yellowbull setup --non-interactive --provider openai --model gpt-4o --api-key sk-test --force` |
| **预期结果** | |

- [ ] 执行成功，不报错
- [ ] 数据库表结构不变（CREATE TABLE IF NOT EXISTS）
- [ ] `.env` 内容更新为新配置

---

## 测试覆盖验收

### AC-14: 单元测试覆盖率

| 模块 | 最低覆盖率要求 |
|------|---------------|
| `cli/setup.py` | ≥ 80% 行覆盖率 |
| `config/settings.py` (新增方法) | ≥ 90% 行覆盖率 |

**测试用例清单：**

| 测试 ID | 名称 | 类型 | Phase |
|---------|------|------|-------|
| S-01 | test_non_interactive_setup | 单元测试 | P0 |
| S-02 | test_non_interactive_missing_params | 单元测试 | P0 |
| S-03 | test_ollama_auto_base_url | 单元测试 | P0 |
| S-04 | test_env_overwrite_protection | 单元测试 | P0 |
| S-05 | test_env_overwrite_force | 单元测试 | P0 |
| S-06 | test_init_data_only | 单元测试 | P3 |
| S-07 | test_show_config | 单元测试 | P3 |
| S-08 | test_python_version_check | 单元测试 | P1 |
| S-09 | test_gitignore_add_env | 单元测试 | P0 |
| S-10 | test_generate_env_content | 单元测试 | P0 |
| S-11 | test_init_database_creates_tables | 单元测试 | P0 |
| S-12 | test_settings_export_env | 单元测试 | P0 |
| S-13 | test_settings_from_dict | 单元测试 | P0 |
| S-14 | test_custom_db_path | 单元测试 | P0 |
| S-15 | test_custom_tools_list | 单元测试 | P0 |
