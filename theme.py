"""Visual layer: the stylesheet and the HTML pieces of the page.

Design tokens
  canvas  #F5F7FD  cool near-white page
  surface #FFFFFF  cards and panels
  ink     #161A35  text
  muted   #5A6183  secondary text
  line    #E3E7F3  borders
  brand gradient: #4F46E5 indigo -> #7C3AED violet -> #0EA5E9 sky
Type: Plus Jakarta Sans for headings, Inter for everything else.
"""
import html
import re
from urllib.parse import urlparse

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800&family=Inter:wght@400;500;600&display=swap');

:root {
  --canvas: #F5F7FD; --surface: #FFFFFF; --ink: #161A35; --muted: #5A6183; --line: #E3E7F3;
  --indigo: #4F46E5; --violet: #7C3AED; --sky: #0EA5E9;
  --brand: linear-gradient(115deg, #4F46E5 0%, #7C3AED 48%, #0EA5E9 100%);
  --ease: cubic-bezier(.2, .8, .2, 1);
  --shadow-lg: 0 1px 2px rgba(22,26,53,.04), 0 18px 40px -18px rgba(79,70,229,.28);
  --shadow-sm: 0 1px 2px rgba(22,26,53,.05), 0 6px 16px -10px rgba(22,26,53,.18);
}

/* ---------- Page frame ---------- */
html { scroll-behavior: smooth; }
[data-testid="stAppViewContainer"] { background: var(--canvas); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer { display: none !important; }
[data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none; }
.block-container, [data-testid="stMainBlockContainer"] {
  max-width: 1080px; padding-top: 2.2rem; padding-bottom: 3rem; position: relative; z-index: 1;
}
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] p, input, textarea,
button p, [data-baseweb="tab"] p { font-family: 'Inter', system-ui, sans-serif; color: var(--ink); }
[data-testid="stMarkdownContainer"] h1, [data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 { font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; color: var(--ink); }
[data-testid="stHeaderActionElements"] { display: none !important; }
::selection { background: rgba(124,58,237,.18); }

/* ---------- Background: one slow drift ---------- */
.hi-bg { position: fixed; inset: 0; z-index: -1; pointer-events: none; overflow: hidden; }
.hi-bg span { position: absolute; border-radius: 50%; filter: blur(70px); opacity: .5;
  animation: hi-drift 26s var(--ease) infinite alternate; }
.hi-bg .b1 { width: 520px; height: 520px; background: #C7D2FE; top: -160px; left: -120px; }
.hi-bg .b2 { width: 460px; height: 460px; background: #DDD6FE; top: 80px; right: -160px; animation-delay: -9s; }
.hi-bg .b3 { width: 380px; height: 380px; background: #BAE6FD; top: 520px; left: 30%; opacity: .35; animation-delay: -17s; }
@keyframes hi-drift { from { transform: translate(0,0) scale(1); } to { transform: translate(60px,40px) scale(1.08); } }

/* ---------- Hero ---------- */
.hi-hero { display: grid; grid-template-columns: 1.15fr .85fr; gap: 2.5rem; align-items: center;
  margin: .5rem 0 2.2rem; }
.hi-brand { display: inline-flex; align-items: center; gap: .55rem; font: 700 1rem 'Plus Jakarta Sans', sans-serif;
  color: var(--ink); margin-bottom: 1.4rem; }
.hi-brand i { width: 26px; height: 26px; border-radius: 8px; background: var(--brand); display: inline-block;
  box-shadow: 0 6px 14px -6px rgba(124,58,237,.6); }
.hi-hero h1 { font: 800 clamp(2.2rem, 4.6vw, 3.4rem)/1.05 'Plus Jakarta Sans', sans-serif !important;
  letter-spacing: -.035em; margin: 0 0 1rem !important; padding: 0 !important;
  background: var(--brand); -webkit-background-clip: text; background-clip: text; color: transparent !important; }
.hi-hero p.lede { font-size: 1.08rem; line-height: 1.6; color: var(--muted); max-width: 34rem; margin: 0 0 1.6rem; }
.hi-steps { display: flex; gap: 1.4rem; flex-wrap: wrap; margin: 0; padding: 0; list-style: none; counter-reset: s; }
.hi-steps li { counter-increment: s; display: flex; align-items: center; gap: .55rem; color: var(--ink);
  font-size: .92rem; font-weight: 500; }
.hi-steps li::before { content: counter(s); width: 24px; height: 24px; border-radius: 50%; display: grid;
  place-items: center; font-size: .75rem; font-weight: 700; color: var(--indigo); background: #EEF0FF; }

.hi-preview { position: relative; background: var(--surface); border: 1px solid var(--line); border-radius: 22px;
  padding: 1.3rem 1.4rem; box-shadow: var(--shadow-lg); transform: rotate(-2deg);
  transition: transform .5s var(--ease), box-shadow .5s var(--ease); }
.hi-preview:hover { transform: rotate(0deg) translateY(-4px); box-shadow: 0 30px 60px -28px rgba(79,70,229,.45); }
.hi-preview::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 5px; border-radius: 22px 22px 0 0;
  background: var(--brand); }
.hi-preview .pv-head { font: 700 1.05rem 'Plus Jakarta Sans', sans-serif; margin: .2rem 0 .15rem; }
.hi-preview .pv-sub { font-size: .8rem; color: var(--muted); margin-bottom: .9rem; }
.hi-preview .pv-line { display: flex; gap: .5rem; align-items: baseline; font-size: .84rem; line-height: 1.45;
  padding: .45rem 0; border-top: 1px dashed var(--line); }

/* ---------- Tags and citations (shared by preview and report) ---------- */
.tag { display: inline-block; flex: none; font: 600 .68rem/1 'Inter', sans-serif; padding: .3rem .48rem;
  border-radius: 6px; margin-right: .35rem; vertical-align: .12em; white-space: nowrap; }
.tag-web { color: #1D6FE0; background: #E8F1FE; }
.tag-you { color: #6D28D9; background: #F1EAFE; }
.tag-ai  { color: #4A5473; background: #EEF0F6; }
a.cite { display: inline-flex; align-items: center; justify-content: center; min-width: 1.15rem; height: 1.15rem;
  padding: 0 .25rem; margin-left: .15rem; border-radius: 6px; font-size: .66rem; font-weight: 600;
  vertical-align: .18em; color: var(--indigo) !important; background: #EEF0FF; text-decoration: none !important;
  transition: background .2s var(--ease), color .2s var(--ease); }
a.cite:hover { background: var(--indigo); color: #fff !important; }

/* ---------- Example chips ---------- */
.st-key-chips { margin-bottom: .2rem; }
.st-key-chips p.chips-label { font-size: .85rem; color: var(--muted); margin: 0 0 .35rem; }
.st-key-chips button { border-radius: 999px !important; border: 1px solid var(--line) !important;
  background: rgba(255,255,255,.75) !important; backdrop-filter: blur(6px); min-height: 0 !important;
  padding: .35rem .9rem !important; transition: border-color .2s var(--ease), transform .2s var(--ease), box-shadow .2s var(--ease); }
.st-key-chips button p { font-size: .84rem !important; font-weight: 500; color: var(--ink) !important; }
.st-key-chips button:hover { border-color: #C7CBF5 !important; transform: translateY(-1px); box-shadow: var(--shadow-sm); }

/* ---------- Form card ---------- */
[data-testid="stForm"] { background: var(--surface); border: 1px solid var(--line) !important; border-radius: 24px;
  padding: 1.6rem 1.7rem 1.4rem; box-shadow: var(--shadow-lg); }
[data-testid="stWidgetLabel"] p { font-weight: 600 !important; font-size: .86rem !important; }
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
  border-radius: 12px !important; border: 1px solid var(--line) !important; background: #FAFBFF !important;
  transition: border-color .2s var(--ease), box-shadow .2s var(--ease), background .2s var(--ease); }
[data-baseweb="input"]:hover, [data-baseweb="textarea"]:hover, [data-baseweb="select"] > div:hover { border-color: #C9CEE6 !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within {
  border-color: var(--indigo) !important; background: #fff !important; box-shadow: 0 0 0 4px rgba(79,70,229,.12); }
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea { background: transparent !important; }
[data-testid="stFileUploaderDropzone"] { border-radius: 14px; border: 1.5px dashed #CDD2EA; background: #FAFBFF;
  transition: border-color .2s var(--ease), background .2s var(--ease); }
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--indigo); background: #F4F5FF; }

[data-testid="stExpander"] details { border: 1px solid var(--line) !important; border-radius: 16px !important;
  background: #FCFCFF; transition: box-shadow .25s var(--ease); }
[data-testid="stExpander"] details[open] { box-shadow: var(--shadow-sm); }
[data-testid="stExpander"] summary p { font-weight: 600; }

[data-testid="stFormSubmitButton"] button, .st-key-download button {
  background: var(--brand) !important; background-size: 160% 100% !important; background-position: 0% 0 !important;
  border: 0 !important; border-radius: 14px !important; padding: .72rem 1.5rem !important; min-height: 0 !important;
  box-shadow: 0 10px 24px -12px rgba(79,70,229,.75);
  transition: transform .25s var(--ease), box-shadow .25s var(--ease), background-position .5s var(--ease) !important; }
[data-testid="stFormSubmitButton"] button p, .st-key-download button p { color: #fff !important; font-weight: 600 !important;
  font-size: .98rem !important; }
[data-testid="stFormSubmitButton"] button:hover, .st-key-download button:hover {
  transform: translateY(-2px); background-position: 100% 0 !important; box-shadow: 0 16px 30px -14px rgba(124,58,237,.8); }
[data-testid="stFormSubmitButton"] button:active, .st-key-download button:active { transform: translateY(0); }
button:focus-visible { outline: 3px solid rgba(79,70,229,.45) !important; outline-offset: 2px; }

.st-key-settings button { border-radius: 12px !important; border: 1px solid var(--line) !important;
  background: rgba(255,255,255,.8) !important; min-height: 0 !important; padding: .4rem .85rem !important; }
.st-key-settings button p { font-size: .84rem !important; color: var(--muted) !important; }
.hi-privacy { font-size: .8rem; color: var(--muted); margin-top: .4rem; }

/* ---------- Progress tracker ---------- */
.hi-track { background: var(--surface); border: 1px solid var(--line); border-radius: 20px; padding: 1.25rem 1.4rem;
  box-shadow: var(--shadow-sm); margin: 1.2rem 0; }
.hi-track .bar { height: 6px; border-radius: 99px; background: #EDEFF8; overflow: hidden; margin-bottom: 1rem; }
.hi-track .bar i { display: block; height: 100%; border-radius: 99px; background: var(--brand); background-size: 200% 100%;
  transition: width .6s var(--ease); animation: hi-shimmer 2.2s linear infinite; }
@keyframes hi-shimmer { from { background-position: 0 0; } to { background-position: -200% 0; } }
.hi-track ol { display: grid; grid-template-columns: repeat(5, 1fr); gap: .6rem; list-style: none; margin: 0; padding: 0; }
.hi-track li { display: flex; align-items: center; gap: .5rem; font-size: .82rem; color: var(--muted); }
.hi-track li .dot { width: 22px; height: 22px; flex: none; border-radius: 50%; display: grid; place-items: center;
  font-size: .7rem; font-weight: 700; border: 1.5px solid #D5D9EC; color: var(--muted); background: #fff; }
.hi-track li.done { color: var(--ink); }
.hi-track li.done .dot { background: var(--indigo); border-color: var(--indigo); color: #fff; }
.hi-track li.active { color: var(--ink); font-weight: 600; }
.hi-track li.active .dot { border-color: var(--violet); color: var(--violet); animation: hi-pulse 1.6s var(--ease) infinite; }
@keyframes hi-pulse { 0% { box-shadow: 0 0 0 0 rgba(124,58,237,.35); } 100% { box-shadow: 0 0 0 9px rgba(124,58,237,0); } }
.hi-track .detail { margin-top: .9rem; font-size: .85rem; color: var(--muted); }

/* ---------- Report ---------- */
.hi-report-head { background: var(--surface); border: 1px solid var(--line); border-radius: 24px; overflow: hidden;
  box-shadow: var(--shadow-lg); margin: 1.6rem 0 1rem; }
.hi-report-head .band { height: 6px; background: var(--brand); }
.hi-report-head .inner { padding: 1.4rem 1.6rem 1.3rem; }
.hi-report-head h2 { font: 800 1.9rem/1.1 'Plus Jakarta Sans', sans-serif !important; letter-spacing: -.02em;
  margin: 0 0 .3rem !important; padding: 0 !important; }
.hi-report-head .sub { color: var(--muted); font-size: .98rem; margin-bottom: .9rem; }
.hi-report-head .pills { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: .9rem; }
.hi-report-head .pill { font-size: .78rem; font-weight: 500; padding: .3rem .65rem; border-radius: 999px;
  background: #F1F3FB; color: var(--ink); }
.hi-report-head .legend { display: flex; flex-wrap: wrap; gap: .35rem 1rem; font-size: .8rem; color: var(--muted);
  padding-top: .85rem; border-top: 1px solid var(--line); }
.hi-report-head .legend span.item { display: inline-flex; align-items: center; }
.hi-meta { font-size: .8rem; color: var(--muted); margin: .4rem 0 0; }

[data-baseweb="tab-list"] { gap: .3rem; background: #ECEFF9; padding: .32rem; border-radius: 14px;
  overflow-x: auto; scrollbar-width: none; }
[data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
[data-baseweb="tab"] { height: auto !important; padding: .5rem .95rem !important; border-radius: 10px !important;
  border: 0 !important; outline-offset: 2px;
  background: transparent !important; white-space: nowrap; transition: background .25s var(--ease), box-shadow .25s var(--ease); }
[data-baseweb="tab"] p { font-size: .86rem !important; font-weight: 500 !important; color: var(--muted) !important; }
[data-baseweb="tab"]:hover p { color: var(--ink) !important; }
[data-baseweb="tab"][aria-selected="true"] { background: var(--surface) !important; box-shadow: var(--shadow-sm); }
[data-baseweb="tab"][aria-selected="true"] p { color: var(--ink) !important; font-weight: 600 !important; }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none !important; }
[data-baseweb="tab-panel"] { background: var(--surface); border: 1px solid var(--line); border-radius: 20px;
  padding: 1.3rem 1.7rem 1.1rem !important; margin-top: .65rem; animation: hi-in .35s var(--ease); }
@keyframes hi-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
[data-baseweb="tab-panel"] h3 { font-size: 1.02rem !important; font-weight: 700 !important; margin: 1.1rem 0 .45rem !important;
  padding: 0 !important; color: var(--indigo) !important; }
[data-baseweb="tab-panel"] h3:first-child { margin-top: .2rem !important; }
[data-baseweb="tab-panel"] li { margin-bottom: .38rem; line-height: 1.6; font-size: .95rem; }
[data-baseweb="tab-panel"] li::marker { color: #A3A9C7; }
[data-baseweb="tab-panel"] blockquote { border-left: 3px solid #F59E0B; background: #FFF8EB; margin: 0 0 .8rem;
  padding: .55rem .9rem; border-radius: 0 12px 12px 0; }
[data-baseweb="tab-panel"] blockquote p { color: #7A4B00 !important; margin: 0; font-size: .9rem; }
[data-baseweb="tab-panel"] input[type="checkbox"] { accent-color: var(--indigo); transform: translateY(1px); }

.hi-sources { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: .6rem; }
.hi-source { display: flex; gap: .65rem; padding: .7rem .8rem; border: 1px solid var(--line); border-radius: 14px;
  background: #fff; text-decoration: none !important; transition: border-color .2s var(--ease), transform .2s var(--ease), box-shadow .2s var(--ease); }
.hi-source:hover { border-color: #C7CBF5; transform: translateY(-2px); box-shadow: var(--shadow-sm); }
.hi-source .n { flex: none; width: 24px; height: 24px; border-radius: 8px; display: grid; place-items: center;
  font-size: .72rem; font-weight: 700; color: var(--indigo); background: #EEF0FF; }
.hi-source .t { font-size: .82rem; line-height: 1.35; color: var(--ink); display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden; }
.hi-source .d { font-size: .74rem; color: var(--muted); margin-top: .15rem; }

[data-testid="stAlert"] { border-radius: 14px; }

/* ---------- Footer ---------- */
.hi-footer { margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--line); display: flex;
  justify-content: space-between; flex-wrap: wrap; gap: .6rem; font-size: .8rem; color: var(--muted); }
.hi-footer a { color: var(--indigo) !important; text-decoration: none; font-weight: 500; }
.hi-footer a:hover { text-decoration: underline; }

/* ---------- Small screens and reduced motion ---------- */
@media (max-width: 820px) {
  .hi-hero { grid-template-columns: 1fr; gap: 1.6rem; }
  .hi-preview { transform: none; }
  .hi-track ol { grid-template-columns: 1fr; }
  [data-testid="stForm"] { padding: 1.2rem 1.1rem 1rem; border-radius: 20px; }
  [data-baseweb="tab-panel"] { padding: 1rem 1.05rem .9rem !important; }
  .hi-report-head h2 { font-size: 1.5rem !important; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
"""

TAG_HTML = {
    "🌐": '<span class="tag tag-web">Source</span>',
    "💼": '<span class="tag tag-you">Your profile</span>',
    "💡": '<span class="tag tag-ai">AI tip</span>',
}
CITE = re.compile(r"\[(\d+)\](?!\()")


def esc(text) -> str:
    return html.escape(str(text or ""), quote=True)


def background_html() -> str:
    return '<div class="hi-bg" aria-hidden="true"><span class="b1"></span><span class="b2"></span><span class="b3"></span></div>'


def hero_html() -> str:
    return f"""{background_html()}
<section class="hi-hero">
  <div>
    <div class="hi-brand"><i></i>HappyInterviews</div>
    <h1>Walk into your interview already briefed.</h1>
    <p class="lede">Name the company and role. HappyInterviews researches the web and writes your prep report:
    how the interviews run, questions candidates were asked, what the company is working on, and what to revise.
    Every fact links to its source.</p>
    <ol class="hi-steps"><li>Tell us the role</li><li>We research the web</li><li>Get your report</li></ol>
  </div>
  <div class="hi-preview" aria-label="Example of a report">
    <div class="pv-head">Swiggy, Data Analyst</div>
    <div class="pv-sub">Example report: Bengaluru, fresher, technical round</div>
    <div class="pv-line">{TAG_HTML['🌐']}<span>The online test covers SQL joins and aptitude in 60 minutes<a class="cite" href="#">2</a></span></div>
    <div class="pv-line">{TAG_HTML['💼']}<span>Tie your churn analysis project to delivery retention metrics</span></div>
    <div class="pv-line">{TAG_HTML['💡']}<span>Ask how the team measures success for Instamart</span></div>
  </div>
</section>"""


STEPS = ["Planning searches", "Searching the web", "Reading pages", "Picking the best material", "Writing your report"]


def tracker_html(active: int, detail: str = "", progress: float = None) -> str:
    """active = index of the current step (len(STEPS) means all done)."""
    if progress is None:
        progress = active / len(STEPS)
    items = []
    for i, name in enumerate(STEPS):
        state = "done" if i < active else "active" if i == active else ""
        mark = "&#10003;" if i < active else str(i + 1)
        items.append(f'<li class="{state}"><span class="dot">{mark}</span>{esc(name)}</li>')
    return f"""<div class="hi-track" role="status" aria-live="polite">
  <div class="bar"><i style="width:{max(4, min(100, progress * 100)):.0f}%"></i></div>
  <ol>{''.join(items)}</ol>
  <div class="detail">{esc(detail)}</div>
</div>"""


def report_head_html(company: str, role: str, location: str, profile: dict, personal: bool) -> str:
    pills = []
    if profile.get("level") and profile["level"] != "Not specified":
        pills.append(profile["level"])
    if profile.get("round") and profile["round"] != "All rounds":
        pills.append(f"{profile['round']} round")
    if profile.get("jd"):
        pills.append("Uses your job description")
    if profile.get("resume"):
        pills.append("Uses your resume")
    pill_html = "".join(f'<span class="pill">{esc(p)}</span>' for p in pills)
    legend = [f'<span class="item">{TAG_HTML["🌐"]} from a web page, with its numbered link</span>']
    if personal:
        legend.append(f'<span class="item">{TAG_HTML["💼"]} from your resume or job description</span>')
    legend.append(f'<span class="item">{TAG_HTML["💡"]} suggestion written by the AI</span>')
    return f"""<div id="hi-report" class="hi-report-head"><div class="band"></div><div class="inner">
  <h2>{esc(company)}</h2>
  <div class="sub">{esc(role)} in {esc(location)}</div>
  {f'<div class="pills">{pill_html}</div>' if pills else ''}
  <div class="legend">{''.join(legend)}</div>
</div></div>"""


def section_markdown(text: str, sources_by_num: dict) -> str:
    """Model markdown -> markdown with styled tags and clickable citations.
    Raw HTML from the model is neutralized by escaping '<'."""
    text = (text or "").replace("<", "&lt;")
    for emoji, tag in TAG_HTML.items():
        text = text.replace(emoji, tag)

    def cite(m):
        n = int(m.group(1))
        src = sources_by_num.get(n)
        if not src:
            return m.group(0)
        return (f'<a class="cite" href="{esc(src["url"])}" target="_blank" rel="noopener" '
                f'title="{esc(src["title"])}">{n}</a>')

    return CITE.sub(cite, text)


def sources_html(sources: list) -> str:
    cards = []
    for s in sources:
        domain = urlparse(s["url"]).netloc.replace("www.", "")
        cards.append(f'<a class="hi-source" href="{esc(s["url"])}" target="_blank" rel="noopener">'
                     f'<span class="n">{s["num"]}</span><span><span class="t">{esc(s["title"])}</span>'
                     f'<span class="d">{esc(domain)}</span></span></a>')
    return f'<div class="hi-sources">{"".join(cards)}</div>'


def footer_html() -> str:
    return """<div class="hi-footer">
  <span>Your resume and job description are used only for your report and are never stored.</span>
  <span>Built by Shubham Bokolia &nbsp;|&nbsp; <a href="https://github.com/Shubham4521/happy-interviews" target="_blank" rel="noopener">View the code on GitHub</a></span>
</div>"""


SCROLL_TO_REPORT_JS = """<script>
try { const el = window.parent.document.getElementById('hi-report');
      if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'}); } catch (e) {}
</script>"""
