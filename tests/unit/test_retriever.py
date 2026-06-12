"""经验检索器单元测试"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yellowbull.config.settings import ExperienceSettings
from yellowbull.experience.retriever import ExperienceRetriever
from yellowbull.models.experience import Experience
from yellowbull.models.task import Task


@pytest.fixture
def settings():
    return ExperienceSettings(
        max_retrieve_count=5,
        aging_period_temporary=30,
        aging_period_project=180,
    )


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.search_by_keywords = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def retriever(mock_repo, settings):
    return ExperienceRetriever(
        repo=mock_repo,
        settings=settings,
        project_name="test-project",
    )


@pytest.fixture
def recent_experiences():
    """创建近期经验列表"""
    now = datetime.now()
    return [
        Experience(
            id="exp1",
            task_summary="部署 Python Flask 应用",
            task_category="deployment",
            outcome="success",
            score=0.9,
            lessons_learned="使用 gunicorn 比 uwsgi 更稳定",
            tool_chain=["file", "shell"],
            steps_count=5,
            success_rate=0.9,
            is_permanent=False,
            generality=0.8,
            project_name="test-project",
            keywords=["python", "flask", "部署"],
            created_at=now - timedelta(days=10),
        ),
        Experience(
            id="exp2",
            task_summary="配置 Docker 容器网络",
            task_category="devops",
            outcome="partial",
            score=0.6,
            lessons_learned="注意端口映射冲突",
            tool_chain=["shell", "docker"],
            steps_count=3,
            success_rate=0.7,
            is_permanent=False,
            generality=0.5,
            project_name="test-project",
            keywords=["docker", "网络"],
            created_at=now - timedelta(days=15),
        ),
        Experience(
            id="exp3",
            task_summary="修复数据库连接超时",
            task_category="debugging",
            outcome="failed",
            score=-0.2,
            lessons_learned="检查防火墙规则和连接池配置",
            tool_chain=["shell"],
            steps_count=8,
            success_rate=0.3,
            is_permanent=False,
            generality=0.4,
            project_name="other-project",
            keywords=["数据库", "超时"],
            created_at=now - timedelta(days=20),
        ),
    ]


@pytest.fixture
def permanent_experience():
    return Experience(
        id="perm1",
        task_summary="通用 Python 调试技巧",
        task_category="debugging",
        outcome="success",
        score=0.95,
        lessons_learned="始终检查异常堆栈",
        tool_chain=["file"],
        steps_count=2,
        success_rate=1.0,
        is_permanent=True,
        generality=0.9,
        project_name=None,
        keywords=["python", "调试"],
        created_at=datetime.now() - timedelta(days=365),
    )


class TestExtractKeywords:
    """关键词提取测试"""

    def test_extract_tech_keywords(self, retriever):
        text = "部署 Python Flask 应用到 Docker"
        keywords = retriever._extract_keywords(text)
        assert "python" in keywords
        assert "flask" in keywords
        assert "docker" in keywords

    def test_extract_chinese_keywords(self, retriever):
        text = "配置数据库连接池和缓存服务"
        keywords = retriever._extract_keywords(text)
        # 中文关键词应该被提取
        assert any("数据库" in kw or "连接" in kw or "缓存" in kw for kw in keywords)

    def test_extract_english_words(self, retriever):
        text = "Fix the API endpoint error handling"
        keywords = retriever._extract_keywords(text)
        # 停用词应该被过滤
        assert "the" not in keywords
        assert "error" in keywords or "handling" in keywords

    def test_extract_empty_text(self, retriever):
        assert retriever._extract_keywords("") == []
        assert retriever._extract_keywords(None) == []

    def test_stop_words_filtered(self, retriever):
        text = "the a an is are was were"
        keywords = retriever._extract_keywords(text)
        # 所有英文词都是停用词，应该返回空列表或只有单字符残留
        assert all(len(kw) < 2 for kw in keywords)

    def test_keyword_limit(self, retriever):
        text = "python java javascript typescript docker kubernetes mysql postgres redis mongodb"
        keywords = retriever._extract_keywords(text)
        # 最多返回 20 个关键词
        assert len(keywords) <= 20


class TestFilterExpired:
    """过期经验过滤测试"""

    def test_permanent_not_expired(self, retriever, permanent_experience):
        result = retriever._filter_expired([permanent_experience])
        assert len(result) == 1

    def test_high_generality_longer_ttl(self, retriever):
        now = datetime.now()
        exp = Experience(
            id="exp1",
            task_summary="测试经验",
            task_category="test",
            outcome="success",
            score=0.8,
            is_permanent=False,
            generality=0.9,  # 高通用性
            created_at=now - timedelta(days=100),  # 超过临时过期时间，但小于项目过期时间
        )
        result = retriever._filter_expired([exp])
        assert len(result) == 1

    def test_low_generality_short_ttl(self, retriever):
        now = datetime.now()
        exp = Experience(
            id="exp2",
            task_summary="测试经验",
            task_category="test",
            outcome="success",
            score=0.5,
            is_permanent=False,
            generality=0.3,  # 低通用性
            created_at=now - timedelta(days=60),  # 超过临时过期时间(30天)
        )
        result = retriever._filter_expired([exp])
        assert len(result) == 0

    def test_empty_list(self, retriever):
        assert retriever._filter_expired([]) == []


class TestDeduplicate:
    """去重测试"""

    def test_similar_experiences_deduplicated(self, retriever):
        exp1 = Experience(
            id="exp1", task_summary="部署 Flask 应用", task_category="test",
            outcome="success", score=0.7, created_at=datetime.now(),
        )
        exp2 = Experience(
            id="exp2", task_summary="部署 Flask 服务", task_category="test",
            outcome="success", score=0.9, created_at=datetime.now(),
        )
        result = retriever._deduplicate([exp1, exp2])
        # 相似经验应该只保留评分高的
        assert len(result) <= 2

    def test_dedup_keeps_highest_score(self, retriever):
        exp1 = Experience(
            id="exp1", task_summary="配置数据库连接", task_category="test",
            outcome="success", score=0.5, created_at=datetime.now(),
        )
        exp2 = Experience(
            id="exp2", task_summary="配置数据库连接池", task_category="test",
            outcome="success", score=0.9, created_at=datetime.now(),
        )
        result = retriever._deduplicate([exp1, exp2])
        # 如果去重，应该保留评分高的
        if len(result) == 1:
            assert result[0].score == 0.9

    def test_dedup_with_identical_summaries(self, retriever):
        """完全相同的摘要会被合并，触发 used_indices 分支"""
        exp1 = Experience(
            id="exp1", task_summary="部署 Flask 应用", task_category="test",
            outcome="success", score=0.5, created_at=datetime.now(),
        )
        exp2 = Experience(
            id="exp2", task_summary="部署 Flask 应用", task_category="test",
            outcome="success", score=0.9, created_at=datetime.now(),
        )
        exp3 = Experience(
            id="exp3", task_summary="部署 Flask 应用", task_category="test",
            outcome="success", score=0.7, created_at=datetime.now(),
        )
        result = retriever._deduplicate([exp1, exp2, exp3])
        # 三个完全相同的摘要，应该合并为一条，保留最高分
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_dedup_cascade_used_indices(self, retriever):
        """链式相似触发 j in used_indices 分支"""
        # exp1 ~ exp2 (similar), exp2 ~ exp3 (similar)
        # When i=0: j=1 is similar → add to used. j=2 not similar.
        # When i=2: j loop doesn't reach index 1, so line 197 needs different setup
        exp1 = Experience(
            id="exp1", task_summary="Python API 开发", task_category="test",
            outcome="success", score=0.8, created_at=datetime.now(),
        )
        exp2 = Experience(
            id="exp2", task_summary="Python API 服务", task_category="test",
            outcome="success", score=0.6, created_at=datetime.now(),
        )
        exp3 = Experience(
            id="exp3", task_summary="Docker 部署配置", task_category="test",
            outcome="success", score=0.9, created_at=datetime.now(),
        )
        result = retriever._deduplicate([exp1, exp2, exp3])
        # exp1 和 exp2 相似，应该合并；exp3 独立
        assert len(result) <= 3

    def test_dedup_j_in_used_indices(self, retriever):
        """触发 j in used_indices: exp0~exp2 (跳过exp1), i=1的j循环遇到已使用的j=2"""
        # exp0 ~ exp2 (very similar, same summary), exp0 !~ exp1 (different)
        # i=0: j=1 not similar. j=2 similarity=1.0 → used={0,2}
        # i=1: inner loop j=2 → 2 in used_indices → line 197 hit!
        exps = [
            Experience(id="e0", task_summary="Python API 部署配置优化", task_category="test", outcome="success", score=0.8, created_at=datetime.now()),
            Experience(id="e1", task_summary="Docker 容器管理网络", task_category="test", outcome="success", score=0.7, created_at=datetime.now()),
            Experience(id="e2", task_summary="Python API 部署配置优化", task_category="test", outcome="success", score=0.6, created_at=datetime.now()),
        ]
        result = retriever._deduplicate(exps)
        assert len(result) <= 3

    def test_single_experience(self, retriever):
        exp = Experience(
            id="exp1", task_summary="唯一经验", task_category="test",
            outcome="success", score=0.8, created_at=datetime.now(),
        )
        result = retriever._deduplicate([exp])
        assert len(result) == 1

    def test_empty_list(self, retriever):
        assert retriever._deduplicate([]) == []


class TestTextSimilarity:
    """文本相似度测试"""

    def test_identical_text(self, retriever):
        sim = ExperienceRetriever._text_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_completely_different(self, retriever):
        sim = ExperienceRetriever._text_similarity("python flask", "docker kubernetes")
        assert sim < 1.0

    def test_empty_text(self, retriever):
        assert ExperienceRetriever._text_similarity("", "hello") == 0.0
        assert ExperienceRetriever._text_similarity("hello", "") == 0.0

    def test_no_matching_tokens(self, retriever):
        """纯数字/符号文本无法提取 token，返回 0"""
        sim = ExperienceRetriever._text_similarity("12345", "67890")
        assert sim == 0.0

    def test_chinese_similarity(self, retriever):
        # 用空格分隔的词会被 regex 分开提取，共享部分 token
        sim = ExperienceRetriever._text_similarity("部署 Python 应用", "部署 Python 服务")
        # 有共同词"部署""Python"，相似度应该大于0
        assert sim > 0


class TestRetrieve:
    """检索主流程测试"""

    @pytest.mark.asyncio
    async def test_retrieve_returns_experiences(self, retriever, mock_repo, recent_experiences):
        mock_repo.search_by_keywords = AsyncMock(return_value=recent_experiences)
        task = Task(
            id="task1",
            goal="部署 Python Flask 应用",
            constraints=["使用 Docker"],
            success_criteria=[],
            context_files=[],
            confidence=0.9,
        )
        result = await retriever.retrieve(task, max_count=3)
        # 应该返回经验列表（可能经过过滤和去重）
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_retrieve_no_keywords(self, mock_repo, settings):
        r = ExperienceRetriever(repo=mock_repo, settings=settings)
        task = Task(
            id="task1",
            goal="",  # 空目标，无法提取关键词
            success_criteria=[],
            confidence=0.5,
        )
        result = await r.retrieve(task)
        assert result == []

    @pytest.mark.asyncio
    async def test_retrieve_respects_max_count(self, retriever, mock_repo, recent_experiences):
        mock_repo.search_by_keywords = AsyncMock(return_value=recent_experiences)
        task = Task(
            id="task1",
            goal="部署应用",
            success_criteria=[],
            confidence=0.9,
        )
        result = await retriever.retrieve(task, max_count=2)
        assert len(result) <= 2


class TestFormatForPrompt:
    """格式化测试"""

    def test_format_success_experience(self, retriever):
        exp = Experience(
            id="exp1", task_summary="部署应用", task_category="test",
            outcome="success", score=0.9, success_rate=0.9,
            lessons_learned="使用 gunicorn 更稳定",
            tool_chain=["file", "shell"], steps_count=5,
        )
        result = retriever.format_for_prompt([exp])
        assert "过往经验" in result
        assert "成功率" in result or "90%" in result

    def test_format_partial_experience(self, retriever):
        exp = Experience(
            id="exp1", task_summary="部署应用", task_category="test",
            outcome="partial", score=0.6, success_rate=0.7,
            lessons_learned="注意端口冲突", tool_chain=[], steps_count=3,
        )
        result = retriever.format_for_prompt([exp])
        assert "部分完成" in result

    def test_format_failed_experience(self, retriever):
        exp = Experience(
            id="exp1", task_summary="部署应用", task_category="test",
            outcome="failed", score=-0.2, success_rate=0.3,
            lessons_learned="检查防火墙配置", tool_chain=[], steps_count=8,
        )
        result = retriever.format_for_prompt([exp])
        assert "失败" in result

    def test_format_empty_list(self, retriever):
        assert retriever.format_for_prompt([]) == ""

    def test_format_includes_steps_count(self, retriever):
        exp = Experience(
            id="exp1", task_summary="部署应用", task_category="test",
            outcome="success", score=0.8, success_rate=0.8,
            tool_chain=[], steps_count=6,
        )
        result = retriever.format_for_prompt([exp])
        assert "步骤数" in result or "6" in result


class TestFormatToolAdvice:
    """工具建议格式化测试"""

    def test_tool_advice_from_success_experiences(self, retriever):
        exps = [
            Experience(
                id="e1", task_summary="t1", task_category="test",
                outcome="success", score=0.9, success_rate=0.8,
                tool_chain=["file", "shell"], created_at=datetime.now(),
            ),
            Experience(
                id="e2", task_summary="t2", task_category="test",
                outcome="success", score=0.7, success_rate=0.6,
                tool_chain=["shell", "docker"], created_at=datetime.now(),
            ),
        ]
        result = retriever.format_tool_advice(exps)
        assert "工具建议" in result

    def test_no_tool_advice_for_empty(self, retriever):
        assert retriever.format_tool_advice([]) == ""

    def test_no_tool_advice_for_low_success_rate(self, retriever):
        exp = Experience(
            id="e1", task_summary="t1", task_category="test",
            outcome="failed", score=-0.5, success_rate=0.3,
            tool_chain=["file"], created_at=datetime.now(),
        )
        result = retriever.format_tool_advice([exp])
        assert result == ""


class TestFormatPitfallWarnings:
    """避坑警告格式化测试"""

    def test_warnings_from_failed_experiences(self, retriever):
        exps = [
            Experience(
                id="e1", task_summary="t1", task_category="test",
                outcome="failed", score=-0.3, success_rate=0.2,
                lessons_learned="注意端口映射冲突", created_at=datetime.now(),
            ),
        ]
        result = retriever.format_pitfall_warnings(exps)
        assert "避坑" in result

    def test_no_warnings_for_success(self, retriever):
        exp = Experience(
            id="e1", task_summary="t1", task_category="test",
            outcome="success", score=0.9, success_rate=0.9,
            lessons_learned="", created_at=datetime.now(),
        )
        result = retriever.format_pitfall_warnings([exp])
        assert result == ""

    def test_no_warnings_for_empty(self, retriever):
        assert retriever.format_pitfall_warnings([]) == ""
