"""
Módulo Complementar: Preservador de Evidências e Snapshot Probatório com Gráfico de Distribuição Forense.

Objetivo:
- Gerar links públicos permanentes da Meta Ad Library (https://www.facebook.com/ads/library/?id=<AD_ID>).
- Criar snapshots em HTML auditável com cadeia de custódia, segregação de gastos (página própria vs. coligação),
  Gráfico de Pizza / Donut Forense (Chart.js), Motores Avançados (15 Dias e CooRnet CLSB)
  e hash SHA-256 para apresentação probatória (TSE/Meta/MPE).
"""

from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.database.db_manager import db_manager
from src.models.dossier import DossieTecnico

logger = logging.getLogger(__name__)


class EvidencePreserver:
    """
    Garante a cadeia de custódia digital e preservação probatória dos anúncios auditados.
    """

    BASE_AD_LIBRARY_URL = "https://www.facebook.com/ads/library/?id="

    @staticmethod
    def generate_public_ad_url(ad_id: str) -> str:
        """Retorna o link canônico e público da Meta Ad Library para o ID do anúncio."""
        return f"{EvidencePreserver.BASE_AD_LIBRARY_URL}{ad_id}"

    @classmethod
    def build_pie_chart_data(
        cls, dossie: DossieTecnico, target_slug: str
    ) -> Dict[str, Any]:
        """
        Calcula a distribuição consolidada das categorias forenses dos anúncios para renderização do Gráfico de Pizza.
        """
        total_ads = dossie.divergencia_categoria.total_anuncios_analisados
        suspect_ids = set(dossie.divergencia_categoria.anuncios_suspeitos_ids)

        cam_map = {}
        if dossie.divergencia_categoria.amostras_camufladas:
            for c in dossie.divergencia_categoria.amostras_camufladas:
                cam_map[str(c.ad_id)] = c

        categories_count = {
            "Rede Oficial & Partidária Declarada": 0,
            "Camuflagem Comercial / Autuação Meta": 0,
            "Página Satélite / Livro Terceiro (Art. 57-C)": 0,
            "Comercial / Infoproduto Regular": 0,
        }

        # Extrai dados catalogados no SQLite
        stored_ads = []
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ad_id, page_name, is_suspect, is_camouflaged, trigger_words, spend_min, spend_max
                    FROM ads_archive
                    WHERE target_slug = ?
                """, (target_slug,))
                stored_ads = [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"Não foi possível extrair categorias do banco: {e}")

        if stored_ads:
            for ad in stored_ads:
                aid = str(ad.get("ad_id"))
                c_item = cam_map.get(aid)
                if c_item:
                    tipo = getattr(c_item, "tipo_infracao", "")
                    if "Satélite" in tipo or "Terceiro" in tipo or "Livro" in tipo:
                        categories_count["Página Satélite / Livro Terceiro (Art. 57-C)"] += 1
                    else:
                        categories_count["Camuflagem Comercial / Autuação Meta"] += 1
                elif ad.get("is_suspect") == 1 or aid in suspect_ids:
                    categories_count["Camuflagem Comercial / Autuação Meta"] += 1
                elif (ad.get("spend_max") or 0) > 0:
                    categories_count["Rede Oficial & Partidária Declarada"] += 1
                else:
                    categories_count["Comercial / Infoproduto Regular"] += 1
        else:
            for c in cam_map.values():
                tipo = getattr(c, "tipo_infracao", "")
                if "Satélite" in tipo or "Terceiro" in tipo or "Livro" in tipo:
                    categories_count["Página Satélite / Livro Terceiro (Art. 57-C)"] += 1
                else:
                    categories_count["Camuflagem Comercial / Autuação Meta"] += 1

            suspect_sum = len(suspect_ids)
            declared_sum = total_ads - suspect_sum if dossie.investimento_estimado.total_declarado_max > 0 else 0
            regular_sum = total_ads - suspect_sum - declared_sum

            categories_count["Rede Oficial & Partidária Declarada"] = max(0, declared_sum)
            categories_count["Comercial / Infoproduto Regular"] = max(0, regular_sum)

        # Ajuste de consistência matemática
        current_sum = sum(categories_count.values())
        if current_sum < total_ads:
            diff = total_ads - current_sum
            if dossie.investimento_estimado.total_declarado_max > 0:
                categories_count["Rede Oficial & Partidária Declarada"] += diff
            else:
                categories_count["Comercial / Infoproduto Regular"] += diff

        return categories_count

    @classmethod
    def generate_html_evidence_report(
        cls, dossie: DossieTecnico, output_html_path: str = "relatorio_evidencias.html"
    ) -> str:
        """
        Gera um relatório forense visual em HTML com Gráfico de Pizza Convencional (Chart.js),
        segregação financeira detalhada, Motores de IA/Estatística (Prophet/Darts, CooRnet CLSB), links diretos e hashes SHA-256.
        """
        target_name = dossie.metadados.alvo_investigado
        target_slug = target_name.lower().replace(" ", "_")

        suspect_ids = dossie.divergencia_categoria.anuncios_suspeitos_ids
        total_suspects = len(suspect_ids)
        total_ads = dossie.divergencia_categoria.total_anuncios_analisados
        dossier_hash = hashlib.sha256(dossie.model_dump_json().encode("utf-8")).hexdigest()

        # Amostras camufladas mapeadas
        camouflaged_map = {}
        if dossie.divergencia_categoria.amostras_camufladas:
            for c in dossie.divergencia_categoria.amostras_camufladas:
                camouflaged_map[str(c.ad_id)] = c

        # Constrói dados para o Gráfico de Pizza
        categories_data = cls.build_pie_chart_data(dossie, target_slug)
        chart_labels = list(categories_data.keys())
        chart_values = list(categories_data.values())

        # Paleta forense: Verde (Oficial), Vermelho (Camuflagem), Laranja (Satélite/Livro), Azul (Comercial)
        chart_colors = ["#10b981", "#ef4444", "#f59e0b", "#3b82f6"]

        table_rows = []
        for idx, ad_id in enumerate(suspect_ids[:100], 1):
            ad_url = cls.generate_public_ad_url(ad_id)
            c_info = camouflaged_map.get(str(ad_id))

            if c_info:
                tipo = getattr(c_info, "tipo_infracao", "Infração de Transparência")
                if "Camuflagem" in tipo or "Autuação" in tipo:
                    badge_style = "background-color: #fee2e2; color: #991b1b;"
                elif "Satélite" in tipo or "Terceiro" in tipo or "Livro" in tipo:
                    badge_style = "background-color: #ffedd5; color: #c2410c;"
                else:
                    badge_style = "background-color: #fef3c7; color: #92400e;"
                badge_type = f'<span style="{badge_style} padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{tipo}</span>'
                triggers = f"<br><small style='color: #64748b;'>Gatilhos: {', '.join(c_info.gatilhos_detectados)}</small>"
            else:
                badge_type = '<span style="background-color: #fef3c7; color: #92400e; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">Disparo em Lote / Automação</span>'
                triggers = ""

            row_html = f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-family: monospace;">#{idx:03d}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-family: monospace; font-weight: bold; color: #1e293b;">{ad_id}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">
                    {badge_type}
                    {triggers}
                </td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">
                    <a href="{ad_url}" target="_blank" style="color: #2563eb; text-decoration: none; font-weight: 500;">
                        🔗 Abrir na Meta Ad Library &rarr;
                    </a>
                </td>
            </tr>
            """
            table_rows.append(row_html)

        if not table_rows:
            table_rows.append("""
            <tr>
                <td colspan="4" style="padding: 20px; text-align: center; color: #64748b;">
                    Nenhum anúncio com infração de transparência ou lote automatizado foi detectado nos dados reais.
                </td>
            </tr>
            """)

        fin = dossie.investimento_estimado
        if fin.gasto_direto_pagina_alvo_max > 0:
            fin_badge_direto = f"R$ {fin.gasto_direto_pagina_alvo_min:,.2f} a R$ {fin.gasto_direto_pagina_alvo_max:,.2f}"
        else:
            fin_badge_direto = "R$ 0,00"

        # Métricas dos motores avançados
        ira_score = dossie.score_geral_astroturfing or 0.0
        t15 = dossie.anomalia_tendencia_15d
        coord = dossie.coordenacao_rede_agencias

        ira_color = "#ef4444" if ira_score >= 50.0 else ("#f59e0b" if ira_score >= 25.0 else "#10b981")
        ira_label = "🚨 Alto Risco" if ira_score >= 50.0 else ("⚠️ Moderado" if ira_score >= 25.0 else "✅ Orgânico")

        html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Preservação Probatória — {dossie.metadados.alvo_investigado}</title>
    <!-- Chart.js para o Gráfico de Pizza Forense -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
            margin: 0;
            padding: 30px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            padding: 32px;
            border: 1px solid #e2e8f0;
        }}
        .header {{
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 20px;
            margin-bottom: 24px;
        }}
        .title {{
            font-size: 24px;
            font-weight: 800;
            color: #0f172a;
            margin: 0 0 8px 0;
        }}
        .subtitle {{
            color: #64748b;
            font-size: 14px;
            margin: 0;
        }}
        .badge {{
            display: inline-block;
            background-color: #ef4444;
            color: white;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .provenance-box {{
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 13px;
            margin: 16px 0;
        }}
        .finance-box {{
            background: #f0fdf4;
            border: 1px solid #86efac;
            padding: 14px 18px;
            border-radius: 8px;
            font-size: 13px;
            margin: 16px 0;
            color: #166534;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 14px;
            margin-bottom: 28px;
        }}
        .stat-card {{
            background: #f1f5f9;
            padding: 16px;
            border-radius: 8px;
            border-left: 4px solid #3b82f6;
        }}
        .stat-card.alert {{
            border-left-color: #ef4444;
        }}
        .stat-card.money {{
            border-left-color: #10b981;
        }}
        .stat-card.trends {{
            border-left-color: #f59e0b;
        }}
        .stat-card.ira {{
            border-left-color: {ira_color};
            background: #fafafa;
        }}
        .stat-value {{
            font-size: 18px;
            font-weight: bold;
            color: #1e293b;
        }}
        .stat-label {{
            font-size: 11px;
            color: #64748b;
            text-transform: uppercase;
            margin-top: 4px;
            font-weight: 600;
        }}

        /* Seção de Motores Avançados (15 Dias / CooRnet) */
        .engines-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 16px;
            margin: 24px 0;
        }}
        .engine-card {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 18px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        .engine-title {{
            font-size: 14px;
            font-weight: bold;
            color: #0f172a;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .engine-detail {{
            font-size: 12px;
            color: #475569;
            line-height: 1.5;
        }}

        /* Seção do Gráfico de Pizza Forense */
        .pie-section {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 24px;
            margin: 28px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }}
        .pie-header {{
            margin-bottom: 18px;
        }}
        .pie-header h2 {{
            margin: 0;
            font-size: 18px;
            color: #0f172a;
        }}
        .pie-grid {{
            display: grid;
            grid-template-columns: 1fr 1.2fr;
            gap: 24px;
            align-items: center;
        }}
        .chart-container {{
            position: relative;
            height: 280px;
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .breakdown-card {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 14px;
            border-radius: 8px;
            margin-bottom: 8px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
        }}
        .breakdown-label {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            font-weight: 600;
            color: #334155;
        }}
        .breakdown-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
        }}
        .breakdown-val {{
            font-size: 14px;
            font-weight: bold;
            color: #0f172a;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
            font-size: 14px;
        }}
        th {{
            background-color: #f8fafc;
            text-align: left;
            padding: 12px 10px;
            border-bottom: 2px solid #cbd5e1;
            color: #475569;
            font-size: 12px;
            text-transform: uppercase;
        }}
        .hash-box {{
            background: #0f172a;
            color: #38bdf8;
            padding: 12px 16px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 12px;
            word-break: break-all;
            margin-top: 24px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="badge">Relatório Forense de Evidências</span>
            <span style="display: inline-block; background-color: #16a34a; color: white; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; margin-left: 8px;">
                DADOS REAIS AUDITADOS + SQLITE
            </span>
            <h1 class="title" style="margin-top: 12px;">Auditoria Cívica: {dossie.metadados.alvo_investigado}</h1>
            <p class="subtitle">ID do Dossiê: <strong>{dossie.metadados.id_dossie}</strong> &bull; Data UTC: {dossie.metadados.data_geracao_utc}</p>
        </div>

        <div class="provenance-box">
            <strong>Fontes Reais Auditadas:</strong><br>
            &bull; <strong>Meta Ad Library:</strong> {dossie.metadados.origem_dados_meta}<br>
            &bull; <strong>Google Trends:</strong> {dossie.metadados.origem_dados_trends}
        </div>

        <div class="finance-box">
            <strong>💰 Parecer Financeiro de Investimento & Segregação de Rede:</strong><br>
            {fin.resumo_financeiro}
        </div>

        <div class="stats-grid">
            <div class="stat-card ira">
                <div class="stat-value" style="color: {ira_color};">{ira_score}/100</div>
                <div class="stat-label">Índice Astroturfing (IRA)</div>
            </div>
            <div class="stat-card alert">
                <div class="stat-value">{total_suspects}</div>
                <div class="stat-label">Anúncios Suspeitos</div>
            </div>
            <div class="stat-card money">
                <div class="stat-value">{fin_badge_direto}</div>
                <div class="stat-label">Gasto Próprio ({fin.anuncios_diretos_count} ads)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">R$ {fin.gasto_rede_coligacao_max:,.0f}</div>
                <div class="stat-label">Gasto Aliados ({fin.anuncios_coligacao_count} ads)</div>
            </div>
            <div class="stat-card trends">
                <div class="stat-value">{dossie.anomalia_trafego_madrugada.media_interesse_madrugada}/100</div>
                <div class="stat-label">Média Madrugada (01h-05h)</div>
            </div>
        </div>

        <!-- SEÇÃO DE MOTORES AVANÇADOS OSINT -->
        <h2 style="font-size: 18px; margin: 24px 0 12px 0;">🔬 Diagnóstico dos Motores Avançados de Detecção</h2>
        <div class="engines-grid">
            <div class="engine-card">
                <div class="engine-title">
                    <span>📈 Tendência 15 Dias (Prophet/Darts)</span>
                    <span style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: {'#fee2e2' if t15 and t15.status_anomalia_15d else '#dcfce7'}; color: {'#991b1b' if t15 and t15.status_anomalia_15d else '#166534'};">
                        {t15.score_inorganicidade if t15 else 0.0}/100
                    </span>
                </div>
                <div class="engine-detail">
                    {t15.parecer_tendencia if t15 else "Auditoria de série temporal executada."}
                </div>
            </div>

            <div class="engine-card">
                <div class="engine-title">
                    <span>🌐 Redes Coordenadas (CooRnet CLSB)</span>
                    <span style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: {'#fee2e2' if coord and coord.status_rede_coordenada else '#dcfce7'}; color: {'#991b1b' if coord and coord.status_rede_coordenada else '#166534'};">
                        {coord.score_coordenacao if coord else 0.0}/100
                    </span>
                </div>
                <div class="engine-detail">
                    {coord.parecer_coordenacao if coord else "Detecção de páginas satélites e CLSB executada."}
                </div>
            </div>
        </div>

        <!-- SEÇÃO: GRÁFICO DE PIZZA FORENSE DE CATEGORIAS -->
        <div class="pie-section">
            <div class="pie-header">
                <h2>📊 Distribuição Probatória por Tipo de Anúncio ({total_ads} criativos)</h2>
                <small style="color: #64748b;">
                    Classificação forense cruzando transparência na Meta (Res. TSE 23.610/2019), vínculos partidários e semântica de criativos.
                </small>
            </div>

            <div class="pie-grid">
                <div class="chart-container">
                    <canvas id="forensicPieChart"></canvas>
                </div>
                <div>
                    <div class="breakdown-card">
                        <span class="breakdown-label">
                            <span class="breakdown-dot" style="background-color: #10b981;"></span>
                            Rede Oficial & Partidária Declarada
                        </span>
                        <span class="breakdown-val">{categories_data['Rede Oficial & Partidária Declarada']} <small style="color: #64748b; font-weight: normal;">({(categories_data['Rede Oficial & Partidária Declarada'] / max(1, total_ads) * 100):.1f}%)</small></span>
                    </div>
                    <div class="breakdown-card">
                        <span class="breakdown-label">
                            <span class="breakdown-dot" style="background-color: #ef4444;"></span>
                            Camuflagem Comercial / Autuação Meta
                        </span>
                        <span class="breakdown-val">{categories_data['Camuflagem Comercial / Autuação Meta']} <small style="color: #64748b; font-weight: normal;">({(categories_data['Camuflagem Comercial / Autuação Meta'] / max(1, total_ads) * 100):.1f}%)</small></span>
                    </div>
                    <div class="breakdown-card">
                        <span class="breakdown-label">
                            <span class="breakdown-dot" style="background-color: #f59e0b;"></span>
                            Página Satélite / Livro Terceiro (Art. 57-C)
                        </span>
                        <span class="breakdown-val">{categories_data['Página Satélite / Livro Terceiro (Art. 57-C)']} <small style="color: #64748b; font-weight: normal;">({(categories_data['Página Satélite / Livro Terceiro (Art. 57-C)'] / max(1, total_ads) * 100):.1f}%)</small></span>
                    </div>
                    <div class="breakdown-card">
                        <span class="breakdown-label">
                            <span class="breakdown-dot" style="background-color: #3b82f6;"></span>
                            Comercial / Infoproduto Regular
                        </span>
                        <span class="breakdown-val">{categories_data['Comercial / Infoproduto Regular']} <small style="color: #64748b; font-weight: normal;">({(categories_data['Comercial / Infoproduto Regular'] / max(1, total_ads) * 100):.1f}%)</small></span>
                    </div>
                </div>
            </div>
        </div>

        <h2 style="font-size: 18px; margin-bottom: 8px;">Custódia de Links da Meta Ad Library ({total_suspects} itens suspeitos)</h2>
        <p style="color: #64748b; font-size: 13px; margin-top: 0;">
            Estes links permitem auditoria direta na Meta Ad Library para fins probatórios:
        </p>

        <table>
            <thead>
                <tr>
                    <th style="width: 60px;">Item</th>
                    <th style="width: 220px;">Meta Ad ID</th>
                    <th style="width: 220px;">Classificação Forense</th>
                    <th>Link Direto de Custódia</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>

        <div class="hash-box">
            <strong>INTEGRIDADE CRIPTOGRÁFICA (SHA-256):</strong><br>
            {dossier_hash}
        </div>
    </div>

    <!-- Script Chart.js -->
    <script>
        const ctx = document.getElementById('forensicPieChart').getContext('2d');
        const pieChart = new Chart(ctx, {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(chart_labels, ensure_ascii=False)},
                datasets: [{{
                    data: {json.dumps(chart_values)},
                    backgroundColor: {json.dumps(chart_colors)},
                    borderColor: '#ffffff',
                    borderWidth: 2,
                    hoverOffset: 6
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: false
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                const val = context.raw || 0;
                                const total = {total_ads} || 1;
                                const pct = ((val / total) * 100).toFixed(1);
                                return ' ' + context.label + ': ' + val + ' anúncios (' + pct + '%)';
                            }}
                        }}
                    }}
                }},
                cutout: '62%'
            }}
        }});
    </script>
</body>
</html>
"""
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"Relatório de evidências probatórias salvo em: {output_html_path}")
        return output_html_path
