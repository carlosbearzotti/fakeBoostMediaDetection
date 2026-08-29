"""
Modelos de dados para o Dossiê Técnico de Auditoria Cívica e OSINT.
Unifica e padroniza as evidências para exportação em formato JSON probatório.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class AdBurstEvidence(BaseModel):
    """Evidência de criação de anúncios em lote sincronizado."""
    window_timestamp: str = Field(description="Janela de tempo de agrupamento (minuto ou segundo)")
    ad_count: int = Field(description="Quantidade de anúncios criados na janela")
    rate_metric: str = Field(description="Taxa calculada (ex: '59 ads/min')")
    sample_ad_ids: List[str] = Field(default_factory=list, description="Amostra de IDs de anúncios disparados no burst")


class CamouflagedAdEvidence(BaseModel):
    """Evidência de criativo com conteúdo político camuflado em produto comercial ou veiculado por página satélite."""
    ad_id: str = Field(description="ID único do anúncio na Meta")
    page_name: Optional[str] = Field(default=None, description="Nome da página anunciante")
    tipo_infracao: str = Field(default="Página Satélite / Terceiro", description="Tipo de irregularidade (Satélite, Camuflagem de Livro ou Lote)")
    preview_titulo: str = Field(description="Título ou headline do criativo")
    gatilhos_detectados: List[str] = Field(description="Termos/expressões sociopolíticas identificadas no criativo")
    motivo_infracao: str = Field(description="Fundamentação da infração de transparência eleitoral")


class InvestimentoEstimado(BaseModel):
    """Métricas de investimento financeiro oficial, segregação de rede e projeção de dark money."""
    total_declarado_min: float = Field(default=0.0, description="Total mínimo declarado oficialmente na Meta em BRL")
    total_declarado_max: float = Field(default=0.0, description="Total máximo declarado oficialmente na Meta em BRL")
    gasto_direto_pagina_alvo_min: float = Field(default=0.0, description="Gasto mínimo da página oficial própria do candidato em BRL")
    gasto_direto_pagina_alvo_max: float = Field(default=0.0, description="Gasto máximo da página oficial própria do candidato em BRL")
    gasto_rede_coligacao_min: float = Field(default=0.0, description="Gasto mínimo de parceiros/candidatos da rede/coligação em BRL")
    gasto_rede_coligacao_max: float = Field(default=0.0, description="Gasto máximo de parceiros/candidatos da rede/coligação em BRL")
    anuncios_diretos_count: int = Field(default=0, description="Quantidade de anúncios da página própria")
    anuncios_coligacao_count: int = Field(default=0, description="Quantidade de anúncios de aliados/coligação citando o alvo")
    estimativa_oculta_min: float = Field(default=0.0, description="Estimativa mínima projetada de gasto não rotulado em BRL")
    estimativa_oculta_max: float = Field(default=0.0, description="Estimativa máxima projetada de gasto não rotulado em BRL")
    media_estimada_por_anuncio: str = Field(description="Média projetada de investimento por criativo")
    resumo_financeiro: str = Field(description="Parecer forense sobre o volume financeiro estimado na campanha")


class DivergenciaCategoria(BaseModel):
    """
    Registros de anúncios que violam transparência (anúncios políticos camuflados de infoprodutos).
    """
    total_anuncios_analisados: int = Field(description="Total de anúncios processados")
    total_anuncios_suspeitos: int = Field(description="Total de anúncios associados a padrões de astroturfing ou infração")
    anuncios_suspeitos_ids: List[str] = Field(description="Lista de IDs de anúncios identificados com irregularidades")
    justificativa_tecnica: str = Field(
        description="Explicação da ausência de rótulo 'Eleições e Política' e ocultação de spend"
    )
    amostras_camufladas: Optional[List[CamouflagedAdEvidence]] = Field(
        default=None, description="Amostras detalhadas de criativos camuflados detectados"
    )
    amostras_conteudo: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Metadados de títulos/criativos detectados"
    )


class PegadaAutomacao(BaseModel):
    """
    Métricas de volume e velocidade temporal comprovando atuação automatizada (bot/script).
    """
    taxa_maxima_identificada: str = Field(description="Pico de vazão de publicação (ex: '150 ads/min')")
    total_janelas_anomalas: int = Field(description="Número de minutos/segundos em que o limiar foi ultrapassado")
    janelas_criticas: List[AdBurstEvidence] = Field(description="Detalhamento das janelas de disparo em massa")
    conclusao_estatistica: str = Field(description="Parecer técnico sobre a impossibilidade de intervenção humana manual")


class AnomaliaTrafegoMadrugada(BaseModel):
    """
    Métricas de detecção de click farms e bots no Google Trends entre 01:00 e 05:00 da manhã.
    """
    status_anomalia: bool = Field(description="Flag indicando se foi detectado platô inorgânico noturno")
    media_interesse_madrugada: float = Field(description="Índice médio de interesse relativo (0-100) na janela 01h-05h")
    media_interesse_diurna: Optional[float] = Field(default=None, description="Média do período diurno ativo para referência")
    media_baseline_noturna: Optional[float] = Field(default=None, description="Linha de base histórica esperada para madrugada")
    razao_noturno_diurno: Optional[float] = Field(default=None, description="Razão canônica entre tráfego noturno e diurno")
    z_score_madrugada: Optional[float] = Field(
        default=None, description="Z-Score canônico de desvio estatístico em relação à linha de base noturna"
    )
    desvio_padrao_madrugada: float = Field(description="Medida de dispersão no período noturno")
    coeficiente_variacao: Optional[float] = Field(default=None, description="Coeficiente de variação (std/mean)")
    horas_com_pico_anomalo: List[str] = Field(description="Horários específicos em que o índice superou o limiar de alerta")
    evidencia_comportamento_inorganico: str = Field(
        description="Demonstração da quebra do ciclo circadiano natural de busca humana"
    )


class AnomaliaTendencia15Dias(BaseModel):
    """
    Métricas de auditoria de séries temporais de 15 dias (Prophet / Darts).
    """
    status_anomalia_15d: bool = Field(description="Indica anomalia estatística na janela de 15 dias")
    score_inorganicidade: float = Field(description="Score de inorganicidade temporal (0-100)")
    tipo_curva: str = Field(description="Classificação da curva de decaimento (orgânico vs step-function artificial)")
    residuos_anomalos_count: int = Field(description="Quantidade de picos violando o intervalo de confiança")
    changepoints_detectados: int = Field(description="Quebras estruturais identificadas na série temporal")
    parecer_tendencia: str = Field(description="Parecer técnico sobre o comportamento da série temporal")


class CoordenacaoRedeAgencias(BaseModel):
    """
    Métricas de detecção de redes coordenadas e páginas satélites (CooRnet / Bot-Detector).
    """
    score_coordenacao: float = Field(description="Score de coordenação de rede (0-100)")
    status_rede_coordenada: bool = Field(description="Indica se há atuação sincronizada de páginas satélites")
    total_paginas_agencia: int = Field(description="Total de páginas satélites não-oficiais detectadas")
    paginas_agencia_detectadas: List[Dict[str, Any]] = Field(default_factory=list, description="Lista de páginas satélites")
    clusters_coordenados: List[Dict[str, Any]] = Field(default_factory=list, description="Clusters temporais de disparo CooRnet")
    parecer_coordenacao: str = Field(description="Parecer forense sobre o grau de coordenação de rede")


class MetadadosInvestigacao(BaseModel):
    """Metadados de controle e cadeia de custódia da investigação."""
    id_dossie: str = Field(description="Identificador único do dossiê")
    data_geracao_utc: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    alvo_investigado: str = Field(description="Nome do perfil/figura pública investigada")
    page_id_meta: str = Field(description="ID da página do Facebook/Instagram ou termo pesquisado")
    termo_busca_trends: str = Field(description="Termo investigado no Google Trends")
    origem_dados_meta: str = Field(
        description="Indica se a fonte foi Meta Graph API Real ou Simulação"
    )
    origem_dados_trends: str = Field(
        description="Indica se a fonte foi Google Trends Live ou Simulação"
    )
    orgaos_destinatarios: List[str] = Field(
        default_factory=lambda: [
            "TSE - Tribunal Superior Eleitoral",
            "Meta Platforms Compliance / Ad Transparency Team",
            "Ministério Público Eleitoral (MPE)"
        ],
        description="Órgãos e entidades de destino da auditoria"
    )


class DossieTecnico(BaseModel):
    """
    Dossiê consolidado de Auditoria Cívica pronto para exportação JSON e HTML probatório.
    """
    metadados: MetadadosInvestigacao
    resumo_executivo: str = Field(description="Sumário dos achados para autoridades e órgãos reguladores")
    
    # Chaves principais da auditoria
    divergencia_categoria: DivergenciaCategoria
    pegada_automacao: PegadaAutomacao
    investimento_estimado: InvestimentoEstimado
    anomalia_trafego_madrugada: AnomaliaTrafegoMadrugada

    # Motores Avançados (15 Dias / CooRnet CLSB)
    anomalia_tendencia_15d: Optional[AnomaliaTendencia15Dias] = None
    coordenacao_rede_agencias: Optional[CoordenacaoRedeAgencias] = None
    score_geral_astroturfing: Optional[float] = Field(default=0.0, description="Índice Consolidado de Risco de Astroturfing (0-100)")
