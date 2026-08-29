"""
Módulo de Classificação NLP Eleitoral & Estimativa de Spend Oculto (Inspirado em facebook-political-ads).

Objetivo:
- Classificar textos e headlines de anúncios na Meta Ad Library segundo a Resolução TSE 23.610/2019.
- Separar criativos comerciais de infoprodutos (livros, cursos) de propaganda política camuflada.
- Estimar o montante financeiro total de spend oculto e declarado com base em custos médios de leilão de tráfego no Brasil.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PoliticalNLPClassifier:
    """
    Classificador semântico e auditor de conformidade eleitoral para publicidade digital.
    """

    # Termos eleitorais e políticos estritos (Tier 1 - Violação direta se não declarado)
    STRICT_POLITICAL_TERMS = [
        "eleicao", "eleicoes", "pre-candidato", "pre candidata", "candidato", "candidata",
        "campanha eleitoral", "voto", "vote", "urna", "deputado", "senador", "governador",
        "presidente", "presidencia", "filiacao", "partido politico", "partido missao",
        "mbl", "avante", "tse", "tre", "horario eleitoral", "debates", "pesquisa eleitoral",
        "projeto de lei", "congresso nacional", "camara dos deputados", "senado federal"
    ]

    # Termos de cunho sociopolítico e bandeiras ideológicas (Tier 2)
    POLITICAL_WEDGE_TERMS = [
        "doutrinacao", "ideologia de genero", "marxismo cultural", "comunismo", "conservadorismo",
        "liberdade de expressao", "censura", "stf", "alexandre de moraes", "ditadura",
        "sistema corrupto", "privatizacao", "desencarceramento", "porte de armas"
    ]

    # Termos comerciais estritos (Infoprodutos, Métodos e Livros)
    COMMERCIAL_PRODUCT_TERMS = [
        "gestao da emocao", "inteligencia emocional", "codigo da inteligencia",
        "ansiedade", "sindrome do pensamento acelerado", "spa", "livro", "best seller",
        "curso online", "masterclass", "mentoria", "escola da inteligencia", "autocontrole",
        "psicologia", "psiquiatria", "saude mental", "comprar livro", "inscricoes abertas"
    ]

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Remove acentos e padroniza para minúsculas."""
        if not text:
            return ""
        text = text.lower().strip()
        replacements = {
            "á": "a", "à": "a", "ã": "a", "â": "a",
            "é": "e", "ê": "e", "í": "i",
            "ó": "o", "ô": "o", "õ": "o",
            "ú": "u", "ü": "u", "ç": "c",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    def __init__(self):
        import joblib
        from pathlib import Path
        model_path = Path("src/models/ml_pipeline/hybrid_svm_pipeline.joblib")
        if model_path.exists():
            self.svm_pipeline = joblib.load(model_path)
        else:
            self.svm_pipeline = None
            logger.warning("SVM model not found. Running in Heuristics-only mode.")

    def classify_ad_creative(self, title: str, body: str, has_byline: bool = False, page_category: str = "Unknown") -> Dict[str, Any]:
        """
        Classifica um anúncio individual e determina sua conformidade regulatória.
        """
        full_text = f"{title or ''} {body or ''}"
        norm_text = self._normalize_text(full_text)

        strict_matches = [t for t in self.STRICT_POLITICAL_TERMS if re.search(r'\b' + re.escape(t) + r'\b', norm_text)]
        wedge_matches = [t for t in self.POLITICAL_WEDGE_TERMS if re.search(r'\b' + re.escape(t) + r'\b', norm_text)]
        comm_matches = [t for t in self.COMMERCIAL_PRODUCT_TERMS if re.search(r'\b' + re.escape(t) + r'\b', norm_text)]

        # Lógica Híbrida: Predição do SVM
        svm_political_prob = 0.0
        if self.svm_pipeline and full_text.strip():
            probs = self.svm_pipeline.predict_proba([full_text.strip()])[0]
            # Assumindo que a classe '1' é político e '0' é não-político
            classes = self.svm_pipeline.classes_
            if 1 in classes:
                svm_political_prob = probs[list(classes).index(1)]
            else:
                svm_political_prob = probs[1]

        is_political_heuristic = (len(strict_matches) > 0) or (len(wedge_matches) >= 2)
        is_political_ml = svm_political_prob >= 0.85
        has_commercial = len(comm_matches) > 0
        
        is_political = is_political_heuristic or is_political_ml

        # Determinação da Categoria Forense Híbrida
        confidence = svm_political_prob if svm_political_prob > 0 else 0.95
        
        if has_byline:
            category = "Rede Oficial & Partidária Declarada"
            is_infraction = False
            confidence = 1.0
        elif is_political_heuristic and not has_commercial:
            category = "Camuflagem Comercial (Spend Oculto)"
            is_infraction = True
            confidence = max(0.95, svm_political_prob)
        elif is_political_ml and not is_political_heuristic:
            category = f"Camuflagem Detectada por ML (Prob: {svm_political_prob:.2f})"
            is_infraction = True
        elif is_political and has_commercial:
            category = "Camuflagem Comercial (Spend Oculto)"
            is_infraction = True
        else:
            category = "Comercial / Infoproduto Regular"
            is_infraction = False
            confidence = max(0.90, 1.0 - svm_political_prob)

        all_triggers = list(set(strict_matches + wedge_matches))
        if is_political_ml and not all_triggers:
            all_triggers.append("Assinatura Semântica SVM")

        return {
            "is_political": is_political,
            "is_infraction": is_infraction,
            "category": category,
            "confidence": confidence,
            "triggers": all_triggers,
            "commercial_triggers": comm_matches,
            "svm_probability": svm_political_prob
        }

    def estimate_financial_spend(
        self,
        total_suspect_ads: int,
        declared_spend_min: float,
        declared_spend_max: float,
        cpm_min: float = 800.0,
        cpm_max: float = 2200.0,
    ) -> Dict[str, Any]:
        """
        Calcula as projeções de aporte financeiro oficial e paralelo com base na média de tráfego.
        """
        projected_hidden_min = round(total_suspect_ads * cpm_min, 2)
        projected_hidden_max = round(total_suspect_ads * cpm_max, 2)

        if declared_spend_max > 0 and total_suspect_ads > 0:
            resumo = (
                f"Campanha com registro oficial na Meta Ad Library (R$ {declared_spend_min:,.2f} a R$ {declared_spend_max:,.2f}) "
                f"combinada com {total_suspect_ads} criativo(s) sem rótulo transparente "
                f"(spend oculto projetado entre R$ {projected_hidden_min:,.2f} e R$ {projected_hidden_max:,.2f})."
            )
        elif declared_spend_max > 0:
            resumo = (
                f"Investimento oficial declarado e transparente na Meta Ad Library totalizando entre "
                f"R$ {declared_spend_min:,.2f} e R$ {declared_spend_max:,.2f}. 100% em conformidade com as regras de transparência."
            )
        elif total_suspect_ads > 0:
            resumo = (
                f"Todos os criativos catalogados foram veiculados sob sigilo comercial (spend oculto). "
                f"Com base na média de leilão de tráfego pago no Brasil, projeta-se um aporte financeiro estimado entre "
                f"R$ {projected_hidden_min:,.2f} e R$ {projected_hidden_max:,.2f} na veiculação dos criativos suspeitos."
            )
        else:
            resumo = (
                f"Anúncios veiculados sob conta comercial regular sem teor político ou infração de transparência eleitoral."
            )

        return {
            "total_declarado_min": declared_spend_min,
            "total_declarado_max": declared_spend_max,
            "estimativa_oculta_min": projected_hidden_min,
            "estimativa_oculta_max": projected_hidden_max,
            "media_estimada_por_anuncio": f"R$ {cpm_min:,.2f} a R$ {cpm_max:,.2f}",
            "resumo_financeiro": resumo,
        }
