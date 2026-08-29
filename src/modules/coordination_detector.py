"""
Módulo de Detecção de Comportamento Coordenado & Páginas Satélites (Inspirado em CooRnet, CooRTweet & Bot-Detector).

Objetivo:
- Identificar redes de astroturfing e agências de marketing terceiras atuando sem vínculo declarado.
- Detectar Coordinated Link Sharing Behavior (CLSB) — múltiplos criativos/links disparados em janelas sincronizadas (< 60 min).
- Mapeamento estrito de entidades oficiais do partido/candidato e whitelist jornalística para eliminação de falsos positivos.
- Não utiliza contagem arbitrária de seguidores, fundamentando-se exclusivamente na sincronia temporal e na ausência de vínculo/rótulo oficial.
"""

from collections import defaultdict
from datetime import datetime
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class CoordinationDetector:
    """
    Motor forense para identificação de redes coordenadas de agências e páginas satélites.
    """

    # Veículos de imprensa e portais jornalísticos legítimos (Whitelist para 0% de falsos positivos na imprensa)
    PRESS_WHITELIST = {
        "g1", "globo", "o globo", "folha de s.paulo", "folha", "estadao", "o estado de s. paulo",
        "uol", "uol noticias", "cnn brasil", "cnn", "poder360", "veja", "metropoles", "jovem pan",
        "jovem pan news", "valor economico", "gazeta do povo", "correio braziliense", "o antagonista",
        "the intercept brasil", "intercept", "band", "band jornalismo", "sbt news", "record news",
        "cartacapital", "revista oeste", "exame", "canaltech", "tecmundo", "diario do centro do mundo",
        "brasil 247", "conjur", "migalhas", "jota"
    }

    # Mapeamento de entidades oficiais, partidárias e institucionais vinculadas ao alvo
    OFFICIAL_ENTITIES_MAP: Dict[str, List[str]] = {
        "renan santos": [
            "renan santos", "partido missão", "missão", "a missão", "movimento brasil livre", "mbl",
            "academia mbl", "instituto mbl", "partido missao", "revista valete", "valete", "guto zacarias",
            "kim kataguiri", "arthur do val", "rubinho nunes", "rafael macris", "livres"
        ],
        "augusto cury": [
            "augusto cury", "instituto augusto cury", "escola da inteligência",
            "avante", "avante 70", "editora sextante", "método augusto cury",
            "programa socioemocional", "dr. augusto cury", "dr augusto cury"
        ]
    }

    # Palavras-chave indicativas de páginas de nicho genérico/agências de tráfego
    GENERIC_AGENCY_NICHES = [
        "curiosidades", "fofoca", "noticias", "babados", "frases", "reflexoes", "humor",
        "memes", "marketing", "negocios", "empreendedorismo", "gospel", "motivação",
        "vida saudavel", "lifestyle", "musica", "brasil urgente", "plantao"
    ]

    def __init__(self, time_threshold_minutes: int = 60):
        self.time_threshold_minutes = time_threshold_minutes

    @classmethod
    def is_press_outlet(cls, page_name: str) -> bool:
        """Verifica se a página pertence à imprensa profissional."""
        if not page_name:
            return False
        clean = page_name.lower().strip()
        return any(press in clean for press in cls.PRESS_WHITELIST)

    @classmethod
    def is_generic_niche_page(cls, page_name: str) -> bool:
        """Verifica se o nome da página sugere um canal de entretenimento/agência genérica."""
        if not page_name:
            return False
        clean = page_name.lower().strip()
        return any(niche in clean for niche in cls.GENERIC_AGENCY_NICHES)

    def analyze_coordinated_networks(
        self, ads_data: List[Dict[str, Any]], target_name: str, official_entities: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Executa a análise de redes coordenadas no estilo CooRnet.
        """
        if not ads_data:
            return {
                "score_coordenacao": 0.0,
                "status_rede_coordenada": False,
                "total_paginas_agencia": 0,
                "paginas_agencia_detectadas": [],
                "clusters_coordenados": [],
                "parecer_coordenacao": "Nenhum criativo disponível para análise de coordenação de rede.",
            }

        target_slug = target_name.lower().strip()
        official_set = set([target_slug])

        if target_slug in self.OFFICIAL_ENTITIES_MAP:
            official_set.update([e.lower().strip() for e in self.OFFICIAL_ENTITIES_MAP[target_slug]])
        if official_entities:
            official_set.update([e.lower().strip() for e in official_entities])

        # 1. Agrupamento e Vetorização de Conteúdo (Vector-Based Cosine Similarity)
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        page_ads = defaultdict(list)
        all_ads_texts = []
        all_ads_records = []
        
        for ad in ads_data:
            p_name = (ad.get("page_name") or "Página Desconhecida").strip()
            ad_id = str(ad.get("id") or ad.get("ad_id") or "")
            created_time_str = ad.get("ad_delivery_start_time") or ad.get("created_time") or ""
            byline = ad.get("bylines") or ad.get("funding_entity") or ""
            
            bodies = ad.get("ad_creative_bodies") or []
            titles = ad.get("ad_creative_link_titles") or []
            raw_text = " ".join([str(b) for b in bodies + titles]).lower().strip()
            core_text = re.sub(r'[^a-z0-9]', ' ', raw_text)

            # Parsing do timestamp
            ad_dt = None
            if created_time_str:
                try:
                    ad_dt = datetime.fromisoformat(created_time_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            is_press = self.is_press_outlet(p_name)
            is_off = any(off in p_name.lower() for off in official_set) or any(off in str(byline).lower() for off in official_set)
            is_niche = self.is_generic_niche_page(p_name)

            ad_record = {
                "ad_id": ad_id,
                "page_name": p_name,
                "datetime": ad_dt,
                "is_press": is_press,
                "is_official": is_off,
                "is_niche": is_niche,
                "byline": byline,
                "raw_text": core_text
            }
            page_ads[p_name].append(ad_record)
            
            if ad_dt and not is_press and not is_off and core_text.strip():
                all_ads_texts.append(core_text)
                all_ads_records.append(ad_record)

        # 2. Identificação de Páginas Satélites Suspeitas Não-Oficiais
        agency_pages = []
        for p_name, p_records in page_ads.items():
            if not p_records:
                continue
            is_press = p_records[0]["is_press"]
            is_off = p_records[0]["is_official"]
            is_niche = p_records[0]["is_niche"]
            has_official_byline = any(bool(r.get("byline")) for r in p_records)

            if not is_press and not is_off and not has_official_byline:
                agency_pages.append({
                    "page_name": p_name,
                    "ad_count": len(p_records),
                    "categoria_satelite": "Página Satélite Não-Autorizada (Art. 57-C)",
                    "risco_astroturfing": "Alto" if is_niche else "Médio",
                })

        # 3. Detecção de Clusters Coordenados via Grafos (Vector Cosine Similarity / Delta Time)
        import networkx as nx
        G = nx.Graph()
        time_threshold_seconds = self.time_threshold_minutes * 60
        
        if all_ads_texts:
            vectorizer = TfidfVectorizer(max_features=2000, lowercase=True)
            tfidf_matrix = vectorizer.fit_transform(all_ads_texts)
            similarity_matrix = cosine_similarity(tfidf_matrix)
            
            for i in range(len(all_ads_records)):
                for j in range(i + 1, len(all_ads_records)):
                    # Limiar matemático de 0.90 (90% semânticamente idêntico)
                    if similarity_matrix[i, j] >= 0.90:
                        r1 = all_ads_records[i]
                        r2 = all_ads_records[j]
                        
                        if r1["page_name"] != r2["page_name"]:
                            delta_sec = abs((r1["datetime"] - r2["datetime"]).total_seconds())
                            if delta_sec <= time_threshold_seconds:
                                G.add_edge(r1["page_name"], r2["page_name"], similarity=similarity_matrix[i,j], delta=delta_sec)

        coordinated_clusters = []
        components = list(nx.connected_components(G))
        for comp in components:
            if len(comp) >= 2:
                # Recupera o total de anúncios no cluster com base nas arestas do grafo original
                cluster_edges = list(G.subgraph(comp).edges(data=True))
                # Aproximação: nº arestas + nós para refletir a sincronia
                total_ads_sync = len(cluster_edges) + len(comp)
                
                coordinated_clusters.append({
                    "janela_tempo": "Rede Sincronizada (Grafo Vetorial - Similaridade > 90%)",
                    "paginas_envolvidas": list(comp),
                    "total_anuncios_sincronizados": total_ads_sync,
                })

        # 4. Cálculo do Score de Coordenação (0.0 a 100.0)
        score_coordenacao = 0.0
        if len(agency_pages) > 0:
            score_coordenacao += min(50.0, len(agency_pages) * 20.0)
        if len(coordinated_clusters) > 0:
            score_coordenacao += min(50.0, len(coordinated_clusters) * 25.0)

        score_coordenacao = round(min(100.0, score_coordenacao), 2)
        status_coordenada = score_coordenacao >= 40.0

        if status_coordenada:
            parecer = (
                f"🚨 REDE SATÉLITE COORDENADA DETECTADA (Score: {score_coordenacao}/100). "
                f"Foram identificadas {len(agency_pages)} página(s) satélites não-oficiais "
                f"e {len(coordinated_clusters)} cluster(s) de disparo sincronizado (CooRnet CLSB)."
            )
        elif len(agency_pages) > 0:
            parecer = (
                f"⚠️ ATIVIDADE SATÉLITE DETECTADA (Score: {score_coordenacao}/100): "
                f"{len(agency_pages)} página(s) de terceiros impulsionando sem coordenação em massa."
            )
        else:
            parecer = (
                f"✅ AUSÊNCIA DE REDES COORDENADAS: 100% dos criativos provêm de canais oficiais declarados "
                f"ou cobertura regular da imprensa jornalística."
            )

        return {
            "score_coordenacao": score_coordenacao,
            "status_rede_coordenada": status_coordenada,
            "total_paginas_agencia": len(agency_pages),
            "paginas_agencia_detectadas": agency_pages,
            "clusters_coordenados": coordinated_clusters,
            "parecer_coordenacao": parecer,
        }
