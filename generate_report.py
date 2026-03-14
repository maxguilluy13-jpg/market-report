#!/usr/bin/env python3
"""
╔══════════════════════════════════════════╗
║       MARKET REPORT — Générateur        ║
║  Gemini API + yfinance + RSS             ║
╚══════════════════════════════════════════╝
"""

import os, json, re
from datetime import datetime
import pytz
import yfinance as yf
import feedparser
from google import genai

# ── Clé API ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("❌  Variable GEMINI_API_KEY manquante !")
client = genai.Client(api_key=GEMINI_API_KEY)

PARIS_TZ = pytz.timezone("Europe/Paris")

# ── Indices boursiers à suivre ───────────────────────────────────
INDICES = {
    "CAC 40":  {"ticker": "^FCHI",    "devise": "pts"},
    "S&P 500": {"ticker": "^GSPC",    "devise": "pts"},
    "Nasdaq":  {"ticker": "^IXIC",    "devise": "pts"},
    "DAX":     {"ticker": "^GDAXI",   "devise": "pts"},
    "EUR/USD": {"ticker": "EURUSD=X", "devise": ""},
    "VIX":     {"ticker": "^VIX",     "devise": ""},
}

# ── Flux RSS d'actualités économiques ───────────────────────────
RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.lesechos.fr/rss/rss_une.xml",
    "https://www.bfmtv.com/rss/economie/",
    "https://www.lefigaro.fr/rss/figaro_economie.xml",
]

# ════════════════════════════════════════════════════════════════
# 1. DONNÉES DE MARCHÉ
# ════════════════════════════════════════════════════════════════
def fetch_market_data():
    """Récupère les cours et variations via yfinance."""
    print("📈  Récupération des cours...")
    data = {}
    for name, cfg in INDICES.items():
        try:
            t = yf.Ticker(cfg["ticker"])
            hist = t.history(period="7d")
            if len(hist) >= 2:
                current  = float(hist["Close"].iloc[-1])
                prev     = float(hist["Close"].iloc[-2])
                change   = ((current - prev) / prev) * 100
                history  = [float(x) for x in hist["Close"].tolist()[-5:]]
                data[name] = {
                    "price":   current,
                    "change":  change,
                    "history": history,
                    "devise":  cfg["devise"],
                }
                print(f"   ✓ {name}: {current:.2f} ({change:+.2f}%)")
        except Exception as e:
            print(f"   ⚠️  Erreur {name}: {e}")
    return data

# ════════════════════════════════════════════════════════════════
# 2. ACTUALITÉS (RSS)
# ════════════════════════════════════════════════════════════════
def fetch_news():
    """Récupère les dernières actualités via flux RSS."""
    print("📰  Récupération des actualités RSS...")
    articles = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                title = entry.get("title", "").strip()
                link  = entry.get("link", "").strip()
                if title and link:
                    articles.append({"title": title, "link": link})
            print(f"   ✓ {len(feed.entries)} articles depuis {url.split('/')[2]}")
        except Exception as e:
            print(f"   ⚠️  Erreur RSS {url}: {e}")
    return articles[:20]

# ════════════════════════════════════════════════════════════════
# 3. ANALYSE GEMINI
# ════════════════════════════════════════════════════════════════
def generate_analysis(market_data, news_articles):
    """Utilise Gemini pour analyser et rédiger le rapport."""
    print("🤖  Génération de l'analyse via Gemini...")
    

    now      = datetime.now(PARIS_TZ)
    date_str = now.strftime("%A %d %B %Y à %H:%M")

    market_str = "\n".join(
        f"- {name}: {d['price']:.2f} ({d['change']:+.2f}%)"
        for name, d in market_data.items()
    )
    news_str = "\n".join(
        f"- {a['title']} | {a['link']}"
        for a in news_articles
    )

    prompt = f"""Tu es un analyste financier senior francophone. Nous sommes le {date_str}.

DONNÉES DE MARCHÉ EN TEMPS RÉEL:
{market_str}

ACTUALITÉS DISPONIBLES:
{news_str}

Génère un rapport JSON. Réponds UNIQUEMENT avec du JSON valide, sans balise markdown, sans texte autour.

{{
  "news": [
    {{
      "titre": "Titre reformulé en français clair",
      "url": "URL originale exacte de l'article",
      "impact": "haussier|baissier|neutre",
      "raison": "Une phrase expliquant l'impact sur les marchés"
    }}
  ],
  "analyse": "Analyse globale en 3-4 phrases sur la situation des marchés aujourd'hui, intégrant les actualités et les mouvements de cours.",
  "recommandation": "Recommandation prudente et nuancée en 3-4 phrases pour un investisseur particulier. Toujours terminer par un rappel que ce n'est pas un conseil financier officiel.",
  "concept": {{
    "titre": "Un concept économique ou financier pertinent par rapport à l'actualité du jour",
    "definition": "Explication simple et claire en 3-4 phrases, accessible à quelqu'un qui débute en finance."
  }}
}}

Sélectionne 6 à 8 actualités parmi celles fournies. Utilise UNIQUEMENT les URLs fournies, ne les invente pas."""

    response = client.models.generate_content(model="gemini-2.0-flash-lite", contents=prompt)
    text = response.text.strip()

    # Nettoyer les balises markdown si présentes
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*",     "", text)
    text = re.sub(r"\s*```$",     "", text)

    return json.loads(text.strip())

# ════════════════════════════════════════════════════════════════
# 4. GÉNÉRATION HTML
# ════════════════════════════════════════════════════════════════
def sparkline_svg(values):
    """Génère un mini graphique SVG sparkline."""
    if not values or len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn or 1
    w, h = 80, 30
    pts = []
    for i, v in enumerate(values):
        x = i / (len(values) - 1) * w
        y = h - ((v - mn) / rng) * h
        pts.append(f"{x:.1f},{y:.1f}")
    color = "#22c55e" if values[-1] >= values[0] else "#ef4444"
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg"><polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

def generate_html(market_data, analysis, now):
    """Génère le fichier HTML complet du rapport."""

    date_fr   = now.strftime("%A %d %B %Y")
    heure_fr  = now.strftime("%H:%M")
    period    = "Rapport du matin" if now.hour < 13 else "Rapport du soir"

    # ── Section indices ──────────────────────────────────────────
    indices_html = ""
    for name, d in market_data.items():
        sign    = "+" if d["change"] >= 0 else ""
        color   = "#22c55e" if d["change"] >= 0 else "#ef4444"
        arrow   = "▲" if d["change"] >= 0 else "▼"
        sparkle = sparkline_svg(d["history"])
        price_fmt = f"{d['price']:.4f}" if d["devise"] == "" and d["price"] < 10 else f"{d['price']:,.2f}"
        indices_html += f"""
        <div class="index-card">
          <div class="index-left">
            <span class="index-name">{name}</span>
            <span class="index-price">{price_fmt} <small>{d["devise"]}</small></span>
          </div>
          <div class="index-mid">{sparkle}</div>
          <div class="index-right" style="color:{color}">
            {arrow} {sign}{d["change"]:.2f}%
          </div>
        </div>"""

    # ── Section news ─────────────────────────────────────────────
    impact_colors = {
        "haussier": ("#dcfce7", "#166534", "↑"),
        "baissier": ("#fee2e2", "#991b1b", "↓"),
        "neutre":   ("#f1f5f9", "#475569", "→"),
    }
    news_html = ""
    for item in analysis.get("news", []):
        impact = item.get("impact", "neutre")
        bg, fg, arrow = impact_colors.get(impact, impact_colors["neutre"])
        news_html += f"""
        <div class="news-item">
          <span class="impact-badge" style="background:{bg};color:{fg}">{arrow} {impact}</span>
          <a href="{item['url']}" target="_blank" rel="noopener">{item['titre']}</a>
          <span class="news-raison">{item.get('raison','')}</span>
        </div>"""

    # ── HTML complet ─────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Report — {date_fr}</title>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #f1f5f9; --muted: #94a3b8; --accent: #38bdf8;
    --green: #22c55e; --red: #ef4444; --border: #334155;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); min-height: 100vh; }}
  .container {{ max-width: 860px; margin: 0 auto; padding: 2rem 1rem; }}

  /* Header */
  header {{ margin-bottom: 2.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }}
  .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem; }}
  .report-title {{ font-size: 1.75rem; font-weight: 700; color: var(--accent); }}
  .report-date {{ font-size: 0.85rem; color: var(--muted); text-align: right; }}
  .period-badge {{ display: inline-block; background: var(--accent); color: #0f172a;
                  font-size: 0.75rem; font-weight: 600; padding: 3px 10px;
                  border-radius: 20px; margin-top: 0.5rem; }}

  /* Sections */
  .section {{ margin-bottom: 2.5rem; }}
  .section-title {{ font-size: 0.7rem; font-weight: 700; letter-spacing: 0.12em;
                   text-transform: uppercase; color: var(--accent);
                   margin-bottom: 1rem; padding-bottom: 0.4rem;
                   border-bottom: 1px solid var(--border); }}

  /* Indices */
  .indices-grid {{ display: flex; flex-direction: column; gap: 0.5rem; }}
  .index-card {{ display: flex; align-items: center; justify-content: space-between;
                background: var(--surface); border: 1px solid var(--border);
                border-radius: 10px; padding: 0.85rem 1.1rem; }}
  .index-left {{ flex: 1; }}
  .index-name {{ display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 2px; }}
  .index-price {{ font-size: 1.1rem; font-weight: 600; }}
  .index-price small {{ font-size: 0.75rem; color: var(--muted); }}
  .index-mid {{ flex: 0 0 90px; text-align: center; }}
  .index-right {{ font-size: 1rem; font-weight: 700; min-width: 80px; text-align: right; }}

  /* News */
  .news-item {{ background: var(--surface); border: 1px solid var(--border);
               border-radius: 10px; padding: 0.85rem 1.1rem; margin-bottom: 0.5rem; }}
  .news-item a {{ color: var(--text); text-decoration: none; font-size: 0.93rem;
                 font-weight: 500; display: block; margin: 0.3rem 0; }}
  .news-item a:hover {{ color: var(--accent); }}
  .impact-badge {{ font-size: 0.68rem; font-weight: 700; padding: 2px 8px;
                  border-radius: 20px; text-transform: uppercase; }}
  .news-raison {{ display: block; font-size: 0.78rem; color: var(--muted); margin-top: 0.3rem; }}

  /* Blocs texte */
  .text-block {{ background: var(--surface); border: 1px solid var(--border);
                border-radius: 10px; padding: 1.2rem 1.4rem;
                font-size: 0.93rem; line-height: 1.75; color: #cbd5e1; }}
  .recommandation {{ border-left: 3px solid var(--accent); }}

  /* Concept */
  .concept-titre {{ font-size: 1.05rem; font-weight: 700; color: var(--accent); margin-bottom: 0.6rem; }}

  /* Footer */
  footer {{ margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border);
           text-align: center; font-size: 0.75rem; color: var(--muted); }}

  @media (max-width: 480px) {{
    .report-title {{ font-size: 1.3rem; }}
    .index-mid {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="container">

  <header>
    <div class="header-top">
      <div>
        <div class="report-title">📊 Market Report</div>
        <div class="period-badge">{period}</div>
      </div>
      <div class="report-date">
        {date_fr}<br>
        Mis à jour à {heure_fr}
      </div>
    </div>
  </header>

  <!-- SECTION 1 : ACTUALITÉS -->
  <div class="section">
    <div class="section-title">01 — Actualités & impact marché</div>
    <div class="news-list">
      {news_html}
    </div>
  </div>

  <!-- SECTION 2 : INDICES -->
  <div class="section">
    <div class="section-title">02 — Indices boursiers</div>
    <div class="indices-grid">
      {indices_html}
    </div>
  </div>

  <!-- SECTION 3 : ANALYSE & RECOMMANDATION -->
  <div class="section">
    <div class="section-title">03 — Analyse & recommandation</div>
    <div class="text-block" style="margin-bottom:0.8rem">
      {analysis.get('analyse', '')}
    </div>
    <div class="text-block recommandation">
      {analysis.get('recommandation', '')}
    </div>
  </div>

  <!-- SECTION 4 : CONCEPT DU JOUR -->
  <div class="section">
    <div class="section-title">04 — Concept du jour</div>
    <div class="text-block">
      <div class="concept-titre">💡 {analysis.get('concept', {{}}).get('titre', '')}</div>
      {analysis.get('concept', {{}}).get('definition', '')}
    </div>
  </div>

  <footer>
    Rapport généré automatiquement · Données à titre informatif uniquement · Pas un conseil en investissement
  </footer>

</div>
</body>
</html>"""

# ════════════════════════════════════════════════════════════════
# 5. MAIN
# ════════════════════════════════════════════════════════════════
def main():
    now = datetime.now(PARIS_TZ)
    print(f"\n🚀  Génération du rapport — {now.strftime('%d/%m/%Y %H:%M')}\n")

    market_data = fetch_market_data()
    news        = fetch_news()
    analysis    = generate_analysis(market_data, news)
    html        = generate_html(market_data, analysis, now)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("\n✅  Rapport généré → docs/index.html")

if __name__ == "__main__":
    main()
