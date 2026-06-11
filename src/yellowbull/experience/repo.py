"""经验数据库操作层

负责经验的增删改查、关键词/标签管理、老化标记与清理。
所有方法均使用参数化查询防止 SQL 注入。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from yellowbull.config.settings import ExperienceSettings
from yellowbull.models.experience import Experience
from yellowbull.storage.db import DatabaseManager

logger = logging.getLogger(__name__)


class ExperienceRepo:
    """经验数据库操作层"""

    def __init__(self, db: DatabaseManager, settings: ExperienceSettings | None = None):
        self._db = db
        self._settings = settings or ExperienceSettings()

    # ── CRUD ──────────────────────────────────────────────

    async def save(self, experience: Experience) -> str:
        """保存经验条目，返回 experience_id

        Args:
            experience: 经验对象

        Returns:
            experience.id

        Raises:
            ValueError: 经验数据无效时抛出
        """
        # 验证数据
        self._validate_experience(experience)

        await self._db.connection.execute(
            """
            INSERT OR REPLACE INTO experiences (
                id, task_summary, task_category, outcome, score,
                lessons_learned, tool_chain, steps_count, success_rate,
                retry_count, duration_seconds, is_permanent, generality,
                project_name, keywords, tags, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experience.id,
                experience.task_summary,
                experience.task_category,
                experience.outcome,
                experience.score,
                experience.lessons_learned,
                json.dumps(experience.tool_chain, ensure_ascii=False),
                experience.steps_count,
                experience.success_rate,
                experience.retry_count,
                experience.duration_seconds,
                int(experience.is_permanent),
                experience.generality,
                experience.project_name,
                json.dumps(experience.keywords, ensure_ascii=False),
                json.dumps(experience.tags, ensure_ascii=False),
                experience.created_at.isoformat(),
            ),
        )
        await self._db.connection.commit()

        # 保存关键词和标签
        await self.save_keywords(experience.id, experience.keywords)
        await self.save_tags(experience.id, experience.tags)

        logger.info("经验已保存: id=%s category=%s", experience.id, experience.task_category)
        return experience.id

    async def get_by_id(self, experience_id: str) -> Experience | None:
        """按 ID 查询单条经验"""
        cursor = await self._db.connection.execute(
            "SELECT * FROM experiences WHERE id = ?", (experience_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_experience(row)

    async def list_by_category(
        self,
        category: str,
        limit: int = 10,
        min_score: float | None = None,
    ) -> list[Experience]:
        """按类别批量查询经验"""
        conditions = ["task_category = ?"]
        params: list = [category]

        if min_score is not None:
            conditions.append("score >= ?")
            params.append(min_score)

        sql = f"SELECT * FROM experiences WHERE {' AND '.join(conditions)} ORDER BY score DESC, created_at DESC LIMIT ?"
        params.append(limit)
        cursor = await self._db.connection.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._row_to_experience(row) for row in rows]

    async def delete(self, experience_id: str) -> bool:
        """删除经验及关联数据

        Returns:
            True 如果删除成功，False 如果经验不存在
        """
        # 先删除关联的关键词和标签
        await self._db.connection.execute(
            "DELETE FROM experience_keywords WHERE experience_id = ?",
            (experience_id,),
        )
        await self._db.connection.execute(
            "DELETE FROM experience_tags WHERE experience_id = ?",
            (experience_id,),
        )

        cursor = await self._db.connection.execute(
            "DELETE FROM experiences WHERE id = ?", (experience_id,)
        )
        await self._db.connection.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("经验已删除: id=%s", experience_id)
        return deleted

    async def update_score(self, experience_id: str, score: float) -> bool:
        """更新经验评分

        Args:
            experience_id: 经验 ID
            score: 新评分 (-1.0 ~ 1.0)

        Returns:
            True 如果更新成功
        """
        score = max(-1.0, min(1.0, score))
        cursor = await self._db.connection.execute(
            "UPDATE experiences SET score = ? WHERE id = ?",
            (score, experience_id),
        )
        await self._db.connection.commit()
        return cursor.rowcount > 0

    # ── 关键词 / 标签 ─────────────────────────────────────

    async def save_keywords(self, experience_id: str, keywords: list[str]) -> None:
        """保存经验关联的关键词（先清除旧关键词再插入）"""
        await self._db.connection.execute(
            "DELETE FROM experience_keywords WHERE experience_id = ?",
            (experience_id,),
        )
        for keyword in keywords:
            await self._db.connection.execute(
                "INSERT INTO experience_keywords (experience_id, keyword) VALUES (?, ?)",
                (experience_id, keyword),
            )
        await self._db.connection.commit()

    async def save_tags(self, experience_id: str, tags: list[str]) -> None:
        """保存经验关联的标签（先清除旧标签再插入）"""
        await self._db.connection.execute(
            "DELETE FROM experience_tags WHERE experience_id = ?",
            (experience_id,),
        )
        for tag in tags:
            await self._db.connection.execute(
                "INSERT INTO experience_tags (experience_id, tag) VALUES (?, ?)",
                (experience_id, tag),
            )
        await self._db.connection.commit()

    # ── 检索辅助 ──────────────────────────────────────────

    async def search_by_keywords(
        self,
        keywords: list[str],
        project_name: str | None = None,
        limit: int = 10,
    ) -> list[Experience]:
        """按关键词搜索经验，计算相关度排序

        相关度 = 关键词匹配数 * 0.5 + score * 0.3 + 时间衰减 * 0.2
        """
        if not keywords:
            return []

        placeholders = ",".join("?" * len(keywords))

        sql = f"""
            SELECT e.*,
                   (COUNT(k.experience_id) * 0.5)
                   + (e.score * 0.3)
                   + (0.2 / (1 + julianday('now') - julianday(e.created_at)))
                AS relevance_score
            FROM experiences e
            JOIN experience_keywords k ON e.id = k.experience_id
            WHERE k.keyword IN ({placeholders})
              AND e.outcome IN ('success', 'partial')
              AND (
                  e.is_permanent = 1
                  OR (julianday('now') - julianday(e.created_at)) < ?
              )
            GROUP BY e.id
            HAVING relevance_score > ?
            ORDER BY
              CASE
                WHEN e.is_permanent = 1 AND e.project_name IS NULL THEN 0
                WHEN ? IS NOT NULL AND e.project_name = ? THEN 1
                ELSE 2
              END,
              relevance_score DESC
            LIMIT ?
        """
        params = (
            *keywords,
            self._settings.aging_period_temporary,
            self._settings.min_relevance_score,
            project_name,
            project_name,
            limit,
        )

        cursor = await self._db.connection.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._row_to_experience(row) for row in rows]

    # ── 老化清理 ──────────────────────────────────────────

    async def mark_expired(self) -> int:
        """标记过期经验

        规则:
        - is_permanent = true → 永不老化
        - generality < 0.8 → 老化周期 30 天
        - generality >= 0.8 → 老化周期 180 天
        - score > 0.8 → 老化周期延长 2 倍
        - score < -0.5 → 老化周期缩短一半

        Returns:
            标记为过期的经验数量
        """
        temp_period = self._settings.aging_period_temporary
        project_period = self._settings.aging_period_project

        sql = """
            UPDATE experiences
            SET is_permanent = 0
            WHERE is_permanent = 0
              AND (
                  (generality < 0.8 AND
                   julianday('now') - julianday(created_at) >
                     CASE
                       WHEN score > 0.8 THEN ? * 2
                       WHEN score < -0.5 THEN ? / 2
                       ELSE ?
                     END)
                  OR
                  (generality >= 0.8 AND
                   julianday('now') - julianday(created_at) >
                     CASE
                       WHEN score > 0.8 THEN ? * 2
                       WHEN score < -0.5 THEN ? / 2
                       ELSE ?
                     END)
              )
        """
        params = (
            temp_period, temp_period, temp_period,
            project_period, project_period, project_period,
        )
        cursor = await self._db.connection.execute(sql, params)
        await self._db.connection.commit()
        count = cursor.rowcount
        if count:
            logger.info("标记 %d 条经验为过期", count)
        return count

    async def cleanup_expired(self, threshold_days: int | None = None) -> int:
        """清理过期经验（删除超过阈值的非永久经验）

        Args:
            threshold_days: 清理阈值天数，默认使用配置值

        Returns:
            删除的经验数量
        """
        if threshold_days is None:
            threshold_days = self._settings.cleanup_threshold_days

        # 先删关联表
        await self._db.connection.execute(
            """
            DELETE FROM experience_keywords
            WHERE experience_id IN (
                SELECT id FROM experiences
                WHERE is_permanent = 0
                  AND julianday('now') - julianday(created_at) > ?
            )
            """,
            (threshold_days,),
        )
        await self._db.connection.execute(
            """
            DELETE FROM experience_tags
            WHERE experience_id IN (
                SELECT id FROM experiences
                WHERE is_permanent = 0
                  AND julianday('now') - julianday(created_at) > ?
            )
            """,
            (threshold_days,),
        )

        cursor = await self._db.connection.execute(
            """
            DELETE FROM experiences
            WHERE is_permanent = 0
              AND julianday('now') - julianday(created_at) > ?
            """,
            (threshold_days,),
        )
        await self._db.connection.commit()
        count = cursor.rowcount
        if count:
            logger.info("清理 %d 条过期经验", count)
        return count

    async def needs_maintenance(self) -> bool:
        """检查是否需要老化维护

        条件:
        - 经验总数 > 100
        - 或上次维护超过 7 天（通过检查最老的非永久经验判断）
        """
        cursor = await self._db.connection.execute(
            "SELECT COUNT(*) FROM experiences WHERE is_permanent = 0"
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0

        if count > 100:
            return True

        # 检查是否有超过 7 天的非永久经验
        cursor = await self._db.connection.execute(
            """
            SELECT COUNT(*) FROM experiences
            WHERE is_permanent = 0
              AND julianday('now') - julianday(created_at) > 7
            """
        )
        row = await cursor.fetchone()
        old_count = row[0] if row else 0
        return old_count > 0

    # ── 内部方法 ──────────────────────────────────────────

    def _validate_experience(self, exp: Experience) -> None:
        """验证经验数据有效性"""
        if not exp.task_summary.strip():
            raise ValueError("经验 task_summary 不能为空")

        # 截断超长字段
        if len(exp.task_summary) > 5000:
            exp.task_summary = exp.task_summary[:5000]
        if len(exp.lessons_learned) > 10000:
            exp.lessons_learned = exp.lessons_learned[:10000]

        # 限制评分范围
        exp.score = max(-1.0, min(1.0, exp.score))

        # 限制 generality 范围
        exp.generality = max(0.0, min(1.0, exp.generality))

        # 限制关键词/标签数量
        if len(exp.keywords) > 50:
            exp.keywords = exp.keywords[:50]
        if len(exp.tags) > 50:
            exp.tags = exp.tags[:50]

    @staticmethod
    def _row_to_experience(row) -> Experience:
        """将数据库行转换为 Experience 对象"""
        dict_factory = row.keys if hasattr(row, "keys") else dict
        data = dict(zip(row.keys(), row))

        # 解析 JSON 字段
        try:
            data["tool_chain"] = json.loads(data.get("tool_chain", "[]"))
        except (json.JSONDecodeError, TypeError):
            data["tool_chain"] = []

        try:
            data["keywords"] = json.loads(data.get("keywords", "[]"))
        except (json.JSONDecodeError, TypeError):
            data["keywords"] = []

        try:
            data["tags"] = json.loads(data.get("tags", "[]"))
        except (json.JSONDecodeError, TypeError):
            data["tags"] = []

        # 转换布尔值
        data["is_permanent"] = bool(data.get("is_permanent", 0))

        # 转换时间
        if data.get("created_at"):
            if isinstance(data["created_at"], str):
                data["created_at"] = datetime.fromisoformat(data["created_at"])
        else:
            data["created_at"] = datetime.now()

        return Experience(**data)
