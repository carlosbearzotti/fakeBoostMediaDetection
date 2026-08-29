import json
import logging
import os
import sqlite3
from pathlib import Path
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC
from sklearn.pipeline import make_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path("dossies/auditoria.db")
MODEL_DIR = Path("src/models/ml_pipeline")

# Conjunto de Dados Sintético (Cold Start)
# Como o banco de dados pode estar vazio na primeira execução ou enviesado,
# injetamos amostras controladas (Seed) para balizar o SVM.
SYNTHETIC_DATA = [
    # Categoria 0: Não-Político (Anúncios comerciais comuns)
    ("Aprenda a controlar sua ansiedade com o método Gestão da Emoção. Inscrições abertas!", 0),
    ("Compre meu novo livro sobre inteligência emocional na Amazon.", 0),
    ("Venha conhecer a nossa escola de inteligência. Matrículas para 2026 abertas.", 0),
    ("Assista ao espetáculo O Vendedor de Sonhos neste final de semana no Teatro Itália.", 0),
    ("Aproveite a promoção de petshop, 20% off em ração.", 0),
    ("Dorama novo na Netflix, venha assistir ao trailer.", 0),
    
    # Categoria 1: Político / Astroturfing (Camuflagem ou Explícito)
    ("Um presidente não precisa ser o melhor em tudo. O Brasil precisa avançar. Augusto Cury 70 para Presidente.", 1),
    ("Quem alimenta o mundo precisa defender a própria imagem. Sabatina com candidatos.", 1),
    ("Lula deveria estar ali. Pela mente dos jovens brasileiros. Eleições 2026.", 1),
    ("Vote no partido missão para mudar o Brasil! Chega de corrupção no STF.", 1),
    ("Campanha eleitoral a todo vapor. Precisamos do seu apoio nas urnas.", 1),
    ("Pablo Marçal, eu discordo de você. O Brasil merece uma política melhor.", 1),
]

def load_data_from_db():
    if not DB_PATH.exists():
        return [], []
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Puxamos do banco e usamos a classificação anterior (is_suspect) para aumentar o dataset
    c.execute("SELECT raw_json, is_suspect FROM ads_archive")
    rows = c.fetchall()
    
    texts = []
    labels = []
    for row in rows:
        raw_json = row[0]
        is_suspect = row[1]
        
        if not raw_json:
            continue
            
        data = json.loads(raw_json)
        bodies = data.get("ad_creative_bodies", [])
        titles = data.get("ad_creative_link_titles", [])
        full_text = " ".join([str(b) for b in bodies + titles]).strip()
        
        if full_text:
            texts.append(full_text)
            labels.append(1 if is_suspect else 0)
            
    # MLOps: Carregar dados com feedback humano (Continuous Learning)
    try:
        c.execute("SELECT raw_text, user_feedback FROM ml_feedback_log WHERE user_feedback IS NOT NULL")
        feedback_rows = c.fetchall()
        for row in feedback_rows:
            texts.append(row[0])
            labels.append(row[1])
        if feedback_rows:
            logger.info(f"Carregadas {len(feedback_rows)} amostras revisadas pelo usuário do ml_feedback_log.")
    except sqlite3.OperationalError:
        # Tabela pode ainda não existir se run_all.py não rodou
        pass
        
    conn.close()
    return texts, labels

def train_and_save():
    logger.info("Coletando dados para treinamento (Cold Start + DB)...")
    texts = [item[0] for item in SYNTHETIC_DATA]
    labels = [item[1] for item in SYNTHETIC_DATA]
    
    db_texts, db_labels = load_data_from_db()
    texts.extend(db_texts)
    labels.extend(db_labels)
    
    logger.info(f"Total de amostras para treinamento: {len(texts)}")
    
    logger.info("Vetorizando e Treinando SVM...")
    # Pipeline Tfidf -> Support Vector Classifier
    # ngram_range=(1,2) pega palavras isoladas e bigramas (ex: "gestão emoção", "eleições 2026")
    pipeline = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), max_features=5000, lowercase=True),
        SVC(kernel='linear', probability=True, class_weight='balanced')
    )
    
    pipeline.fit(texts, labels)
    
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "hybrid_svm_pipeline.joblib"
    joblib.dump(pipeline, model_path)
    logger.info(f"Modelo salvo com sucesso em {model_path}")

if __name__ == "__main__":
    train_and_save()
