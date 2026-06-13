"""结果持久化模块

将执行结果保存到 SQLite 数据库。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from yellowbull.models.result import (
    AggregationResult,
    EvaluationResult,
    ExecutionSummary,
    StepSummary,
)

logger = logging.getLogger(__name__)


class ResultRepository:
    """T04-07 结果仓库"""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """初始化数据库表结构"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_results (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT,
                    conclusion TEXT,
                    achievement_score REAL,
                    total_steps INTEGER,
                    done_steps INTEGER,
                    failed_steps INTEGER,
                    skipped_steps INTEGER,
                    termination_reason TEXT,
                    total_duration_seconds REAL,
                    steps_consumed INTEGER,
                    report_level INTEGER,
                    created_at TEXT,
                    report_json TEXT,
                    evaluation_json TEXT
                );

                CREATE TABLE IF NOT EXISTS step_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    step_id TEXT,
                    status TEXT,
                    duration_seconds REAL,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    FOREIGN KEY (task_id) REFERENCES task_results(task_id)
                );

                CREATE INDEX IF NOT EXISTS idx_step_results_task
                    ON step_results(task_id);
                """
            )

    def save(self, summary: ExecutionSummary, result: AggregationResult) -> None:
        """保存执行结果"""
        evaluation = result.evaluation or EvaluationResult(conclusion="unknown")

        with sqlite3.connect(self._db_path) as conn:
            # 保存任务级结果（UPSERT）
            conn.execute(
                """
                INSERT INTO task_results (
                    task_id, goal, conclusion, achievement_score,
                    total_steps, done_steps, failed_steps, skipped_steps,
                    termination_reason, total_duration_seconds, steps_consumed,
                    report_level, created_at, report_json, evaluation_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    conclusion=excluded.conclusion,
                    achievement_score=excluded.achievement_score,
                    done_steps=excluded.done_steps,
                    failed_steps=excluded.failed_steps,
                    skipped_steps=excluded.skipped_steps,
                    termination_reason=excluded.termination_reason,
                    total_duration_seconds=excluded.total_duration_seconds,
                    report_level=excluded.report_level,
                    created_at=excluded.created_at,
                    report_json=excluded.report_json,
                    evaluation_json=excluded.evaluation_json
                """,
                (
                    summary.task_id,
                    summary.goal,
                    evaluation.conclusion,
                    evaluation.achievement_score,
                    summary.total_steps,
                    summary.done_steps,
                    summary.failed_steps,
                    summary.skipped_steps,
                    summary.termination_reason,
                    summary.total_duration_seconds,
                    summary.steps_consumed,
                    evaluation.report_level,
                    datetime.now().isoformat(),
                    json.dumps({"report": result.report}, ensure_ascii=False),
                    self._eval_to_json(evaluation),
                ),
            )

            # 删除旧步骤结果
            conn.execute("DELETE FROM step_results WHERE task_id = ?", (summary.task_id,))

            # 保存步骤级结果
            for detail in summary.step_details:
                conn.execute(
                    """
                    INSERT INTO step_results (
                        task_id, step_id, status, duration_seconds, error, retry_count
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        summary.task_id,
                        detail.step_id,
                        str(detail.status),
                        detail.duration_seconds,
                        detail.error,
                        detail.retry_count,
                    ),
                )

            conn.commit()
            logger.info("结果已保存: task=%s conclusion=%s", summary.task_id, evaluation.conclusion)

    def get_task_result(self, task_id: str) -> dict[str, Any] | None:
        """查询任务结果"""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM task_results WHERE task_id = ?", (task_id,)
            ).fetchone()

            if not row:
                return None

            result = dict(row)
            # 解析 JSON 字段
            for key in ("report_json", "evaluation_json"):
                if result.get(key):
                    try:
                        result[key] = json.loads(result[key])
                    except (json.JSONDecodeError, TypeError):
                        pass

            return result

    def get_step_summaries(self, task_id: str) -> list[StepSummary]:
        """查询步骤摘要列表"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT step_id, status, duration_seconds FROM step_results WHERE task_id = ?",
                (task_id,),
            ).fetchall()

            return [
                StepSummary(
                    step_id=row[0],
                    status=row[1],
                    duration_seconds=float(row[2]) if row[2] else 0.0,
                )
                for row in rows
            ]

    def list_recent_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """列出最近的任务结果"""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT task_id, goal, conclusion, achievement_score, created_at FROM task_results ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]

    @staticmethod
    def _eval_to_json(evaluation: EvaluationResult) -> str:
        """评估结果转 JSON"""
        data = {
            "conclusion": evaluation.conclusion,
            "achievement_score": evaluation.achievement_score,
            "failure_analysis": evaluation.failure_analysis,
            "side_effects": evaluation.side_effects,
            "suggestions": evaluation.suggestions,
            "report_level": evaluation.report_level,
        }
        return json.dumps(data, ensure_ascii=False)


__all__ = ["ResultRepository"]
