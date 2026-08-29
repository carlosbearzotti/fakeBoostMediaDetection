# 🕵️‍♂️ Fake Boost & Astroturfing Media Detection (OSINT Forense & Graph ML)

Sistema enterprise de inteligência em fontes abertas (OSINT), análise forense computacional e **Graph Machine Learning** para rastrear, mapear e comprovar judicialmente o uso de **redes coordenadas de impulsionamento inautêntico (Astroturfing)**, campanhas de camuflagem comercial (Art. 57-C da Lei 9.504/97), disparos sincronizados na Meta Ad Library e anomalias de séries temporais.

---

## 🌟 Arquitetura dos 3 Motores de IA & OSINT

```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │                      ALVO / CANDIDATO INVESTIGADO                      │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                   DUAL-ENGINE COLLECTOR (INGESTÃO)                     │
  │  ┌──────────────────────────────┐    ┌──────────────────────────────┐  │
  │  │  Meta Graph API v19.0        │    │  GraphQL Web Scraper         │  │
  │  │  (Spend, Impressões & UFs)   │    │  (Criativos Ativos & Imagens)│  │
  │  └──────────────┬───────────────┘    └──────────────┬───────────────┘  │
  │                 └─────────────────┬─────────────────┘                  │
  │                                   ▼                                    │
  │                   Fusão & Deduplicação por ad_id                       │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                     OCR & EXTRAÇÃO DE TEXTO / MÍDIA                    │
  └───────────────────┬────────────────────────────────┬───────────────────┘
                      │                                │
                      ▼                                ▼
  ┌──────────────────────────────┐   ┌───────────────────────────────────┐
  │   MOTOR 1: COORNET GRAFOS    │   │      MOTOR 2: NLP HÍBRIDO & ML    │
  │   - Vetorização TF-IDF       │   │      - Classificador SVM Linear   │
  │   - Similaridade Cosseno ≥ 90│   │      - Probabilidade de Infração  │
  │   - Janela Temporal Δt ≤ 60s │   │      - Logging em ml_feedback_log │
  │   - Grafo Bipartido NetworkX │   │      - Dataset de Treino Contínuo │
  └──────────────┬───────────────┘   └─────────────────┬─────────────────┘
                 │                                     │
                 └──────────────────┬──────────────────┘
                                    │
                                    ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │              MOTOR 3: GRAPH NEURAL NETWORKS (DGL & R-GCN)              │
  │  - ETL Estrutural dgl.heterograph (Páginas, Anúncios & Relações)       │
  │  - Rede Convolucional Relacional em PyTorch (Detecção de Astroturfing) │
  └─────────────────────────────────┬──────────────────────────────────────┘
                                    │
                                    ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                             DOSSIÊ              
  │     HTML Interativo (Chart.js) │ JSON Forense │ Hash SHA-256 │ SQLite  │
  └────────────────────────────────────────────────────────────────────────┘
```

### 1. 🔄 Dual-Engine Ingestion (Ensemble Collector)

- **Meta Graph API v19.0 Oficial:** Coleta dados auditados de investimento (`spend`), impressões (`impressions`), responsáveis jurídicos (`bylines`/`funding_entity`) e distribuição geográfica por estados (`delivery_by_region`).
- **GraphQL Web Scraper (`MetaAdsCollector`):** Captura em tempo real criativos ativos, links e imagens, garantindo que o sistema nunca falhe caso o token expire.
- **Fusão Inteligente:** Deduplica anúncios por `ad_id`, combinando o melhor dos dois mundos.

### 2. 🕸️ Motor 1: Detecção de Redes via Similaridade de Cossenos (CooRnet Vetorial)

- Vetorização dos criativos em espaço multidimensional via `TfidfVectorizer`.
- Cálculo de matriz de proximidade semântica via **Similaridade de Cossenos (`Cosine Similarity >= 0.90`)**.
- Construção de grafos bipartidos (`networkx`) conectando páginas distintas que dispararam variações do mesmo texto em janelas temporais críticas ($\Delta t \le 60s$).

### 3. 🧠 Motor 2: Classificador NLP Híbrido & MLOps Feedback Loop

- **Modelo SVM Linear (`scikit-learn`):** Treinado com quase 1.000 amostras reais de campanhas políticas brasileiras para classificar criativos camuflados (ex: venda de livros com discurso eleitoral velado).
- **Ciclo de Aprendizado Contínuo (MLOps):** Registra cada predição e probabilidade na tabela `ml_feedback_log` do SQLite, permitindo retreinamento progressivo sem perda de dados históricos.

### 4. 🔬 Motor 3: Graph Neural Networks (DGL & SageMaker R-GCN)

- **ETL Estrutural (`hetero_builder.py`):** Converte a base relacional de anúncios em grafos heterogêneos (`dgl.heterograph`) com nós de `Página` e `Anúncio`.
- **Arquitetura PyTorch R-GCN (`rgcn_model.py`):** Baseada no estado da arte de detecção de fraudes da AWS (*SageMaker Graph Fraud Detection*), utilizando convoluções relacionais para aprender a topologia de fazendas de bots e páginas satélites.

---

## 🏛️ Catálogo de Candidatos — Eleições Presidenciais 2026

O sistema possui mapeamento de entidades oficiais, partidos e filtros anti-homônimos (eliminando doramas, futebol e novelas) para todos os candidatos oficiais:

1. **Luiz Inácio Lula da Silva** (PT)
2. **Flávio Bolsonaro** (PL)
3. **Ronaldo Caiado** (PSD)
4. **Romeu Zema** (Novo)
5. **Pablo Marçal** (PRTB)
6. **Clariana Barão** (DC)
7. **Edmilson Costa** (PCB)
8. **Hertz Dias** (PSTU)
9. **Rui Costa Pimenta** (PCO)
10. **Samara Martins** (UP)
11. **Veterinário Wilson Grassi** (Democrata)
12. **Escritor Augusto Cury** (Avante)
13. **Renan Santos** (Missão)

---

## 🚀 Como Executar

### 1. Configuração do Ambiente (.env)

Crie ou edite o arquivo `.env` na raiz do projeto:

```env
# Meta Graph API Token (Opcional, ativa o Dual-Engine completo com UFs e Spend)
META_ACCESS_TOKEN=seu_token_aqui
META_API_VERSION=v19.0

# Limiares Forenses
AD_BURST_THRESHOLD=50
TRENDS_NIGHT_THRESHOLD=60.0
TRENDS_VARIANCE_MAX=150.0
```

### 2. Execução da Auditoria em Lote (Batch OSINT Engine)

Executa a auditoria completa de todos os 13 candidatos presidenciais, computa os grafos e gera a tabela consolidada no terminal:

```bash
python run_all.py
```

### 3. Forçar Atualização em Tempo Real (Bypass Cache)

Para forçar novas requisições em tempo real para todos os candidatos:

```bash
python -c "from run_all import run_batch_investigation; run_batch_investigation(force_refresh=True)"
```

### 4. Investigação Individual de Alvo

```bash
python main.py --target "Augusto Cury"
python main.py --target "Renan Santos" --context-tags "MBL, Movimento Brasil Livre, Partido Missao"
```

### 5. Retreinamento do Modelo SVM (MLOps Pipeline)

```bash
python src/models/ml_pipeline/train_svm.py
```

---

## 📁 Estrutura de Dossiês e Relatórios

Cada alvo auditado gera uma pasta própria dentro de `dossies/`:

```text
dossies/
├── auditoria.db                    <- Banco SQLite relacional com histórico e predições ML
├── luiz_inácio_lula_da_silva/
│   ├── dossie.html                 <- Relatório visual forense com gráficos Chart.js
│   └── dossie.json                 <- Dossiê técnico estruturado (JSON com SHA-256)
├── flávio_bolsonaro/
│   ├── dossie.html
│   └── dossie.json
├── augusto_cury/
└── renan_santos/
```

---

## 🔒 Cadeia de Custódia e Apresentação Judicial

Cada dossiê gerado inclui:

- **Hash Criptográfico SHA-256** gravado no cabeçalho do documento.
- **Links Canônicos Permanentes** para cada criativo na Meta Ad Library (`https://www.facebook.com/ads/library/?id=<AD_ID>`).
- **Segregação Contábil-Eleitoral**: Separação clara entre Gastos da Página Oficial, Gastos de Aliados/Coligações e Spend Oculto em Terceiros.
- Relatório em conformidade com as normas probatórias do **Tribunal Superior Eleitoral (TSE)** e **Ministério Público Eleitoral (MPE)**.
