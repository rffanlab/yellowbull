"""T00-05: SQLite 数据库单元测试"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from yellowbull.config.settings import DatabaseSettings
from yellowbull.storage.db import DatabaseManager


@pytest.fixture(autouse=True)
def reset_database():
    """每次测试前重置单例"""
    DatabaseManager._instance = None
    DatabaseManager._db = None
    yield
    # 清理：关闭连接
    if DatabaseManager._instance and DatabaseManager._db:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(DatabaseManager._db.close())
            else:
                loop.run_until_complete(DatabaseManager._db.close())
        except Exception:
            pass
    DatabaseManager._instance = None
    DatabaseManager._db = None


class TestDatabaseInitialization:
    """TC-00-05-01 ~ TC-00-05-02: 数据库初始化"""

    @pytest.mark.asyncio
    async def test_auto_create_tables(self):
        """TC-00-05-01: 自动建表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db = await DatabaseManager.get(settings)
            assert db._initialized is True
            assert Path(db_path).exists()

    @pytest.mark.asyncio
    async def test_duplicate_init_safe(self):
        """TC-00-05-02: 重复建表安全"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db = await DatabaseManager.get(settings)
            await db.initialize()  # 重复调用不应报错
            assert db._initialized is True

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """单例模式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db1 = await DatabaseManager.get(settings)
            db2 = await DatabaseManager.get()
            assert db1 is db2

    @pytest.mark.asyncio
    async def test_connection_property(self):
        """connection 属性返回连接"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db = await DatabaseManager.get(settings)
            conn = db.connection
            assert conn is not None

    @pytest.mark.asyncio
    async def test_uninitialized_connection_raises(self):
        """未初始化时获取连接抛出异常"""
        DatabaseManager._instance = None
        DatabaseManager._db = None
        db = DatabaseManager()
        with pytest.raises(RuntimeError, match="未初始化"):
            _ = db.connection


class TestDatabaseOperations:
    """TC-00-05-03 ~ TC-00-05-04: 数据操作"""

    @pytest.mark.asyncio
    async def test_data_persistence(self):
        """TC-00-05-03: 数据持久化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db = await DatabaseManager.get(settings)

            conn = db.connection
            await conn.execute(
                "INSERT INTO experiences (id, task_summary, task_category, outcome, score) VALUES (?, ?, ?, ?, ?)",
                ("test1", "summary", "category", "success", 0.8),
            )
            await conn.commit()

            # 读取验证
            cursor = await conn.execute("SELECT id, score FROM experiences WHERE id = ?", ("test1",))
            row = await cursor.fetchone()
            assert row is not None
            assert row[1] == 0.8

    @pytest.mark.asyncio
    async def test_async_operations(self):
        """TC-00-05-04: 异步操作"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db = await DatabaseManager.get(settings)

            async def write_data():
                conn = db.connection
                await conn.execute(
                    "INSERT INTO experiences (id, task_summary, task_category, outcome, score) VALUES (?, ?, ?, ?, ?)",
                    ("async1", "async test", "test", "success", 0.5),
                )
                await conn.commit()

            await write_data()

            conn = db.connection
            cursor = await conn.execute("SELECT id FROM experiences WHERE id = ?", ("async1",))
            row = await cursor.fetchone()
            assert row is not None

    @pytest.mark.asyncio
    async def test_sql_injection_prevention(self):
        """TC-00-12-06: 特殊字符处理 / SQL 注入防护"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db = await DatabaseManager.get(settings)

            malicious = "'); DROP TABLE experiences; --"
            conn = db.connection
            await conn.execute(
                "INSERT INTO experiences (id, task_summary, task_category, outcome, score) VALUES (?, ?, ?, ?, ?)",
                ("inj1", malicious, "test", "success", 0.5),
            )
            await conn.commit()

            # 表应仍然存在
            cursor = await conn.execute("SELECT id FROM experiences WHERE id = ?", ("inj1",))
            row = await cursor.fetchone()
            assert row is not None

    @pytest.mark.asyncio
    async def test_large_field_storage(self):
        """TC-00-12-05: 大字段存储"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db = await DatabaseManager.get(settings)

            large_text = "x" * 100_000
            conn = db.connection
            await conn.execute(
                "INSERT INTO experiences (id, task_summary, task_category, outcome, score) VALUES (?, ?, ?, ?, ?)",
                ("large1", large_text, "test", "success", 0.5),
            )
            await conn.commit()

            cursor = await conn.execute("SELECT task_summary FROM experiences WHERE id = ?", ("large1",))
            row = await cursor.fetchone()
            assert len(row[0]) == 100_000

    @pytest.mark.asyncio
    async def test_wal_mode_enabled(self):
        """WAL 模式已启用"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db = await DatabaseManager.get(settings)

            conn = db.connection
            cursor = await conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            assert row[0] == "wal"


class TestDatabaseCleanup:
    """数据库清理"""

    @pytest.mark.asyncio
    async def test_close_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            settings = DatabaseSettings(path=db_path)
            db = await DatabaseManager.get(settings)
            await db.close()
            assert db._initialized is False
