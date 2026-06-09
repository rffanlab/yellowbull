"""SQLite 数据库连接与初始化模块

提供单例模式的数据库管理器，支持异步操作。
首次运行时自动建表，包括经验表、关键词表、标签表。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import aiosqlite

from yellowbull.config.settings import DatabaseSettings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库连接管理器（单例）"""

    _instance: ClassVar[DatabaseManager | None] = None
    _db: aiosqlite.Connection | None = None

    def __new__(cls, settings: DatabaseSettings | None = None) -> DatabaseManager:
        """用途: 单例构造器，确保全局只有一个 DatabaseManager 实例

        入参:
            settings (DatabaseSettings | None): 数据库配置，仅在首次创建时生效

        返回:
            DatabaseManager: 单例实例
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = settings or DatabaseSettings()
            cls._instance._initialized = False
        return cls._instance

    @classmethod
    async def get(cls, settings: DatabaseSettings | None = None) -> DatabaseManager:
        """用途: 获取单例实例，若未初始化则自动初始化

        入参:
            settings (DatabaseSettings | None): 数据库配置

        返回:
            DatabaseManager: 已初始化的单例实例
        """
        instance = cls(settings)
        if not instance._initialized:
            await instance.initialize()
        return instance

    async def initialize(self) -> None:
        """用途: 创建所有数据表（幂等操作，重复调用不会重复建表）

        入参: 无
        返回: 无
        """
        if self._initialized:
            return

        db_path = self._settings.path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(db_path)
        self._db.row_factory = aiosqlite.Row

        # 启用 WAL 模式提升并发性能
        await self._db.execute("PRAGMA journal_mode=WAL")

        await self._create_tables()
        await self._db.commit()

        self._initialized = True
        logger.info("数据库初始化完成: %s", db_path)

    async def _create_tables(self) -> None:
        """用途: 执行建表 SQL 脚本

        入参: 无
        返回: 无
        """
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS experiences (
                id TEXT PRIMARY KEY,
                task_summary TEXT NOT NULL,
                task_category TEXT NOT NULL,
                outcome TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0.0,
                lessons_learned TEXT DEFAULT '',
                tool_chain TEXT DEFAULT '[]',
                steps_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0.0,
                retry_count INTEGER DEFAULT 0,
                duration_seconds INTEGER DEFAULT 0,
                is_permanent INTEGER DEFAULT 0,
                generality REAL DEFAULT 0.5,
                project_name TEXT,
                keywords TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                created_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS experience_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experience_id TEXT NOT NULL,
                keyword TEXT NOT NULL,
                FOREIGN KEY (experience_id) REFERENCES experiences(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS experience_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experience_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                FOREIGN KEY (experience_id) REFERENCES experiences(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_experiences_category ON experiences(task_category);
            CREATE INDEX IF NOT EXISTS idx_experiences_outcome ON experiences(outcome);
            CREATE INDEX IF NOT EXISTS idx_experiences_score ON experiences(score);
            CREATE INDEX IF NOT EXISTS idx_experiences_created ON experiences(created_at);
            CREATE INDEX IF NOT EXISTS idx_exp_keywords_exp_id ON experience_keywords(experience_id);
            CREATE INDEX IF NOT EXISTS idx_exp_tags_exp_id ON experience_tags(experience_id);
            """
        )

    async def close(self) -> None:
        """用途: 关闭数据库连接

        入参: 无
        返回: 无
        """
        if self._db:
            await self._db.close()
            self._db = None
            self._initialized = False
            logger.info("数据库连接已关闭")

    @property
    def connection(self) -> aiosqlite.Connection:
        """用途: 获取当前数据库连接

        返回:
            aiosqlite.Connection: 异步连接对象

        异常:
            RuntimeError: 数据库未初始化时抛出
        """
        if self._db is None:
            raise RuntimeError("数据库未初始化，请先调用 initialize()")
        return self._db
