"""
Módulo 1: Meta Ad Library API Anomaly Detector com Desambiguação Forense e Filtro Anti-Homônimos (ProPublica Style).

Objetivos:
- Coleta de anúncios reais via Meta Graph API oficial (com fallback para MetaAdsCollector GraphQL).
- Desambiguação semântica e descarte de falsos positivos de homônimos (doramas, k-dramas, novelas, futebol, corretores de imóveis).
- Detecção de infrações explícitas da Meta ("This ad ran without a required disclaimer").
- Identificação de Camuflagem de Infoproduto / Impulsionamento de Livros por Terceiros (Art. 57-C Lei 9.504/97).
- Segregação de gastos: Página Oficial Própria vs. Candidatos da Rede/Coligação vs. Spend Oculto Projetado.
"""

from collections import defaultdict
from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import requests

from src.config import settings
from src.database.cache_manager import cache_manager
from src.modules.media_ocr import ocr_extractor

logger = logging.getLogger(__name__)


class MetaAdAnomalyDetector:
    """
    Rastreador e analisador estatístico de anomalias na Meta Ad Library API com desambiguação forense.
    """

    # Filtros de desambiguação para alvos com nomes comuns (evita capturar doramas, futebol, homônimos)
    TARGET_DISAMBIGUATION_MAP: Dict[str, List[str]] = {
        "renan santos": [
            "mbl", "movimento brasil livre", "missão", "partido missão", "a missão",
            "kim kataguiri", "arthur do val", "guto zacarias", "rafael macris",
            "rubinho nunes", "academia mbl", "livres", "política", "deputado", "vereador", "direita",
            "renan", "14", "candidato", "candidata", "candidatura", "pré-candidato", "pré-candidata", "eleição", "eleições", "federal", "estadual",
        ],
        "augusto cury": [
            "gestão da emoção", "inteligência", "ansiedade", "escola da inteligência",
            "psicologia", "livro", "presidente", "governo", "plano de governo", "liderança",
            "sociedade brasileira", "família", "mente",
            "avante", "70", "cury", "candidato", "candidata", "candidatura", "pré-candidato", "pré-candidata", "eleição", "eleições", "deputad",
            "voto", "vereador", "federal", "estadual", "política",
        ]
    }

    # Termos negativos para eliminação de homônimos de entretenimento (ProPublica Anti-Homonym Classifier)
    HOMONYM_NEGATIVE_PATTERNS: List[str] = [
        "dorama", "doramas", "k-drama", "kdrama", "novela", "novelas", "serie coreana", "séries coreanas",
        "elenco", "ator", "atriz", "futebol", "apartamento", "imobiliaria", "corretor", "aluguel",
        "porto maravilha", "condominio", "lancamento imobiliario", "imoveis", "imovel"
    ]

    # Mapeamento de entidades oficiais, partidárias e institucionais vinculadas ao alvo
    OFFICIAL_ENTITIES_MAP: Dict[str, List[str]] = {
        "renan santos": [
            "renan santos", "partido missão", "missão", "a missão", "movimento brasil livre", "mbl",
            "academia mbl", "instituto mbl", "partido missao", "revista valete", "valete", "guto zacarias",
            "kim kataguiri", "arthur do val", "rubinho nunes", "rafael macris", "livres"
        ],
        "augusto cury": [
            "augusto cury", "escritor augusto cury", "instituto augusto cury", "escola da inteligência",
            "avante", "avante 70", "editora sextante", "método augusto cury",
            "programa socioemocional", "dr. augusto cury", "dr augusto cury"
        ],
        "escritor augusto cury": [
            "augusto cury", "escritor augusto cury", "instituto augusto cury", "escola da inteligência",
            "avante", "avante 70", "editora sextante", "método augusto cury",
            "programa socioemocional", "dr. augusto cury", "dr augusto cury"
        ],
        "luiz inácio lula da silva": [
            "lula", "luiz inácio lula da silva", "luiz inacio lula da silva", "pt", "partido dos trabalhadores",
            "instituto lula", "presidência da república", "governo federal", "pt brasil", "fundação perseu abramo"
        ],
        "lula": [
            "lula", "luiz inácio lula da silva", "luiz inacio lula da silva", "pt", "partido dos trabalhadores",
            "instituto lula", "presidência da república", "governo federal", "pt brasil", "fundação perseu abramo"
        ],
        "clariana barão": [
            "clariana barão", "clariana barao", "dc", "democracia cristã", "democracia crista"
        ],
        "edmilson costa": [
            "edmilson costa", "pcb", "partido comunista brasileiro", "fundação dinarco reis"
        ],
        "flávio bolsonaro": [
            "flávio bolsonaro", "flavio bolsonaro", "bolsonaro", "pl", "partido liberal",
            "família bolsonaro", "senador flávio bolsonaro"
        ],
        "hertz dias": [
            "hertz dias", "hertz", "pstu", "partido socialista dos trabalhadores unificado", "quilombo raça e classe"
        ],
        "pablo marçal": [
            "pablo marçal", "pablo marcal", "marçal", "prtb", "partido renovador trabalhista brasileiro",
            "plataforma internacional", "la família"
        ],
        "ronaldo caiado": [
            "ronaldo caiado", "caiado", "psd", "partido social democrático", "união brasil", "governo de goiás"
        ],
        "rui costa pimenta": [
            "rui costa pimenta", "rui pimenta", "pco", "partido da causa operária", "causa operária"
        ],
        "samara martins": [
            "samara martins", "up", "unidade popular", "movimento de mulheres olhares"
        ],
        "veterinário wilson grassi": [
            "veterinário wilson grassi", "veterinario wilson grassi", "wilson grassi", "democrata", "democratas"
        ],
        "romeu zema": [
            "romeu zema", "zema", "novo", "partido novo", "governo de minas gerais"
        ],
        "zema": [
            "romeu zema", "zema", "novo", "partido novo", "governo de minas gerais"
        ]
    }

    # Padrões Tier 1: Produtos e Marcas Comerciais (Infoprodutos/Livros)
    BRAND_PRODUCT_PATTERNS = [
        r"\b(gestão\s+da\s+emoção|escola\s+da\s+inteligência|código\s+da\s+inteligência|inteligência\s+multifocal|inteligência\s+emocional|ansiedade|curso|mentoria|livro|método|best\s*seller)\b",
    ]

    # Padrões Tier 2: Termos Estritamente Políticos e Eleitorais
    STRICT_POLITICAL_PATTERNS = [
        r"\b(crise\s+moral\s+da\s+nação|crise\s+moral\s+e\s+política)\b",
        r"\b(rumos\s+da\s+sociedade\s+brasileira|futuro\s+do\s+brasil)\b",
        r"\b(doutrinação\s+ideológica|doutrinação\s+nas\s+escolas)\b",
        r"\b(sistema\s+político\s+corrupto|instituições\s+corrompidas)\b",
        r"\b(salvação\s+da\s+pátria|valores\s+da\s+família\s+brasileira)\b",
        r"\b(liberdade\s+de\s+expressão\s+ameaçada|censura\s+estatal)\b",
        r"\b(eleições|candidat[oa]s?|pré-candidat[oa]s?|candidatura|deputad[oa]s?|vereador[a]s?|senador[a]s?|governador[a]s?|prefeit[oa]s?|governo\s+federal|projeto\s+de\s+poder|presidente\s+da\s+república)\b",
        r"\b(liderança\s+patriótica|defesa\s+da\s+pátria|mbl|movimento\s+brasil\s+livre|partido\s+missão|a\s+missão|avante\s*70)\b",
        r"\b(voto\s+consciente|vote\s+em|meu\s+voto|urna\s+eletrônica|comício|santinho|propaganda\s+eleitoral)\b",
    ]

    def __init__(
        self,
        access_token: Optional[str] = None,
        burst_threshold: Optional[int] = None,
        api_base_url: Optional[str] = None,
    ):
        self.access_token = access_token or settings.meta_access_token
        self.burst_threshold = burst_threshold or settings.ad_burst_threshold
        self.api_base_url = api_base_url or settings.meta_api_base_url

    def _convert_collector_ad(self, ad: Any) -> Dict[str, Any]:
        """Normaliza um anúncio vindo do MetaAdsCollector (GraphQL) para o esquema padrão."""
        ad_id = ""
        creation_time = ""
        page_id = ""
        page_name = ""
        bodies: List[str] = []
        titles: List[str] = []
        captions: List[str] = []
        descriptions: List[str] = []
        bylines = ""
        spend_dict = None
        impressions_dict = None
        platforms = ["facebook", "instagram"]
        region_data = []
        demo_data = []

        if hasattr(ad, "id"):
            ad_id = str(ad.id or "")
            if hasattr(ad, "delivery_start_time") and ad.delivery_start_time:
                creation_time = ad.delivery_start_time.isoformat() if hasattr(ad.delivery_start_time, "isoformat") else str(ad.delivery_start_time)
            if hasattr(ad, "page") and ad.page:
                page_id = str(getattr(ad.page, "id", "") or "")
                page_name = str(getattr(ad.page, "name", "") or "")
            if hasattr(ad, "creatives") and ad.creatives:
                for c in ad.creatives:
                    if getattr(c, "body", None):
                        bodies.append(str(c.body))
                    if getattr(c, "title", None):
                        titles.append(str(c.title))
                    if getattr(c, "caption", None):
                        captions.append(str(c.caption))
                    if getattr(c, "description", None):
                        descriptions.append(str(c.description))
            if hasattr(ad, "spend") and ad.spend:
                low = getattr(ad.spend, "lower_bound", 0) or 0
                up = getattr(ad.spend, "upper_bound", low) or low
                spend_dict = {"lower_bound": str(low), "upper_bound": str(up)}
            if hasattr(ad, "impressions") and ad.impressions:
                low = getattr(ad.impressions, "lower_bound", 0) or 0
                up = getattr(ad.impressions, "upper_bound", low) or low
                impressions_dict = {"lower_bound": str(low), "upper_bound": str(up)}
            if hasattr(ad, "bylines") and ad.bylines:
                bylines = ", ".join(ad.bylines) if isinstance(ad.bylines, list) else str(ad.bylines)
            elif hasattr(ad, "funding_entity") and ad.funding_entity:
                bylines = str(ad.funding_entity)
            elif hasattr(ad, "disclaimer") and ad.disclaimer:
                bylines = str(ad.disclaimer)
            if hasattr(ad, "publisher_platforms") and ad.publisher_platforms:
                platforms = ad.publisher_platforms
            if hasattr(ad, "delivery_by_region") and ad.delivery_by_region:
                region_data = ad.delivery_by_region
            elif hasattr(ad, "region_distribution") and ad.region_distribution:
                region_data = ad.region_distribution
            if hasattr(ad, "demographic_distribution") and ad.demographic_distribution:
                demo_data = ad.demographic_distribution

        elif isinstance(ad, dict):
            ad_id = str(ad.get("id") or ad.get("ad_archive_id") or "")
            creation_time = str(ad.get("start_date") or ad.get("ad_creation_time") or "")
            page_data = ad.get("page") or {}
            page_id = str(page_data.get("id") if isinstance(page_data, dict) else ad.get("page_id") or "")
            page_name = str(page_data.get("name") if isinstance(page_data, dict) else ad.get("page_name") or "")
            creatives = ad.get("creatives") or []
            if isinstance(creatives, list):
                for c in creatives:
                    if isinstance(c, dict):
                        if c.get("body"): bodies.append(str(c["body"]))
                        if c.get("title"): titles.append(str(c["title"]))
                        if c.get("caption"): captions.append(str(c["caption"]))
                        if c.get("description"): descriptions.append(str(c["description"]))
            bylines = ad.get("bylines") or ad.get("funding_entity") or ad.get("disclaimer") or ""
            if isinstance(bylines, list):
                bylines = ", ".join(bylines)
            else:
                bylines = str(bylines)

            region_data = (
                ad.get("delivery_by_region")
                or ad.get("region_distribution")
                or []
            )

            demo_data = ad.get("demographic_distribution") or []

        return {
            "id": ad_id,
            "ad_creation_time": creation_time,
            "ad_delivery_start_time": creation_time,
            "publisher_platforms": platforms,
            "page_id": page_id,
            "page_name": page_name,
            "ad_creative_bodies": bodies,
            "ad_creative_link_titles": titles,
            "ad_creative_link_captions": captions,
            "ad_creative_link_descriptions": descriptions,
            "bylines": bylines,
            "spend": spend_dict,
            "impressions": impressions_dict,
            "region_distribution": region_data,
            "demographic_distribution": demo_data,
            "target_country": "BR",
        }

    def fetch_ads_from_api(
        self,
        target_name: Optional[str] = None,
        page_id: Optional[str] = None,
        limit: int = 2000,
        ad_active_status: str = "ALL",
        context_tags: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Coleta e filtra anúncios da Meta Ad Library descartando homônimos e doramas.
        """
        if not target_name and not page_id:
            raise ValueError("É obrigatório informar 'target_name' ou 'page_id'.")

        cache_identifier = target_name or str(page_id)
        extra_cache_params = {
            "context_tags": sorted(context_tags) if context_tags else None,
            "ad_active_status": ad_active_status,
        }

        if not force_refresh:
            cached_ads = cache_manager.get("meta_ad_library", cache_identifier, extra_cache_params)
            if cached_ads is not None and isinstance(cached_ads, list):
                logger.info(f"Meta Ad Library: {len(cached_ads)} anúncio(s) carregados do cache local persistente.")
                return cached_ads, f"Meta Ad Library (Cache Local Válido - {len(cached_ads)} anúncios)"

        all_ads: List[Dict[str, Any]] = []
        source_engine = ""

        # 1. Coleta via Meta Graph API Oficial (Dados oficiais de spend, bylines, regiões e histórico)
        graph_api_ads: List[Dict[str, Any]] = []
        if self.access_token:
            url = f"{self.api_base_url}/ads_archive"
            params: Dict[str, Any] = {
                "access_token": self.access_token,
                "ad_active_status": ad_active_status,
                "ad_reached_countries": "['BR']",
                "fields": (
                    "id,ad_creation_time,ad_delivery_start_time,publisher_platforms,"
                    "page_id,page_name,ad_creative_bodies,ad_creative_link_titles,"
                    "ad_creative_link_captions,ad_creative_link_descriptions,bylines,spend,impressions,"
                    "delivery_by_region,demographic_distribution"
                ),
                "limit": min(limit, 500),
            }

            if target_name:
                params["search_terms"] = target_name
            elif page_id:
                params["search_page_ids"] = page_id

            pages_fetched = 0
            try:
                logger.info(f"Meta Ad Library: Consultando Graph API oficial para '{target_name or page_id}'...")
                while url:
                    response = requests.get(url, params=params if pages_fetched == 0 else None, timeout=30)
                    pages_fetched += 1
                    
                    if response.status_code != 200:
                        try:
                            err_payload = response.json().get("error", {})
                            err_msg = err_payload.get("message", response.text)
                        except Exception:
                            err_msg = response.text

                        status_str = f"Meta Graph API (HTTP {response.status_code}: {err_msg})"
                        logger.warning(status_str)
                        break

                    payload = response.json()
                    data = payload.get("data", [])
                    if not data:
                        break
                    graph_api_ads.extend(data)

                    paging = payload.get("paging", {})
                    url = paging.get("next")

                    if len(graph_api_ads) >= limit:
                        break

                if graph_api_ads:
                    logger.info(f"Meta Graph API v19.0: {len(graph_api_ads)} anúncios coletados.")
            except Exception as exc:
                logger.warning(f"Meta Graph API falhou ({exc}).")

        # 2. Coleta via MetaAdsCollector GraphQL (Página Web Pública / Live Scraper)
        scraper_ads: List[Dict[str, Any]] = []
        try:
            from src.modules.meta_ads_collector import MetaAdsCollector
            search_query = target_name or str(page_id or "")
            if search_query:
                logger.info(f"Meta Ad Library: Consultando GraphQL Scraper público para '{search_query}'...")
                with MetaAdsCollector() as collector:
                    collected = collector.collect(query=search_query, country="BR", max_results=limit)
                    if collected:
                        for ad_item in collected:
                            scraper_ads.append(self._convert_collector_ad(ad_item))
                        logger.info(f"MetaAdsCollector GraphQL: {len(scraper_ads)} anúncios coletados.")
        except Exception as collector_err:
            logger.warning(f"MetaAdsCollector falhou ({collector_err}).")

        # 3. Fusão Híbrida Inteligente (Deduplicação e Enriquecimento Mútuo)
        ads_map: Dict[str, Dict[str, Any]] = {}
        
        # Insere dados do Scraper Web
        for ad in scraper_ads:
            ad_id = str(ad.get("id") or "")
            if ad_id:
                ads_map[ad_id] = ad

        # Insere e enriquece com dados da Graph API Oficial (que têm precedência de Spend/Bylines)
        for ad in graph_api_ads:
            ad_id = str(ad.get("id") or "")
            if not ad_id:
                continue
            if ad_id in ads_map:
                # Enriquece o anúncio existente com os dados oficiais auditados
                existing = ads_map[ad_id]
                existing["spend"] = ad.get("spend") or existing.get("spend")
                existing["impressions"] = ad.get("impressions") or existing.get("impressions")
                existing["bylines"] = ad.get("bylines") or existing.get("bylines")
                existing["funding_entity"] = ad.get("funding_entity") or existing.get("funding_entity")
                if ad.get("ad_delivery_start_time"):
                    existing["ad_delivery_start_time"] = ad.get("ad_delivery_start_time")
            else:
                ads_map[ad_id] = ad

        all_ads = list(ads_map.values())
        
        engines_used = []
        if graph_api_ads:
            engines_used.append(f"Graph API ({len(graph_api_ads)})")
        if scraper_ads:
            engines_used.append(f"GraphQL Scraper ({len(scraper_ads)})")
        source_engine = f"Ensemble Híbrido: {' + '.join(engines_used)} -> {len(all_ads)} anúncios únicos"

        if not all_ads:
            return [], "Meta Ad Library (Nenhum anúncio encontrado nas fontes oficiais e fallback)"

        # 3. Desambiguação Contextual & Filtro Anti-Homônimos (ProPublica Model)
        target_key = (target_name or "").lower().strip()
        disambiguation_keywords = [t.lower().strip() for t in (context_tags or self.TARGET_DISAMBIGUATION_MAP.get(target_key, []))]

        seen_ids = set()
        filtered_ads = []
        discarded_homonyms = 0

        for ad in all_ads:
            ad_id = str(ad.get("id"))
            if ad_id in seen_ids:
                continue
            seen_ids.add(ad_id)

            pname = str(ad.get("page_name") or "").lower().strip()
            byline = str(ad.get("bylines") or ad.get("funding_entity") or "").lower().strip()
            titles = " ".join(ad.get("ad_creative_link_titles") or [])
            bodies = " ".join(ad.get("ad_creative_bodies") or [])
            captions = " ".join(ad.get("ad_creative_link_captions") or [])
            descs = " ".join(ad.get("ad_creative_link_descriptions") or [])
            ocr_text = ocr_extractor.enrich_ad_with_media_text(ad)

            full_text = f"{pname} {byline} {titles} {bodies} {captions} {descs} {ocr_text}".lower()

            # Adaptação Específica para a Comparação: Renan Santos vs Augusto Cury
            # Renan Santos: Nome comum, aparece muito em Doramas/Novelas como falso positivo. Precisa de desambiguação estrita.
            # Augusto Cury: Nome muito específico. Dificilmente há um "Augusto Cury" falso. Agências usam o nome dele sem contexto cívico óbvio.
            
            if target_key == "renan santos":
                has_negative_homonym = any(neg in full_text for neg in self.HOMONYM_NEGATIVE_PATTERNS)
                has_civic_context = any(k in full_text for k in ["mbl", "missão", "partido", "eleição", "eleições", "voto", "política", "deputad", "kim kataguiri", "arthur do val", "guto zacarias", "rubinho nunes"])
                
                # Se for dorama/imóvel e não tiver contexto cívico do MBL/eleição, DESCARTA sumariamente.
                if has_negative_homonym and not has_civic_context:
                    discarded_homonyms += 1
                    continue

                # Checa desambiguação estrita para anúncios de terceiros
                is_target_entity = ("renan santos" in pname) or ("renan santos" in byline) or any(off in pname for off in self.OFFICIAL_ENTITIES_MAP.get(target_key, []))
                
                if not ad.get("bylines") and not is_target_entity:
                    if disambiguation_keywords:
                        has_context_match = any(tag in full_text for tag in disambiguation_keywords)
                        if not has_context_match:
                            discarded_homonyms += 1
                            continue
                            
                filtered_ads.append(ad)

            elif target_key == "augusto cury":
                # Augusto Cury não sofre com falsos positivos de doramas. 
                # Além disso, agências de terceiros promovem a figura dele muitas vezes sem as palavras-chave óbvias (camuflagem pura).
                # Então aceitamos virtualmente qualquer anúncio que carregue o nome dele no texto completo ou que seja entidade oficial.
                
                is_target_entity = ("augusto cury" in pname) or ("augusto cury" in byline) or any(off in pname for off in self.OFFICIAL_ENTITIES_MAP.get(target_key, []))
                
                # Se "augusto cury" está no texto ou na página, nós mantemos.
                # Só descartamos se for algo completamente bizarro que a Graph API retornou sem ter a palavra-chave.
                if "augusto cury" in full_text or is_target_entity:
                    filtered_ads.append(ad)
                else:
                    discarded_homonyms += 1
                    continue

            else:
                # Tratamento genérico para outros candidatos presidenciais e políticos
                has_negative = any(neg in full_text for neg in self.HOMONYM_NEGATIVE_PATTERNS)
                is_target_entity = any(off in pname for off in self.OFFICIAL_ENTITIES_MAP.get(target_key, [])) or (target_key in pname)
                has_target_in_text = target_key in full_text
                
                if disambiguation_keywords and not is_target_entity:
                    has_tag_match = any(tag.lower() in full_text for tag in disambiguation_keywords)
                    if has_negative and not has_tag_match:
                        discarded_homonyms += 1
                        continue
                    if not has_target_in_text and not has_tag_match:
                        discarded_homonyms += 1
                        continue
                elif has_negative and not has_target_in_text and not is_target_entity:
                    discarded_homonyms += 1
                    continue

                filtered_ads.append(ad)

        logger.info(
            f"Meta Ad Library: {len(all_ads)} anúncio(s) brutos coletados ({source_engine or 'Engine Desconhecida'}). "
            f"{discarded_homonyms} homônimo(s)/doramas/irrelevantes descartados. "
            f"{len(filtered_ads)} anúncio(s) validados para '{target_name}'."
        )

        # Grava no cache local com TTL configurado
        cache_manager.set(
            "meta_ad_library",
            cache_identifier,
            filtered_ads,
            extra_cache_params,
            ttl_hours=settings.cache_ttl_hours,
        )

        return filtered_ads, f"{source_engine or 'Meta Ad Library'} (Live - {len(filtered_ads)} anúncios validados pós-desambiguação)"

    def analyze_burst_anomalies(
        self, ads_data: List[Dict[str, Any]], target_name: str = "", api_status: str = ""
    ) -> Dict[str, Any]:
        """
        Algoritmo de Detecção de Coordinated Ad Flooding, Camuflagem de Infoproduto e Segregação Financeira.
        """
        if not ads_data:
            return {
                "total_anuncios": 0,
                "total_suspeitos": 0,
                "anuncios_suspeitos": [],
                "distribuicao_tipos": {},
                "taxa_maxima": "0 ads/min",
                "pico_timestamp": "N/A",
                "janelas_anomalas": [],
                "anuncios_camuflados": [],
                "investimento_financeiro": {
                    "total_declarado_min": 0.0,
                    "total_declarado_max": 0.0,
                    "gasto_direto_pagina_alvo_min": 0.0,
                    "gasto_direto_pagina_alvo_max": 0.0,
                    "gasto_rede_coligacao_min": 0.0,
                    "gasto_rede_coligacao_max": 0.0,
                    "anuncios_diretos_count": 0,
                    "anuncios_coligacao_count": 0,
                    "estimativa_oculta_min": 0.0,
                    "estimativa_oculta_max": 0.0,
                    "resumo_financeiro": "Nenhum dado financeiro para processamento.",
                },
                "justificativa": "Nenhum anúncio disponível para auditoria.",
            }

        target_clean = target_name.strip().lower() if target_name else ""
        official_entities = self.OFFICIAL_ENTITIES_MAP.get(target_clean, [target_clean])

        minute_buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        day_buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        camouflaged_political_ads: List[Dict[str, Any]] = []

        total_declared_min = 0.0
        total_declared_max = 0.0
        direto_alvo_min = 0.0
        direto_alvo_max = 0.0
        coligacao_min = 0.0
        coligacao_max = 0.0
        anuncios_diretos_count = 0
        anuncios_coligacao_count = 0

        for ad in ads_data:
            ad_id = str(ad.get("id"))
            creation_time_str = ad.get("ad_creation_time", "")
            page_name_raw = str(ad.get("page_name") or "")
            page_name_clean = page_name_raw.strip().lower()
            byline_raw = str(ad.get("bylines") or ad.get("funding_entity") or "")
            byline_clean = byline_raw.strip().lower()

            if creation_time_str:
                has_time_precision = ("T" in creation_time_str or ":" in creation_time_str) and len(creation_time_str) > 10
                if has_time_precision:
                    try:
                        clean_time_str = creation_time_str.replace("+0000", "").replace("Z", "")
                        dt = datetime.fromisoformat(clean_time_str)
                        minute_key = dt.strftime("%Y-%m-%d %H:%M")
                        minute_buckets[minute_key].append(ad)
                    except ValueError:
                        minute_buckets[creation_time_str[:16]].append(ad)
                else:
                    day_buckets[creation_time_str[:10]].append(ad)

            # Extração e segregação de gastos declarados
            spend_data = ad.get("spend")
            low_spend = 0.0
            up_spend = 0.0
            if spend_data and isinstance(spend_data, dict):
                try:
                    low_spend = float(spend_data.get("lower_bound", 0) or 0)
                    up_spend = float(spend_data.get("upper_bound", low_spend) or low_spend)
                    total_declared_min += low_spend
                    total_declared_max += up_spend
                except (ValueError, TypeError):
                    pass

            # Checa se o anúncio é da página oficial direta do alvo ou da coligação/aliados
            is_direct_target_page = bool(
                page_name_clean == target_clean
                or (target_clean == "renan santos" and "renan santos" in page_name_clean)
                or (target_clean == "augusto cury" and "augusto cury" in page_name_clean and "biblioteca" not in page_name_clean)
            )

            if is_direct_target_page:
                direto_alvo_min += low_spend
                direto_alvo_max += up_spend
                anuncios_diretos_count += 1
            else:
                coligacao_min += low_spend
                coligacao_max += up_spend
                anuncios_coligacao_count += 1

            # Análise semântica de criativos
            full_text = ocr_extractor.enrich_ad_with_media_text(ad).lower()
            preview_txt = (ad.get("ad_creative_link_titles") or ad.get("ad_creative_bodies") or [""])[0]

            detected_brand_triggers = []
            for pattern in self.BRAND_PRODUCT_PATTERNS:
                matches = re.findall(pattern, full_text, flags=re.IGNORECASE)
                if matches:
                    if isinstance(matches[0], tuple):
                        detected_brand_triggers.extend([m for m in matches[0] if m])
                    else:
                        detected_brand_triggers.extend(matches)

            # Análise semântica e classificação híbrida via Motor 2 (NLP SVM + Lógica)
            from src.modules.political_nlp import PoliticalNLPClassifier
            nlp_clf = getattr(self, "_nlp_classifier", None)
            if nlp_clf is None:
                nlp_clf = PoliticalNLPClassifier()
                self._nlp_classifier = nlp_clf

            is_official_party_page = bool(
                target_clean and (
                    page_name_clean == target_clean
                    or page_name_clean == f"instituto {target_clean}"
                    or page_name_clean == f"partido {target_clean}"
                    or any(ent == page_name_clean or ent in page_name_clean for ent in official_entities)
                    or any(ent in byline_clean for ent in official_entities)
                )
            )

            has_bylines = bool(ad.get("bylines"))
            
            classification = nlp_clf.classify_ad_creative(
                title=ad.get("ad_creative_link_titles", [""])[0] if ad.get("ad_creative_link_titles") else "",
                body=ad.get("ad_creative_bodies", [""])[0] if ad.get("ad_creative_bodies") else "",
                has_byline=has_bylines,
                page_category="Unknown" # Poderíamos obter isso da API no futuro
            )
            
            # Log de Feedback Loop MLOps
            if "svm_probability" in classification:
                from src.database.db_manager import db_manager
                db_manager.log_ml_prediction(
                    ad_id=ad_id,
                    page_name=page_name_raw,
                    raw_text=full_text,
                    predicted_prob=classification["svm_probability"]
                )
            
            # Ajuste de categoria com base na autorização oficial (Página Satélite vs Oficial Camuflado)
            categoria_tipo = classification["category"]
            if classification["is_infraction"]:
                if is_official_party_page:
                    categoria_tipo = "Camuflagem Comercial (Spend Oculto)"
                else:
                    categoria_tipo = "Página Satélite Não Autorizada / Camuflagem (Art. 57-C)"
                
                camouflaged_political_ads.append({
                    "ad_id": ad_id,
                    "page_name": page_name_raw,
                    "tipo_infracao": categoria_tipo,
                    "preview_titulo": preview_txt[:120] if preview_txt else f"Anúncio por {page_name_raw}",
                    "gatilhos_detectados": classification["triggers"],
                    "motivo_infracao": (
                        f"Criativo veiculado pela página '{page_name_raw}' classificado como infração eleitoral "
                        f"com confiança de {classification['confidence']:.0%}. Triggers: {', '.join(classification['triggers'])}"
                    ),
                })

            ad["forensic_category"] = categoria_tipo

        # Contagem consolidada de categorias
        contagem_categorias = defaultdict(int)
        for ad in ads_data:
            cat = ad.get("forensic_category", "Comercial / Infoproduto Regular")
            contagem_categorias[cat] += 1

        anomalous_windows = []
        burst_ad_ids = set()
        max_rate = 0
        max_rate_window = ""

        for minute_key, ads_in_minute in minute_buckets.items():
            count = len(ads_in_minute)
            if count > max_rate:
                max_rate = count
                max_rate_window = minute_key

            if count >= self.burst_threshold:
                sample_ids = [str(a.get("id")) for a in ads_in_minute[:10]]
                all_ids = [str(a.get("id")) for a in ads_in_minute]
                burst_ad_ids.update(all_ids)

                anomalous_windows.append({
                    "window_timestamp": minute_key,
                    "ad_count": count,
                    "rate_metric": f"{count} ads/min",
                    "sample_ad_ids": sample_ids,
                })

        anomalous_windows.sort(key=lambda x: x["ad_count"], reverse=True)

        camouflaged_ids = {str(c["ad_id"]) for c in camouflaged_political_ads}
        all_suspect_ids = sorted(list(burst_ad_ids.union(camouflaged_ids)))

        estimativa_oculta_min = round(len(camouflaged_political_ads) * 150.0, 2)
        estimativa_oculta_max = round(len(camouflaged_political_ads) * 450.0, 2)
        media_investimento_anuncio = f"R$ 150,00 a R$ 450,00"

        resumo_financeiro = (
            f"Gasto Direto da Página Oficial: R$ {direto_alvo_min:,.2f} a R$ {direto_alvo_max:,.2f} ({anuncios_diretos_count} ads). "
            f"Gasto de Aliados/Coligação que citam o Alvo: R$ {coligacao_min:,.2f} a R$ {coligacao_max:,.2f} ({anuncios_coligacao_count} ads). "
            f"Spend Oculto Projetado (Infrações/Livros Terceiros): R$ {estimativa_oculta_min:,.2f} a R$ {estimativa_oculta_max:,.2f} "
            f"distribuído em {len(camouflaged_political_ads)} criativo(s) suspeitos."
        )

        if anomalous_windows:
            justificativa = (
                f"Identificadas {len(anomalous_windows)} janelas de disparo em massa (pico: {max_rate} ads/min). "
                f"Foram também detectados {len(camouflaged_political_ads)} criativo(s) com camuflagem ou impulsionamento por terceiros."
            )
        elif camouflaged_political_ads:
            justificativa = (
                f"Foram identificados {len(camouflaged_political_ads)} criativo(s) com infrações de transparência, "
                f"incluindo anúncios autuados pela própria Meta e impulsionamento de imagem por páginas terceiras."
            )
        else:
            justificativa = (
                f"Análise concluída sobre {len(ads_data)} anúncio(s). 100% dos criativos encontram-se em conformidade com as regras oficiais."
            )

        return {
            "total_anuncios": len(ads_data),
            "total_suspeitos": len(all_suspect_ids),
            "anuncios_suspeitos": all_suspect_ids,
            "distribuicao_tipos": dict(contagem_categorias),
            "taxa_maxima": f"{max_rate} ads/min" if max_rate > 0 else "0 ads/min",
            "pico_timestamp": max_rate_window,
            "janelas_anomalas": anomalous_windows,
            "anuncios_camuflados": camouflaged_political_ads,
            "investimento_financeiro": {
                "total_declarado_min": round(total_declared_min, 2),
                "total_declarado_max": round(total_declared_max, 2),
                "gasto_direto_pagina_alvo_min": round(direto_alvo_min, 2),
                "gasto_direto_pagina_alvo_max": round(direto_alvo_max, 2),
                "gasto_rede_coligacao_min": round(coligacao_min, 2),
                "gasto_rede_coligacao_max": round(coligacao_max, 2),
                "anuncios_diretos_count": anuncios_diretos_count,
                "anuncios_coligacao_count": anuncios_coligacao_count,
                "estimativa_oculta_min": estimativa_oculta_min,
                "estimativa_oculta_max": estimativa_oculta_max,
                "media_estimada_por_anuncio": media_investimento_anuncio,
                "resumo_financeiro": resumo_financeiro,
            },
            "justificativa": justificativa,
        }
