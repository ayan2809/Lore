#!/usr/bin/env python3
"""
FalkorDB Complete Documentation Generator
Extracts all 620 documentation pages from FalkorDB's official documentation
and compiles them into a single, beautiful, offline-ready HTML documentation viewer.
"""

import os
import sys
import re
import json
import time
import urllib.request
import markdown
from pygments.formatters import HtmlFormatter

CACHE_FILE = "/tmp/falkordb_llms_full.txt"
OUTPUT_HTML = "/Volumes/Projects/Graph Hacks/docs/reference/falkordb_documentation.html"

def fetch_documentation():
    if os.path.exists(CACHE_FILE) and os.path.getsize(CACHE_FILE) > 1000000:
        print(f"Loading cached documentation from {CACHE_FILE}...")
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    
    print("Fetching documentation from https://docs.falkordb.com/llms-full.txt ...")
    url = "https://docs.falkordb.com/llms-full.txt"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8")
    
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Downloaded and cached {len(content)} characters.")
    return content

def clean_markdown(text):
    # Escape dangerous HTML script tags inside documentation content
    text = re.sub(r'<\s*script\b', '&lt;script', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/\s*script\b', '&lt;/script', text, flags=re.IGNORECASE)

    # Fix code fences with Mintlify attributes like ```python Python theme={null} -> ```python
    text = re.sub(r'```([a-zA-Z0-9_\-]+)[^\n]*theme=\{null\}', r'```\1', text)
    text = re.sub(r'theme=\{null\}', '', text)
    
    # Accordion components
    text = re.sub(r'<AccordionGroup>', r'<div class="accordion-group">', text)
    text = re.sub(r'</AccordionGroup>', r'</div>', text)
    text = re.sub(r'<Accordion\s+title="([^"]*)">', 
                  r'<details class="doc-accordion"><summary class="accordion-title"><span>\1</span><span class="chevron">▾</span></summary><div class="accordion-body">\n', text)
    text = re.sub(r'</Accordion>', r'\n</div></details>', text)

    # Callouts: Tip, Note, Warning, Info, Check
    callouts = [
        ('Tip', '💡', 'Tip'),
        ('Note', 'ℹ️', 'Note'),
        ('Warning', '⚠️', 'Warning'),
        ('Info', 'ℹ️', 'Info'),
        ('Check', '✅', 'Success')
    ]
    for tag, icon, name in callouts:
        text = re.sub(rf'<{tag}>', rf'<div class="callout callout-{tag.lower()}"><div class="callout-header"><span class="callout-icon">{icon}</span><span class="callout-label">{name}</span></div><div class="callout-body">\n', text)
        text = re.sub(rf'</{tag}>', r'\n</div></div>', text)

    # Cards and CardGroups
    text = re.sub(r'<CardGroup[^>]*>', r'<div class="card-group">', text)
    text = re.sub(r'</CardGroup>', r'</div>', text)
    def card_repl(m):
        attrs = m.group(1)
        title = re.search(r'title="([^"]*)"', attrs)
        href = re.search(r'href="([^"]*)"', attrs)
        icon = re.search(r'icon="([^"]*)"', attrs)
        t_str = title.group(1) if title else 'Documentation'
        h_str = href.group(1) if href else '#'
        if h_str.startswith('/'):
            h_str = '#' + h_str.strip('/').replace('/', '__')
        i_icon = '📄'
        if icon:
            ic = icon.group(1).lower()
            if 'rocket' in ic: i_icon = '🚀'
            elif 'book' in ic: i_icon = '📖'
            elif 'code' in ic: i_icon = '💻'
            elif 'database' in ic: i_icon = '🗄️'
            elif 'server' in ic: i_icon = '🖥️'
            elif 'key' in ic: i_icon = '🔑'
            elif 'shield' in ic: i_icon = '🛡️'
            elif 'cloud' in ic: i_icon = '☁️'
            elif 'sparkle' in ic or 'magic' in ic: i_icon = '✨'
            elif 'gear' in ic or 'setting' in ic: i_icon = '⚙️'
        return f'<a class="doc-card" href="{h_str}"><div class="card-header"><span class="card-icon">{i_icon}</span><span class="card-title">{t_str}</span></div><div class="card-body">\n'
    text = re.sub(r'<Card\s+([^>]*)>', card_repl, text)
    text = re.sub(r'</Card>', r'\n</div></a>', text)

    # Steps lists
    text = re.sub(r'<Steps>', r'<div class="steps-list">', text)
    text = re.sub(r'</Steps>', r'</div>', text)
    text = re.sub(r'<Step\s+title="([^"]*)">', r'<div class="step-item"><div class="step-header"><span class="step-badge"></span><span class="step-title">\1</span></div><div class="step-body">\n', text)
    text = re.sub(r'</Step>', r'\n</div></div>', text)

    # Expandable components
    text = re.sub(r'<Expandable\s+title="([^"]*)">', r'<details class="doc-expandable"><summary class="expandable-title"><span>\1</span><span class="chevron">▾</span></summary><div class="expandable-body">\n', text)
    text = re.sub(r'</Expandable>', r'\n</div></details>', text)

    # ParamField & ResponseField (API Reference items)
    def field_repl(m):
        attrs = m.group(2)
        name = re.search(r'(?:name|path|query|header)="([^"]*)"', attrs)
        ftype = re.search(r'type="([^"]*)"', attrs)
        req = 'required' in attrs.lower()
        n_str = name.group(1) if name else ''
        t_str = f'<span class="badge badge-type">{ftype.group(1)}</span>' if ftype else ''
        r_str = '<span class="badge badge-required">required</span>' if req else '<span class="badge badge-optional">optional</span>'
        return f'<div class="api-field"><div class="api-field-header"><code class="field-name">{n_str}</code> {t_str} {r_str}</div><div class="api-field-body">\n'
    text = re.sub(r'<(ParamField|ResponseField)\s+([^>]*)>', field_repl, text)
    text = re.sub(r'</(ParamField|ResponseField)>', r'\n</div></div>', text)

    # Frames and CodeGroups
    text = re.sub(r'</?Frame>', '', text)
    text = re.sub(r'</?CodeGroup>', '', text)

    # Internal markdown link resolution: [text](/cypher/match) -> [text](#cypher__match)
    def link_repl(m):
        label = m.group(1)
        url = m.group(2)
        if url.startswith('/') and not url.startswith('//'):
            anchor = '#' + url.strip('/').replace('/', '__')
            return f'[{label}]({anchor})'
        return m.group(0)
    text = re.sub(r'\[([^\]]+)\]\((/[^\)]+)\)', link_repl, text)

    return text

def categorize_path(path):
    p = path.lower()
    parts = p.split('/')
    top = parts[0]
    
    if top in ('index', 'support', 'datatypes', 'getting-started'):
        return 'Getting Started & Overview', 'Overview', '🚀', 1
    elif top == 'cypher':
        if len(parts) > 1 and parts[1] == 'cheat-sheet':
            return 'Cypher Query Language', 'Quick Reference', '⚡', 2
        return 'Cypher Query Language', 'Clauses & Syntax', '⚡', 2
    elif top == 'commands':
        return 'Redis Commands Reference', 'Server Commands', '🛠️', 3
    elif top == 'algorithms':
        return 'Graph Algorithms', 'Built-in Graph Algorithms', '📐', 4
    elif top == 'graphrag':
        if 'api-reference' in p:
            return 'GraphRAG SDK', 'API Reference', '🧠', 5
        elif any(k in p for k in ('benchmark', 'accuracy')):
            return 'GraphRAG SDK', 'Benchmarks & Evaluation', '🧠', 5
        return 'GraphRAG SDK', 'Pipeline & Guides', '🧠', 5
    elif top == 'agentic-memory':
        return 'Agentic Memory & Context', 'Agent Frameworks', '🤖', 6
    elif top == 'genai-tools':
        return 'GenAI Frameworks & Tools', 'AI Integrations', '🔮', 7
    elif top == 'udfs':
        sub = parts[2] if len(parts) > 2 and parts[1] == 'flex' else (parts[1] if len(parts) > 1 else 'general')
        return 'User Defined Functions (UDFs)', f'Flex: {sub.title()}', '🧩', 8
    elif top == 'integration':
        return 'Integrations & Ecosystem', 'Connectors & Drivers', '🔌', 9
    elif top == 'operations':
        return 'Operations & Deployment', 'Deployment & Management', '⚙️', 10
    elif top == 'browser':
        return 'FalkorDB Browser & Canvas', 'Visual Explorer', '🖥️', 11
    elif top == 'cloud':
        if 'api-reference' in p:
            sub = parts[2] if len(parts) > 2 else 'api'
            return 'FalkorDB Cloud', f'API: {sub.replace("-", " ").title()}', '☁️', 12
        return 'FalkorDB Cloud', 'Platform & Console', '☁️', 12
    elif top == 'enterprise':
        if 'api-reference' in p:
            sub = parts[2] if len(parts) > 2 else 'api'
            return 'FalkorDB Enterprise', f'API: {sub.replace("-", " ").title()}', '🏢', 13
        return 'FalkorDB Enterprise', 'Platform & Kubernetes', '🏢', 13
    elif top == 'design':
        return 'Internal Architecture & Specs', 'Design Specifications', '📐', 14
    elif top == 'references':
        return 'References & SSPL License', 'References', '📜', 15
    else:
        return 'Additional Resources', 'General', '📚', 16

def extract_toc(html_content):
    """Extract h2 and h3 elements for table of contents."""
    headings = []
    pattern = re.compile(r'<h([23])\s+(?:id="([^"]*)")?[^>]*>(.*?)</h\1>', re.IGNORECASE | re.DOTALL)
    for m in pattern.finditer(html_content):
        level = int(m.group(1))
        hid = m.group(2)
        raw_text = re.sub(r'<[^>]+>', '', m.group(3)).strip()
        if not hid:
            hid = re.sub(r'[^a-zA-Z0-9_\-]+', '-', raw_text.lower()).strip('-')
        headings.append({'level': level, 'id': hid, 'text': raw_text})
    return headings

def main():
    start_time = time.time()
    raw = fetch_documentation()
    
    # Extract agent instructions if present
    agent_instructions_html = ""
    m_inst = re.search(r'> ## Agent Instructions[\s\S]*?(?=\n#[^\n]+\nSource:)', raw)
    if m_inst:
        inst_md = m_inst.group(0).strip()
        md_inst = markdown.Markdown()
        agent_instructions_html = md_inst.convert(inst_md)

    pattern = re.compile(r'(?:^|\n)(#[^\n]+)\nSource:\s*https://docs\.falkordb\.com/([^\n]*)', re.MULTILINE)
    matches = list(pattern.finditer(raw))
    print(f"Found {len(matches)} documentation pages.")

    md = markdown.Markdown(extensions=['fenced_code', 'codehilite', 'tables', 'attr_list', 'toc'])
    
    pages = []
    category_tree = {} # {cat_name: {'icon': icon, 'order': order, 'subs': {sub_name: [page_ids]}}}

    for i in range(len(matches)):
        start = matches[i].end()
        end = matches[i+1].start() if i + 1 < len(matches) else len(raw)
        title = matches[i].group(1).lstrip('#').strip()
        path = matches[i].group(2).strip()
        content = raw[start:end].strip()
        
        cleaned = clean_markdown(content)
        html_content = md.reset().convert(cleaned)
        
        slug = path.strip('/').replace('/', '__') if path else 'index'
        if not slug:
            slug = 'index'
        
        main_cat, sub_cat, icon, order = categorize_path(path)
        
        # Build category tree
        if main_cat not in category_tree:
            category_tree[main_cat] = {'icon': icon, 'order': order, 'subs': {}}
        if sub_cat not in category_tree[main_cat]['subs']:
            category_tree[main_cat]['subs'][sub_cat] = []
        category_tree[main_cat]['subs'][sub_cat].append(slug)

        # Snippet for search
        raw_text = re.sub(r'<[^>]+>', ' ', html_content)
        snippet = ' '.join(raw_text.split()[:45])
        
        headings = extract_toc(html_content)

        pages.append({
            'id': slug,
            'title': title,
            'path': path,
            'url': f'https://docs.falkordb.com/{path}',
            'category': main_cat,
            'subcategory': sub_cat,
            'icon': icon,
            'html': html_content,
            'snippet': snippet,
            'headings': headings
        })

    # Sort categories by order
    sorted_categories = sorted(category_tree.items(), key=lambda x: x[1]['order'])

    # Build search index JSON
    search_index = [
        {
            'id': p['id'],
            'title': p['title'],
            'path': p['path'],
            'category': p['category'],
            'subcategory': p['subcategory'],
            'icon': p['icon'],
            'snippet': p['snippet']
        }
        for p in pages
    ]

    # Pygments CSS
    formatter_dark = HtmlFormatter(style='one-dark')
    pygments_dark_css = formatter_dark.get_style_defs('.dark .codehilite')
    formatter_light = HtmlFormatter(style='friendly')
    pygments_light_css = formatter_light.get_style_defs('.light .codehilite')

    print(f"Parsed {len(pages)} pages. Assembling HTML document...")

    html_out = build_html(
        pages=pages,
        sorted_categories=sorted_categories,
        search_index=search_index,
        pygments_dark_css=pygments_dark_css,
        pygments_light_css=pygments_light_css,
        agent_instructions_html=agent_instructions_html
    )

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_out)

    file_size_mb = os.path.getsize(OUTPUT_HTML) / (1024 * 1024)
    elapsed = time.time() - start_time
    print(f"Done! Successfully generated {OUTPUT_HTML}")
    print(f"File size: {file_size_mb:.2f} MB ({len(pages)} pages)")
    print(f"Total time elapsed: {elapsed:.2f}s")

def build_html(pages, sorted_categories, search_index, pygments_dark_css, pygments_light_css, agent_instructions_html):
    # Lookup map for page index
    page_by_id = {p['id']: p for p in pages}
    id_list = [p['id'] for p in pages]

    # Pre-render sidebar navigation items
    sidebar_html = []
    for cat_name, cat_data in sorted_categories:
        icon = cat_data['icon']
        subs = cat_data['subs']
        cat_total_pages = sum(len(ids) for ids in subs.values())
        
        sidebar_html.append(f'''
        <div class="nav-category" data-category="{cat_name}">
          <div class="category-header" onclick="toggleCategory(this)">
            <span class="cat-icon">{icon}</span>
            <span class="cat-title">{cat_name}</span>
            <span class="cat-badge">{cat_total_pages}</span>
            <span class="cat-chevron">▾</span>
          </div>
          <div class="category-content">
        ''')
        
        for sub_name, p_ids in subs.items():
            if len(subs) > 1:
                sidebar_html.append(f'<div class="sub-category-title">{sub_name}</div>')
            sidebar_html.append('<ul class="nav-page-list">')
            for pid in p_ids:
                page = page_by_id[pid]
                sidebar_html.append(f'''
                <li class="nav-page-item" id="nav-item-{pid}" data-id="{pid}" onclick="navigateToPage('{pid}')">
                  <a href="#{pid}" class="nav-page-link" onclick="event.preventDefault(); navigateToPage('{pid}');">
                    <span class="nav-bullet"></span>
                    <span class="nav-title-text">{page['title']}</span>
                  </a>
                </li>
                ''')
            sidebar_html.append('</ul>')
            
        sidebar_html.append('</div></div>')

    # Pre-render articles
    articles_html = []
    for idx, p in enumerate(pages):
        prev_id = id_list[idx - 1] if idx > 0 else None
        next_id = id_list[idx + 1] if idx < len(id_list) - 1 else None
        
        prev_page = page_by_id[prev_id] if prev_id else None
        next_page = page_by_id[next_id] if next_id else None

        # Build footer nav
        footer_nav = ['<div class="doc-footer-nav">']
        if prev_page:
            footer_nav.append(f'''
            <a class="footer-nav-btn prev" href="#{prev_page['id']}" onclick="event.preventDefault(); navigateToPage('{prev_page['id']}');">
              <span class="nav-direction">← Previous</span>
              <span class="nav-target-title">{prev_page['title']}</span>
            </a>
            ''')
        else:
            footer_nav.append('<div></div>')
            
        if next_page:
            footer_nav.append(f'''
            <a class="footer-nav-btn next" href="#{next_page['id']}" onclick="event.preventDefault(); navigateToPage('{next_page['id']}');">
              <span class="nav-direction">Next →</span>
              <span class="nav-target-title">{next_page['title']}</span>
            </a>
            ''')
        else:
            footer_nav.append('<div></div>')
        footer_nav.append('</div>')

        # Breadcrumbs
        breadcrumbs = f'''
        <nav class="doc-breadcrumbs">
          <span class="crumb" onclick="navigateToPage('index')">Docs</span>
          <span class="crumb-separator">/</span>
          <span class="crumb">{p['category']}</span>
          <span class="crumb-separator">/</span>
          <span class="crumb active">{p['subcategory']}</span>
        </nav>
        '''

        # Source badge
        source_badge = f'''
        <div class="doc-meta-bar">
          <span class="doc-category-badge">{p['icon']} {p['category']}</span>
          <a class="doc-source-link" href="{p['url']}" target="_blank" rel="noopener noreferrer">
            <span>Source: {p['url']}</span>
            <svg class="external-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
          </a>
        </div>
        '''

        # Special banner for index page
        special_banner = ""
        if p['id'] == 'index' and agent_instructions_html:
            special_banner = f'''
            <div class="agent-rules-banner">
              <div class="banner-badge">⚡ OFFICIAL AGENT INSTRUCTIONS</div>
              <div class="banner-body">{agent_instructions_html}</div>
            </div>
            '''

        articles_html.append(f'''
        <article id="doc-{p['id']}" class="doc-article" data-id="{p['id']}" data-title="{p['title']}" data-category="{p['category']}">
          {breadcrumbs}
          <div class="doc-header">
            <h1 class="doc-main-title">{p['title']}</h1>
            {source_badge}
          </div>
          {special_banner}
          <div class="doc-body markdown-body">
            {p['html']}
          </div>
          {"".join(footer_nav)}
        </article>
        ''')

    search_json_str = json.dumps(search_index)

    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FalkorDB Complete Documentation — Offline Edition</title>
  <meta name="description" content="Complete FalkorDB documentation containing all 620 pages including Cypher, GraphRAG SDK, Commands, Agentic Memory, Algorithms, Cloud, and Enterprise references.">
  <style>
    /* =====================================================================
       CSS DESIGN TOKENS & RESET
       ===================================================================== */
    :root {{
      --primary: #FF8101;
      --primary-hover: #E07200;
      --primary-light: #FF9E3B;
      --primary-glow: rgba(255, 129, 1, 0.2);
      
      --accent-cyan: #06B6D4;
      --accent-purple: #8B5CF6;
      --accent-emerald: #10B981;
      --accent-amber: #F59E0B;
      --accent-rose: #F43F5E;
      
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 14px;
      --radius-full: 9999px;
      
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      --font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
      
      --sidebar-width: 320px;
      --toc-width: 260px;
      --header-height: 64px;
      --transition-speed: 0.18s;
    }}

    /* Dark Mode Theme */
    html.dark {{
      --bg-page: #0B0F19;
      --bg-surface: #111827;
      --bg-surface-elevated: #1F2937;
      --bg-surface-hover: #263346;
      --bg-code: #0D121F;
      
      --border-subtle: #1E293B;
      --border-muted: #334155;
      --border-focus: #FF8101;
      
      --text-heading: #F9FAFB;
      --text-body: #D1D5DB;
      --text-muted: #94A3B8;
      --text-dim: #64748B;
      
      --code-bg: #0F172A;
      --code-border: #1E293B;
      --code-text: #E2E8F0;
      
      --scrollbar-thumb: #334155;
      --scrollbar-track: #0B0F19;
      --kbd-bg: #1F2937;
      --kbd-border: #374151;
    }}

    /* Light Mode Theme */
    html.light {{
      --bg-page: #F8FAFC;
      --bg-surface: #FFFFFF;
      --bg-surface-elevated: #F1F5F9;
      --bg-surface-hover: #E2E8F0;
      --bg-code: #F1F5F9;
      
      --border-subtle: #E2E8F0;
      --border-muted: #CBD5E1;
      --border-focus: #FF8101;
      
      --text-heading: #0F172A;
      --text-body: #334155;
      --text-muted: #64748B;
      --text-dim: #94A3B8;
      
      --code-bg: #F8FAFC;
      --code-border: #E2E8F0;
      --code-text: #1E293B;
      
      --scrollbar-thumb: #CBD5E1;
      --scrollbar-track: #F8FAFC;
      --kbd-bg: #E2E8F0;
      --kbd-border: #CBD5E1;
    }}

    /* Global Reset & Base */
    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    html {{
      font-size: 15px;
      scroll-behavior: smooth;
    }}

    body {{
      font-family: var(--font-sans);
      background-color: var(--bg-page);
      color: var(--text-body);
      line-height: 1.65;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      overflow-x: hidden;
    }}

    /* Custom Scrollbar */
    ::-webkit-scrollbar {{
      width: 7px;
      height: 7px;
    }}
    ::-webkit-scrollbar-track {{
      background: var(--scrollbar-track);
    }}
    ::-webkit-scrollbar-thumb {{
      background: var(--scrollbar-thumb);
      border-radius: var(--radius-full);
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: var(--text-dim);
    }}

    /* =====================================================================
       HEADER NAVIGATION BAR
       ===================================================================== */
    .app-header {{
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      height: var(--header-height);
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 1.5rem;
      z-index: 100;
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }}

    .header-left {{
      display: flex;
      align-items: center;
      gap: 1.25rem;
    }}

    .brand-link {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      text-decoration: none;
      color: var(--text-heading);
      font-weight: 700;
      font-size: 1.15rem;
    }}

    .brand-logo-icon {{
      width: 32px;
      height: 32px;
      background: linear-gradient(135deg, #FF8101, #FF5500);
      border-radius: var(--radius-sm);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 2px 8px var(--primary-glow);
      color: #FFF;
      font-weight: 900;
      font-size: 1.1rem;
    }}

    .brand-badge {{
      background: rgba(255, 129, 1, 0.12);
      color: var(--primary);
      border: 1px solid rgba(255, 129, 1, 0.3);
      padding: 0.15rem 0.5rem;
      border-radius: var(--radius-full);
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .header-center {{
      flex: 1;
      max-width: 520px;
      margin: 0 1.5rem;
    }}

    .search-trigger-btn {{
      width: 100%;
      height: 38px;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 0 0.85rem;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      font-size: 0.88rem;
      transition: all var(--transition-speed);
    }}
    .search-trigger-btn:hover {{
      border-color: var(--border-muted);
      background: var(--bg-surface-hover);
      color: var(--text-heading);
    }}
    .search-trigger-content {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }}
    .kbd-shortcut {{
      background: var(--kbd-bg);
      border: 1px solid var(--kbd-border);
      color: var(--text-muted);
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      font-size: 0.75rem;
      font-family: var(--font-mono);
      font-weight: 600;
    }}

    .header-right {{
      display: flex;
      align-items: center;
      gap: 0.85rem;
    }}

    .view-mode-toggle {{
      display: flex;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 2px;
    }}
    .view-mode-btn {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 0.35rem 0.75rem;
      border-radius: var(--radius-sm);
      font-size: 0.82rem;
      font-weight: 500;
      cursor: pointer;
      transition: all var(--transition-speed);
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }}
    .view-mode-btn.active {{
      background: var(--primary);
      color: #FFF;
      font-weight: 600;
      box-shadow: 0 1px 4px rgba(0,0,0,0.2);
    }}

    .icon-btn {{
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      width: 38px;
      height: 38px;
      border-radius: var(--radius-md);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all var(--transition-speed);
    }}
    .icon-btn:hover {{
      color: var(--text-heading);
      border-color: var(--border-muted);
      background: var(--bg-surface-hover);
    }}

    .sidebar-toggle-btn {{
      display: none;
    }}

    /* =====================================================================
       LAYOUT CONTAINER
       ===================================================================== */
    .app-layout {{
      display: flex;
      margin-top: var(--header-height);
      min-height: calc(100vh - var(--header-height));
    }}

    /* =====================================================================
       LEFT SIDEBAR NAVIGATION
       ===================================================================== */
    .sidebar {{
      width: var(--sidebar-width);
      flex-shrink: 0;
      background: var(--bg-surface);
      border-right: 1px solid var(--border-subtle);
      height: calc(100vh - var(--header-height));
      position: sticky;
      top: var(--header-height);
      display: flex;
      flex-direction: column;
      overflow-y: hidden;
      z-index: 50;
    }}

    .sidebar-filter-wrapper {{
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border-subtle);
      background: var(--bg-surface);
    }}
    .sidebar-filter-input {{
      width: 100%;
      height: 34px;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 0 0.75rem;
      color: var(--text-heading);
      font-size: 0.82rem;
      outline: none;
      transition: border-color var(--transition-speed);
    }}
    .sidebar-filter-input:focus {{
      border-color: var(--primary);
    }}

    .sidebar-scroll-area {{
      flex: 1;
      overflow-y: auto;
      padding: 0.75rem 0.65rem 3rem 0.65rem;
    }}

    .nav-category {{
      margin-bottom: 0.5rem;
    }}

    .category-header {{
      display: flex;
      align-items: center;
      padding: 0.55rem 0.65rem;
      border-radius: var(--radius-sm);
      cursor: pointer;
      user-select: none;
      transition: background var(--transition-speed);
      gap: 0.5rem;
    }}
    .category-header:hover {{
      background: var(--bg-surface-hover);
    }}
    .cat-icon {{
      font-size: 1.05rem;
    }}
    .cat-title {{
      flex: 1;
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-heading);
    }}
    .cat-badge {{
      font-size: 0.72rem;
      color: var(--text-muted);
      background: var(--bg-surface-elevated);
      padding: 0.1rem 0.45rem;
      border-radius: var(--radius-full);
      font-weight: 600;
    }}
    .cat-chevron {{
      font-size: 0.75rem;
      color: var(--text-dim);
      transition: transform var(--transition-speed);
    }}
    .nav-category.collapsed .cat-chevron {{
      transform: rotate(-90deg);
    }}
    .nav-category.collapsed .category-content {{
      display: none;
    }}

    .sub-category-title {{
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-dim);
      padding: 0.5rem 0.65rem 0.25rem 1.6rem;
    }}

    .nav-page-list {{
      list-style: none;
      margin-left: 0.5rem;
      border-left: 1px solid var(--border-subtle);
      padding-left: 0.5rem;
    }}

    .nav-page-item {{
      margin: 1px 0;
    }}

    .nav-page-link {{
      display: flex;
      align-items: center;
      padding: 0.35rem 0.6rem;
      border-radius: var(--radius-sm);
      text-decoration: none;
      color: var(--text-muted);
      font-size: 0.82rem;
      transition: all var(--transition-speed);
      gap: 0.5rem;
      line-height: 1.35;
    }}
    .nav-page-link:hover {{
      color: var(--text-heading);
      background: var(--bg-surface-hover);
    }}

    .nav-bullet {{
      width: 5px;
      height: 5px;
      border-radius: var(--radius-full);
      background: var(--text-dim);
      flex-shrink: 0;
      transition: transform var(--transition-speed), background var(--transition-speed);
    }}

    .nav-page-item.active .nav-page-link {{
      background: rgba(255, 129, 1, 0.12);
      color: var(--primary);
      font-weight: 600;
    }}
    .nav-page-item.active .nav-bullet {{
      background: var(--primary);
      transform: scale(1.5);
    }}

    /* =====================================================================
       MAIN DOCUMENT CONTENT AREA
       ===================================================================== */
    .main-content {{
      flex: 1;
      min-width: 0;
      padding: 2rem 2.5rem 6rem 2.5rem;
      max-width: 960px;
    }}

    /* Reader View vs Continuous View */
    .mode-reader .doc-article {{
      display: none;
    }}
    .mode-reader .doc-article.active {{
      display: block;
      animation: fadeIn 0.15s ease-out;
    }}

    .mode-all .doc-article {{
      display: block;
      margin-bottom: 5rem;
      padding-bottom: 4rem;
      border-bottom: 2px dashed var(--border-subtle);
    }}

    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(4px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}

    /* Breadcrumbs */
    .doc-breadcrumbs {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-bottom: 0.85rem;
    }}
    .crumb {{
      cursor: pointer;
      transition: color var(--transition-speed);
    }}
    .crumb:hover {{
      color: var(--primary);
    }}
    .crumb.active {{
      color: var(--text-heading);
      font-weight: 500;
      cursor: default;
    }}
    .crumb-separator {{
      color: var(--text-dim);
    }}

    /* Header & Meta */
    .doc-header {{
      margin-bottom: 1.75rem;
    }}
    .doc-main-title {{
      font-size: 2.25rem;
      font-weight: 800;
      color: var(--text-heading);
      line-height: 1.25;
      letter-spacing: -0.025em;
      margin-bottom: 0.85rem;
    }}

    .doc-meta-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 0.75rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border-subtle);
    }}

    .doc-category-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: var(--bg-surface-elevated);
      color: var(--text-heading);
      border: 1px solid var(--border-subtle);
      padding: 0.2rem 0.65rem;
      border-radius: var(--radius-full);
      font-size: 0.78rem;
      font-weight: 600;
    }}

    .doc-source-link {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.78rem;
      color: var(--text-muted);
      text-decoration: none;
      transition: color var(--transition-speed);
    }}
    .doc-source-link:hover {{
      color: var(--primary);
      text-decoration: underline;
    }}

    /* Special Agent Instructions Banner */
    .agent-rules-banner {{
      background: linear-gradient(135deg, rgba(255, 129, 1, 0.08), rgba(139, 92, 246, 0.08));
      border: 1px solid rgba(255, 129, 1, 0.3);
      border-radius: var(--radius-md);
      padding: 1.25rem 1.5rem;
      margin-bottom: 2rem;
    }}
    .banner-badge {{
      display: inline-block;
      background: var(--primary);
      color: #FFF;
      font-size: 0.72rem;
      font-weight: 800;
      padding: 0.2rem 0.6rem;
      border-radius: var(--radius-sm);
      letter-spacing: 0.05em;
      margin-bottom: 0.75rem;
    }}
    .banner-body blockquote {{
      border-left: 3px solid var(--primary);
      padding-left: 1rem;
      font-style: normal;
      color: var(--text-heading);
      font-size: 0.92rem;
      line-height: 1.6;
    }}

    /* =====================================================================
       MARKDOWN BODY STYLES
       ===================================================================== */
    .markdown-body {{
      font-size: 1rem;
      color: var(--text-body);
      line-height: 1.75;
    }}

    .markdown-body h1,
    .markdown-body h2,
    .markdown-body h3,
    .markdown-body h4 {{
      color: var(--text-heading);
      font-weight: 700;
      margin-top: 2rem;
      margin-bottom: 0.85rem;
      line-height: 1.35;
      scroll-margin-top: 80px;
    }}
    .markdown-body h1 {{ font-size: 1.85rem; }}
    .markdown-body h2 {{ font-size: 1.45rem; border-bottom: 1px solid var(--border-subtle); padding-bottom: 0.4rem; }}
    .markdown-body h3 {{ font-size: 1.2rem; }}
    .markdown-body h4 {{ font-size: 1.05rem; }}

    .markdown-body p {{
      margin-bottom: 1.25rem;
    }}

    .markdown-body a {{
      color: var(--primary);
      text-decoration: none;
      font-weight: 500;
      transition: color var(--transition-speed);
    }}
    .markdown-body a:hover {{
      color: var(--primary-light);
      text-decoration: underline;
    }}

    .markdown-body ul,
    .markdown-body ol {{
      margin-bottom: 1.25rem;
      padding-left: 1.75rem;
    }}
    .markdown-body li {{
      margin-bottom: 0.4rem;
    }}

    .markdown-body blockquote {{
      border-left: 4px solid var(--primary);
      padding: 0.6rem 1.2rem;
      background: var(--bg-surface-elevated);
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      color: var(--text-heading);
      margin-bottom: 1.25rem;
    }}

    .markdown-body hr {{
      border: 0;
      height: 1px;
      background: var(--border-subtle);
      margin: 2rem 0;
    }}

    .markdown-body img {{
      max-width: 100%;
      height: auto;
      border-radius: var(--radius-md);
      margin: 1.25rem 0;
      border: 1px solid var(--border-subtle);
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }}

    /* Markdown Tables */
    .markdown-body table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      margin: 1.5rem 0;
      border-radius: var(--radius-md);
      overflow: hidden;
      border: 1px solid var(--border-subtle);
      background: var(--bg-surface);
    }}
    .markdown-body th,
    .markdown-body td {{
      padding: 0.75rem 1rem;
      text-align: left;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .markdown-body th {{
      background: var(--bg-surface-elevated);
      color: var(--text-heading);
      font-weight: 600;
      font-size: 0.88rem;
    }}
    .markdown-body tr:last-child td {{
      border-bottom: none;
    }}
    .markdown-body tr:nth-child(even) td {{
      background: rgba(255, 255, 255, 0.015);
    }}

    /* Inline Code */
    .markdown-body :not(pre) > code {{
      font-family: var(--font-mono);
      font-size: 0.88em;
      background: var(--bg-surface-elevated);
      color: var(--primary);
      padding: 0.15rem 0.4rem;
      border-radius: 4px;
      border: 1px solid var(--border-subtle);
    }}

    /* Code Blocks */
    .code-block-wrapper {{
      position: relative;
      margin: 1.5rem 0;
      border-radius: var(--radius-md);
      overflow: hidden;
      border: 1px solid var(--code-border);
      background: var(--code-bg);
      box-shadow: 0 4px 14px rgba(0,0,0,0.15);
    }}
    .code-block-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--bg-surface-elevated);
      padding: 0.45rem 1rem;
      border-bottom: 1px solid var(--code-border);
      font-size: 0.75rem;
      font-family: var(--font-mono);
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .copy-code-btn {{
      background: transparent;
      border: 1px solid var(--border-muted);
      color: var(--text-muted);
      border-radius: var(--radius-sm);
      padding: 0.2rem 0.55rem;
      font-size: 0.75rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.35rem;
      transition: all var(--transition-speed);
    }}
    .copy-code-btn:hover {{
      color: var(--text-heading);
      border-color: var(--primary);
      background: var(--bg-surface-hover);
    }}
    .copy-code-btn.copied {{
      background: var(--accent-emerald);
      color: #FFF;
      border-color: var(--accent-emerald);
    }}

    .codehilite {{
      background: var(--code-bg);
      padding: 1rem 1.25rem;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 0.88rem;
      line-height: 1.6;
    }}
    .codehilite pre {{
      margin: 0;
      white-space: pre;
    }}

    /* =====================================================================
       CUSTOM MINTLIFY COMPONENTS
       ===================================================================== */
    /* Callouts */
    .callout {{
      border-radius: var(--radius-md);
      padding: 1rem 1.25rem;
      margin: 1.5rem 0;
      border-left: 4px solid;
    }}
    .callout-header {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-weight: 700;
      font-size: 0.95rem;
      margin-bottom: 0.5rem;
    }}
    .callout-body p:last-child {{
      margin-bottom: 0;
    }}

    .callout-tip {{
      background: rgba(16, 185, 129, 0.08);
      border-color: var(--accent-emerald);
      color: var(--text-body);
    }}
    .callout-tip .callout-header {{ color: var(--accent-emerald); }}

    .callout-note {{
      background: rgba(6, 182, 212, 0.08);
      border-color: var(--accent-cyan);
      color: var(--text-body);
    }}
    .callout-note .callout-header {{ color: var(--accent-cyan); }}

    .callout-warning {{
      background: rgba(245, 158, 11, 0.08);
      border-color: var(--accent-amber);
      color: var(--text-body);
    }}
    .callout-warning .callout-header {{ color: var(--accent-amber); }}

    .callout-info {{
      background: rgba(139, 92, 246, 0.08);
      border-color: var(--accent-purple);
      color: var(--text-body);
    }}
    .callout-info .callout-header {{ color: var(--accent-purple); }}

    .callout-check {{
      background: rgba(16, 185, 129, 0.08);
      border-color: var(--accent-emerald);
      color: var(--text-body);
    }}
    .callout-check .callout-header {{ color: var(--accent-emerald); }}

    /* Accordions */
    .accordion-group {{
      margin: 1.25rem 0;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }}
    .doc-accordion,
    .doc-expandable {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      overflow: hidden;
    }}
    .accordion-title,
    .expandable-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.85rem 1.25rem;
      cursor: pointer;
      font-weight: 600;
      color: var(--text-heading);
      background: var(--bg-surface-elevated);
      user-select: none;
      list-style: none;
    }}
    .accordion-title::-webkit-details-marker,
    .expandable-title::-webkit-details-marker {{
      display: none;
    }}
    .accordion-title:hover,
    .expandable-title:hover {{
      background: var(--bg-surface-hover);
    }}
    .accordion-body,
    .expandable-body {{
      padding: 1.25rem;
      border-top: 1px solid var(--border-subtle);
    }}

    /* Card Groups */
    .card-group {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1rem;
      margin: 1.5rem 0;
    }}
    .doc-card {{
      display: block;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 1.25rem;
      text-decoration: none;
      color: var(--text-body);
      transition: all var(--transition-speed);
      box-shadow: 0 2px 6px rgba(0,0,0,0.05);
    }}
    .doc-card:hover {{
      border-color: var(--primary);
      transform: translateY(-2px);
      box-shadow: 0 6px 16px var(--primary-glow);
    }}
    .card-header {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      margin-bottom: 0.5rem;
    }}
    .card-icon {{
      font-size: 1.25rem;
    }}
    .card-title {{
      font-weight: 700;
      color: var(--text-heading);
      font-size: 1rem;
    }}
    .card-body {{
      font-size: 0.88rem;
      color: var(--text-muted);
      line-height: 1.5;
    }}

    /* Steps */
    .steps-list {{
      margin: 1.5rem 0;
      counter-reset: step-counter;
      border-left: 2px solid var(--border-subtle);
      padding-left: 1.5rem;
      margin-left: 0.75rem;
    }}
    .step-item {{
      position: relative;
      margin-bottom: 1.75rem;
      counter-increment: step-counter;
    }}
    .step-item::before {{
      content: counter(step-counter);
      position: absolute;
      left: calc(-1.5rem - 13px);
      top: 0;
      width: 24px;
      height: 24px;
      border-radius: var(--radius-full);
      background: var(--primary);
      color: #FFF;
      font-size: 0.75rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 2px 6px var(--primary-glow);
    }}
    .step-title {{
      font-weight: 700;
      color: var(--text-heading);
      font-size: 1.05rem;
      margin-bottom: 0.5rem;
    }}

    /* API Fields (ParamField & ResponseField) */
    .api-field {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      margin: 1rem 0;
      overflow: hidden;
    }}
    .api-field-header {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      padding: 0.6rem 1rem;
      background: var(--bg-surface-elevated);
      border-bottom: 1px solid var(--border-subtle);
      font-size: 0.85rem;
    }}
    .field-name {{
      font-family: var(--font-mono);
      font-weight: 700;
      color: var(--text-heading);
    }}
    .badge {{
      font-size: 0.72rem;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      font-weight: 600;
    }}
    .badge-type {{
      background: rgba(6, 182, 212, 0.15);
      color: var(--accent-cyan);
      font-family: var(--font-mono);
    }}
    .badge-required {{
      background: rgba(244, 63, 94, 0.15);
      color: var(--accent-rose);
    }}
    .badge-optional {{
      background: rgba(148, 163, 184, 0.15);
      color: var(--text-dim);
    }}
    .api-field-body {{
      padding: 0.85rem 1rem;
      font-size: 0.88rem;
    }}

    /* Footer Prev/Next Navigation */
    .doc-footer-nav {{
      display: flex;
      align-items: stretch;
      justify-content: space-between;
      gap: 1.5rem;
      margin-top: 4rem;
      padding-top: 2rem;
      border-top: 1px solid var(--border-subtle);
    }}
    .footer-nav-btn {{
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 1rem 1.25rem;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      text-decoration: none;
      transition: all var(--transition-speed);
      gap: 0.35rem;
    }}
    .footer-nav-btn:hover {{
      border-color: var(--primary);
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }}
    .footer-nav-btn.next {{
      text-align: right;
      align-items: flex-end;
    }}
    .nav-direction {{
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-dim);
    }}
    .nav-target-title {{
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--text-heading);
    }}

    /* =====================================================================
       RIGHT TABLE OF CONTENTS (TOC)
       ===================================================================== */
    .toc-sidebar {{
      width: var(--toc-width);
      flex-shrink: 0;
      height: calc(100vh - var(--header-height));
      position: sticky;
      top: var(--header-height);
      padding: 2rem 1.5rem;
      overflow-y: auto;
      border-left: 1px solid var(--border-subtle);
    }}
    .toc-header {{
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
      margin-bottom: 1rem;
    }}
    .toc-list {{
      list-style: none;
    }}
    .toc-item {{
      margin-bottom: 0.45rem;
    }}
    .toc-item.level-3 {{
      padding-left: 0.85rem;
    }}
    .toc-link {{
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.82rem;
      line-height: 1.4;
      display: block;
      transition: color var(--transition-speed);
    }}
    .toc-link:hover,
    .toc-link.active {{
      color: var(--primary);
    }}

    .back-to-top-btn {{
      margin-top: 2rem;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.78rem;
      color: var(--text-dim);
      cursor: pointer;
      background: none;
      border: none;
      transition: color var(--transition-speed);
    }}
    .back-to-top-btn:hover {{
      color: var(--primary);
    }}

    /* =====================================================================
       GLOBAL SEARCH MODAL
       ===================================================================== */
    .search-modal-backdrop {{
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(4px);
      z-index: 1000;
      display: none;
      align-items: flex-start;
      justify-content: center;
      padding: 10vh 1rem 2rem 1rem;
    }}
    .search-modal-backdrop.open {{
      display: flex;
    }}

    .search-modal {{
      background: var(--bg-surface);
      border: 1px solid var(--border-muted);
      width: 100%;
      max-width: 640px;
      border-radius: var(--radius-lg);
      box-shadow: 0 20px 50px rgba(0,0,0,0.5);
      overflow: hidden;
      display: flex;
      flex-direction: column;
      max-height: 80vh;
      animation: modalSlide 0.15s ease-out;
    }}
    @keyframes modalSlide {{
      from {{ opacity: 0; transform: scale(0.97); }}
      to {{ opacity: 1; transform: scale(1); }}
    }}

    .search-input-header {{
      display: flex;
      align-items: center;
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--border-subtle);
      gap: 0.85rem;
    }}
    .search-input {{
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: var(--text-heading);
      font-size: 1.1rem;
      font-family: inherit;
    }}
    .search-clear-btn {{
      background: none;
      border: none;
      color: var(--text-dim);
      cursor: pointer;
      font-size: 1.1rem;
    }}

    .search-results-list {{
      flex: 1;
      overflow-y: auto;
      padding: 0.75rem;
      list-style: none;
    }}
    .search-result-item {{
      padding: 0.75rem 1rem;
      border-radius: var(--radius-md);
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
      transition: background var(--transition-speed);
      margin-bottom: 0.25rem;
    }}
    .search-result-item:hover,
    .search-result-item.selected {{
      background: var(--bg-surface-elevated);
    }}
    .result-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .result-title {{
      font-weight: 700;
      color: var(--text-heading);
      font-size: 0.95rem;
    }}
    .result-category {{
      font-size: 0.72rem;
      color: var(--primary);
      background: rgba(255, 129, 1, 0.1);
      padding: 0.1rem 0.45rem;
      border-radius: var(--radius-full);
      font-weight: 600;
    }}
    .result-snippet {{
      font-size: 0.82rem;
      color: var(--text-muted);
      line-height: 1.4;
    }}
    .result-match-highlight {{
      color: var(--primary);
      font-weight: 700;
      text-decoration: underline;
    }}

    .search-modal-footer {{
      padding: 0.65rem 1.25rem;
      background: var(--bg-surface-elevated);
      border-top: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 0.75rem;
      color: var(--text-dim);
    }}
    .search-footer-keys {{
      display: flex;
      align-items: center;
      gap: 1rem;
    }}

    /* =====================================================================
       PYGMENTS SYNTAX HIGHLIGHTING
       ===================================================================== */
    {pygments_dark_css}
    {pygments_light_css}

    /* =====================================================================
       RESPONSIVE BREAKPOINTS
       ===================================================================== */
    @media (max-width: 1200px) {{
      .toc-sidebar {{
        display: none;
      }}
      .main-content {{
        max-width: 100%;
      }}
    }}

    @media (max-width: 768px) {{
      .sidebar {{
        position: fixed;
        left: -100%;
        top: var(--header-height);
        bottom: 0;
        transition: left 0.25s ease-in-out;
        box-shadow: 10px 0 30px rgba(0,0,0,0.5);
      }}
      .sidebar.open {{
        left: 0;
      }}
      .sidebar-toggle-btn {{
        display: flex;
      }}
      .main-content {{
        padding: 1.5rem 1rem 5rem 1rem;
      }}
      .header-center {{
        display: none;
      }}
    }}
  </style>
</head>
<body class="mode-reader">

  <!-- =====================================================================
       APP HEADER
       ===================================================================== -->
  <header class="app-header">
    <div class="header-left">
      <button class="icon-btn sidebar-toggle-btn" onclick="toggleSidebar()" title="Toggle Sidebar">☰</button>
      <a href="#index" class="brand-link" onclick="navigateToPage('index')">
        <div class="brand-logo-icon">F</div>
        <span>FalkorDB Docs</span>
      </a>
      <span class="brand-badge">Offline Edition · 620 Pages</span>
    </div>

    <div class="header-center">
      <button class="search-trigger-btn" onclick="openSearchModal()">
        <span class="search-trigger-content">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <span>Search docs (e.g. Cypher, GraphRAG, Cognee)...</span>
        </span>
        <span class="kbd-shortcut">⌘K / /</span>
      </button>
    </div>

    <div class="header-right">
      <div class="view-mode-toggle">
        <button id="btn-mode-reader" class="view-mode-btn active" onclick="setViewMode('reader')" title="Focused single page view">
          <span>📖 Reader</span>
        </button>
        <button id="btn-mode-all" class="view-mode-btn" onclick="setViewMode('all')" title="Single continuous document with all 620 pages">
          <span>📄 All in One</span>
        </button>
      </div>

      <button class="icon-btn" onclick="toggleTheme()" id="theme-toggle-btn" title="Toggle Light/Dark Theme">
        <span id="theme-icon">☀️</span>
      </button>
    </div>
  </header>

  <!-- =====================================================================
       MAIN LAYOUT
       ===================================================================== -->
  <div class="app-layout">
    
    <!-- LEFT SIDEBAR -->
    <aside class="sidebar" id="sidebar">
      <div class="sidebar-filter-wrapper">
        <input type="text" id="sidebar-filter" class="sidebar-filter-input" placeholder="Filter topics..." oninput="filterSidebar(this.value)">
      </div>
      <div class="sidebar-scroll-area" id="sidebar-scroll">
        {"".join(sidebar_html)}
      </div>
    </aside>

    <!-- CENTER CONTENT -->
    <main class="main-content" id="main-content">
      {"".join(articles_html)}
    </main>

    <!-- RIGHT TOC -->
    <aside class="toc-sidebar" id="toc-sidebar">
      <div class="toc-header">On This Page</div>
      <ul class="toc-list" id="toc-list">
        <!-- Generated dynamically via JS -->
      </ul>
      <button class="back-to-top-btn" onclick="window.scrollTo({{top: 0, behavior: 'smooth'}})">
        <span>↑ Back to top</span>
      </button>
    </aside>

  </div>

  <!-- =====================================================================
       GLOBAL SEARCH MODAL
       ===================================================================== */ -->
  <div class="search-modal-backdrop" id="search-modal-backdrop" onclick="handleBackdropClick(event)">
    <div class="search-modal">
      <div class="search-input-header">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        <input type="text" id="global-search-input" class="search-input" placeholder="Type to search all 620 documentation pages..." oninput="handleSearch(this.value)" onkeydown="handleSearchKeyDown(event)">
        <button class="search-clear-btn" onclick="closeSearchModal()">✕</button>
      </div>
      <ul class="search-results-list" id="search-results-list">
        <!-- Results injected here -->
      </ul>
      <div class="search-modal-footer">
        <div class="search-footer-keys">
          <span><kbd class="kbd-shortcut">↑</kbd> <kbd class="kbd-shortcut">↓</kbd> to navigate</span>
          <span><kbd class="kbd-shortcut">Enter</kbd> to select</span>
          <span><kbd class="kbd-shortcut">Esc</kbd> to close</span>
        </div>
        <span id="search-results-count">Showing results</span>
      </div>
    </div>
  </div>

  <!-- =====================================================================
       CLIENT SCRIPT
       ===================================================================== -->
  <script>
    // Search Index
    const SEARCH_INDEX = {search_json_str};

    let activePageId = 'index';
    let currentSelectedResultIndex = 0;
    let searchResults = [];

    // Initialize application
    window.addEventListener('DOMContentLoaded', () => {{
      initTheme();
      initCodeBlocks();
      
      // Handle initial URL hash
      const hash = window.location.hash.replace('#', '');
      if (hash && document.getElementById('doc-' + hash)) {{
        navigateToPage(hash, false);
      }} else {{
        navigateToPage('index', false);
      }}

      // Keyboard shortcuts
      document.addEventListener('keydown', (e) => {{
        if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && document.activeElement.tagName !== 'INPUT')) {{
          e.preventDefault();
          openSearchModal();
        }} else if (e.key === 'Escape') {{
          closeSearchModal();
        }}
      }});
    }});

    // Navigation
    function navigateToPage(pageId, updateHash = true) {{
      const targetArticle = document.getElementById('doc-' + pageId);
      if (!targetArticle) return;

      activePageId = pageId;

      // Update articles
      document.querySelectorAll('.doc-article').forEach(art => art.classList.remove('active'));
      targetArticle.classList.add('active');

      // Update sidebar
      document.querySelectorAll('.nav-page-item').forEach(item => item.classList.remove('active'));
      const navItem = document.getElementById('nav-item-' + pageId);
      if (navItem) {{
        navItem.classList.add('active');
        // Expand parent category if collapsed
        const categoryParent = navItem.closest('.nav-category');
        if (categoryParent) {{
          categoryParent.classList.remove('collapsed');
        }}
        // Scroll sidebar to show item
        navItem.scrollIntoView({{ block: 'nearest', behavior: 'smooth' }});
      }}

      // Update Right TOC
      updateTOC(targetArticle);

      if (updateHash) {{
        window.history.pushState(null, '', '#' + pageId);
      }}

      // Scroll window to top
      window.scrollTo({{ top: 0, behavior: 'smooth' }});

      // Close mobile sidebar if open
      document.getElementById('sidebar').classList.remove('open');
    }}

    // Update Right Table of Contents
    function updateTOC(article) {{
      const tocList = document.getElementById('toc-list');
      tocList.innerHTML = '';

      const headings = article.querySelectorAll('h2, h3');
      if (headings.length === 0) {{
        tocList.innerHTML = '<li class="toc-item"><span style="color:var(--text-dim);font-size:0.8rem">No sub-sections</span></li>';
        return;
      }}

      headings.forEach((h, idx) => {{
        if (!h.id) {{
          h.id = 'heading-' + idx;
        }}
        const li = document.createElement('li');
        li.className = 'toc-item level-' + (h.tagName === 'H2' ? '2' : '3');
        
        const a = document.createElement('a');
        a.className = 'toc-link';
        a.href = '#' + h.id;
        a.textContent = h.textContent;
        a.onclick = (e) => {{
          e.preventDefault();
          h.scrollIntoView({{ behavior: 'smooth' }});
        }};
        li.appendChild(a);
        tocList.appendChild(li);
      }});
    }}

    // Toggle Category Accordion in Sidebar
    function toggleCategory(headerEl) {{
      const cat = headerEl.closest('.nav-category');
      cat.classList.toggle('collapsed');
    }}

    // Filter Sidebar Topics
    function filterSidebar(query) {{
      const q = query.toLowerCase().trim();
      document.querySelectorAll('.nav-page-item').forEach(item => {{
        const title = item.querySelector('.nav-title-text').textContent.toLowerCase();
        const matches = !q || title.includes(q);
        item.style.display = matches ? '' : 'none';
      }});

      // Auto-expand categories with matching items
      document.querySelectorAll('.nav-category').forEach(cat => {{
        const visibleItems = cat.querySelectorAll('.nav-page-item:not([style*="display: none"])');
        if (q) {{
          cat.classList.toggle('collapsed', visibleItems.length === 0);
          cat.style.display = visibleItems.length === 0 ? 'none' : '';
        }} else {{
          cat.style.display = '';
        }}
      }});
    }}

    // View Mode Switcher: Reader vs All
    function setViewMode(mode) {{
      const body = document.body;
      const btnReader = document.getElementById('btn-mode-reader');
      const btnAll = document.getElementById('btn-mode-all');

      if (mode === 'all') {{
        body.className = body.className.replace('mode-reader', 'mode-all');
        btnAll.classList.add('active');
        btnReader.classList.remove('active');
      }} else {{
        body.className = body.className.replace('mode-all', 'mode-reader');
        btnReader.classList.add('active');
        btnAll.classList.remove('active');
        navigateToPage(activePageId, false);
      }}
    }}

    // Theme Switcher (Dark / Light)
    function initTheme() {{
      const saved = localStorage.getItem('falkordb_theme') || 'dark';
      setTheme(saved);
    }}

    function toggleTheme() {{
      const isDark = document.documentElement.classList.contains('dark');
      setTheme(isDark ? 'light' : 'dark');
    }}

    function setTheme(theme) {{
      const html = document.documentElement;
      const icon = document.getElementById('theme-icon');
      if (theme === 'light') {{
        html.classList.remove('dark');
        html.classList.add('light');
        icon.textContent = '🌙';
        localStorage.setItem('falkordb_theme', 'light');
      }} else {{
        html.classList.remove('light');
        html.classList.add('dark');
        icon.textContent = '☀️';
        localStorage.setItem('falkordb_theme', 'dark');
      }}
    }}

    // Code Blocks: Add copy button & language badge
    function initCodeBlocks() {{
      document.querySelectorAll('.codehilite').forEach(block => {{
        const wrapper = document.createElement('div');
        wrapper.className = 'code-block-wrapper';
        block.parentNode.insertBefore(wrapper, block);

        // Detect language from class
        let lang = 'CODE';
        const classes = block.className.split(' ');
        for (const c of classes) {{
          if (c !== 'codehilite') {{
            lang = c.toUpperCase();
            break;
          }}
        }}

        const header = document.createElement('div');
        header.className = 'code-block-header';
        header.innerHTML = `<span>${{lang}}</span><button class="copy-code-btn">📋 Copy</button>`;
        
        const copyBtn = header.querySelector('.copy-code-btn');
        copyBtn.onclick = () => {{
          const code = block.querySelector('pre').textContent;
          navigator.clipboard.writeText(code).then(() => {{
            copyBtn.textContent = '✓ Copied!';
            copyBtn.classList.add('copied');
            setTimeout(() => {{
              copyBtn.textContent = '📋 Copy';
              copyBtn.classList.remove('copied');
            }}, 2000);
          }});
        }};

        wrapper.appendChild(header);
        wrapper.appendChild(block);
      }});
    }}

    // Mobile Sidebar Toggle
    function toggleSidebar() {{
      document.getElementById('sidebar').classList.toggle('open');
    }}

    // Global Search Modal Logic
    function openSearchModal() {{
      const modal = document.getElementById('search-modal-backdrop');
      modal.classList.add('open');
      const input = document.getElementById('global-search-input');
      input.focus();
      input.select();
      handleSearch(input.value);
    }}

    function closeSearchModal() {{
      document.getElementById('search-modal-backdrop').classList.remove('open');
    }}

    function handleBackdropClick(e) {{
      if (e.target.id === 'search-modal-backdrop') {{
        closeSearchModal();
      }}
    }}

    function handleSearch(query) {{
      const q = query.toLowerCase().trim();
      const listEl = document.getElementById('search-results-list');
      const countEl = document.getElementById('search-results-count');
      listEl.innerHTML = '';

      if (!q) {{
        // Show featured/getting started docs
        searchResults = SEARCH_INDEX.slice(0, 10);
      }} else {{
        const terms = q.split(/\\s+/);
        searchResults = SEARCH_INDEX.filter(item => {{
          const target = (item.title + ' ' + item.path + ' ' + item.category + ' ' + item.snippet).toLowerCase();
          return terms.every(term => target.includes(term));
        }}).slice(0, 35);
      }}

      countEl.textContent = `${{searchResults.length}} results found`;
      currentSelectedResultIndex = 0;

      if (searchResults.length === 0) {{
        listEl.innerHTML = '<li style="padding:1.5rem;text-align:center;color:var(--text-muted)">No matching documentation found. Try a different query.</li>';
        return;
      }}

      searchResults.forEach((res, idx) => {{
        const li = document.createElement('li');
        li.className = 'search-result-item' + (idx === 0 ? ' selected' : '');
        li.onclick = () => {{
          navigateToPage(res.id);
          closeSearchModal();
        }};

        let titleDisplay = res.title;
        if (q) {{
          const regex = new RegExp(`(${{q.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&')}})`, 'gi');
          titleDisplay = titleDisplay.replace(regex, '<span class="result-match-highlight">$1</span>');
        }}

        li.innerHTML = `
          <div class="result-top">
            <span class="result-title">${{res.icon}} ${{titleDisplay}}</span>
            <span class="result-category">${{res.category}}</span>
          </div>
          <div class="result-snippet">${{res.snippet}}</div>
        `;
        listEl.appendChild(li);
      }});
    }}

    function handleSearchKeyDown(e) {{
      const items = document.querySelectorAll('.search-result-item');
      if (items.length === 0) return;

      if (e.key === 'ArrowDown') {{
        e.preventDefault();
        items[currentSelectedResultIndex].classList.remove('selected');
        currentSelectedResultIndex = (currentSelectedResultIndex + 1) % items.length;
        items[currentSelectedResultIndex].classList.add('selected');
        items[currentSelectedResultIndex].scrollIntoView({{ block: 'nearest' }});
      }} else if (e.key === 'ArrowUp') {{
        e.preventDefault();
        items[currentSelectedResultIndex].classList.remove('selected');
        currentSelectedResultIndex = (currentSelectedResultIndex - 1 + items.length) % items.length;
        items[currentSelectedResultIndex].classList.add('selected');
        items[currentSelectedResultIndex].scrollIntoView({{ block: 'nearest' }});
      }} else if (e.key === 'Enter') {{
        e.preventDefault();
        if (searchResults[currentSelectedResultIndex]) {{
          navigateToPage(searchResults[currentSelectedResultIndex].id);
          closeSearchModal();
        }}
      }}
    }}
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
