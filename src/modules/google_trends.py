"""
Módulo 2: Google Trends Detector (Auditoria Forense de Séries Temporais Reais).

Objetivo:
- Consultar exclusivamente o Google Trends em tempo real via pytrends.
- Configurar fuso horário do Brasil (tz=180 -> UTC-3) e janela horária de 7 dias ('now 7-d').
- Decompor o ciclo circadiano real (01h-05h vs período diurno).
- Identificar desvios da linha de base biológica e platôs inorgânicos.
- Não utiliza dados sintéticos/mock.
"""

import io
import json
from datetime import datetime
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.config import settings
from src.database.cache_manager import cache_manager

logger = logging.getLogger(__name__)


class GoogleTrendsAnomalyDetector:
    """
    Analisador de séries temporais reais do Google Trends para auditoria de Click Farms.
    """

    def __init__(
        self,
        timezone: Optional[int] = None,
        geo: Optional[str] = None,
        timeframe: Optional[str] = None,
        night_threshold: Optional[float] = None,
        variance_max: Optional[float] = None,
    ):
        self.timezone = timezone or settings.pytrends_timezone
        self.geo = geo or settings.pytrends_geo
        self.timeframe = timeframe or settings.pytrends_timeframe
        self.night_threshold = night_threshold or settings.trends_night_threshold
        self.variance_max = variance_max or settings.trends_variance_max

    def fetch_hourly_trends(self, keyword: str, force_refresh: bool = False) -> Tuple[pd.DataFrame, str]:
        """
        Coleta a série temporal horária real do Google Trends para a palavra-chave.
        Utiliza camada de cache local para prevenir erros 429 e otimizar tempo de resposta.
        Implementa retentativa suave em caso de 429.
        """
        cache_identifier = keyword.strip().lower()
        extra_cache_params = {
            "geo": self.geo,
            "timeframe": self.timeframe,
            "timezone": self.timezone,
        }

        # 1. Consulta no Cache Local
        if not force_refresh:
            cached_data = cache_manager.get("google_trends", cache_identifier, extra_cache_params)
            if cached_data is not None:
                try:
                    raw_str = cached_data if isinstance(cached_data, str) else json.dumps(cached_data)
                    df_cached = pd.read_json(io.StringIO(raw_str))
                    if not df_cached.empty and keyword in df_cached.columns:
                        logger.info(f"Google Trends: {len(df_cached)} pontos carregados do cache persistente para '{keyword}'.")
                        return df_cached[[keyword]].copy(), "Google Trends pytrends API (Cache Local Válido)"
                except Exception as e:
                    logger.warning(f"Erro ao converter dados cacheados do Trends: {e}")

        # 2. Consulta Live à API do Google Trends
        for attempt in range(1, 3):
            try:
                from pytrends.request import TrendReq

                pytrends = TrendReq(hl="pt-BR", tz=self.timezone, timeout=(10, 25))
                pytrends.build_payload([keyword], cat=0, timeframe=self.timeframe, geo=self.geo)
                df = pytrends.interest_over_time()

                if df is not None and not df.empty and keyword in df.columns:
                    logger.info(f"Google Trends: {len(df)} pontos horários reais coletados para '{keyword}'.")
                    # Salva no cache
                    cache_manager.set(
                        "google_trends",
                        cache_identifier,
                        df[[keyword]],
                        extra_cache_params,
                        ttl_hours=settings.cache_ttl_hours,
                    )
                    return df[[keyword]].copy(), "Google Trends pytrends API (Dados Reais)"
                else:
                    logger.warning(f"Google Trends retornou volume zero ou vazio para '{keyword}'.")
                    return pd.DataFrame(), "Google Trends pytrends API (Sem volume de busca registrado)"

            except Exception as exc:
                if "429" in str(exc) and attempt == 1:
                    logger.warning("Google Trends respondeu com 429. Aguardando 3s antes de nova tentativa...")
                    time.sleep(3)
                    continue
                
                logger.warning(f"Google Trends indisponível ({exc}).")
                return pd.DataFrame(), f"Google Trends (Indisponível temporariamente: {exc})"

        return pd.DataFrame(), "Google Trends (Rate-limited temporário pelo Google)"

    def analyze_night_traffic(
        self, df: pd.DataFrame, keyword: str
    ) -> Dict[str, Any]:
        """
        Algoritmo de Detecção de Platô Noturno e Quebra Circadiana sobre Dados Reais do Google Trends.
        """
        if df.empty or keyword not in df.columns:
            return {
                "status_anomalia": False,
                "media_madrugada": 0.0,
                "media_diurna": 0.0,
                "media_baseline_noturna": 0.0,
                "razao_noturno_diurno": 0.0,
                "z_score_madrugada": 0.0,
                "desvio_padrao": 0.0,
                "coeficiente_variacao": 0.0,
                "total_dias_anomalos": 0,
                "picos_anomalos": [],
                "evidencia": "Nenhum dado de interesse relativo foi registrado para o termo no Google Trends no período.",
            }

        df_analysis = df.copy()
        if not isinstance(df_analysis.index, pd.DatetimeIndex):
            df_analysis.index = pd.to_datetime(df_analysis.index)

        df_analysis["audit_hour"] = df_analysis.index.hour
        df_analysis["audit_date_str"] = df_analysis.index.strftime("%Y-%m-%d")

        # Segmentação horária: Madrugada (01h-05h) vs Dia Ativo (08h-22h)
        night_mask = df_analysis["audit_hour"].isin([1, 2, 3, 4, 5])
        day_mask = df_analysis["audit_hour"].isin(range(8, 23))

        night_df = df_analysis[night_mask]
        day_df = df_analysis[day_mask]

        if night_df.empty or day_df.empty:
            return {
                "status_anomalia": False,
                "media_madrugada": 0.0,
                "media_diurna": 0.0,
                "media_baseline_noturna": 0.0,
                "razao_noturno_diurno": 0.0,
                "z_score_madrugada": 0.0,
                "desvio_padrao": 0.0,
                "coeficiente_variacao": 0.0,
                "total_dias_anomalos": 0,
                "picos_anomalos": [],
                "evidencia": "Série temporal com granularidade horária insuficiente para decomposição circadiana.",
            }

        # Estatísticas diárias da madrugada
        daily_night_stats = (
            night_df.groupby("audit_date_str")[keyword]
            .agg(mean="mean", std="std", count="count")
            .reset_index()
        )
        anomalous_days = daily_night_stats[daily_night_stats["mean"] >= self.night_threshold]
        normal_days = daily_night_stats[daily_night_stats["mean"] < self.night_threshold]

        # Médias consolidadas reais
        media_madrugada_global = float(night_df[keyword].mean())
        desvio_padrao_global = float(night_df[keyword].std()) if float(night_df[keyword].std()) > 0 else 0.1
        media_diurna_global = float(day_df[keyword].mean())
        desvio_padrao_diurno = float(day_df[keyword].std()) if float(day_df[keyword].std()) > 0 else 1.0

        # Filtro de Quantização (Volume Diurno Mínimo)
        MIN_DAYTIME_VOLUME = 30.0
        if media_diurna_global < MIN_DAYTIME_VOLUME:
            return {
                "status_anomalia": False,
                "media_madrugada": round(media_madrugada_global, 2),
                "media_diurna": round(media_diurna_global, 2),
                "media_baseline_noturna": 0.0,
                "razao_noturno_diurno": round(float(media_madrugada_global / media_diurna_global) if media_diurna_global > 0 else 0.0, 3),
                "z_score_madrugada": 0.0,
                "desvio_padrao": round(desvio_padrao_global, 2),
                "coeficiente_variacao": 0.0,
                "total_dias_anomalos": 0,
                "picos_anomalos": [],
                "evidencia": f"Volume diurno médio ({media_diurna_global:.1f}/100) abaixo do limiar de significância estatística ({MIN_DAYTIME_VOLUME}/100). Flutuações noturnas descartadas como ruído de quantização.",
            }

        # Linha de base noturna real
        if not normal_days.empty and len(normal_days) >= 2:
            media_baseline_noturna = float(normal_days["mean"].mean())
            desvio_padrao_baseline = float(normal_days["std"].mean()) if float(normal_days["std"].mean()) > 0 else 1.0
        else:
            media_baseline_noturna = float(media_diurna_global * 0.18)
            desvio_padrao_baseline = float(media_baseline_noturna * 0.25) if media_baseline_noturna > 0 else 1.0

        # Média nas noites sob suspeita
        if not anomalous_days.empty:
            media_madrugada_analisada = float(anomalous_days["mean"].max())
            desvio_padrao_analisado = (
                float(anomalous_days["std"].mean())
                if not anomalous_days["std"].isna().all()
                else desvio_padrao_global
            )
        else:
            media_madrugada_analisada = media_madrugada_global
            desvio_padrao_analisado = desvio_padrao_global

        razao_noturno_diurno = (
            float(media_madrugada_analisada / media_diurna_global)
            if media_diurna_global > 0
            else 0.0
        )

        # Laplace Smoothing para evitar divisão por zero/instabilidade estatística
        LAPLACE_EPSILON = 2.0
        z_score_madrugada = float(
            (media_madrugada_analisada - media_baseline_noturna) / (desvio_padrao_baseline + LAPLACE_EPSILON)
        )

        cv_madrugada = (
            float(desvio_padrao_analisado / media_madrugada_analisada)
            if media_madrugada_analisada > 0
            else 0.0
        )

        picos_df = night_df[night_df[keyword] >= self.night_threshold]
        picos_anomalos = [dt.strftime("%Y-%m-%d %H:%M") for dt in picos_df.index]

        is_anomaly = bool(
            len(anomalous_days) > 0
            or (media_madrugada_global >= self.night_threshold and z_score_madrugada > 2.0)
        )

        if is_anomaly:
            dias_str = ", ".join(anomalous_days["audit_date_str"].tolist()) if not anomalous_days.empty else "Período recente"
            evidencia = (
                f"Quebra de ciclo circadiano e platô inorgânico comprovados nos dados reais: "
                f"Identificados {len(anomalous_days)} dia(s) ({dias_str}) com platô noturno sustentado "
                f"(pico médio na madrugada de {media_madrugada_analisada:.1f}/100 vs baseline real de {media_baseline_noturna:.1f}/100, "
                f"Z-Score Canônico = +{z_score_madrugada:.2f}, Razão Noturno/Diurno = {razao_noturno_diurno:.2f}). "
                f"Registrados {len(picos_anomalos)} pontos horários de alta intensidade entre 01h e 05h com CV de {cv_madrugada:.2%}."
            )
        else:
            evidencia = (
                f"Comportamento orgânico real: Média noturna real de {media_madrugada_global:.1f}/100 "
                f"(Razão Noturno/Diurno = {razao_noturno_diurno:.2f}, Z-Score = +{z_score_madrugada:.2f}), "
                f"em conformidade com o ciclo natural de descompressão humana."
            )

        return {
            "status_anomalia": is_anomaly,
            "media_madrugada": round(media_madrugada_analisada if is_anomaly else media_madrugada_global, 2),
            "media_diurna": round(media_diurna_global, 2),
            "media_baseline_noturna": round(media_baseline_noturna, 2),
            "razao_noturno_diurno": round(razao_noturno_diurno, 3),
            "z_score_madrugada": round(z_score_madrugada, 2),
            "desvio_padrao": round(desvio_padrao_analisado if is_anomaly else desvio_padrao_global, 2),
            "coeficiente_variacao": round(cv_madrugada, 3),
            "total_dias_anomalos": len(anomalous_days),
            "picos_anomalos": picos_anomalos,
            "evidencia": evidencia,
        }
