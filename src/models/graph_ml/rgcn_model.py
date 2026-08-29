import torch
import torch.nn as nn
import torch.nn.functional as F

import dgl.function as fn
from dgl.nn.pytorch import HeteroGraphConv, GraphConv

class HeteroRGCNLayer(nn.Module):
    def __init__(self, in_size, out_size, etypes):
        super(HeteroRGCNLayer, self).__init__()
        # W_r para cada tipo de relação (ex: 'postou', 'similar_a')
        self.weight = nn.ModuleDict({
            name: nn.Linear(in_size, out_size) for name in etypes
        })

    def forward(self, G, feat_dict):
        funcs = {}
        for srctype, etype, dsttype in G.canonical_etypes:
            if srctype in feat_dict:
                Wh = self.weight[etype](feat_dict[srctype])
                G.nodes[srctype].data[f'Wh_{etype}'] = Wh
                funcs[etype] = (fn.copy_u(f'Wh_{etype}', 'm'), fn.mean('m', 'h'))
                
        G.multi_update_all(funcs, 'sum')
        return {ntype: G.dstnodes[ntype].data['h'] for ntype in G.ntypes if 'h' in G.dstnodes[ntype].data}

class AstroturfingHeteroRGCN(nn.Module):
    """
    Modelo GNN adaptado do SageMaker Fraud Detection (HeteroRGCN).
    Classifica nós do tipo 'pagina' como Satélites (1) ou Oficiais/Normais (0).
    """
    def __init__(self, g, in_size, hidden_size, out_size, n_layers, embedding_size):
        super(AstroturfingHeteroRGCN, self).__init__()
        
        # Embeddings treináveis para nós sem features puras (ex: Páginas). 
        # Nós do tipo 'anuncio' receberão as features TF-IDF diretamente.
        embed_dict = {
            ntype: nn.Parameter(torch.Tensor(g.number_of_nodes(ntype), embedding_size))
            for ntype in g.ntypes if ntype != 'anuncio'
        }
        for key, embed in embed_dict.items():
            nn.init.xavier_uniform_(embed)
            
        self.embed = nn.ParameterDict(embed_dict)
        self.layers = nn.ModuleList()
        
        # Primeira camada (Input -> Hidden)
        self.layers.append(HeteroRGCNLayer(embedding_size, hidden_size, g.etypes))
        
        # Camadas ocultas (Hidden -> Hidden)
        for _ in range(n_layers - 1):
            self.layers.append(HeteroRGCNLayer(hidden_size, hidden_size, g.etypes))

        # Camada de saída para o nó 'pagina'
        self.classifier = nn.Linear(hidden_size, out_size)

    def forward(self, g, ad_features):
        h_dict = {ntype: emb for ntype, emb in self.embed.items()}
        # Para anúncios, injetamos as features textuais (TF-IDF convertidas)
        # Assumindo que ad_features tem dimensão correspondente ao embedding_size 
        # (pode exigir uma camada linear antes se as dimensões não baterem)
        h_dict['anuncio'] = ad_features

        # Passagem pelas camadas convolucionais de grafo
        for i, layer in enumerate(self.layers):
            if i != 0:
                h_dict = {k: F.leaky_relu(h) for k, h in h_dict.items()}
            h_dict = layer(g, h_dict)

        # Retorna apenas os Logits das Páginas para classificação binária
        return self.classifier(h_dict['pagina'])
