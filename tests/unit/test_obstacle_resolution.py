"""T03-05: 障碍排除测试"""

import pytest
from unittest.mock import AsyncMock

from yellowbull.agent.step_state import StepState
from yellowbull.agent.obstacle_resolver import ObstacleResolver, ObstacleAnalysis
from yellowbull.models.step import Step


@pytest.fixture
def llm_client():
    client = AsyncMock()
    return client


@pytest.fixture
def resolver(llm_client):
    return ObstacleResolver(llm_client)


@pytest.fixture
def failed_step():
    return Step(
        step_id="s1",
        description="读取配置文件",
        tool_hint="file",
    )


@pytest.fixture
def step_state():
    state = StepState("s1")
    state.retry_count = 0
    return state


class TestObstacleDetection:
    """TC-03-05-01 ~ TC-03-05-04"""

    @pytest.mark.asyncio
    async def test_obstacle_detected(self, resolver, failed_step, step_state):
        """TC-03-05-01: 障碍被正确检测并分析"""
        resolver.llm_client.chat = AsyncMock(
            return_value="原因：文件不存在\n建议：创建文件\n可恢复"
        )

        result = await resolver.resolve(failed_step, step_state, "文件读取失败")

        assert isinstance(result, ObstacleAnalysis)
        assert result.cause is not None
        assert result.suggestion is not None

    @pytest.mark.asyncio
    async def test_recovery_suggestion(self, resolver, failed_step, step_state):
        """TC-03-05-02: 方案生成合理"""
        resolver.llm_client.chat = AsyncMock(
            return_value="原因：权限不足\n建议：检查文件权限\ntrue"
        )

        result = await resolver.resolve(failed_step, step_state, "权限拒绝")

        assert isinstance(result, ObstacleAnalysis)
        assert result.is_recoverable is True
        assert "权限" in result.suggestion or len(result.suggestion) > 0

    @pytest.mark.asyncio
    async def test_subtask_execution(self, resolver, failed_step, step_state):
        """TC-03-05-03: 子任务执行建议包含在方案中"""
        resolver.llm_client.chat = AsyncMock(
            return_value="原因：依赖缺失\n建议：先安装依赖再重试\ntrue"
        )

        result = await resolver.resolve(failed_step, step_state, "依赖错误")

        assert isinstance(result, ObstacleAnalysis)
        assert result.is_recoverable is True

    @pytest.mark.asyncio
    async def test_flow_recovery(self, resolver, failed_step, step_state):
        """TC-03-05-04: 可恢复障碍标记正确"""
        resolver.llm_client.chat = AsyncMock(
            return_value="原因：临时网络故障\n建议：重试连接\ntrue"
        )

        result = await resolver.resolve(failed_step, step_state, "连接超时")

        assert isinstance(result, ObstacleAnalysis)
        assert result.is_recoverable is True


class TestObstacleUnrecoverable:
    """TC-03-05 不可恢复障碍"""

    @pytest.mark.asyncio
    async def test_unrecoverable_obstacle(self, resolver, failed_step, step_state):
        """不可恢复障碍正确标记"""
        resolver.llm_client.chat = AsyncMock(
            return_value="原因：配置错误\n建议：修改配置\nfalse"
        )

        result = await resolver.resolve(failed_step, step_state, "配置无效")

        assert isinstance(result, ObstacleAnalysis)
        assert result.is_recoverable is False


class TestObstacleWithRetry:
    """TC-03-05 带重试次数"""

    @pytest.mark.asyncio
    async def test_retry_count_in_context(self, resolver, failed_step):
        """重试次数包含在分析上下文中"""
        step_state = StepState("s1")
        step_state.retry_count = 3

        resolver.llm_client.chat = AsyncMock(
            return_value="原因：持续失败\n建议：检查配置\ntrue"
        )

        result = await resolver.resolve(failed_step, step_state, "重复失败")

        assert isinstance(result, ObstacleAnalysis)
        # 验证 LLM 被调用且包含重试次数信息
        call_args = resolver.llm_client.chat.call_args
        assert "重试次数: 3" in str(call_args)


class TestObstacleWithContext:
    """TC-03-05 带额外上下文"""

    @pytest.mark.asyncio
    async def test_extra_context_passed(self, resolver, failed_step, step_state):
        """额外上下文传递给 LLM"""
        context = {"env": "production", "user": "admin"}

        resolver.llm_client.chat = AsyncMock(
            return_value="原因：环境问题\n建议：检查环境配置\ntrue"
        )

        result = await resolver.resolve(
            failed_step, step_state, "执行失败", context=context
        )

        assert isinstance(result, ObstacleAnalysis)
        call_args = resolver.llm_client.chat.call_args
        assert "production" in str(call_args)


class TestObstacleLLMFailure:
    """TC-03-05 LLM 故障"""

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self, resolver, failed_step, step_state):
        """LLM 调用失败时返回 None"""
        resolver.llm_client.chat = AsyncMock(side_effect=Exception("服务不可用"))

        result = await resolver.resolve(failed_step, step_state, "执行失败")

        assert result is None


class TestObstacleParseAnalysis:
    """TC-03-05 解析分析"""

    def test_parse_recoverable_true(self, resolver):
        """解析 true 为可恢复"""
        result = resolver._parse_analysis("true", "错误信息")
        assert result.is_recoverable is True

    def test_parse_recoverable_chinese(self, resolver):
        """解析中文可恢复标记"""
        result = resolver._parse_analysis("可以解决，建议重试", "错误信息")
        assert result.is_recoverable is True

    def test_parse_unrecoverable_false(self, resolver):
        """解析 false 为不可恢复"""
        result = resolver._parse_analysis("false", "错误信息")
        assert result.is_recoverable is False

    def test_parse_long_response_truncated(self, resolver):
        """长响应被截断"""
        long_response = "a" * 1000
        result = resolver._parse_analysis(long_response, "错误信息")
        assert len(result.suggestion) <= 500
