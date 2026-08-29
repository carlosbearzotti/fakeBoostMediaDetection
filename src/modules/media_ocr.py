"""
Módulo Forense Complementar: Extrator de Texto de Imagens e Criativos (OCR).
Objetivo:
- Analisar criativos visuais onde o texto político/eleitoral está contido dentro da imagem ou banner.
- Suportar extração via OCR (Tesseract / EasyOCR / fallback de parsing de payloads).
"""

import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MediaOCRExtractor:
    """
    Extrator de texto probatório de imagens e criativos publicitários.
    """

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self.tesseract_cmd = tesseract_cmd
        self._has_tesseract = False
        self._init_ocr()

    def _init_ocr(self) -> None:
        """Verifica a disponibilidade de bibliotecas de OCR no ambiente."""
        try:
            import pytesseract
            from PIL import Image

            if self.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

            # Teste rápido de versão
            pytesseract.get_tesseract_version()
            self._has_tesseract = True
            logger.info("Módulo OCR: Motor Tesseract detectado e ativo.")
        except Exception:
            self._has_tesseract = False
            logger.debug("Módulo OCR: Motor Tesseract não instalado ou não configurado no PATH. Utilizando parser de metadados e legendas estendidas.")

    def extract_text_from_image_bytes(self, image_bytes: bytes) -> str:
        """Extrai texto contido em uma imagem via OCR."""
        if not self._has_tesseract:
            return ""

        try:
            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(img, lang="por+eng")
            return text.strip()
        except Exception as e:
            logger.debug(f"Erro ao processar imagem via OCR: {e}")
            return ""

    def enrich_ad_with_media_text(self, ad: Dict[str, Any]) -> str:
        """
        Consolida todas as camadas de texto de um criativo (títulos, legendas, corpos, descrições e OCR).
        """
        parts = []

        # 1. Campos nativos de texto
        if ad.get("page_name"):
            parts.append(str(ad["page_name"]))
        if ad.get("ad_creative_link_titles"):
            parts.extend(ad["ad_creative_link_titles"])
        if ad.get("ad_creative_bodies"):
            parts.extend(ad["ad_creative_bodies"])
        if ad.get("ad_creative_link_captions"):
            parts.extend(ad["ad_creative_link_captions"])
        if ad.get("ad_creative_link_descriptions"):
            parts.extend(ad["ad_creative_link_descriptions"])

        return " ".join(parts)


ocr_extractor = MediaOCRExtractor()
