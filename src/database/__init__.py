"""
Módulo de Banco de Dados e Persistência do Sistema de Auditoria OSINT.
Fornece gerenciamento de dados SQLite e camada de Caching para histórico e alta resiliência.
"""

from src.database.db_manager import DatabaseManager, db_manager
from src.database.cache_manager import CacheManager, cache_manager

__all__ = ["DatabaseManager", "db_manager", "CacheManager", "cache_manager"]
