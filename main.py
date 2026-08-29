"""
Ponto de Entrada Principal (CLI) do Sistema de Auditoria OSINT e Astroturfing.
Executa o pipeline completo sobre dados reais e salva os dossiês organizados por pasta do alvo.
"""

import argparse
import io
import json
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path

from src.config import settings
from src.database.db_manager import db_manager
from src.modules.evidence_preserver import EvidencePreserver
from src.pipeline import ForensicAuditPipeline

# Força codificação UTF-8 para evitar problemas de console no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("OSINT-Auditor")


def slugify_target_name(name: str) -> str:
    """Normaliza o nome do alvo para formato de diretório seguro (ex: 'Augusto Cury' -> 'augusto_cury')."""
    nfkd = unicodedata.normalize("NFKD", name)
    clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", clean).strip("_").lower()
    return clean or "alvo"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistema de Auditoria Civica e OSINT para Deteccao de Astroturfing Eleitoral e Manipulacao Digital (100% Dados Reais)."
    )
    parser.add_argument(
        "--target",
        type=str,
        default="Augusto Cury",
        help="Nome do alvo ou figura publica sob investigacao (padrao: 'Augusto Cury')",
    )
    parser.add_argument(
        "--page-id",
        type=str,
        default=None,
        help="ID opcional da pagina na Meta Ad Library (se omitido, pesquisa por nome na rede inteira)",
    )
    parser.add_argument(
        "--keyword",
        type=str,
        default=None,
        help="Palavra-chave a ser consultada no Google Trends (padrao: igual ao target)",
    )
    parser.add_argument(
        "--context-tags",
        type=str,
        default=None,
        help="Tags separadas por virgula para desambiguacao de homonimos (ex: 'MBL, Partido Missao, A Missao')",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignora o cache local persistente e forca novas consultas live as APIs",
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="Exibe todos os alvos auditados e salvos no banco de dados SQLite e encerra",
    )
    parser.add_argument(
        "--history",
        type=str,
        default=None,
        help="Exibe o historico probatorio de dossies gerados para o alvo informado e encerra",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("ALVO1", "ALVO2"),
        help="Cruza a rede de anuncios entre dois alvos para identificar paginas satelites compartilhadas",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Diretorio de saida (padrao: dossies/<nome_do_alvo>/)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Caminho personalizado do arquivo JSON de saida (opcional)",
    )
    parser.add_argument(
        "--html-output",
        type=str,
        default=None,
        help="Caminho personalizado do relatorio visual HTML (opcional)",
    )
    parser.add_argument(
        "--burst-threshold",
        type=int,
        default=settings.ad_burst_threshold,
        help=f"Limiar de anuncios por minuto para sinalizar Ad Spamming (padrao: {settings.ad_burst_threshold})",
    )
    parser.add_argument(
        "--night-threshold",
        type=float,
        default=settings.trends_night_threshold,
        help=f"Limiar de indice de busca no Google Trends na madrugada (padrao: {settings.trends_night_threshold})",
    )
    return parser.parse_args()


def handle_db_commands(args: argparse.Namespace) -> bool:
    """Executa operacoes de banco de dados se solicitadas via flags especificas."""
    if args.list_targets:
        targets = db_manager.list_targets()
        print("\n" + "=" * 80)
        print(" [ALVOS AUDITADOS E PERSISTIDOS NO BANCO DE DADOS SQLITE] ")
        print("=" * 80)
        if not targets:
            print("Nenhum alvo persistido no banco de dados ainda.")
        else:
            for t in targets:
                print(f" • Alvo: {t['name']} (slug: {t['slug']})")
                print(f"   Dossiês Gerados : {t['total_dossiers_count']}")
                print(f"   Anúncios Salvos : {t.get('total_ads_stored', 0)} ({t.get('total_suspect_ads', 0)} suspeitos)")
                print(f"   Última Auditoria: {t['last_audited_at']}")
                print("-" * 60)
        print()
        return True

    if args.history:
        slug = slugify_target_name(args.history)
        history = db_manager.get_history_for_target(slug)
        print("\n" + "=" * 80)
        print(f" [HISTORICO FORENSE DE DOSSIES: {args.history.upper()}] ")
        print("=" * 80)
        if not history:
            print(f"Nenhum dossiê encontrado para o alvo '{args.history}'.")
        else:
            for d in history:
                print(f" • Dossiê ID : {d['dossier_id']}")
                print(f"   Data UTC   : {d['generated_at_utc']}")
                print(f"   Suspeitos  : {d['total_suspects']}/{d['total_ads_analyzed']} anúncios")
                print(f"   Dark Money : R$ {d['estimated_hidden_min']:,.2f} a R$ {d['estimated_hidden_max']:,.2f}")
                print(f"   Madrugada  : {d['trends_dawn_mean']}/100 (Z-Score: +{d['trends_z_score']})")
                print(f"   SHA-256    : {d['sha256_hash']}")
                print("-" * 60)
        print()
        return True

    if args.compare:
        t1, t2 = args.compare
        slug1 = slugify_target_name(t1)
        slug2 = slugify_target_name(t2)
        comp = db_manager.compare_targets(slug1, slug2)
        print("\n" + "=" * 80)
        print(f" [CRUZAMENTO DE REDE FORENSE: {t1.upper()} vs {t2.upper()}] ")
        print("=" * 80)
        shared = comp.get("shared_satellite_pages", [])
        if shared:
            print(f"🚨 ALERTA: Detectadas {len(shared)} PÁGINAS SATÉLITES COMPARTILHADAS veiculando anúncios para ambos os alvos:")
            for p in shared:
                print(f"   🔗 Página: {p.get('page_name')} (ID: {p.get('page_id')})")
        else:
            print("Nenhuma página satélite compartilhada identificada entre os alvos no acervo atual.")
        print("-" * 80 + "\n")
        return True

    return False


def main() -> None:
    args = parse_arguments()

    if handle_db_commands(args):
        return

    target_slug = slugify_target_name(args.target)

    # Organização de diretórios por alvo investigado
    target_dir = Path(args.output_dir or Path("dossies") / target_slug)
    target_dir.mkdir(parents=True, exist_ok=True)

    json_output_path = Path(args.output) if args.output else (target_dir / "dossie.json")
    html_output_path = Path(args.html_output) if args.html_output else (target_dir / "dossie.html")

    print("=" * 80)
    print(" [SISTEMA DE AUDITORIA CIVICA & OSINT: RASTREAMENTO DE ASTROTURFING] ")
    print(" [MODO: 100% DADOS REAIS - META GRAPH API & GOOGLE TRENDS + SQLITE CACHE] ")
    print("=" * 80)
    print(f" * Alvo Investigado    : {args.target}")
    print(f" * Pasta de Destino    : {target_dir}")
    print(f" * Page ID (Meta)      : {args.page_id or 'Busca Ampla com Desambiguação'}")
    print(f" * Termo Google Trends : {args.keyword or args.target}")
    print(f" * Forçar Refresh Live : {'Sim (Ignorando Cache)' if args.force_refresh else 'Não (Usando Cache Inteligente)'}")
    print(f" * Limiar Ad Spam      : >= {args.burst_threshold} anuncios/minuto")
    print(f" * Limiar Madrugada    : >= {args.night_threshold} indice relativo (01h-05h)")
    print(f" * Arquivo JSON Saida  : {json_output_path}")
    print(f" * Arquivo HTML Saida  : {html_output_path}")
    print("-" * 80)

    pipeline = ForensicAuditPipeline()
    
    pipeline.meta_detector.burst_threshold = args.burst_threshold
    pipeline.trends_detector.night_threshold = args.night_threshold

    context_tags_list = (
        [t.strip() for t in args.context_tags.split(",") if t.strip()]
        if args.context_tags
        else None
    )

    try:
        dossie = pipeline.run_investigation(
            target_name=args.target,
            page_id=args.page_id,
            keyword=args.keyword,
            context_tags=context_tags_list,
            force_refresh=args.force_refresh,
            target_slug=target_slug,
        )

        json_str = pipeline.export_dossier_json(dossie, output_path=str(json_output_path))
        EvidencePreserver.generate_html_evidence_report(dossie, output_html_path=str(html_output_path))

        print("\n" + "=" * 80)
        print(" [DOSSIE TECNICO GERADO COM SUCESSO - DADOS REAIS PROBATORIOS] ")
        print("=" * 80)
        print(json_str)
        print("=" * 80)
        print(f"\n[SUCESSO] Dossie probatorio JSON salvo em : {json_output_path}")
        print(f"[SUCESSO] Relatorio visual de custodia HTML: {html_output_path}")
        print(f"[SUCESSO] Persistência relacional gravada no SQLite: {db_manager.db_path}\n")

    except PermissionError as pe:
        print("\n" + "!" * 80)
        print(" [ERRO DE AUTORIZACAO NA META AD LIBRARY API] ")
        print("!" * 80)
        print(f"Motivo: {pe}")
        print("!" * 80 + "\n")
        sys.exit(1)

    except (ValueError, ConnectionError, RuntimeError) as e:
        print("\n" + "!" * 80)
        print(" [FALHA NA EXECUCAO DA AUDITORIA] ")
        print("!" * 80)
        print(f"Erro: {e}")
        print("!" * 80 + "\n")
        sys.exit(1)

    except Exception as e:
        logger.exception(f"Erro critico inesperado durante a execucao: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

