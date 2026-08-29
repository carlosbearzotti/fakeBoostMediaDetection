"""
Gerenciador de Cache Proativo para APIs Externas (Meta Graph API e Google Trends).
Objetivo:
- Prevenir erros HTTP 429 (Too Many Requests) no Google Trends.
- Proteger quotas e limites de taxa de chamadas do token da Meta Graph API.
- Viabilizar reanálises ultra-rápidas e reprodução offline de auditorias.
"""

from datetime import datetime, timedelta
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DB_PATH = Path("dossies") / "auditoria.db"


class CacheManager:
    """
    Camada de cache local persistente com expiração (TTL) via SQLite.
    """

    def __init__(self, db_path: Optional[Path | str] = None, default_ttl_hours: float = 4.0):
        self.db_path = Path(db_path) if db_path else DEFAULT_CACHE_DB_PATH
        self.default_ttl_hours = default_ttl_hours
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_cache_table()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_cache_table(self) -> None:
        """Cria a tabela de cache se não existir."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_query_cache (
                    cache_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    query_identifier TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON api_query_cache(expires_at)")
            conn.commit()

    @staticmethod
    def generate_key(source: str, identifier: str, extra_params: Optional[Dict[str, Any]] = None) -> str:
        """Gera uma chave SHA-256 única para o par (fonte, identificador, parâmetros)."""
        raw_str = f"{source}::{identifier.strip().lower()}"
        if extra_params:
            raw_str += "::" + json.dumps(extra_params, sort_keys=True)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def get(self, source: str, identifier: str, extra_params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """
        Recupera dados do cache se a chave existir e o TTL ainda for válido.
        """
        cache_key = self.generate_key(source, identifier, extra_params)
        now = datetime.utcnow().isoformat() + "Z"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT payload_json, expires_at, cached_at
                FROM api_query_cache
                WHERE cache_key = ?
            """, (cache_key,))
            row = cursor.fetchone()

            if not row:
                return None

            expires_at = row["expires_at"]
            if expires_at < now:
                logger.debug(f"Cache expirado para {source}:{identifier} (expirou em {expires_at}).")
                return None

            logger.info(f"⚡ [CACHE HIT] Carregando dados pré-coletados de '{source}' para '{identifier}' (coletado em {row['cached_at']}).")
            try:
                data = json.loads(row["payload_json"])
                return data
            except Exception as e:
                logger.warning(f"Erro ao desserializar JSON do cache: {e}")
                return None

    def set(
        self,
        source: str,
        identifier: str,
        payload: Any,
        extra_params: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[float] = None,
    ) -> None:
        """
        Grava dados no cache com tempo de vida definido.
        """
        ttl = ttl_hours if ttl_hours is not None else self.default_ttl_hours
        cache_key = self.generate_key(source, identifier, extra_params)
        now_dt = datetime.utcnow()
        expires_dt = now_dt + timedelta(hours=ttl)

        cached_at = now_dt.isoformat() + "Z"
        expires_at = expires_dt.isoformat() + "Z"

        try:
            if isinstance(payload, pd.DataFrame):
                payload_json = payload.to_json(date_format="iso")
            else:
                payload_json = json.dumps(payload, ensure_ascii=False)

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO api_query_cache (
                        cache_key, source, query_identifier, cached_at, expires_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        cached_at = excluded.cached_at,
                        expires_at = excluded.expires_at,
                        payload_json = excluded.payload_json
                """, (cache_key, source, identifier, cached_at, expires_at, payload_json))
                conn.commit()

            logger.debug(f"Dados cacheados para {source}:{identifier} até {expires_at} ({ttl}h TTL).")
        except Exception as e:
            logger.warning(f"Falha ao salvar entrada no cache: {e}")

    def clear_expired(self) -> int:
        """Remove entradas vencidas da tabela de cache."""
        now = datetime.utcnow().isoformat() + "Z"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM api_query_cache WHERE expires_at < ?", (now,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted


# Instância global Singleton
cache_manager = CacheManager()
