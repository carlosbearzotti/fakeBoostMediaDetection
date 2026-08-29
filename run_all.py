"""
Script de Execução em Lote (Batch Auditor): Executa a auditoria completa de todos os alvos configurados.
Gera os dossiês JSON/HTML, persiste no SQLite (auditoria.db) e exibe um relatório comparativo consolidado no console.
"""

import io
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from src.database.db_manager import db_manager
from src.modules.evidence_preserver import EvidencePreserver
from src.pipeline import ForensicAuditPipeline

# Força codificação UTF-8 para evitar problemas de console no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Batch-Auditor")

# Catálogo oficial dos candidatos à Presidência da República (Eleições 2026)
TARGETS_CATALOG: List[Dict[str, Any]] = [
    {
        "target": "Luiz Inácio Lula da Silva",
        "keyword": "Lula",
        "context_tags": ["PT", "Partido dos Trabalhadores", "Presidente", "Governo Federal", "Janja", "Haddad", "Alckmin"],
        "desc": "Presidente da República / Candidato Oficial (PT)",
    },
    {
        "target": "Flávio Bolsonaro",
        "keyword": "Flávio Bolsonaro",
        "context_tags": ["PL", "Partido Liberal", "Bolsonaro", "Senador", "Rio de Janeiro"],
        "desc": "Senador da República / Candidato Oficial (PL)",
    },
    {
        "target": "Ronaldo Caiado",
        "keyword": "Ronaldo Caiado",
        "context_tags": ["PSD", "União Brasil", "Goiás", "Governador"],
        "desc": "Governador de Goiás / Candidato Oficial (PSD)",
    },
    {
        "target": "Romeu Zema",
        "keyword": "Romeu Zema",
        "context_tags": ["Novo", "Partido Novo", "Minas Gerais", "Governador", "Zema"],
        "desc": "Governador de Minas Gerais / Candidato Oficial (Novo)",
    },
    {
        "target": "Pablo Marçal",
        "keyword": "Pablo Marçal",
        "context_tags": ["PRTB", "Marçal", "São Paulo", "Plataforma Internacional"],
        "desc": "Empresário / Candidato Oficial (PRTB)",
    },
    {
        "target": "Clariana Barão",
        "keyword": "Clariana Barão",
        "context_tags": ["DC", "Democracia Cristã"],
        "desc": "Candidata Oficial (DC)",
    },
    {
        "target": "Edmilson Costa",
        "keyword": "Edmilson Costa",
        "context_tags": ["PCB", "Partido Comunista Brasileiro"],
        "desc": "Economista / Candidato Oficial (PCB)",
    },
    {
        "target": "Hertz Dias",
        "keyword": "Hertz Dias",
        "context_tags": ["PSTU", "Socialismo"],
        "desc": "Professor / Candidato Oficial (PSTU)",
    },
    {
        "target": "Rui Costa Pimenta",
        "keyword": "Rui Costa Pimenta",
        "context_tags": ["PCO", "Causa Operária"],
        "desc": "Jornalista / Candidato Oficial (PCO)",
    },
    {
        "target": "Samara Martins",
        "keyword": "Samara Martins",
        "context_tags": ["UP", "Unidade Popular"],
        "desc": "Militante / Candidata Oficial (UP)",
    },
    {
        "target": "Veterinário Wilson Grassi",
        "keyword": "Wilson Grassi",
        "context_tags": ["Democrata", "Veterinário"],
        "desc": "Médico Veterinário / Candidato Oficial (Democrata)",
    },
    {
        "target": "Augusto Cury",
        "keyword": "Augusto Cury",
        "context_tags": None,  # usa desambiguação mapeada no sistema
        "desc": "Escritor / Candidato Oficial (Avante)",
    },
    {
        "target": "Renan Santos",
        "keyword": "Renan Santos",
        "context_tags": ["MBL", "Movimento Brasil Livre", "Partido Missão", "A Missão", "Missão"],
        "desc": "Presidente Partido Missão / Candidato Oficial (Missão)",
    },
]


def run_batch_investigation(force_refresh: bool = False) -> None:
    """Executa a esteira investigativa para todos os alvos catalogados."""
    pipeline = ForensicAuditPipeline()
    summary_results: List[Dict[str, Any]] = []

    print("\n" + "=" * 110)
    print(" 🚀 INICIANDO AUDITORIA CÍVICA EM MASSA (BATCH OSINT ENGINE) ")
    print(" MODO: 100% DADOS REAIS - META GRAPH API & GOOGLE TRENDS + SQLITE CACHE")
    print(f" TOTAL DE ALVOS NA FILA: {len(TARGETS_CATALOG)}")
    print("=" * 110 + "\n")

    start_total_time = time.time()

    for idx, item in enumerate(TARGETS_CATALOG, 1):
        target_name = item["target"]
        keyword = item.get("keyword") or target_name
        tags = item.get("context_tags")
        desc = item.get("desc", "")
        slug = target_name.lower().replace(" ", "_")

        target_dir = Path("dossies") / slug
        target_dir.mkdir(parents=True, exist_ok=True)

        json_path = target_dir / "dossie.json"
        html_path = target_dir / "dossie.html"

        print(f"[{idx}/{len(TARGETS_CATALOG)}] 🔍 Processando Alvo: {target_name.upper()} ({desc})")
        print(f"      📁 Diretório: {target_dir}")
        print(f"      🏷️  Tags de Contexto: {', '.join(tags) if tags else 'Padrão do Sistema'}")
        
        t0 = time.time()
        try:
            dossie = pipeline.run_investigation(
                target_name=target_name,
                keyword=keyword,
                context_tags=tags,
                force_refresh=force_refresh,
                target_slug=slug,
            )

            # Exporta JSON e Relatório Visual HTML
            pipeline.export_dossier_json(dossie, output_path=str(json_path))
            EvidencePreserver.generate_html_evidence_report(dossie, output_html_path=str(html_path))

            elapsed = time.time() - t0
            print(f"      ✅ Concluído em {elapsed:.2f}s | Salvo em {html_path}\n")

            suspects = len(dossie.divergencia_categoria.anuncios_suspeitos_ids)
            total_ads = dossie.divergencia_categoria.total_anuncios_analisados
            ira_score = dossie.score_geral_astroturfing or 0.0
            t15_score = dossie.anomalia_tendencia_15d.score_inorganicidade if dossie.anomalia_tendencia_15d else 0.0
            coord_score = dossie.coordenacao_rede_agencias.score_coordenacao if dossie.coordenacao_rede_agencias else 0.0

            fin = dossie.investimento_estimado

            summary_results.append({
                "alvo": target_name,
                "total_ads": total_ads,
                "suspeitos": suspects,
                "ira": f"{ira_score:.1f}/100",
                "coord": f"{coord_score:.0f}/100",
                "trend15d": f"{t15_score:.0f}/100",
                "gasto_proprio": f"R$ {fin.gasto_direto_pagina_alvo_max:,.0f} ({fin.anuncios_diretos_count} ads)",
                "gasto_rede": f"R$ {fin.gasto_rede_coligacao_max:,.0f} ({fin.anuncios_coligacao_count} ads)",
                "html_path": str(html_path),
            })

        except Exception as err:
            logger.exception(f"Erro ao processar alvo '{target_name}': {err}")
            print(f"      ❌ Falha no alvo {target_name}: {err}\n")

    total_time = time.time() - start_total_time

    # Tabela Executiva Consolidada
    print("=" * 110)
    print(" 📊 SUMÁRIO EXECUTIVO DA AUDITORIA CONSOLIDADA (MOTORES OSINT AVANÇADOS)")
    print("=" * 110)
    header = f"{'ALVO':<16} | {'ADS':<5} | {'SUSP':<5} | {'RISCO (IRA)':<12} | {'COORDENAÇÃO':<12} | {'GASTO PRÓPRIO':<20} | {'GASTO REDE ALIADOS'}"
    print(header)
    print("-" * 110)

    for r in summary_results:
        row = f"{r['alvo']:<16} | {r['total_ads']:<5} | {r['suspeitos']:<5} | {r['ira']:<12} | {r['coord']:<12} | {r['gasto_proprio']:<20} | {r['gasto_rede']}"
        print(row)

    print("=" * 110)
    print(f"✨ Auditoria concluída com sucesso em {total_time:.2f}s!")
    print(f"💾 Base de dados relacional e histórico: {db_manager.db_path}")
    print("📂 Todos os relatórios HTML e JSON foram salvos na pasta 'dossies/'\n")


if __name__ == "__main__":
    force = "--force-refresh" in sys.argv
    run_batch_investigation(force_refresh=force)
