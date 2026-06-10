"""Pytest 配置"""

import sys
from pathlib import Path

import pytest

# 确保 src 目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    """创建测试数据目录"""
    return tmp_path_factory.mktemp("data")


@pytest.fixture(scope="session")
def tmp_db_dir(tmp_path_factory):
    """创建临时数据库目录"""
    return tmp_path_factory.mktemp("db")
