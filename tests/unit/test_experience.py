"""T02: 经验系统单元测试"""

import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yellowbull.config.settings import DatabaseSettings, ExperienceSettings
from yellowbull.experience.repo import ExperienceRepo
from yellowbull.experience.retriever import ExperienceRetriever
from yellowbull.experience.recorder import ExperienceRecorder
from yellowbull.experience import ExperienceService
from yellowbull.models.experience import Experience
from yellowbull.models.task import Task
from yellowbull.models.result import TaskResult, TaskConclusion, StepResult, StepStatus
from yellowbull.storage.db import DatabaseManager

TEST_DB_DIR = Path(__file__).resolve().parent / "test_exp_data"


@pytest.fixture(autouse=True)
async def reset_db():
    """每次测试前重置单例，测试后清理"""
    DatabaseManager._instance = None
    DatabaseManager._db = None
    yield
    try:
        if DatabaseManager._db is not None:
            await DatabaseManager._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            await DatabaseManager._db.close()
    except Exception:
        pass
    DatabaseManager._instance = None
    DatabaseManager._db = None
    await asyncio.sleep(0.1)
    if TEST_DB_DIR.exists():
        try:
            shutil.rmtree(TEST_DB_DIR)
        except Exception:
            pass


def _db_path(name: str = "test_exp.db"):
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    return str(TEST_DB_DIR / name)


def _make_experience(**kwargs):
    defaults = dict(
        id=kwargs.pop("id", "exp_001"),
        task_summary=kwargs.pop("task_summary", "测试任务"),
        task_category=kwargs.pop("task_category", "code_refactor"),
        outcome=kwargs.pop("outcome", "success"),
        score=kwargs.pop("score", 0.8),
        lessons_learned=kwargs.pop("lessons_learned", "注意路径问题"),
        tool_chain=kwargs.pop("tool_chain", ["file", "shell"]),
        steps_count=kwargs.pop("steps_count", 5),
        success_rate=kwargs.pop("success_rate", 0.9),
        retry_count=kwargs.pop("retry_count", 1),
        duration_seconds=kwargs.pop("duration_seconds", 120),
        is_permanent=kwargs.pop("is_permanent", False),
        generality=kwargs.pop("generality", 0.6),
        project_name=kwargs.pop("project_name", None),
        keywords=kwargs.pop("keywords", ["python", "重构"]),
        tags=kwargs.pop("tags", ["backend"]),
        created_at=kwargs.pop("created_at", datetime.now()),
    )
    return Experience(**defaults)


def _make_task(goal: str = "测试任务"):
    return Task(goal=goal, constraints=[], confidence=0.8)


def _make_task_result(conclusion=TaskConclusion.SUCCESS, steps=3):
    step_results = [
        StepResult(
            step_id=f"s{i}",
            status=StepStatus.DONE,
            output={"tool_type": "file"},
            retry_count=0,
            duration_seconds=10.0,
        )
        for i in range(steps)
    ]
    return TaskResult(
        task_id="task_001",
        conclusion=conclusion,
        achievement_score=0.9,
        step_results=step_results,
        total_duration_seconds=30.0,
    )


class TestExperienceRepo:
    """TC-02-01: 经验 CRUD"""

    @pytest.mark.asyncio
    async def test_save_and_get(self):
        """TC-02-01-01: 保存后能读取"""
        settings = DatabaseSettings(path=_db_path("save_get.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        exp = _make_experience()
        await repo.save(exp)
        found = await repo.get_by_id(exp.id)
        assert found is not None
        assert found.id == exp.id
        assert found.task_summary == exp.task_summary

    @pytest.mark.asyncio
    async def test_delete(self):
        """TC-02-01-02: 删除经验"""
        settings = DatabaseSettings(path=_db_path("delete.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        exp = _make_experience()
        await repo.save(exp)
        deleted = await repo.delete(exp.id)
        assert deleted is True
        found = await repo.get_by_id(exp.id)
        assert found is None

    @pytest.mark.asyncio
    async def test_update_score(self):
        """TC-02-01-03: 更新评分"""
        settings = DatabaseSettings(path=_db_path("update.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        exp = _make_experience()
        await repo.save(exp)
        updated = await repo.update_score(exp.id, 0.95)
        assert updated is True
        found = await repo.get_by_id(exp.id)
        assert found.score == 0.95

    @pytest.mark.asyncio
    async def test_save_empty_summary_raises(self):
        """TC-02-01-04: 空摘要拒绝保存"""
        settings = DatabaseSettings(path=_db_path("empty.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        exp = _make_experience(task_summary="")
        with pytest.raises(ValueError):
            await repo.save(exp)

    @pytest.mark.asyncio
    async def test_list_by_category(self):
        """TC-02-01-05: 按类别查询"""
        settings = DatabaseSettings(path=_db_path("category.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        await repo.save(_make_experience(id="e1", task_category="refactor"))
        await repo.save(_make_experience(id="e2", task_category="refactor"))
        await repo.save(_make_experience(id="e3", task_category="debug"))
        results = await repo.list_by_category("refactor")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_by_keywords(self):
        """TC-02-01-06: 关键词搜索"""
        settings = DatabaseSettings(path=_db_path("keyword.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        exp = _make_experience(keywords=["python", "重构", "测试"])
        await repo.save(exp)
        results = await repo.search_by_keywords(["python"])
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_needs_maintenance(self):
        """TC-02-01-07: 维护检查"""
        settings = DatabaseSettings(path=_db_path("maint.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        needs = await repo.needs_maintenance()
        assert isinstance(needs, bool)

    @pytest.mark.asyncio
    async def test_mark_expired(self):
        """TC-02-01-08: 标记过期"""
        settings = DatabaseSettings(path=_db_path("expire.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        exp = _make_experience(is_permanent=False)
        await repo.save(exp)
        count = await repo.mark_expired()
        assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        """TC-02-01-09: 清理过期"""
        settings = DatabaseSettings(path=_db_path("cleanup.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        count = await repo.cleanup_expired()
        assert isinstance(count, int)


class TestExperienceRetriever:
    """TC-02-02: 经验检索"""

    def test_extract_keywords_english(self):
        """TC-02-02-01: 英文关键词提取"""
        repo = MagicMock()
        ret = ExperienceRetriever(repo, ExperienceSettings())
        keywords = ret._extract_keywords("Fix python docker mysql issue")
        assert "python" in keywords
        assert "docker" in keywords

    def test_extract_keywords_chinese(self):
        """TC-02-02-02: 中文关键词提取"""
        repo = MagicMock()
        ret = ExperienceRetriever(repo, ExperienceSettings())
        keywords = ret._extract_keywords("修复Python代码中的重构问题")
        assert len(keywords) > 0

    def test_extract_keywords_empty(self):
        """TC-02-02-03: 空输入"""
        repo = MagicMock()
        ret = ExperienceRetriever(repo, ExperienceSettings())
        keywords = ret._extract_keywords("")
        assert keywords == []

    def test_text_similarity(self):
        """TC-02-02-04: 文本相似度"""
        ret = ExperienceRetriever(MagicMock(), ExperienceSettings())
        sim = ret._text_similarity("Python重构代码", "重构Python代码")
        assert 0 < sim <= 1.0

    def test_text_similarity_zero(self):
        """TC-02-02-05: 完全不相关"""
        ret = ExperienceRetriever(MagicMock(), ExperienceSettings())
        sim = ret._text_similarity("Python", "12345")
        assert sim == 0.0

    def test_format_for_prompt_empty(self):
        """TC-02-02-06: 空列表"""
        ret = ExperienceRetriever(MagicMock(), ExperienceSettings())
        result = ret.format_for_prompt([])
        assert result == ""

    def test_format_for_prompt_with_experiences(self):
        """TC-02-02-07: 有经验的格式化"""
        ret = ExperienceRetriever(MagicMock(), ExperienceSettings())
        exp = _make_experience()
        result = ret.format_for_prompt([exp])
        assert "过往经验" in result

    def test_format_tool_advice(self):
        """TC-02-02-08: 工具建议"""
        ret = ExperienceRetriever(MagicMock(), ExperienceSettings())
        exp = _make_experience(outcome="success", success_rate=0.8, tool_chain=["file", "shell"])
        result = ret.format_tool_advice([exp])
        assert "工具建议" in result

    def test_format_pitfall_warnings(self):
        """TC-02-02-09: 避坑警告"""
        ret = ExperienceRetriever(MagicMock(), ExperienceSettings())
        exp = _make_experience(outcome="failed", lessons_learned="注意权限问题")
        result = ret.format_pitfall_warnings([exp])
        assert "避坑提醒" in result


class TestExperienceRecorder:
    """TC-02-03: 经验记录"""

    @pytest.mark.asyncio
    async def test_calculate_score_success(self):
        """TC-02-03-01: 成功任务评分"""
        repo = MagicMock()
        rec = ExperienceRecorder(repo, None, ExperienceSettings())
        result = _make_task_result(TaskConclusion.SUCCESS, 5)
        score = rec._calculate_score(result)
        assert -1.0 <= score <= 1.0
        assert score > 0

    @pytest.mark.asyncio
    async def test_calculate_score_failure(self):
        """TC-02-03-02: 失败任务评分"""
        repo = MagicMock()
        rec = ExperienceRecorder(repo, None, ExperienceSettings())
        result = _make_task_result(TaskConclusion.FAILURE, 5)
        score = rec._calculate_score(result)
        assert -1.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_calculate_score_empty(self):
        """TC-02-03-03: 空步骤"""
        repo = MagicMock()
        rec = ExperienceRecorder(repo, None, ExperienceSettings())
        result = TaskResult(
            task_id="task_001",
            conclusion=TaskConclusion.FAILURE,
            achievement_score=0.0,
            step_results=[],
            total_duration_seconds=0,
        )
        score = rec._calculate_score(result)
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_record_without_llm(self):
        """TC-02-03-04: 无 LLM 时降级记录"""
        settings = DatabaseSettings(path=_db_path("no_llm.db"))
        db = await DatabaseManager.get(settings)
        await db.initialize()
        repo = ExperienceRepo(db, ExperienceSettings())
        rec = ExperienceRecorder(repo, None, ExperienceSettings())
        task = _make_task()
        result = _make_task_result()
        exp = await rec.record(task, result)
        assert exp is not None
        assert exp.task_summary is not None

    @pytest.mark.asyncio
    async def test_map_outcome(self):
        """TC-02-03-05: 结果映射"""
        assert ExperienceRecorder._map_outcome(TaskConclusion.SUCCESS) == "success"
        assert ExperienceRecorder._map_outcome(TaskConclusion.FAILURE) == "failed"
        assert ExperienceRecorder._map_outcome(TaskConclusion.PARTIAL_SUCCESS) == "partial"
        assert ExperienceRecorder._map_outcome(TaskConclusion.CANCELLED) == "failed"

    def test_extract_tool_chain(self):
        """TC-02-03-06: 工具链提取"""
        steps = [
            StepResult(step_id="s1", status=StepStatus.DONE, output={"tool_type": "file"}, retry_count=0, duration_seconds=1.0),
            StepResult(step_id="s2", status=StepStatus.DONE, output={"tool_type": "shell"}, retry_count=0, duration_seconds=1.0),
            StepResult(step_id="s3", status=StepStatus.DONE, output={"tool_type": "file"}, retry_count=0, duration_seconds=1.0),
        ]
        chain = ExperienceRecorder._extract_tool_chain(steps)
        assert "file" in chain
        assert "shell" in chain
        assert len(chain) == 2  # 去重

    def test_fallback_keywords(self):
        """TC-02-03-07: 降级关键词提取"""
        keywords = ExperienceRecorder._fallback_keywords("Python 重构代码")
        assert len(keywords) > 0


class TestExperienceService:
    """TC-02-04: MVP 服务接口"""

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_mvp(self):
        """TC-02-04-01: MVP 检索返回空列表"""
        settings = ExperienceSettings(enabled=True)
        svc = ExperienceService(settings)
        task = _make_task()
        result = await svc.retrieve_experiences(task)
        assert result == []

    @pytest.mark.asyncio
    async def test_record_noop_mvp(self):
        """TC-02-04-02: MVP 记录静默跳过"""
        settings = ExperienceSettings(enabled=True)
        svc = ExperienceService(settings)
        task = _make_task()
        result = _make_task_result()
        await svc.record_experience(task, result)

    @pytest.mark.asyncio
    async def test_disabled_service(self):
        """TC-02-04-03: 禁用时直接返回"""
        settings = ExperienceSettings(enabled=False)
        svc = ExperienceService(settings)
        task = _make_task()
        assert await svc.retrieve_experiences(task) == []
        await svc.record_experience(task, _make_task_result())

    def test_enabled_flag(self):
        """TC-02-04-04: enabled 标志"""
        enabled_svc = ExperienceService(ExperienceSettings(enabled=True))
        assert enabled_svc.enabled is True
        disabled_svc = ExperienceService(ExperienceSettings(enabled=False))
        assert disabled_svc.enabled is False
