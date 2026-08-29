"""
Gerenciador de Banco de Dados SQLite do Sistema de Auditoria OSINT.
Responsável pelo armazenamento estruturado de alvos, dossiês, anúncios e histórico probatório.
"""

from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.models.dossier import DossieTecnico

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("dossies") / "auditoria.db"


class DatabaseManager:
    """
    Controlador de persistência relacional local SQLite para investigações OSINT.
    """

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Cria e retorna uma conexão configurada com row_factory ativado."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        """Inicializa as tabelas do banco de dados SQLite caso ainda não existam."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Tabela de Alvos Investigados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    slug TEXT NOT NULL,
                    first_audited_at TEXT NOT NULL,
                    last_audited_at TEXT NOT NULL,
                    total_dossiers_count INTEGER DEFAULT 1
                )
            """)

            # 2. Tabela de Dossiês Forenses
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dossiers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dossier_id TEXT NOT NULL UNIQUE,
                    target_name TEXT NOT NULL,
                    target_slug TEXT NOT NULL,
                    generated_at_utc TEXT NOT NULL,
                    total_ads_analyzed INTEGER DEFAULT 0,
                    total_suspects INTEGER DEFAULT 0,
                    total_declared_min REAL DEFAULT 0.0,
                    total_declared_max REAL DEFAULT 0.0,
                    estimated_hidden_min REAL DEFAULT 0.0,
                    estimated_hidden_max REAL DEFAULT 0.0,
                    peak_burst_rate TEXT,
                    trends_dawn_mean REAL,
                    trends_z_score REAL,
                    trends_anomaly_status INTEGER DEFAULT 0,
                    sha256_hash TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # 3. Tabela de Anúncios Catalogados (Ads Archive)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ads_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ad_id TEXT NOT NULL UNIQUE,
                    target_name TEXT NOT NULL,
                    target_slug TEXT NOT NULL,
                    page_id TEXT,
                    page_name TEXT,
                    ad_creation_time TEXT,
                    is_suspect INTEGER DEFAULT 0,
                    is_camouflaged INTEGER DEFAULT 0,
                    trigger_words TEXT,
                    ad_url TEXT,
                    spend_min REAL DEFAULT 0.0,
                    spend_max REAL DEFAULT 0.0,
                    raw_json TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
            """)

            # Índices para alta performance em consultas cruzadas
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dossiers_target ON dossiers(target_slug)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_target ON ads_archive(target_slug)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_page_name ON ads_archive(page_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_is_suspect ON ads_archive(is_suspect)")

            # 4. MLOps: Tabela de Log de Feedback
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ml_feedback_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ad_id TEXT,
                    page_name TEXT,
                    raw_text TEXT,
                    predicted_prob REAL,
                    predicted_class INTEGER,
                    user_feedback INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    def log_ml_prediction(self, ad_id: str, page_name: str, raw_text: str, predicted_prob: float) -> None:
        """Registra a predição do modelo ML para futuro Reinforcement Learning / MLOps."""
        with self.get_connection() as conn:
            c = conn.cursor()
            predicted_class = 1 if predicted_prob >= 0.85 else 0
            c.execute('''
                INSERT INTO ml_feedback_log (ad_id, page_name, raw_text, predicted_prob, predicted_class)
                VALUES (?, ?, ?, ?, ?)
            ''', (str(ad_id), page_name, raw_text, predicted_prob, predicted_class))
            conn.commit()
    def record_target(self, name: str, slug: str) -> None:
        """Registra ou atualiza o alvo investigado."""
        now = datetime.utcnow().isoformat() + "Z"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO targets (name, slug, first_audited_at, last_audited_at, total_dossiers_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(name) DO UPDATE SET
                    last_audited_at = excluded.last_audited_at,
                    total_dossiers_count = targets.total_dossiers_count + 1
            """, (name, slug, now, now))
            conn.commit()

    def save_dossier(self, dossie: DossieTecnico, target_slug: str) -> int:
        """
        Salva um dossiê técnico completo e calcula seu hash SHA-256 probatório.
        """
        now = datetime.utcnow().isoformat() + "Z"
        raw_json = dossie.model_dump_json(indent=2)
        dossier_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

        self.record_target(dossie.metadados.alvo_investigado, target_slug)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO dossiers (
                    dossier_id, target_name, target_slug, generated_at_utc,
                    total_ads_analyzed, total_suspects,
                    total_declared_min, total_declared_max,
                    estimated_hidden_min, estimated_hidden_max,
                    peak_burst_rate, trends_dawn_mean, trends_z_score,
                    trends_anomaly_status, sha256_hash, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dossier_id) DO UPDATE SET
                    raw_json = excluded.raw_json,
                    sha256_hash = excluded.sha256_hash
            """, (
                dossie.metadados.id_dossie,
                dossie.metadados.alvo_investigado,
                target_slug,
                dossie.metadados.data_geracao_utc,
                dossie.divergencia_categoria.total_anuncios_analisados,
                dossie.divergencia_categoria.total_anuncios_suspeitos,
                dossie.investimento_estimado.total_declarado_min,
                dossie.investimento_estimado.total_declarado_max,
                dossie.investimento_estimado.estimativa_oculta_min,
                dossie.investimento_estimado.estimativa_oculta_max,
                dossie.pegada_automacao.taxa_maxima_identificada,
                dossie.anomalia_trafego_madrugada.media_interesse_madrugada,
                dossie.anomalia_trafego_madrugada.z_score_madrugada or 0.0,
                1 if dossie.anomalia_trafego_madrugada.status_anomalia else 0,
                dossier_hash,
                raw_json,
                now,
            ))
            conn.commit()
            dossier_row_id = cursor.lastrowid or 0

        logger.info(f"Dossiê '{dossie.metadados.id_dossie}' persistido com sucesso no banco SQLite ({self.db_path}).")
        return dossier_row_id

    def save_ads(
        self,
        ads_raw: List[Dict[str, Any]],
        target_name: str,
        target_slug: str,
        suspect_ids: List[str],
        camouflaged_map: Dict[str, Any],
    ) -> int:
        """
        Salva ou atualiza criativos da Meta Ad Library para cruzamento de inteligência.
        """
        if not ads_raw:
            return 0

        now = datetime.utcnow().isoformat() + "Z"
        suspect_set = set(str(s) for s in suspect_ids)
        inserted_count = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for ad in ads_raw:
                ad_id = str(ad.get("id", ""))
                if not ad_id:
                    continue

                page_id = str(ad.get("page_id", ""))
                page_name = str(ad.get("page_name", ""))
                creation_time = str(ad.get("ad_creation_time", ""))
                is_suspect = 1 if ad_id in suspect_set else 0

                cam_info = camouflaged_map.get(ad_id)
                is_camouflaged = 1 if cam_info else 0
                triggers_str = ", ".join(cam_info.gatilhos_detectados) if cam_info else ""

                spend_data = ad.get("spend", {}) or {}
                spend_min = float(spend_data.get("lower_bound", 0.0) or 0.0)
                spend_max = float(spend_data.get("upper_bound", 0.0) or 0.0)

                ad_url = f"https://www.facebook.com/ads/library/?id={ad_id}"
                raw_json = json.dumps(ad, ensure_ascii=False)

                cursor.execute("""
                    INSERT INTO ads_archive (
                        ad_id, target_name, target_slug, page_id, page_name,
                        ad_creation_time, is_suspect, is_camouflaged, trigger_words,
                        ad_url, spend_min, spend_max, raw_json, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ad_id) DO UPDATE SET
                        is_suspect = excluded.is_suspect,
                        is_camouflaged = excluded.is_camouflaged,
                        trigger_words = excluded.trigger_words,
                        spend_min = excluded.spend_min,
                        spend_max = excluded.spend_max,
                        last_seen_at = excluded.last_seen_at
                """, (
                    ad_id, target_name, target_slug, page_id, page_name,
                    creation_time, is_suspect, is_camouflaged, triggers_str,
                    ad_url, spend_min, spend_max, raw_json, now, now
                ))
                inserted_count += 1

            conn.commit()

        logger.info(f"{inserted_count} anúncio(s) catalogados e atualizados na tabela ads_archive.")
        return inserted_count

    def list_targets(self) -> List[Dict[str, Any]]:
        """Retorna todos os alvos auditados e seus totais consolidados."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    t.name,
                    t.slug,
                    t.first_audited_at,
                    t.last_audited_at,
                    t.total_dossiers_count,
                    COUNT(DISTINCT a.ad_id) as total_ads_stored,
                    SUM(CASE WHEN a.is_suspect = 1 THEN 1 ELSE 0 END) as total_suspect_ads
                FROM targets t
                LEFT JOIN ads_archive a ON t.slug = a.target_slug
                GROUP BY t.slug
                ORDER BY t.last_audited_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_history_for_target(self, target_slug: str) -> List[Dict[str, Any]]:
        """Retorna a linha do tempo de dossiês gerados para um alvo."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    dossier_id, target_name, generated_at_utc,
                    total_ads_analyzed, total_suspects,
                    total_declared_min, total_declared_max,
                    estimated_hidden_min, estimated_hidden_max,
                    peak_burst_rate, trends_dawn_mean, trends_z_score,
                    trends_anomaly_status, sha256_hash
                FROM dossiers
                WHERE target_slug = ?
                ORDER BY generated_at_utc DESC
            """, (target_slug,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def compare_targets(self, slug1: str, slug2: str) -> Dict[str, Any]:
        """Compara métricas e páginas em comum entre dois alvos investigados."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Último dossiê do alvo 1
            cursor.execute("SELECT * FROM dossiers WHERE target_slug = ? ORDER BY generated_at_utc DESC LIMIT 1", (slug1,))
            d1 = cursor.fetchone()
            
            # Último dossiê do alvo 2
            cursor.execute("SELECT * FROM dossiers WHERE target_slug = ? ORDER BY generated_at_utc DESC LIMIT 1", (slug2,))
            d2 = cursor.fetchone()

            # Identifica se existem páginas que veicularam anúncios para AMBOS os alvos (Rede Compartilhada)
            cursor.execute("""
                SELECT DISTINCT page_name, page_id 
                FROM ads_archive 
                WHERE target_slug = ? 
                INTERSECT 
                SELECT DISTINCT page_name, page_id 
                FROM ads_archive 
                WHERE target_slug = ?
            """, (slug1, slug2))
            shared_pages = [dict(row) for row in cursor.fetchall()]

            return {
                "target1": dict(d1) if d1 else None,
                "target2": dict(d2) if d2 else None,
                "shared_satellite_pages": shared_pages,
            }


# Instância global Singleton
db_manager = DatabaseManager()
