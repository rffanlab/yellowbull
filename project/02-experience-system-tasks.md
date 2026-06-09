# 经验回顾与记录系统 — 代码开发任务

> 对应设计文档：02-experience-system.md
> 模块职责：经验检索 → 注入 Prompt → 经验记录 → 评分计算 → 持久化存储 → 老化清理

---

## 一、经验仓库模块

### T02-01: 经验 CRUD 操作

**对应设计**: 六、数据模型 → 6.2 SQLite 表结构

**文件**: `src/yellowbull/experience/repo.py`

**需要实现的类**:
```python
class ExperienceRepo:
    """经验数据库操作层"""

    def __init__(self, db: DatabaseManager):
        ...

    async def save(self, experience: Experience) -> str:
        """保存经验条目，返回 experience_id"""
        ...

    async def get_by_id(self, experience_id: str) -> Experience | None:
        """按 ID 查询单条经验"""
        ...

    async def save_keywords(self, experience_id: str, keywords: list[str]):
        """保存经验关联的关键词"""
        ...

    async def save_tags(self, experience_id: str, tags: list[str]):
        """保存经验关联的标签"""
        ...

    async def delete(self, experience_id: str):
        """删除经验及关联数据"""
        ...

    async def update_score(self, experience_id: str, score: float):
        """更新经验评分"""
        ...
```

**测试点**:
- [ ] 保存经验返回正确 ID
- [ ] 关键词和标签正确关联
- [ ] 按 ID 查询返回正确数据
- [ ] 删除经验级联删除关键词和标签

---

## 二、经验检索模块

### T02-02: 关键词检索

**对应设计**: 四、经验回顾流程 → 4.1 完整流程、4.2 检索策略

**文件**: `src/yellowbull/experience/retriever.py`

**需要实现的类**:
```python
class ExperienceRetriever:
    """经验检索器"""

    def __init__(
        self,
        repo: ExperienceRepo,
        settings: ExperienceSettings,
        project_name: str | None = None,
    ):
        ...

    async def retrieve(
        self,
        task: Task,
        max_count: int | None = None,
    ) -> list[Experience]:
        """
        根据任务检索相关经验:
        1. 从 task.goal 提取关键词
        2. 按优先级检索（当前项目 → 通用 → 其他项目）
        3. 过滤过期经验
        4. 按相关度排序，取 Top K
        """
        ...

    def _extract_keywords(self, text: str) -> list[str]:
        """
        从任务描述中提取关键词:
        - 提取动词/名词
        - 提取技术栈标签（Python, Docker, MySQL 等）
        - MVP 阶段使用简单分词 + 停用词过滤
        """
        ...

    def _build_query(self, keywords: list[str]) -> str:
        """
        构建检索 SQL（来自设计文档 6.3）:
        按关键词 + 类别 + 评分 + 时间衰减计算相关度
        """
        ...

    def _filter_expired(self, experiences: list[Experience]) -> list[Experience]:
        """过滤过期经验"""
        ...

    def _deduplicate(self, experiences: list[Experience]) -> list[Experience]:
        """
        去重: 相似经验只保留评分最高的一条
        - 按 task_summary 相似度分组（MVP 用简单文本重叠度）
        - 每组保留 score 最高的一条
        """
        ...
```

**测试点**:
- [ ] 关键词正确提取
- [ ] 当前项目经验优先返回
- [ ] 过期经验被过滤
- [ ] 相似经验正确去重
- [ ] 返回数量不超过 max_count

---

## 三、经验格式化模块

### T02-03: 经验注入 Prompt

**对应设计**: 四、经验回顾流程 → 4.3 经验注入方式

**文件**: `src/yellowbull/experience/retriever.py`

**需要实现的方法**:
```python
class ExperienceRetriever:
    def format_for_prompt(self, experiences: list[Experience]) -> str:
        """
        将经验列表格式化为自然语言提示文本:
        
        输出示例:
        "过往经验:
         - 类似任务曾使用 file+shell 工具链，成功率 90%
         - 注意: 日志配置文件可能在 config/ 而非根目录
         - 建议步骤数: 4-6 步"
        """
        ...

    def format_tool_advice(self, experiences: list[Experience]) -> str:
        """提取工具使用建议"""
        ...

    def format_pitfall_warnings(self, experiences: list[Experience]) -> str:
        """提取避坑警告"""
        ...
```

**测试点**:
- [ ] 空经验列表返回空字符串
- [ ] 经验正确格式化为可读文本
- [ ] 工具建议正确提取
- [ ] 失败经验生成警告

---

## 四、经验记录模块

### T02-04: 经验总结与评分

**对应设计**: 五、经验记录流程、5.2 评分公式、八、经验总结 Prompt 设计

**文件**: `src/yellowbull/experience/recorder.py`

**需要实现的类**:
```python
class ExperienceRecorder:
    """经验记录器"""

    def __init__(
        self,
        repo: ExperienceRepo,
        llm_client: LLMClient,
        settings: ExperienceSettings,
    ):
        ...

    async def record(
        self,
        task: Task,
        task_result: TaskResult,
        project_name: str | None = None,
    ) -> Experience | None:
        """
        任务结束后记录经验:
        1. 收集执行数据
        2. 计算评分
        3. LLM 总结（生成摘要、教训、关键词、标签）
        4. 判断经验级别
        5. 持久化存储
        """
        ...

    def _calculate_score(self, task_result: TaskResult) -> float:
        """
        计算经验评分 (-1.0 ~ 1.0):
        
        score = (success_rate × 0.5)
              + (step_efficiency × 0.2)
              + (tool_effectiveness × 0.2)
              - (retry_penalty × 0.1)
        
        success_rate: 成功步骤 / 总步骤
        step_efficiency: 1 - (实际步骤数 / 理想步骤数)
        tool_effectiveness: 工具一次成功的比例
        retry_penalty: 总重试次数 × 0.1
        """
        ...

    async def _summarize_with_llm(
        self,
        task: Task,
        task_result: TaskResult,
        score: float,
    ) -> dict:
        """
        使用 LLM 总结经验:
        - 生成任务摘要（脱敏）
        - 提取经验教训
        - 自动打标签
        - 判断经验级别（generality 评分）
        
        返回:
        {
            "task_summary": str,
            "task_category": str,
            "lessons_learned": str,
            "keywords": list[str],
            "tags": list[str],
            "is_permanent": bool,
            "generality": float,
        }
        """
        ...

    def _build_summary_prompt(
        self,
        task: Task,
        task_result: TaskResult,
        score: float,
    ) -> tuple[str, str]:
        """构建经验总结 Prompt"""
        ...
```

**Prompt 模板**（存于 `src/yellowbull/prompts/experience.py`）:
```python
EXPERIENCE_SUMMARY_SYSTEM_PROMPT = """
你是经验总结专家。从本次任务执行记录中提取经验教训。
...
"""
```

**测试点**:
- [ ] 评分公式正确计算
- [ ] LLM 总结返回结构化数据
- [ ] 通用经验正确标记为永久
- [ ] 关键词和标签自动生成
- [ ] LLM 失败时降级为机械记录

---

## 五、经验老化模块

### T02-05: 老化检查与清理

**对应设计**: 七、经验老化机制

**文件**: `src/yellowbull/experience/repo.py`

**需要实现的方法**:
```python
class ExperienceRepo:
    async def mark_expired(self) -> int:
        """
        标记过期经验:
        - is_permanent = true → 永不老化
        - generality < 0.8 → 老化周期 30 天
        - generality >= 0.8 → 老化周期 180 天
        - score > 0.8 → 老化周期延长 2 倍
        - score < -0.5 → 老化周期缩短一半
        
        返回: 标记为过期的经验数量
        """
        ...

    async def cleanup_expired(self, threshold_days: int = 365) -> int:
        """
        清理过期经验:
        删除超过 2 倍老化周期的 expired 经验
        
        返回: 删除的经验数量
        """
        ...

    async def needs_maintenance(self) -> bool:
        """
        检查是否需要老化维护:
        - 经验总数 > 100
        - 或上次维护超过 7 天
        """
        ...
```

**测试点**:
- [ ] 永久经验不被标记过期
- [ ] 临时经验 30 天后过期
- [ ] 项目经验 180 天后过期
- [ ] 高分经验老化周期延长
- [ ] 低分经验快速淘汰

---

## 六、MVP 经验接口预留

### T02-06: MVP 空实现

**对应设计**: 主文档 → 经验回顾（MVP 阶段返回空列表）

**文件**: `src/yellowbull/experience/__init__.py`

**需要实现的接口**:
```python
class ExperienceService:
    """
    经验系统对外服务接口。
    MVP 阶段: 检索返回空列表，记录操作静默跳过。
    后续版本: 接入完整的经验库。
    """

    def __init__(self, settings: ExperienceSettings):
        self.enabled = settings.enabled

    async def retrieve_experiences(self, task: Task) -> list[Experience]:
        """MVP: 始终返回空列表"""
        return []

    async def record_experience(
        self,
        task: Task,
        task_result: TaskResult,
        project_name: str | None = None,
    ) -> None:
        """MVP: 静默跳过"""
        pass
```

**测试点**:
- [ ] retrieve_experiences 返回空列表
- [ ] record_experience 不报错
- [ ] enabled=False 时完全跳过

---

## 七、任务依赖顺序

```
T02-01 (经验 CRUD)
    │
    ├─→ T02-02 (关键词检索)
    │       │
    │       └─→ T02-03 (经验格式化)
    │
    ├─→ T02-04 (经验记录)
    │
    ├─→ T02-05 (老化清理)
    │
    └─→ T02-06 (MVP 空实现)
```

---

## 八、MVP 范围

| 任务 | MVP 是否必须 | 说明 |
|------|-------------|------|
| T02-01 | ✅ 是 | 经验 CRUD 基础 |
| T02-02 | ⏺ 可选 | MVP 返回空列表 |
| T02-03 | ⏺ 可选 | MVP 无经验可格式化 |
| T02-04 | ⏺ 可选 | MVP 暂不记录经验 |
| T02-05 | ⏺ 可选 | MVP 暂不老化 |
| T02-06 | ✅ 是 | MVP 空接口预留 |
