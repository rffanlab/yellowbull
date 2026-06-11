"""任务接收模块

负责接收用户输入 → 预处理 → 意图分类 → LLM 解析 → 置信度评估 → 危险操作检查。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from yellowbull.config.settings import Settings
from yellowbull.llm.client import LLMClient
from yellowbull.models.task import Task, TaskStatus
from yellowbull.prompts.task_parse import build_task_parse_prompt

logger = logging.getLogger(__name__)

# ==================== 输入预处理 ====================

_MAX_INPUT_LENGTH = 4096


class PreprocessedInput(BaseModel):
    """预处理后的用户输入"""

    cleaned_text: str
    is_truncated: bool = False
    code_contexts: list[str] = Field(default_factory=list)
    file_references: list[str] = Field(default_factory=list)


class TaskReceiver:
    """任务接收器"""

    def __init__(self, llm_client: LLMClient, settings: Settings):
        self._llm = llm_client
        self._settings = settings
        self._conversation = ConversationBuffer(max_rounds=settings.execution.max_subtask_steps or 10)

    async def preprocess_input(self, raw_input: str) -> PreprocessedInput:
        """预处理用户输入。

        1. 去噪/格式化（去除多余空白、统一换行）
        2. 超长截断（>4096 字符截断并标记）
        3. 代码块识别（``` 包裹的内容标记为代码上下文）
        4. 文件路径识别（提取 @file.md 或 path/to/file 引用）
        """
        if not raw_input or not raw_input.strip():
            return PreprocessedInput(cleaned_text="")

        # 去噪：统一换行，去除首尾空白
        text = raw_input.replace("\r\n", "\n").replace("\r", "\n").strip()

        # 提取代码块
        code_contexts = re.findall(r"```[^`]*```", text, re.DOTALL)
        # 提取文件引用 (@file.md 或 path/to/file)
        file_references = re.findall(r"[@]?\S+?\.\w{1,6}", text)

        # 超长截断
        is_truncated = False
        if len(text) > _MAX_INPUT_LENGTH:
            text = text[:_MAX_INPUT_LENGTH] + "\n...(内容已截断)"
            is_truncated = True

        return PreprocessedInput(
            cleaned_text=text,
            is_truncated=is_truncated,
            code_contexts=code_contexts,
            file_references=file_references,
        )


# ==================== 意图分类 ====================

class InputIntent(str, Enum):
    """用户输入意图枚举"""

    NEW_TASK = "new_task"
    SUPPLEMENT = "supplement"
    CHAT = "chat"
    CONTROL = "control"


# 控制指令关键词
_CONTROL_KEYWORDS = {
    "退出", "quit", "exit", "q",
    "取消", "cancel", "停", "stop",
    "帮助", "help", "怎么用",
    "状态", "status", "当前状态",
}

# 闲聊关键词
_CHAT_KEYWORDS = {
    "你好", "hello", "hi", "在吗", "嗨",
    "hello", "hi", "hey",
}


def _is_control(text: str) -> bool:
    text_lower = text.strip().lower()
    return text_lower in _CONTROL_KEYWORDS or text.strip() in _CONTROL_KEYWORDS


def _is_chat(text: str) -> bool:
    text_lower = text.strip().lower()
    return any(kw in text_lower for kw in _CHAT_KEYWORDS)


# ==================== 对话上下文管理 ====================

class ConversationRound(BaseModel):
    """单轮对话"""

    user_input: str
    assistant_response: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ConversationBuffer:
    """对话上下文缓冲区"""

    def __init__(self, max_rounds: int = 10):
        self.rounds: list[ConversationRound] = []
        self.max_rounds = max_rounds

    def add_round(self, user_input: str, assistant_response: str) -> None:
        """添加一轮对话，超过 max_rounds 自动淘汰旧轮次。"""
        self.rounds.append(ConversationRound(
            user_input=user_input,
            assistant_response=assistant_response,
        ))
        if len(self.rounds) > self.max_rounds:
            self.rounds = self.rounds[-self.max_rounds:]

    def get_full_context(self) -> str:
        """合并所有轮次为完整上下文文本。"""
        if not self.rounds:
            return ""
        lines = []
        for i, round_ in enumerate(self.rounds, 1):
            lines.append(f"[第{i}轮] 用户: {round_.user_input}")
            lines.append(f"[第{i}轮] 助手: {round_.assistant_response}")
        return "\n".join(lines)

    def is_empty(self) -> bool:
        return len(self.rounds) == 0

    def clear(self) -> None:
        self.rounds.clear()


# ==================== LLM 任务解析 ====================

class TaskParseResult(BaseModel):
    """LLM 解析结果"""

    goal: str
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    context_files: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    clarification_needed: str = ""
    clarification_options: list[str] = Field(default_factory=list)


# ==================== 危险操作检查 ====================

class DangerLevel(str, Enum):
    """危险级别"""

    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


class DangerCheckResult(BaseModel):
    """危险检查结果"""

    level: DangerLevel
    reasons: list[str] = Field(default_factory=list)


_DANGER_PATTERNS = {
    DangerLevel.RED: [
        (r'\brm\s+(-r|-f|-rf|-fr)\b', "删除命令"),
        (r'\bformat\b', "磁盘格式化"),
        (r'\bDROP\s+TABLE\b', "数据库删除表"),
        (r'\bTRUNCATE\b', "数据库清空表"),
        (r'\bmkfs\b', "文件系统创建"),
        (r'[:]\(\{[:]\|[:]&\}\s*;:', "fork bomb"),
    ],
    DangerLevel.YELLOW: [
        (r'\binstall\b', "安装依赖"),
        (r'\bPOST\b', "网络请求"),
        (r'\bDELETE\b', "网络删除请求"),
    ],
}


def _rule_based_check(text: str) -> DangerCheckResult:
    """规则匹配危险操作。"""
    # 按危险级别从高到低检查
    for level in [DangerLevel.RED, DangerLevel.YELLOW]:
        for pattern, reason in _DANGER_PATTERNS.get(level, []):
            if re.search(pattern, text, re.IGNORECASE):
                return DangerCheckResult(level=level, reasons=[reason])
    return DangerCheckResult(level=DangerLevel.GREEN)


# ==================== 主接收器 ====================

class TaskReceiver:
    """任务接收器（完整版）"""

    def __init__(self, llm_client: LLMClient, settings: Settings):
        self._llm = llm_client
        self._settings = settings
        self._conversation = ConversationBuffer(
            max_rounds=getattr(settings.execution, "max_subtask_steps", 10) or 10,
        )

    # --- T01-01: 输入预处理 ---

    async def preprocess_input(self, raw_input: str) -> PreprocessedInput:
        """预处理用户输入。"""
        if not raw_input or not raw_input.strip():
            return PreprocessedInput(cleaned_text="")

        text = raw_input.replace("\r\n", "\n").replace("\r", "\n").strip()

        # 提取代码块
        code_contexts = re.findall(r"```[^`]*```", text, re.DOTALL)
        # 提取文件引用
        file_references = re.findall(r"[@]?\S+?\.\w{1,6}", text)

        # 超长截断
        is_truncated = False
        if len(text) > _MAX_INPUT_LENGTH:
            text = text[:_MAX_INPUT_LENGTH] + "\n...(内容已截断)"
            is_truncated = True

        return PreprocessedInput(
            cleaned_text=text,
            is_truncated=is_truncated,
            code_contexts=code_contexts,
            file_references=file_references,
        )

    # --- T01-02: 意图分类 ---

    async def classify_intent(self, input_text: str, has_context: bool = False) -> InputIntent:
        """判断用户输入意图。"""
        if not input_text or not input_text.strip():
            return InputIntent.CHAT

        # 控制指令
        if _is_control(input_text):
            return InputIntent.CONTROL

        # 闲聊
        if _is_chat(input_text):
            return InputIntent.CHAT

        # 有上下文且不是明确的新任务关键词 → 可能是补充
        if has_context and self._conversation.is_empty() is False:
            # 简短输入（<20字）且无明确任务动词 → 视为补充
            if len(input_text) < 20:
                return InputIntent.SUPPLEMENT

        return InputIntent.NEW_TASK

    # --- 控制指令处理 ---

    def handle_control_command(self, command: str) -> str | None:
        """处理控制指令，返回响应文本或 None（表示内部处理）。"""
        cmd = command.strip().lower()

        if cmd in ("退出", "quit", "exit", "q"):
            return None  # 表示退出

        if cmd in ("取消", "cancel", "停", "stop"):
            return "任务已取消。"

        if cmd in ("帮助", "help", "怎么用"):
            return (
                "YellowBull 使用帮助:\n"
                "- 直接输入任务描述即可开始执行\n"
                "- 输入 '状态' 查看当前任务状态\n"
                "- 输入 '取消' 中断当前任务\n"
                "- 输入 '退出' 退出程序"
            )

        if cmd in ("状态", "status", "当前状态"):
            return "当前无正在执行的任务。"

        return f"未知指令: {command}"

    # --- T01-04: LLM 任务解析 ---

    async def parse_task(self, input_text: str, context: str = "") -> TaskParseResult:
        """使用 LLM 将用户输入解析为结构化 Task。"""
        system_prompt, user_message = build_task_parse_prompt(input_text, context)

        try:
            result = await self._llm.structured_chat(
                system_prompt=system_prompt,
                user_messages=[user_message],
                response_model=TaskParseResult,
            )
            return TaskParseResult(**result.model_dump())
        except Exception as e:
            logger.warning("LLM 任务解析失败，使用降级方案: %s", e)
            return self._fallback_parse(input_text)

    def _fallback_parse(self, input_text: str) -> TaskParseResult:
        """LLM 解析失败时的降级方案。"""
        return TaskParseResult(
            goal=input_text.strip(),
            confidence=0.5,
        )

    # --- T01-05: 置信度评估与确认 ---

    async def evaluate_and_confirm(
        self,
        parse_result: TaskParseResult,
        on_confirm: Callable[[str], Awaitable[bool]] | None = None,
        on_clarify: Callable[[str, list[str]], Awaitable[str]] | None = None,
    ) -> Task | None:
        """根据置信度决定流程。

        - >= 0.8 → 直接创建 Task
        - 0.5 ~ 0.8 → 展示计划让用户确认
        - < 0.5 → 追问澄清（最多 3 轮）
        """
        confidence = parse_result.confidence

        if confidence >= 0.8:
            # 高置信 → 直接创建 Task
            return self._create_task(parse_result)

        if confidence >= 0.5:
            # 中置信 → 让用户确认
            if on_confirm:
                confirmed = await on_confirm(
                    f"任务目标: {parse_result.goal}\n"
                    f"约束: {', '.join(parse_result.constraints) or '无'}\n"
                    f"是否继续？",
                )
                if confirmed:
                    return self._create_task(parse_result)
                return None
            return self._create_task(parse_result)

        # 低置信 → 追问澄清
        if on_clarify:
            clarified = await self._clarify_with_user(parse_result, on_clarify)
            if clarified:
                return self._create_task(clarified)
        return None

    async def _clarify_with_user(
        self,
        parse_result: TaskParseResult,
        on_clarify: Callable[[str, list[str]], Awaitable[str]],
        max_rounds: int = 3,
    ) -> TaskParseResult | None:
        """追问澄清流程（最多 3 轮）。"""
        for _ in range(max_rounds):
            question = parse_result.clarification_needed or "请明确任务目标。"
            options = parse_result.clarification_options or ["继续执行", "取消"]

            response = await on_clarify(question, options)
            if not response:
                return None

            # 用用户回答重新解析
            try:
                new_result = await self.parse_task(response)
                if new_result.confidence >= 0.5:
                    return new_result
                parse_result = new_result
            except Exception:
                return None

        # 超过最大轮数，使用默认假设
        logger.warning("追问超过 %d 轮，使用默认假设", max_rounds)
        parse_result.confidence = 0.5
        return parse_result

    def _create_task(self, parse_result: TaskParseResult) -> Task:
        """从解析结果创建 Task 对象。"""
        return Task(
            goal=parse_result.goal,
            constraints=parse_result.constraints,
            success_criteria=parse_result.success_criteria,
            context_files=parse_result.context_files,
            confidence=parse_result.confidence,
            clarification_needed=parse_result.clarification_needed,
            clarification_options=parse_result.clarification_options,
            status=TaskStatus.PENDING,
        )

    # --- T01-06: 危险操作检查 ---

    async def check_danger_level(self, task: Task) -> DangerCheckResult:
        """检查任务是否包含危险操作。"""
        text = task.goal
        if task.constraints:
            text += " " + " ".join(task.constraints)

        return _rule_based_check(text)

    # --- 完整接收流程 ---

    async def receive(self, raw_input: str) -> dict[str, Any]:
        """完整接收流程入口。

        返回:
            dict: 包含 intent, task, danger_level 等字段
        """
        # 1. 预处理
        preprocessed = await self.preprocess_input(raw_input)
        if not preprocessed.cleaned_text:
            return {
                "intent": InputIntent.CHAT,
                "response": "请输入任务描述。",
            }

        # 2. 意图分类
        intent = await self.classify_intent(
            preprocessed.cleaned_text,
            has_context=not self._conversation.is_empty(),
        )

        # 3. 处理控制指令
        if intent == InputIntent.CONTROL:
            response = self.handle_control_command(preprocessed.cleaned_text)
            return {"intent": intent, "response": response}

        # 4. 处理闲聊
        if intent == InputIntent.CHAT:
            return {
                "intent": intent,
                "response": "你好！请告诉我需要完成什么任务。",
            }

        # 5. 补充输入 → 加入上下文
        if intent == InputIntent.SUPPLEMENT:
            self._conversation.add_round(preprocessed.cleaned_text, "")
            return {
                "intent": intent,
                "response": "已记录补充信息，请继续或输入完整任务。",
            }

        # 6. LLM 解析
        context = self._conversation.get_full_context()
        parse_result = await self.parse_task(preprocessed.cleaned_text, context)

        # 7. 危险检查
        task = self._create_task(parse_result)
        danger = await self.check_danger_level(task)

        # 8. 记录对话
        self._conversation.add_round(preprocessed.cleaned_text, "")

        return {
            "intent": intent,
            "task": task,
            "parse_result": parse_result,
            "danger_level": danger,
            "preprocessed": preprocessed,
        }
