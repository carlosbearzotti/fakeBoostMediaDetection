"""
Configurações Globais do Sistema de Auditoria OSINT.
Carrega parâmetros a partir de variáveis de ambiente (.env) com tipagem estrita.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import warnings
from dotenv import load_dotenv
import pandas as pd

# Suprime FutureWarnings do Pandas no ecossistema de DataFrames e pytrends
pd.set_option("future.no_silent_downcasting", True)
warnings.filterwarnings("ignore", category=FutureWarning)

# Carrega arquivo .env da raiz do projeto se existir
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    # Meta Graph API
    meta_access_token: str = os.getenv("META_ACCESS_TOKEN", "")
    meta_api_version: str = os.getenv("META_API_VERSION", "v19.0")
    meta_api_base_url: str = f"https://graph.facebook.com/{meta_api_version}"

    # Limiares de Detecção Estatística
    ad_burst_threshold: int = int(os.getenv("AD_BURST_THRESHOLD", "50"))
    trends_night_threshold: float = float(os.getenv("TRENDS_NIGHT_THRESHOLD", "60.0"))
    trends_variance_max: float = float(os.getenv("TRENDS_VARIANCE_MAX", "150.0"))

    # Configuração de Fuso Horário e Geo (Brasil)
    # tz=180 representa UTC-3 na API do Google Trends (3h * 60min = 180min de offset)
    pytrends_timezone: int = int(os.getenv("PYTRENDS_TIMEZONE", "180"))
    pytrends_geo: str = os.getenv("PYTRENDS_GEO", "BR")
    pytrends_timeframe: str = os.getenv("PYTRENDS_TIMEFRAME", "now 7-d")

    # Persistência e Cache
    db_path: str = os.getenv("DB_PATH", "dossies/auditoria.db")
    cache_ttl_hours: float = float(os.getenv("CACHE_TTL_HOURS", "4.0"))


settings = Settings()
