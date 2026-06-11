"""经验检索器

根据任务描述提取关键词，检索相关经验，格式化后注入 Prompt。
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from yellowbull.config.settings import ExperienceSettings
from yellowbull.experience.repo import ExperienceRepo
from yellowbull.models.experience import Experience
from yellowbull.models.task import Task

logger = logging.getLogger(__name__)

# 中文/英文通用停用词
_STOP_WORDS = {
    # 英文
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "and",
    "but", "or", "nor", "not", "so", "yet", "both", "either", "neither",
    "each", "every", "all", "any", "few", "more", "most", "other",
    "some", "such", "no", "only", "own", "same", "than", "too", "very",
    "this", "that", "these", "those", "it", "its", "i", "me", "my",
    "we", "our", "you", "your", "he", "him", "his", "she", "her",
    "they", "them", "their", "what", "which", "who", "whom",
    # 中文
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
    "们", "那", "个", "里", "被", "让", "给", "把", "从", "到",
    "与", "及", "而", "且", "或", "但", "因为", "所以", "如果",
}

# 技术栈关键词（提升匹配优先级）
_TECH_KEYWORDS = {
    "python", "java", "javascript", "typescript", "docker", "kubernetes",
    "mysql", "postgres", "redis", "mongodb", "elasticsearch",
    "linux", "windows", "macos", "git", "npm", "pip", "maven",
    "nginx", "apache", "vue", "react", "angular", "flask", "django",
    "spring", "go", "rust", "c++", "c#", "php", "ruby", "swift",
    "kotlin", "scala", "r", "matlab", "tensorflow", "pytorch",
    "sql", "html", "css", "json", "yaml", "xml", "csv",
    "ssh", "ftp", "http", "https", "api", "rest", "graphql",
    "webpack", "vite", "eslint", "prettier", "pytest", "jest",
    "ansible", "terraform", "jenkins", "github", "gitlab",
    "log", "日志", "配置", "部署", "调试", "重构", "测试",
    "环境", "依赖", "权限", "网络", "数据库", "缓存", "队列",
}


class ExperienceRetriever:
    """经验检索器"""

    def __init__(
        self,
        repo: ExperienceRepo,
        settings: ExperienceSettings,
        project_name: str | None = None,
    ):
        self._repo = repo
        self._settings = settings
        self._project_name = project_name

    async def retrieve(
        self,
        task: Task,
        max_count: int | None = None,
    ) -> list[Experience]:
        """根据任务检索相关经验

        流程:
        1. 从 task.goal 提取关键词
        2. 按优先级检索（当前项目 → 通用 → 其他项目）
        3. 过滤过期经验
        4. 按相关度排序，取 Top K

        Args:
            task: 任务对象
            max_count: 最大返回条数，默认使用配置值

        Returns:
            相关经验列表
        """
        limit = max_count or self._settings.max_retrieve_count

        # 从任务中提取关键词
        keywords = self._extract_keywords(task.goal)
        if task.constraints:
            for constraint in task.constraints:
                keywords.extend(self._extract_keywords(constraint))

        if not keywords:
            return []

        # 去重
        keywords = list(dict.fromkeys(keywords))

        # 搜索经验
        experiences = await self._repo.search_by_keywords(
            keywords,
            project_name=self._project_name,
            limit=limit * 2,  # 多取一些以便后续去重
        )

        # 过滤过期 + 去重
        experiences = self._filter_expired(experiences)
        experiences = self._deduplicate(experiences)

        # 截取 Top K
        return experiences[:limit]

    def _extract_keywords(self, text: str) -> list[str]:
        """从任务描述中提取关键词

        策略:
        - 提取技术栈标签（高优先级）
        - 简单分词 + 停用词过滤
        - 保留长度 >= 2 的词
        """
        if not text:
            return []

        keywords = []

        # 1. 提取技术栈关键词（不区分大小写）
        text_lower = text.lower()
        for tech in _TECH_KEYWORDS:
            if tech.lower() in text_lower:
                keywords.append(tech)

        # 2. 简单分词（中英文混合）
        # 提取英文单词
        english_words = re.findall(r'[a-zA-Z_]+', text)
        for word in english_words:
            w = word.lower().strip()
            if len(w) >= 2 and w not in _STOP_WORDS and w not in keywords:
                keywords.append(w)

        # 提取中文词（简单按标点/空格切分）
        chinese_parts = re.findall(r'[\u4e00-\u9fff]{2,}', text)
        for part in chinese_parts:
            if part not in _STOP_WORDS:
                keywords.append(part)

        # 3. 按频率排序，取前 20 个
        counter = Counter(keywords)
        return [word for word, _ in counter.most_common(20)]

    def _filter_expired(self, experiences: list[Experience]) -> list[Experience]:
        """过滤过期经验"""
        now = datetime.now()
        result = []
        for exp in experiences:
            if exp.is_permanent:
                result.append(exp)
                continue

            age_days = (now - exp.created_at).days
            if exp.generality >= 0.8:
                if age_days < self._settings.aging_period_project:
                    result.append(exp)
            else:
                if age_days < self._settings.aging_period_temporary:
                    result.append(exp)
        return result

    def _deduplicate(self, experiences: list[Experience]) -> list[Experience]:
        """去重: 相似经验只保留评分最高的一条

        按 task_summary 相似度分组（简单文本重叠度），
        每组保留 score 最高的一条。
        """
        if len(experiences) <= 1:
            return experiences

        deduped = []
        used_indices = set()

        for i, exp in enumerate(experiences):
            if i in used_indices:
                continue

            best = exp
            best_idx = i
            used_indices.add(i)

            # 与后续经验比较
            for j in range(i + 1, len(experiences)):
                if j in used_indices:
                    continue

                similarity = self._text_similarity(
                    exp.task_summary, experiences[j].task_summary
                )
                if similarity > 0.6:  # 相似度阈值
                    used_indices.add(j)
                    if experiences[j].score > best.score:
                        best = experiences[j]
                        best_idx = j

            deduped.append(best)

        return deduped

    @staticmethod
    def _text_similarity(text_a: str, text_b: str) -> float:
        """简单文本重叠度计算（Jaccard 相似度）"""
        if not text_a or not text_b:
            return 0.0

        set_a = set(re.findall(r'[\u4e00-\u9fff]{1,4}|[a-zA-Z]+', text_a))
        set_b = set(re.findall(r'[\u4e00-\u9fff]{1,4}|[a-zA-Z]+', text_b))

        if not set_a or not set_b:
            return 0.0

        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)

    # ── 格式化方法 ────────────────────────────────────────

    def format_for_prompt(self, experiences: list[Experience]) -> str:
        """将经验列表格式化为自然语言提示文本

        输出示例:
        "过往经验:
         - 类似任务曾使用 file+shell 工具链，成功率 90%
         - 注意: 日志配置文件可能在 config/ 而非根目录
         - 建议步骤数: 4-6 步"
        """
        if not experiences:
            return ""

        lines = ["\n过往经验:"]

        for exp in experiences:
            # 成功经验提示
            if exp.outcome == "success":
                tool_info = ""
                if exp.tool_chain:
                    tool_info = f" (工具链: {'+'.join(exp.tool_chain)})"
                lines.append(
                    f"  - 类似任务{tool_info}，成功率 {exp.success_rate * 100:.0f}%，"
                    f"评分 {exp.score:.1f}"
                )
                if exp.lessons_learned:
                    lines.append(f"    经验: {exp.lessons_learned}")
            elif exp.outcome == "partial":
                lines.append(
                    f"  - 部分完成任务 (评分 {exp.score:.1f})"
                )
                if exp.lessons_learned:
                    lines.append(f"    注意: {exp.lessons_learned}")
            else:
                lines.append(
                    f"  - 失败经验 (评分 {exp.score:.1f})"
                )
                if exp.lessons_learned:
                    lines.append(f"    教训: {exp.lessons_learned}")

            # 步骤建议
            if exp.steps_count > 0:
                lines.append(f"    参考步骤数: {exp.steps_count}")

        # 工具建议
        tool_advice = self.format_tool_advice(experiences)
        if tool_advice:
            lines.append(tool_advice)

        # 避坑警告
        warnings = self.format_pitfall_warnings(experiences)
        if warnings:
            lines.append(warnings)

        return "\n".join(lines)

    def format_tool_advice(self, experiences: list[Experience]) -> str:
        """提取工具使用建议"""
        if not experiences:
            return ""

        tool_counts = Counter()
        for exp in experiences:
            if exp.success_rate > 0.5:
                for tool in exp.tool_chain:
                    tool_counts[tool] += 1

        if not tool_counts:
            return ""

        top_tools = tool_counts.most_common(3)
        tools_str = ", ".join(f"{t}(使用{n}次)" for t, n in top_tools)
        return f"\n工具建议: 历史成功经验中常用工具为 {tools_str}"

    def format_pitfall_warnings(self, experiences: list[Experience]) -> str:
        """提取避坑警告（来自失败/部分成功经验）"""
        warnings = []
        for exp in experiences:
            if exp.outcome in ("failed", "partial") and exp.lessons_learned:
                # 提取警告信息
                warning = exp.lessons_learned[:200]  # 截断过长内容
                if warning not in warnings:
                    warnings.append(warning)

        if not warnings:
            return ""

        lines = ["\n避坑提醒:"]
        for w in warnings[:5]:  # 最多 5 条
            lines.append(f"  - {w}")
        return "\n".join(lines)


from datetime import datetime  # noqa: E402
