"""T01-01 ~ T01-06: 任务接收模块单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from yellowbull.agent.receiver import (
    TaskReceiver,
    PreprocessedInput,
    InputIntent,
    DangerLevel,
    DangerCheckResult,
    ConversationBuffer,
    ConversationRound,
    TaskParseResult,
    _rule_based_check,
    _is_control,
    _is_chat,
)
from yellowbull.config.settings import Settings
from yellowbull.models.task import Task, TaskStatus
from yellowbull.llm.client import LLMClient


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "yellowbull_data")


@pytest.fixture
def mock_llm():
    return MagicMock(spec=LLMClient)


@pytest.fixture
def receiver(mock_llm, settings):
    return TaskReceiver(mock_llm, settings)


# ==================== T01-01: 输入预处理 ====================

class TestPreprocessInput:
    """TC-01-01-01 ~ TC-01-01-04"""

    @pytest.mark.asyncio
    async def test_normal_input(self, receiver):
        """TC-01-01-01: 正常输入"""
        result = await receiver.preprocess_input("读取 src/main.py 文件")
        assert result.cleaned_text == "读取 src/main.py 文件"
        assert result.is_truncated is False

    @pytest.mark.asyncio
    async def test_empty_input(self, receiver):
        """TC-01-01-02: 空输入"""
        result = await receiver.preprocess_input("")
        assert result.cleaned_text == ""

    @pytest.mark.asyncio
    async def test_whitespace_only(self, receiver):
        """TC-01-01-02: 纯空白输入"""
        result = await receiver.preprocess_input("   \n\n  ")
        assert result.cleaned_text == ""

    @pytest.mark.asyncio
    async def test_truncation(self, receiver):
        """TC-01-01-03: 超长输入截断"""
        long_text = "a" * 5000
        result = await receiver.preprocess_input(long_text)
        assert result.is_truncated is True
        assert result.cleaned_text.endswith("...(内容已截断)")

    @pytest.mark.asyncio
    async def test_code_block_extraction(self, receiver):
        """TC-01-01-04: 代码块识别"""
        text = '这段代码有问题:\n```python\nprint("hello")\n```'
        result = await receiver.preprocess_input(text)
        assert len(result.code_contexts) > 0

    @pytest.mark.asyncio
    async def test_file_reference_extraction(self, receiver):
        """TC-01-01-05: 文件引用识别"""
        text = "请查看 src/main.py 和 @README.md"
        result = await receiver.preprocess_input(text)
        assert "src/main.py" in result.file_references or "README.md" in result.file_references

    @pytest.mark.asyncio
    async def test_newline_normalization(self, receiver):
        """TC-01-01-06: 换行符统一"""
        text = "line1\r\nline2\rline3"
        result = await receiver.preprocess_input(text)
        assert "\r" not in result.cleaned_text


# ==================== T01-02: 意图分类 ====================

class TestIntentClassification:
    """TC-01-02-01 ~ TC-01-02-04"""

    @pytest.mark.asyncio
    async def test_new_task(self, receiver):
        """TC-01-02-01: 新任务"""
        intent = await receiver.classify_intent("读取 src/main.py 文件并检查语法")
        assert intent == InputIntent.NEW_TASK

    @pytest.mark.asyncio
    async def test_control_command(self, receiver):
        """TC-01-02-02: 控制指令"""
        intent = await receiver.classify_intent("退出")
        assert intent == InputIntent.CONTROL

    @pytest.mark.asyncio
    async def test_chat(self, receiver):
        """TC-01-02-03: 闲聊"""
        intent = await receiver.classify_intent("你好")
        assert intent == InputIntent.CHAT

    @pytest.mark.asyncio
    async def test_supplement(self, receiver):
        """TC-01-02-04: 补充信息"""
        receiver._conversation.add_round("原始任务", "")
        intent = await receiver.classify_intent("多加个约束", has_context=True)
        assert intent == InputIntent.SUPPLEMENT

    @pytest.mark.asyncio
    async def test_empty_input(self, receiver):
        """TC-01-02-05: 空输入视为闲聊"""
        intent = await receiver.classify_intent("")
        assert intent == InputIntent.CHAT


# ==================== 控制指令处理 ====================

class TestControlCommands:
    """TC-01-02-06 ~ TC-01-02-10"""

    def test_quit_command(self, receiver):
        result = receiver.handle_control_command("退出")
        assert result is None

    def test_cancel_command(self, receiver):
        result = receiver.handle_control_command("取消")
        assert "取消" in result

    def test_help_command(self, receiver):
        result = receiver.handle_control_command("帮助")
        assert "帮助" in result or "使用" in result

    def test_status_command(self, receiver):
        result = receiver.handle_control_command("状态")
        assert "任务" in result

    def test_unknown_command(self, receiver):
        result = receiver.handle_control_command("未知指令")
        assert "未知" in result


# ==================== 对话缓冲区 ====================

class TestConversationBuffer:
    """TC-01-02-11 ~ TC-01-02-13"""

    def test_add_round(self):
        buf = ConversationBuffer(max_rounds=5)
        buf.add_round("用户输入", "助手回复")
        assert len(buf.rounds) == 1

    def test_max_rounds_eviction(self):
        buf = ConversationBuffer(max_rounds=3)
        for i in range(5):
            buf.add_round(f"输入{i}", f"回复{i}")
        assert len(buf.rounds) == 3
        # 最早的两轮已被淘汰
        assert buf.rounds[0].user_input == "输入2"

    def test_get_full_context(self):
        buf = ConversationBuffer()
        buf.add_round("问题1", "回答1")
        buf.add_round("问题2", "回答2")
        context = buf.get_full_context()
        assert "问题1" in context
        assert "回答1" in context
        assert "问题2" in context

    def test_empty_buffer(self):
        buf = ConversationBuffer()
        assert buf.is_empty() is True
        assert buf.get_full_context() == ""

    def test_clear(self):
        buf = ConversationBuffer()
        buf.add_round("input", "output")
        buf.clear()
        assert buf.is_empty() is True


# ==================== 危险操作检查 ====================

class TestDangerCheck:
    """TC-01-06-01 ~ TC-01-06-04"""

    def test_red_danger_rm(self):
        result = _rule_based_check("rm -rf /")
        assert result.level == DangerLevel.RED

    def test_red_danger_drop_table(self):
        result = _rule_based_check("DROP TABLE users")
        assert result.level == DangerLevel.RED

    def test_yellow_danger_install(self):
        result = _rule_based_check("pip install package")
        assert result.level == DangerLevel.YELLOW

    def test_green_safe(self):
        result = _rule_based_check("读取 src/main.py 文件")
        assert result.level == DangerLevel.GREEN

    def test_case_insensitive(self):
        result = _rule_based_check("drop table users")
        assert result.level == DangerLevel.RED


# ==================== LLM 任务解析 ====================

class TestTaskParse:
    """TC-01-04-01 ~ TC-01-04-03"""

    @pytest.mark.asyncio
    async def test_parse_success(self, receiver):
        """TC-01-04-01: 正常解析"""
        mock_result = TaskParseResult(
            goal="读取文件",
            confidence=0.9,
        )
        receiver._llm.structured_chat = AsyncMock(return_value=mock_result)

        result = await receiver.parse_task("读取 src/main.py")
        assert result.goal == "读取文件"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_parse_failure_fallback(self, receiver):
        """TC-01-04-02: LLM 解析失败降级"""
        receiver._llm.structured_chat = AsyncMock(side_effect=Exception("LLM 失败"))

        result = await receiver.parse_task("读取文件")
        assert result.goal == "读取文件"
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_parse_with_context(self, receiver):
        """TC-01-04-03: 带上下文的解析"""
        mock_result = TaskParseResult(goal="任务", confidence=0.8)
        receiver._llm.structured_chat = AsyncMock(return_value=mock_result)

        result = await receiver.parse_task("输入", context="之前的对话")
        assert result is not None


# ==================== 置信度评估 ====================

class TestConfidenceEvaluation:
    """TC-01-05-01 ~ TC-01-05-03"""

    @pytest.mark.asyncio
    async def test_high_confidence(self, receiver):
        """TC-01-05-01: 高置信度直接创建"""
        parse_result = TaskParseResult(goal="读取文件", confidence=0.9)
        task = await receiver.evaluate_and_confirm(parse_result)
        assert task is not None
        assert task.goal == "读取文件"

    @pytest.mark.asyncio
    async def test_medium_confidence_confirmed(self, receiver):
        """TC-01-05-02: 中置信度确认后创建"""
        parse_result = TaskParseResult(goal="读取文件", confidence=0.6)
        on_confirm = AsyncMock(return_value=True)
        task = await receiver.evaluate_and_confirm(parse_result, on_confirm=on_confirm)
        assert task is not None

    @pytest.mark.asyncio
    async def test_medium_confidence_rejected(self, receiver):
        """TC-01-05-02: 中置信度拒绝"""
        parse_result = TaskParseResult(goal="读取文件", confidence=0.6)
        on_confirm = AsyncMock(return_value=False)
        task = await receiver.evaluate_and_confirm(parse_result, on_confirm=on_confirm)
        assert task is None

    @pytest.mark.asyncio
    async def test_low_confidence_clarify(self, receiver):
        """TC-01-05-03: 低置信度追问"""
        parse_result = TaskParseResult(
            goal="模糊任务",
            confidence=0.3,
            clarification_needed="请明确",
        )
        # 用户澄清后置信度提升
        clarified_result = TaskParseResult(goal="明确任务", confidence=0.7)
        receiver.parse_task = AsyncMock(return_value=clarified_result)

        on_clarify = AsyncMock(return_value="明确后的输入")
        task = await receiver.evaluate_and_confirm(parse_result, on_clarify=on_clarify)
        assert task is not None


# ==================== 完整接收流程 ====================

class TestReceive:
    """TC-01-01-10 ~ TC-01-06-10: 完整流程"""

    @pytest.mark.asyncio
    async def test_full_flow(self, receiver):
        """TC-01-01-10: 完整接收流程"""
        mock_result = TaskParseResult(goal="读取文件", confidence=0.9)
        receiver._llm.structured_chat = AsyncMock(return_value=mock_result)

        result = await receiver.receive("读取 src/main.py 文件")
        assert result["intent"] == InputIntent.NEW_TASK
        assert result["task"].goal == "读取文件"
        assert result["danger_level"].level == DangerLevel.GREEN

    @pytest.mark.asyncio
    async def test_empty_input(self, receiver):
        """TC-01-01-11: 空输入"""
        result = await receiver.receive("")
        assert result["intent"] == InputIntent.CHAT

    @pytest.mark.asyncio
    async def test_control_command_flow(self, receiver):
        """TC-01-02-14: 控制指令流程"""
        result = await receiver.receive("帮助")
        assert result["intent"] == InputIntent.CONTROL
