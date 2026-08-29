import sqlite3
import torch
from pathlib import Path
from typing import Dict, Any, Tuple
import datetime
import json
import logging

try:
    import dgl
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    dgl = None

logger = logging.getLogger(__name__)

class DGLGraphBuilder:
    """
    ETL Pipeline para converter dados relacionais do SQLite em Grafos Heterogêneos (DGL).
    """
    def __init__(self, db_path: str = "dossies/auditoria.db"):
        self.db_path = Path(db_path)

    def load_data(self):
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM ads_archive")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def build_heterograph(self) -> Tuple[Any, Dict[str, Any]]:
        """
        Constrói um dgl.heterograph estruturando a rede de Astroturfing.
        Retorna o Grafo e os mapeamentos de features.
        """
        if dgl is None:
            raise ImportError("DGL, PyTorch ou scikit-learn não estão instalados.")

        ads_data = self.load_data()
        if not ads_data:
            logger.warning("Banco de dados vazio. Não é possível construir o grafo DGL.")
            return None, None

        # 1. Mapeamento de Entidades (Nós)
        page_ids = {} # nome da página -> ID numérico contínuo
        ad_ids = {}   # ad_id -> ID numérico contínuo
        
        pages_list = []
        ads_list = []
        
        # Estruturas para extração de Features e Relações
        ad_texts = []
        ad_times = []
        
        postou_src = []
        postou_dst = []

        for row in ads_data:
            p_name = row.get("page_name") or "Desconhecida"
            a_id = row.get("ad_id")
            
            # Garante IDs contínuos
            if p_name not in page_ids:
                page_ids[p_name] = len(page_ids)
                pages_list.append(p_name)
                
            if a_id not in ad_ids:
                ad_ids[a_id] = len(ad_ids)
                ads_list.append(row)
                
                # Relacionamento ('pagina', 'postou', 'anuncio')
                postou_src.append(page_ids[p_name])
                postou_dst.append(ad_ids[a_id])
                
                # Para TF-IDF
                raw = row.get("raw_json", "{}")
                try:
                    data = json.loads(raw)
                    bodies = data.get("ad_creative_bodies", [])
                    titles = data.get("ad_creative_link_titles", [])
                    txt = " ".join([str(b) for b in bodies + titles]).lower()
                except:
                    txt = ""
                ad_texts.append(txt)
                
                # Para tempo
                t_str = row.get("ad_creation_time") or ""
                ad_dt = None
                if t_str:
                    try:
                        ad_dt = datetime.datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                    except:
                        pass
                ad_times.append(ad_dt)

        # 2. Relações intra-anúncios ('anuncio', 'similar', 'anuncio') e ('anuncio', 'mesmo_tempo', 'anuncio')
        similar_src, similar_dst = [], []
        tempo_src, tempo_dst = [], []
        
        # Extração das features TF-IDF para o nó 'anuncio'
        vectorizer = TfidfVectorizer(max_features=512, lowercase=True)
        tfidf_matrix = vectorizer.fit_transform(ad_texts).toarray()
        features_anuncio = torch.tensor(tfidf_matrix, dtype=torch.float32)
        
        from sklearn.metrics.pairwise import cosine_similarity
        sim_matrix = cosine_similarity(tfidf_matrix)

        for i in range(len(ads_list)):
            for j in range(i + 1, len(ads_list)):
                # Relação Semântica
                if sim_matrix[i, j] >= 0.90:
                    similar_src.extend([i, j])
                    similar_dst.extend([j, i])
                
                # Relação Temporal (< 60 segundos)
                dt_i = ad_times[i]
                dt_j = ad_times[j]
                if dt_i and dt_j:
                    delta = abs((dt_i - dt_j).total_seconds())
                    if delta <= 60:
                        tempo_src.extend([i, j])
                        tempo_dst.extend([j, i])

        # 3. Construção do dgl.heterograph
        graph_data = {
            ('pagina', 'postou', 'anuncio'): (torch.tensor(postou_src), torch.tensor(postou_dst)),
            ('anuncio', 'similar', 'anuncio'): (torch.tensor(similar_src), torch.tensor(similar_dst)),
            ('anuncio', 'mesmo_tempo', 'anuncio'): (torch.tensor(tempo_src), torch.tensor(tempo_dst))
        }
        
        g = dgl.heterograph(graph_data)
        
        # Embutindo as features TF-IDF nos nós de anúncio (O RGCN lerá isso)
        g.nodes['anuncio'].data['feat'] = features_anuncio
        
        # Para nós 'pagina', podemos não ter features explícitas (Embeddings aprendíveis serão gerados no modelo)
        # O modelo RGCN que construímos já trata a geração de embeddings treináveis para nós sem features.
        
        meta_info = {
            "page_map": {idx: name for name, idx in page_ids.items()},
            "ad_map": {idx: list_row["ad_id"] for list_row, idx in ad_ids.items()},
            "num_pages": len(page_ids),
            "num_ads": len(ad_ids)
        }
        
        logger.info(f"Grafo DGL Construído: {g.num_nodes('pagina')} Páginas, {g.num_nodes('anuncio')} Anúncios.")
        logger.info(f"Arestas - Postou: {g.num_edges('postou')}, Similar: {g.num_edges('similar')}, Tempo: {g.num_edges('mesmo_tempo')}")
        
        return g, meta_info

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    builder = DGLGraphBuilder()
    g, meta = builder.build_heterograph()
    print("DGL Graph gerado com sucesso!")
