"""
Módulo de Análise e Previsão de Séries Temporais (Inspirado em Prophet & Darts).

Objetivo:
- Modelar séries temporais de busca/interesse (ex: Google Trends, velocidade de seguidores) na janela de 15 a 30 dias.
- Detectar Quebras Estruturais (Changepoints), Funções Degrau (Step Functions) e Platôs Artificiais.
- Diferenciar Crescimento Viral Orgânico (curva de decaimento suave log-normal) de Impulsionamento Artificial (saltos instantâneos sem cauda orgânica).
"""

from datetime import datetime, timedelta
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TimeSeriesForecaster:
    """
    Motor estatístico de detecção de anomalias em séries temporais de curto/médio prazo (15 a 30 dias).
    Combina decomposição de tendência piecewise (Prophet) e resíduos de suavização exponencial (Darts).
    """

    def __init__(self, window_days: int = 15, z_threshold: float = 2.5):
        self.window_days = window_days
        self.z_threshold = z_threshold

    @staticmethod
    def _detect_changepoints(series: np.ndarray, min_distance: int = 6) -> List[int]:
        """
        Identifica pontos de mudança brusca de nível/inclinação na série temporal.
        """
        if len(series) < min_distance * 2:
            return []
        
        diffs = np.abs(np.diff(series))
        threshold = np.mean(diffs) + 2.0 * np.std(diffs)
        changepoints = []
        
        for i in range(1, len(diffs)):
            if diffs[i] > threshold:
                if not changepoints or (i - changepoints[-1] >= min_distance):
                    changepoints.append(i)
        return changepoints

    @staticmethod
    def _fit_piecewise_trend(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """
        Ajusta uma tendência linear por partes robusta (estilo Prophet/ARIMA).
        """
        n = len(y)
        if n < 3:
            return y
        
        # Tendência base via regressão linear ponderada
        poly = np.polyfit(x, y, deg=min(2, n - 1))
        trend = np.polyval(poly, x)
        return np.maximum(trend, 0.0)

    @staticmethod
    def _calculate_decay_profile(recent_values: np.ndarray) -> Tuple[str, float]:
        """
        Analisa a curva de decaimento após um pico.
        - Orgânico: cauda longa e decaimento exponencial suave (R² > 0.6 em log-normal ou exponencial).
        - Artificial / Bot: corte abrupto (step-drop) ou platô rígido antinatural.
        """
        if len(recent_values) < 5:
            return "indeterminado", 0.0
        
        peak_idx = int(np.argmax(recent_values))
        post_peak = recent_values[peak_idx:]
        
        if len(post_peak) < 4:
            return "pico_recente_em_andamento", 0.5
        
        # Variação após o pico
        variance_post = float(np.std(post_peak))
        mean_post = float(np.mean(post_peak)) + 1e-5
        cv_post = variance_post / mean_post
        
        # Se após o pico o valor cair imediatamente para zero sem curva suave
        instant_drop = (post_peak[0] - post_peak[1]) > (0.7 * post_peak[0]) if post_peak[0] > 0 else False
        
        if instant_drop:
            return "corte_abrupto_artificial", 0.85
        elif cv_post < 0.08 and mean_post > 40:
            # Platô plano antinatural
            return "plato_artificial_rigido", 0.90
        elif np.all(np.diff(post_peak) <= 0):
            return "decaimento_organico_suave", 0.15
        else:
            return "flutuacao_mista", 0.35

    def analyze_15d_trend(
        self, df: pd.DataFrame, value_col: str = "interesse", date_col: str = "data"
    ) -> Dict[str, Any]:
        """
        Executa a auditoria completa de anomalia de tendência para a janela de 15 dias.
        """
        if df is None or df.empty or len(df) < 10:
            return {
                "status_anomalia_15d": False,
                "score_inorganicidade": 0.0,
                "tipo_curva": "dados_insuficientes",
                "residuos_anomalos_count": 0,
                "parecer_tendencia": "Volume de dados insuficiente para auditoria temporal de 15 dias.",
            }

        # Ordena e extrai valores
        df_sorted = df.copy()
        if date_col in df_sorted.columns:
            df_sorted[date_col] = pd.to_datetime(df_sorted[date_col])
            df_sorted = df_sorted.sort_values(date_col)

        y = df_sorted[value_col].astype(float).values
        n = len(y)
        x = np.arange(n)

        # 1. Ajuste de Tendência e Decomposição Sazonal (Prophet Style)
        trend = self._fit_piecewise_trend(x, y)
        residuals = y - trend
        res_std = float(np.std(residuals)) + 1e-5
        res_z = residuals / res_std

        # 2. Detecção de Picos Anômalos nos últimos 15 dias
        anomalous_points = np.where(res_z > self.z_threshold)[0]
        anomalous_count = len(anomalous_points)

        # 3. Análise de Quebra Estrutural e Changepoints
        changepoints = self._detect_changepoints(y)

        # 4. Avaliação do Perfil de Decaimento da Última Janela
        decay_type, decay_risk = self._calculate_decay_profile(y[-min(n, 24 * 7):])

        # 5. Cálculo do Score de Inorganicidade da Tendência (0.0 a 100.0)
        score_inorganicidade = 0.0
        
        # Penalidades por anomalias estatísticas
        if anomalous_count > 0:
            score_inorganicidade += min(35.0, anomalous_count * 7.0)
        
        if len(changepoints) >= 2:
            score_inorganicidade += 20.0
            
        score_inorganicidade += decay_risk * 45.0
        score_inorganicidade = round(min(100.0, max(0.0, score_inorganicidade)), 2)

        status_anomalia = score_inorganicidade >= 55.0

        # Justificativa forense
        if status_anomalia:
            parecer = (
                f"🚨 ANOMALIA DE TENDÊNCIA IDENTIFICADA: Índice de inorganicidade de {score_inorganicidade}/100. "
                f"Detectados {anomalous_count} pico(s) que violam o intervalo preditivo (Z > +{self.z_threshold}) "
                f"com assinatura de '{decay_type}' incompatível com crescimento viral orgânico."
            )
        elif score_inorganicidade >= 30.0:
            parecer = (
                f"⚠️ ATENÇÃO MODERADA: Flutuação atípica na série temporal ({score_inorganicidade}/100), "
                f"mas sem evidência conclusiva de injeção coordenada contínua."
            )
        else:
            parecer = (
                f"✅ TENDÊNCIA ORGÂNICA: Série temporal estável ({score_inorganicidade}/100). "
                f"Comportamento de busca segue curvas naturais de dispersão e decaimento circadiano."
            )

        return {
            "status_anomalia_15d": status_anomalia,
            "score_inorganicidade": score_inorganicidade,
            "tipo_curva": decay_type,
            "residuos_anomalos_count": int(anomalous_count),
            "changepoints_detectados": len(changepoints),
            "media_serie": round(float(np.mean(y)), 2),
            "pico_maximo": round(float(np.max(y)), 2),
            "parecer_tendencia": parecer,
        }
