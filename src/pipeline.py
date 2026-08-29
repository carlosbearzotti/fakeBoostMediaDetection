"""
Módulo 3: Pipeline de Consolidação e Gerador do Dossiê Técnico.

Objetivo:
- Orquestrar a execução dos motores de auditoria:
  1. Meta Ad Library & Desambiguação Forense.
  2. Google Trends & Detecção de Tráfego Noturno (01h-05h).
  3. Previsão Temporal e Quebra Estrutural em 15 Dias (Prophet & Darts).
  4. Detecção de Redes Coordenadas e Páginas Satélites (CooRnet & Bot-Detector).
  5. Classificação Semântica NLP e Estimativa de Spend Oculto (facebook-political-ads).
- Calcular o Índice Consolidado de Risco de Astroturfing (IRA).
- Gerar o dossiê probatório em formatos JSON e HTML para denúncias (TSE/Meta/MPE).
"""

import json
import logging
from typing import List, Optional
import uuid

from src.config import settings
from src.database.db_manager import db_manager
from src.models.dossier import (
    AdBurstEvidence,
    AnomaliaTrafegoMadrugada,
    AnomaliaTendencia15Dias,
    CamouflagedAdEvidence,
    CoordenacaoRedeAgencias,
    DivergenciaCategoria,
    DossieTecnico,
    InvestimentoEstimado,
    MetadadosInvestigacao,
    PegadaAutomacao,
)
from src.modules.coordination_detector import CoordinationDetector
from src.modules.google_trends import GoogleTrendsAnomalyDetector
from src.modules.meta_ad_library import MetaAdAnomalyDetector
from src.modules.political_nlp import PoliticalNLPClassifier
from src.modules.time_series_forecaster import TimeSeriesForecaster

logger = logging.getLogger(__name__)


class ForensicAuditPipeline:
    """
    Pipeline unificado de auditoria forense sobre dados reais com motores de IA e estatística avançada.
    """

    def __init__(
        self,
        meta_detector: Optional[MetaAdAnomalyDetector] = None,
        trends_detector: Optional[GoogleTrendsAnomalyDetector] = None,
        forecaster: Optional[TimeSeriesForecaster] = None,
        coordination_detector: Optional[CoordinationDetector] = None,
        nlp_classifier: Optional[PoliticalNLPClassifier] = None,
    ):
        self.meta_detector = meta_detector or MetaAdAnomalyDetector()
        self.trends_detector = trends_detector or GoogleTrendsAnomalyDetector()
        self.forecaster = forecaster or TimeSeriesForecaster(window_days=15)
        self.coordination_detector = coordination_detector or CoordinationDetector(time_threshold_minutes=60)
        self.nlp_classifier = nlp_classifier or PoliticalNLPClassifier()

    def run_investigation(
        self,
        target_name: str = "Augusto Cury",
        page_id: Optional[str] = None,
        keyword: Optional[str] = None,
        context_tags: Optional[List[str]] = None,
        force_refresh: bool = False,
        target_slug: Optional[str] = None,
    ) -> DossieTecnico:
        """
        Executa a investigação forense completa cruzando dados reais e calculando o risco de astroturfing.
        """
        search_keyword = keyword or target_name
        dossier_id = f"DOSSIE-{target_name.upper().replace(' ', '_')}-{uuid.uuid4().hex[:8].upper()}"
        slug = target_slug or target_name.lower().replace(" ", "_")

        logger.info(f"Iniciando auditoria para o alvo '{target_name}'...")

        # 1. Coleta e análise de anúncios reais na Meta Ad Library com desambiguação de homônimos
        logger.info(f"Etapa 1/4: Consultando Meta Ad Library com desambiguação para '{target_name}'...")
        ads_raw, origem_meta = self.meta_detector.fetch_ads_from_api(
            target_name=target_name,
            page_id=page_id,
            context_tags=context_tags,
            force_refresh=force_refresh,
        )
        meta_analysis = self.meta_detector.analyze_burst_anomalies(
            ads_raw, target_name=target_name, api_status=origem_meta
        )

        # 2. Coleta e análise de tráfego real no Google Trends
        logger.info(f"Etapa 2/4: Consultando Google Trends para '{search_keyword}' (7-15 dias)...")
        trends_df, origem_trends = self.trends_detector.fetch_hourly_trends(
            keyword=search_keyword,
            force_refresh=force_refresh,
        )
        trends_analysis = self.trends_detector.analyze_night_traffic(trends_df, keyword=search_keyword)

        # 3. Motor A: Auditoria de Séries Temporais de 15 Dias (Prophet / Darts Style)
        logger.info(f"Etapa 3/4: Executando análise de quebra estrutural e decaimento em 15 dias...")
        trends_col = "interesse" if "interesse" in trends_df.columns else trends_df.columns[0] if not trends_df.empty else "interesse"
        trend_15d_raw = self.forecaster.analyze_15d_trend(trends_df, value_col=trends_col)

        anomalia_15d = AnomaliaTendencia15Dias(
            status_anomalia_15d=trend_15d_raw.get("status_anomalia_15d", False),
            score_inorganicidade=trend_15d_raw.get("score_inorganicidade", 0.0),
            tipo_curva=trend_15d_raw.get("tipo_curva", "indeterminado"),
            residuos_anomalos_count=trend_15d_raw.get("residuos_anomalos_count", 0),
            changepoints_detectados=trend_15d_raw.get("changepoints_detectados", 0),
            parecer_tendencia=trend_15d_raw.get("parecer_tendencia", ""),
        )

        # 4. Motor B: Detecção de Redes Coordenadas & Satélites (CooRnet Style)
        logger.info(f"Etapa 4/4: Executando detecção de Coordinated Link Sharing e páginas satélites...")
        coordination_raw = self.coordination_detector.analyze_coordinated_networks(
            ads_data=ads_raw,
            target_name=target_name,
            official_entities=context_tags,
        )

        coordenacao_agencias = CoordenacaoRedeAgencias(
            score_coordenacao=coordination_raw.get("score_coordenacao", 0.0),
            status_rede_coordenada=coordination_raw.get("status_rede_coordenada", False),
            total_paginas_agencia=coordination_raw.get("total_paginas_agencia", 0),
            paginas_agencia_detectadas=coordination_raw.get("paginas_agencia_detectadas", []),
            clusters_coordenados=coordination_raw.get("clusters_coordenados", []),
            parecer_coordenacao=coordination_raw.get("parecer_coordenacao", ""),
        )

        # 5. Mapeamento das evidências de Ad Flooding e Camuflagem
        janelas_evidencias = [
            AdBurstEvidence(
                window_timestamp=w["window_timestamp"],
                ad_count=w["ad_count"],
                rate_metric=w["rate_metric"],
                sample_ad_ids=w["sample_ad_ids"],
            )
            for w in meta_analysis.get("janelas_anomalas", [])
        ]

        amostras_camufladas = [
            CamouflagedAdEvidence(
                ad_id=str(c["ad_id"]),
                page_name=c.get("page_name"),
                tipo_infracao=c.get("tipo_infracao", "Página Satélite Não Registrada"),
                preview_titulo=c["preview_titulo"],
                gatilhos_detectados=c["gatilhos_detectados"],
                motivo_infracao=c["motivo_infracao"],
            )
            for c in meta_analysis.get("anuncios_camuflados", [])
        ]

        divergencia_categoria = DivergenciaCategoria(
            total_anuncios_analisados=meta_analysis.get("total_anuncios", 0),
            total_anuncios_suspeitos=meta_analysis.get("total_suspeitos", 0),
            anuncios_suspeitos_ids=meta_analysis.get("anuncios_suspeitos", []),
            justificativa_tecnica=(
                "Auditoria forense sobre anúncios reais da Meta Ad Library: "
                + meta_analysis.get("justificativa", "")
            ),
            amostras_camufladas=amostras_camufladas if amostras_camufladas else None,
            amostras_conteudo=[
                {
                    "id": ad.get("id"),
                    "page_name": ad.get("page_name"),
                    "titulos": ad.get("ad_creative_link_titles", []),
                    "criativos": ad.get("ad_creative_bodies", []),
                }
                for ad in ads_raw[:5]
            ] if ads_raw else None,
        )

        pegada_automacao = PegadaAutomacao(
            taxa_maxima_identificada=meta_analysis.get("taxa_maxima", "0 ads/min"),
            total_janelas_anomalas=len(janelas_evidencias),
            janelas_criticas=janelas_evidencias,
            conclusao_estatistica=meta_analysis.get("justificativa", ""),
        )

        fin_data = meta_analysis.get("investimento_financeiro", {})
        investimento_estimado = InvestimentoEstimado(
            total_declarado_min=fin_data.get("total_declarado_min", 0.0),
            total_declarado_max=fin_data.get("total_declarado_max", 0.0),
            gasto_direto_pagina_alvo_min=fin_data.get("gasto_direto_pagina_alvo_min", 0.0),
            gasto_direto_pagina_alvo_max=fin_data.get("gasto_direto_pagina_alvo_max", 0.0),
            gasto_rede_coligacao_min=fin_data.get("gasto_rede_coligacao_min", 0.0),
            gasto_rede_coligacao_max=fin_data.get("gasto_rede_coligacao_max", 0.0),
            anuncios_diretos_count=fin_data.get("anuncios_diretos_count", 0),
            anuncios_coligacao_count=fin_data.get("anuncios_coligacao_count", 0),
            estimativa_oculta_min=fin_data.get("estimativa_oculta_min", 0.0),
            estimativa_oculta_max=fin_data.get("estimativa_oculta_max", 0.0),
            media_estimada_por_anuncio=fin_data.get("media_estimada_por_anuncio", "R$ 0,00"),
            resumo_financeiro=fin_data.get("resumo_financeiro", ""),
        )

        anomalia_madrugada = AnomaliaTrafegoMadrugada(
            status_anomalia=trends_analysis.get("status_anomalia", False),
            media_interesse_madrugada=trends_analysis.get("media_madrugada", 0.0),
            media_interesse_diurna=trends_analysis.get("media_diurna"),
            media_baseline_noturna=trends_analysis.get("media_baseline_noturna"),
            razao_noturno_diurno=trends_analysis.get("razao_noturno_diurno"),
            z_score_madrugada=trends_analysis.get("z_score_madrugada"),
            desvio_padrao_madrugada=trends_analysis.get("desvio_padrao", 0.0),
            coeficiente_variacao=trends_analysis.get("coeficiente_variacao"),
            horas_com_pico_anomalo=trends_analysis.get("picos_anomalos", []),
            evidencia_comportamento_inorganico=trends_analysis.get("evidencia", ""),
        )

        # 6. Cálculo do Índice Consolidado de Risco de Astroturfing (IRA: 0 a 100)
        score_madrugada_component = min(100.0, (trends_analysis.get("z_score_madrugada", 0.0) or 0.0) * 20.0) if anomalia_madrugada.status_anomalia else 0.0
        suspect_ratio_score = min(100.0, (meta_analysis.get("total_suspeitos", 0) / max(1, meta_analysis.get("total_anuncios", 1))) * 100.0 * 5.0)

        ira_score = (
            0.35 * score_madrugada_component +
            0.30 * anomalia_15d.score_inorganicidade +
            0.20 * coordenacao_agencias.score_coordenacao +
            0.15 * suspect_ratio_score
        )
        ira_score = round(min(100.0, max(0.0, ira_score)), 2)

        # 7. Resumo Executivo probatório
        if ira_score >= 50.0:
            resumo_executivo = (
                f"🚨 ALERTA FORENSE CRÍTICO — Risco de Astroturfing Alto ({ira_score}/100) para '{target_name}': "
                f"Foram identificados indícios de impulsionamento inorgânico/satélite cruzando "
                f"{meta_analysis.get('total_anuncios', 0)} criativo(s) da Meta e a série temporal de busca. "
                f"Coordenação de Redes: {coordenacao_agencias.score_coordenacao}/100. "
                f"Inorganicidade Temporal 15d: {anomalia_15d.score_inorganicidade}/100."
            )
        elif ira_score >= 25.0:
            resumo_executivo = (
                f"⚠️ ATENÇÃO FORENSE — Risco Moderado de Astroturfing ({ira_score}/100) para '{target_name}': "
                f"Atividade pontual em canais satélites ou flutuações temporais detectadas sem coordenação em massa contínua."
            )
        else:
            resumo_executivo = (
                f"✅ AUDITORIA CONFORME — Comportamento Orgânico ({ira_score}/100) para '{target_name}': "
                f"Foram analisados {meta_analysis.get('total_anuncios', 0)} anúncio(s) na Meta Ad Library e a série temporal real do Google Trends. "
                f"Todos os parâmetros encontram-se rigorosamente dentro dos padrões de conformidade da Res. TSE 23.610/2019."
            )

        dossie = DossieTecnico(
            metadados=MetadadosInvestigacao(
                id_dossie=dossier_id,
                alvo_investigado=target_name,
                page_id_meta=page_id or "Busca Ampla por Termo com Desambiguação",
                termo_busca_trends=search_keyword,
                origem_dados_meta=origem_meta,
                origem_dados_trends=origem_trends,
            ),
            resumo_executivo=resumo_executivo,
            divergencia_categoria=divergencia_categoria,
            pegada_automacao=pegada_automacao,
            investimento_estimado=investimento_estimado,
            anomalia_trafego_madrugada=anomalia_madrugada,
            anomalia_tendencia_15d=anomalia_15d,
            coordenacao_rede_agencias=coordenacao_agencias,
            score_geral_astroturfing=ira_score,
        )

        # 8. Persistência relacional no SQLite
        try:
            db_manager.save_dossier(dossie, target_slug=slug)
            cam_map = {str(c.ad_id): c for c in (amostras_camufladas or [])}
            db_manager.save_ads(
                ads_raw=ads_raw,
                target_name=target_name,
                target_slug=slug,
                suspect_ids=meta_analysis.get("anuncios_suspeitos", []),
                camouflaged_map=cam_map,
            )
        except Exception as err:
            logger.warning(f"Não foi possível persistir no SQLite: {err}")

        return dossie

    def export_dossier_json(self, dossie: DossieTecnico, output_path: str = "dossie_tecnico.json") -> str:
        """
        Exporta o dossiê técnico em formato JSON padronizado com indentação UTF-8.
        """
        json_data = dossie.model_dump_json(indent=2)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_data)
        logger.info(f"Dossiê exportado com sucesso para: {output_path}")
        return json_data
