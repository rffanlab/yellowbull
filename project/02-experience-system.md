# 经验回顾与记录系统 — 详细设计

> 对应主流程第 2 步（经验回顾）和第 6 步（记录经验）

---

## 一、核心目标

```
核心问题: 同样的坑不要踩两次，同样的路不要重新探索

具体场景:
  1. "上次改日志配置时，配置文件在 config/logging.yaml，不是 log.conf"
  2. "上次搜索这个接口时用了 grep 失败了，应该用 rg"
  3. "上次重构认证模块时，改了 5 个文件，不是 3 个"
```

---

## 二、经验产生与使用时机

```
产生时机:
  - 任务完成后（记录成功经验）
  - 步骤失败后（记录失败教训）
  - 动态工具生成后（记录工具有效性）

使用时机:
  - 任务接收后 → 判断任务类型，找相似经验
  - 步骤拆解前 → 参考历史拆解模式
  - 工具选择时 → 参考历史工具有效性
```

---

## 三、经验分级体系

### 3.1 三级分类

```
1. 通用经验（永久保存）
   - 与具体项目无关的通用知识
   - 例: "Windows 上路径分隔符用反斜杠"
   - 例: "Python 虚拟环境激活命令因 shell 而异"
   - is_permanent = true，永不老化

2. 项目经验（长期保存）
   - 与特定项目相关的经验
   - 例: "该项目配置文件在 config/ 目录下"
   - is_permanent = false，老化周期 180 天

3. 临时经验（短期保存）
   - 一次性/时效性经验
   - 例: "本次部署时服务器 A 暂时不可用"
   - is_permanent = false，老化周期 30 天
```

### 3.2 LLM 自动分级

```
LLM 在总结经验时自动判断级别:

  Prompt 追加:
    "请判断此经验属于通用级、项目级还是临时级，
     并给出 generality 评分 (0.0~1.0，1.0=完全通用)"

  规则:
    - generality >= 0.8 → 标记为永久
    - generality >= 0.5 → 项目级
    - generality < 0.5 → 临时级
```

---

## 四、经验回顾流程

### 4.1 完整流程

```
结构化 Task
        │
        ▼
┌─────────────────┐
│ 1. 提取检索关键词 │
│ - 从 goal 提取关键动词/名词 │
│ - 从 constraints 提取技术栈标签 │
│ - 从 context_files 提取项目类型 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 查询经验库     │
│ - 按关键词匹配     │
│ - 按任务类别匹配   │
│ - 按时间衰减排序   │  ← 近期经验权重更高
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 经验过滤       │
│ - 去重（相似经验只留最优） │
│ - 过滤过期经验     │  ← 超过老化周期且低分
│ - 最多取 Top K    │  ← 避免污染 Prompt
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 经验格式化     │
│ 转为自然语言提示   │
│ 注入拆解 Prompt   │
└────────┬────────┘
         │
         ▼
    "过往经验:
     - 类似任务曾使用 file+shell 工具链，成功率 90%
     - 注意: 日志配置文件可能在 config/ 而非根目录"
```

### 4.2 检索策略

```
检索优先级:
  1. 先查当前项目专属经验
  2. 再查通用经验（永久经验）
  3. 最后查其他项目相似经验

检索条件:
  - 关键词匹配（MVP）
  - 任务类别匹配
  - 排除过期经验
  - 优先高分经验

MVP 使用关键词检索，后续可升级为向量语义检索
```

### 4.3 经验注入方式

```
经验如何影响后续流程:

  1. 影响步骤拆解:
     Prompt 追加: "历史经验表明: ..."
     例: "类似任务通常需要 4-6 步，建议不要少于 3 步"

  2. 影响工具选择:
     Prompt 追加: "工具建议: ..."
     例: "file 工具在 Windows 上搜索建议用 dir 而非 find"

  3. 影响结果评估:
     已知常见错误模式 → 评估时额外检查
     例: "上次改配置后忘记重启服务，本次请检查"

  4. 影响修正策略:
     已知有效修复方式 → 优先尝试
     例: "上次遇到此错误时，改用 UTF-8 编码解决了"
```

---

## 五、经验记录流程

### 5.1 完整流程

```
任务执行完毕（无论成败）
        │
        ▼
┌─────────────────┐
│ 1. 收集执行数据   │
│ - 每步状态/耗时   │
│ - 工具使用记录    │
│ - 重试次数        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. LLM 总结      │
│ - 生成任务摘要    │
│ - 提取经验教训    │
│ - 自动打标签      │
│ - 判断经验级别    │
│ - 给出 generality 评分 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 评分计算      │
│ 基于以下因素:     │
│ - 整体成功率      │
│ - 步骤完成度      │
│ - 重试频率        │
│ - 是否用户介入    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 持久化存储    │
│ 写入 SQLite       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. 索引更新      │
│ 更新关键词索引    │
│ 更新类别统计      │
└─────────────────┘
```

### 5.2 评分公式

```
经验评分 (-1.0 ~ 1.0):

  score = (success_rate × 0.5)
        + (step_efficiency × 0.2)
        + (tool_effectiveness × 0.2)
        - (retry_penalty × 0.1)

  success_rate: 成功步骤 / 总步骤
  step_efficiency: 1 - (实际步骤数 / 理想步骤数)
  tool_effectiveness: 工具一次成功的比例
  retry_penalty: 总重试次数 × 0.1

  含义:
    1.0 = 完美执行
    0.5 = 勉强完成
    0.0 = 一半一半
   -0.5 = 基本失败但有收获
   -1.0 = 完全失败
```

---

## 六、数据模型

### 6.1 经验条目结构

```python
Experience {
  # 基础信息
  id: str
  task_summary: str              # 任务摘要（脱敏后）
  task_category: str             # 任务类别（自动打标）
  created_at: datetime

  # 执行信息
  outcome: str                   # success / partial / failed
  steps_count: int
  tool_chain: list[str]          # 使用的工具序列
  success_rate: float

  # 评分信息
  score: float                   # -1.0 ~ 1.0
  retry_count: int
  duration_seconds: int

  # 经验内容
  lessons_learned: str           # LLM 总结的经验教训
  keywords: list[str]            # 关键词列表
  tags: list[str]               # 上下文标签

  # 分级信息
  is_permanent: bool             # 是否永久保存
  generality: float              # 0.0~1.0，通用程度
  project_name: str | None       # 关联项目名（通用经验则为空）
}
```

### 6.2 SQLite 表结构

```sql
-- 经验主表
CREATE TABLE experiences (
    id TEXT PRIMARY KEY,
    task_summary TEXT NOT NULL,
    task_category TEXT,
    outcome TEXT NOT NULL,              -- success / partial / failed
    score REAL NOT NULL,                -- -1.0 ~ 1.0
    lessons_learned TEXT,               -- LLM 总结的经验教训
    tool_chain TEXT,                    -- JSON: ["file", "shell", "code"]
    steps_count INTEGER,
    success_rate REAL,
    retry_count INTEGER,
    duration_seconds INTEGER,
    is_permanent BOOLEAN DEFAULT 0,
    generality REAL DEFAULT 0.5,        -- 0~1
    project_name TEXT,                  -- 关联项目（NULL=通用）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 关键词索引表
CREATE TABLE experience_keywords (
    experience_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    FOREIGN KEY (experience_id) REFERENCES experiences(id)
);

-- 上下文标签表
CREATE TABLE experience_tags (
    experience_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    FOREIGN KEY (experience_id) REFERENCES experiences(id)
);

-- 索引
CREATE INDEX idx_exp_category ON experiences(task_category);
CREATE INDEX idx_exp_outcome ON experiences(outcome);
CREATE INDEX idx_exp_score ON experiences(score);
CREATE INDEX idx_exp_permanent ON experiences(is_permanent);
CREATE INDEX idx_exp_keyword ON experience_keywords(keyword);
CREATE INDEX idx_exp_tag ON experience_tags(tag);
CREATE INDEX idx_exp_project ON experiences(project_name);
```

### 6.3 检索查询示例

```sql
-- 按关键词 + 类别 + 评分 + 时间衰减检索
-- 先查当前项目经验，再查通用经验
SELECT e.*,
       (COUNT(k.experience_id) * 0.5)
       + (e.score * 0.3)
       + (0.2 / (1 + julianday('now') - julianday(e.created_at)))
  AS relevance_score
FROM experiences e
JOIN experience_keywords k ON e.id = k.experience_id
WHERE k.keyword IN ('日志', '配置', '修改')
  AND e.outcome IN ('success', 'partial')
  AND (
      e.is_permanent = 1
      OR (julianday('now') - julianday(e.created_at)) < 30
  )
GROUP BY e.id
HAVING relevance_score > 0.3
ORDER BY
  CASE WHEN e.is_permanent = 1 AND e.project_name IS NULL THEN 0
       WHEN e.project_name = '当前项目' THEN 1
       ELSE 2
  END,
  relevance_score DESC
LIMIT 5;
```

---

## 七、经验老化机制

### 7.1 老化规则

```
- is_permanent = true → 永不老化
- generality >= 0.8 → 老化周期 180 天
- generality < 0.8 → 老化周期 30 天
- score > 0.8 的经验自动延长老化周期 2 倍
- score < -0.5 的经验老化周期缩短为一半（快速淘汰坏经验）

老化操作:
  - 超过老化周期的经验标记为 expired
  - expired 经验不参与检索
  - 定期清理任务删除超过 2 倍老化周期的 expired 经验
```

### 7.2 老化检查 SQL

```sql
-- 标记过期经验
UPDATE experiences
SET is_expired = 1
WHERE is_expired = 0
  AND is_permanent = 0
  AND (
      (generality < 0.8 AND julianday('now') - julianday(created_at) > 30)
      OR (generality >= 0.8 AND julianday('now') - julianday(created_at) > 180)
  );

-- 清理过期经验
DELETE FROM experiences
WHERE is_expired = 1
  AND julianday('now') - julianday(created_at) > 365;
```

---

## 八、经验总结 Prompt 设计

```
System Prompt 结构:
  角色设定 → 你是经验总结专家
  任务说明 → 从本次任务执行记录中提取经验教训
  输入数据 → 任务目标、执行步骤、每步结果、最终状态
  输出格式 → JSON Schema 约束

输出 Schema:
{
  "task_summary": "任务摘要（脱敏）",
  "task_category": "code_refactor | config_change | debug | ...",
  "lessons_learned": "经验教训描述",
  "keywords": ["关键词1", "关键词2"],
  "tags": ["python", "windows", "config"],
  "is_permanent": true/false,
  "generality": 0.0 ~ 1.0,
  "project_name": "项目名（若为通用经验则为空）"
}
```

---

## 九、MVP 与后续升级路径

### 9.1 MVP 功能清单

```
✅ SQLite + 关键词表
✅ 基础评分公式
✅ 经验注入 Prompt
✅ 经验三级分类（永久/项目/临时）
✅ 基础老化机制
✅ 经验总结 Prompt
```

### 9.2 后续升级方向

```
→ 引入 embedding 模型（如 sentence-transformers）
→ 将 task_summary + lessons_learned 向量化
→ 用向量相似度替代关键词匹配
→ SQLite 可升级为 sqlite-vss 或 ChromaDB
→ 评分公式引入用户反馈（用户可给经验点赞/踩）
→ 经验共享（多项目间经验迁移）
→ 经验可视化（查看历史经验库）
```

---

## 十、配置项

```python
# 经验系统相关配置

experience:
  enabled: bool = true           # 是否启用经验系统
  max_retrieve_count: int = 5    # 每次最多检索 N 条经验
  min_relevance_score: float = 0.3  # 最低相关度阈值

  # 老化周期（天）
  aging_period_temporary: int = 30     # 临时经验
  aging_period_project: int = 180      # 项目经验

  # 清理策略
  cleanup_threshold_days: int = 365    # 过期经验清理阈值

  # 评分权重
  score_weight_success_rate: float = 0.5
  score_weight_efficiency: float = 0.2
  score_weight_tool: float = 0.2
  score_weight_retry: float = 0.1
```
