"""Re-mint the downloadable book PDF from the live text of index.html.

    python3 tools/pdf/build_pdf.py                 # writes tnf_pdf20160715220260715.pdf, dated today
    python3 tools/pdf/build_pdf.py --date "November 6, 2026" --out /tmp/check.pdf

Reads CHAPTER_TEXT, INTRO_TEXT, CHAPTERS, MECHANISMS, MECHANISM_FULL and LEDGER out of
index.html, so the PDF always matches the site. Fonts and artwork live beside this file.
"""
import argparse, datetime, json, re, sys, os, html
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Flowable,
                                PageBreak, CondPageBreak)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.lib import colors
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
today = datetime.date.today()
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--src', default=os.path.join(ROOT, 'index.html'), help='site page to read the text from')
ap.add_argument('--out', default=os.path.join(ROOT, 'tnf_pdf20160715220260715.pdf'), help='PDF to write')
ap.add_argument('--date', default=f'{today:%B} {today.day}, {today.year}', help='"Compiled ..." date on the last page')
args = ap.parse_args()
SRC, OUT, COMPILED = args.src, args.out, args.date
FONTS = os.path.join(HERE, 'fonts'); IMG = os.path.join(HERE, 'img')

W, H = 486, 648
LM, RM = 56, 430            # text block 56..430

for name, f in [('Anton', 'Anton-Regular.ttf'), ('Lora', 'Lora-Regular.ttf'), ('Lora-Bold', 'Lora-Bold.ttf'),
                ('Lora-Italic', 'Lora-Italic.ttf'), ('Mono', 'CourierPrime-Regular.ttf'), ('Mono-Bold', 'CourierPrime-Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(name, os.path.join(FONTS, f)))
pdfmetrics.registerFont(TTFont('DejaVu', os.path.join(FONTS, 'DejaVuSerif.ttf')))
pdfmetrics.registerFontFamily('Lora', normal='Lora', bold='Lora-Bold', italic='Lora-Italic', boldItalic='Lora-Bold')

# ───────────────────────────── data ─────────────────────────────
s = open(SRC, encoding='utf-8').read()
def const(name):
    return json.loads(re.search(r'const ' + name + r' = (.*?);\n', s, re.S).group(1))
CT, INTRO, CHS, MS, MF, LED = (const('CHAPTER_TEXT'), const('INTRO_TEXT'), const('CHAPTERS'),
                               const('MECHANISMS'), const('MECHANISM_FULL'), const('LEDGER'))
CH = {c['n']: c['title'] for c in CHS}
MECH = {m['n']: m for m in MS}

def smart(t):
    t = re.sub(r"(\w)'(\w)", '\\1’\\2', t)                 # it's
    t = re.sub(r"(^|[\s(\[{—–\"“])'", '\\1‘', t)              # 'open
    t = t.replace("'", '’')
    t = re.sub(r'(^|[\s(\[{—–‘])"', '\\1“', t)
    t = t.replace('"', '”')
    return t
def esc(t):
    return html.escape(smart(t), quote=False).replace('→', '<font name="DejaVu">→</font>')
def linkify(t):          # t already escaped
    return re.sub(r'https?://[^\s<"]+[^\s<".,;:)”]', lambda m: f'<a href="{m.group(0)}" color="#000000">{m.group(0)}</a>', t)

# ───────────────────────────── styles ─────────────────────────────
ST = dict(
 body=ParagraphStyle('body', fontName='Lora', fontSize=10, leading=14.6, spaceAfter=7.4),
 lead=ParagraphStyle('lead', fontName='Lora', fontSize=12.2, leading=17.3, spaceAfter=8.6),
 dateline=ParagraphStyle('dl', fontName='Mono-Bold', fontSize=8.6, leading=11, spaceAfter=5),
 sub=ParagraphStyle('sub', fontName='Anton', fontSize=11.5, leading=14.5, spaceAfter=4),
 quote=ParagraphStyle('q', fontName='Lora-Italic', fontSize=10, leading=14.6, leftIndent=16, spaceAfter=7.4),
 bullet=ParagraphStyle('b', fontName='Lora', fontSize=10, leading=14.6, leftIndent=14, bulletIndent=2, spaceAfter=4),
 src=ParagraphStyle('src', fontName='Lora', fontSize=8.6, leading=12, leftIndent=12, firstLineIndent=-12, spaceAfter=5),
 kicker=ParagraphStyle('k', fontName='Mono-Bold', fontSize=8.5, leading=10),
 title=ParagraphStyle('t', fontName='Anton', fontSize=27, leading=31),
 boxlabel=ParagraphStyle('bl', fontName='Mono-Bold', fontSize=6.6, leading=9),
 boxtext=ParagraphStyle('bt', fontName='Lora', fontSize=8.4, leading=12),
 boxtext2=ParagraphStyle('bt2', fontName='Lora', fontSize=9.4, leading=12),
)

# ───────────────────────────── flowables ─────────────────────────────
class State(Flowable):
    """Zero-size marker: sets running-header title / volume, marks an opening page, records a page number."""
    def __init__(self, title=None, vol=None, opening=False, mark=None):
        super().__init__(); self.title, self.vol, self.opening, self.mark = title, vol, opening, mark
    def wrap(self, aw, ah): return 0, 0
    def draw(self):
        c = self.canv
        if self.title is not None: c._tnf_title = self.title
        if self.vol is not None: c._tnf_vol = self.vol
        if self.opening: c._tnf_opening = c.getPageNumber()
        if self.mark: MARKS[self.mark] = c.getPageNumber()

class FullPage(Flowable):
    """Occupies a whole page; draws with absolute page coordinates; no header or badge."""
    def __init__(self, fn): super().__init__(); self.fn = fn
    def wrap(self, aw, ah): return aw, ah - 1
    def draw(self):
        self.canv._tnf_full = self.fn

class Rule(Flowable):
    def __init__(self, w=30, t=2, space=4): super().__init__(); self.w, self.t, self.sp = w, t, space
    def wrap(self, aw, ah): return self.w, self.t + self.sp
    def draw(self): self.canv.setFillColor(colors.black); self.canv.rect(0, self.sp, self.w, self.t, stroke=0, fill=1)

class Box(Flowable):
    """Left-ruled box: small mono label over a line of text (Mechanisms deployed / Cross-referenced in)."""
    def __init__(self, label, text, style):
        super().__init__(); self.l = Paragraph(label, ST['boxlabel']); self.p = Paragraph(text, style)
    def wrap(self, aw, ah):
        self.aw = aw; _, h1 = self.l.wrap(aw - 10, ah); _, h2 = self.p.wrap(aw - 10, ah); self.h1, self.h2 = h1, h2
        return aw, h1 + h2 + 8
    def draw(self):
        c = self.canv; h = self.h1 + self.h2 + 8
        c.setLineWidth(1.5); c.line(0, 0, 0, h)
        self.l.drawOn(c, 10, h - 4 - self.h1); self.p.drawOn(c, 10, h - 4 - self.h1 - self.h2 - 1)

class Img(Flowable):
    def __init__(self, path, maxw, maxh, space=14):
        super().__init__(); self.r = ImageReader(path); iw, ih = self.r.getSize()
        k = min(maxw / iw, maxh / ih); self.w, self.h = iw * k, ih * k; self.sp = space
    def wrap(self, aw, ah): self.aw = aw; return aw, self.h + 2 * self.sp
    def draw(self): self.canv.drawImage(self.r, (self.aw - self.w) / 2, self.sp, self.w, self.h)

class TOCLine(Flowable):
    def __init__(self, text, key, bold=False, indent=0, gap=0):
        super().__init__(); self.text, self.key, self.bold, self.ind, self.gap = text, key, bold, indent, gap
        self.font, self.size = ('Lora-Bold', 9.6) if bold else ('Lora', 8.8)
    def wrap(self, aw, ah):
        self.aw = aw; num = str(PAGES.get(self.key, 888)); self.num = num
        self.lines = simpleSplit(smart(self.text), self.font, self.size, aw - self.ind - 40)
        self.lh = 15.6; return aw, self.lh * len(self.lines) + self.gap
    def draw(self):
        c = self.canv; y = self.lh * len(self.lines) - 11
        for i, ln in enumerate(self.lines):
            x = self.ind + (10 if i else 0); c.setFont(self.font, self.size); c.drawString(x, y, ln)
            if i == len(self.lines) - 1:
                end = x + c.stringWidth(ln, self.font, self.size) + 6
                nw = c.stringWidth(self.num, self.font, self.size)
                c.setFont('Lora', self.size); dx = c.stringWidth('. ', 'Lora', self.size)
                xx = end
                while xx + dx < self.aw - nw - 6: c.drawString(xx, y, '.'); xx += dx
                c.setFont(self.font, self.size); c.drawRightString(self.aw, y, self.num)
            y -= self.lh

# ───────────────────────────── page furniture ─────────────────────────────
BADGE = {1: ImageReader(os.path.join(IMG, 'badge-book.png')), 2: ImageReader(os.path.join(IMG, 'badge-brain.png'))}
def on_page_end(c, doc):
    fn = getattr(c, '_tnf_full', None)
    if fn:
        c._tnf_full = None; fn(c); return
    pg = c.getPageNumber(); title = getattr(c, '_tnf_title', None)
    if title and getattr(c, '_tnf_opening', -1) != pg:
        c.setFont('Mono-Bold', 6.4); c.drawString(LM, H - 38, 'THE NARRATIVE FORGERY')
        c.setFont('Mono', 6.4); c.drawRightString(RM, H - 38, smart(title).upper())
        c.setStrokeColor(colors.Color(.55, .55, .55)); c.setLineWidth(.5); c.line(LM, H - 44, RM, H - 44)
        c.setStrokeColor(colors.black)
    c.drawImage(BADGE[getattr(c, '_tnf_vol', 1)], 221, 15, 44, 44)
    c.setFillColor(colors.white); c.setFont('Anton', 8.6); c.drawCentredString(243, 34.3, str(pg)); c.setFillColor(colors.black)

def cb(c, text, y0, font, size):
    """Centered line whose glyph box bottom sits at y0 (PDF coordinates), matching the previous edition."""
    c.setFont(font, size); c.drawCentredString(W / 2, y0 - pdfmetrics.getDescent(font, size), text)

def cmix(c, parts, y0, size):
    tw = sum(pdfmetrics.stringWidth(t, f, size) for t, f in parts); x = (W - tw) / 2
    base = y0 - pdfmetrics.getDescent(parts[0][1], size)
    for t, f in parts:
        c.setFont(f, size); c.drawString(x, base, t); x += pdfmetrics.stringWidth(t, f, size)

def para_at(c, text, style, x, y_top, w):
    p = Paragraph(text, style); _, h = p.wrap(w, 1000); p.drawOn(c, x, H - y_top - h); return h

# ───────────────────────────── full pages ─────────────────────────────
def cover(c):
    r = ImageReader(os.path.join(IMG, 'cover.jpg')); c.drawImage(r, 0, H - 563.2, 486, 478.4)
def vol2cover(c):
    r = ImageReader(os.path.join(IMG, 'volume-two-cover.jpg')); c.drawImage(r, 0, H - 567, 486, 486)

SYNOPSIS = ["Between 2016 and 2026, institutions across media, federal law enforcement, intelligence, technology, public health, and politics arrived independently at the same assumption: the public could not be trusted with the primary record, and managing what people were permitted to know was a duty.",
            "No meeting was required. Shared incentives, shared assumptions, and shared identity produced the coordination a conspiracy would have had to arrange. Primary-source evidence was suppressed. Claims the institutions’ own investigations would later contradict were amplified. Accountability was applied along political lines and withheld along others.",
            "The decisions left a documentary record. This book reads that record back to the institutions that produced it."]
def titlepage(c):
    cb(c, 'A PRIMARY-SOURCE RECORD', 534, 'Mono', 7)
    cb(c, 'THE NARRATIVE', 475.8, 'Anton', 32); cb(c, 'FORGERY', 439.8, 'Anton', 32)
    cmix(c, [('A Book ', 'Lora'), ('of', 'Lora-Italic'), (' Receipts', 'Lora')], 417.2, 15)
    cb(c, '2016–2026', 394, 'Anton', 12)
    c.rect(228, H - 268.4, 30, 1.3, stroke=0, fill=1)
    cb(c, 'SYNOPSIS', 356.7, 'Mono-Bold', 6.6)
    y = 300; st = ParagraphStyle('syn', fontName='Lora', fontSize=9, leading=13.4, alignment=TA_CENTER)
    for t in SYNOPSIS: y += para_at(c, t, st, 42, y, 402) + 6.6
    st2 = ParagraphStyle('v', fontName='Lora', fontSize=8, leading=12, alignment=TA_CENTER)
    para_at(c, '<font name="Lora-Bold">VOLUME ONE</font> · The Narrative Forgery — 18 Chapters<br/><font name="Lora-Bold">VOLUME TWO</font> · The Neural Architecture of Deception — 18 Mechanisms', st2, 42, 474, 402)
    c.setLineWidth(.5); c.line(123, H - 462.6, 363, H - 462.6)
    cb(c, 'THE RECEIPTS ARE THE ARGUMENT', 118.4, 'Anton', 10)

def exhibit(n, files):
    def fn(c):
        if len(files) == 1:
            r = ImageReader(os.path.join(IMG, files[0])); iw, ih = r.getSize()
            k = min(345.2 / iw, 518 / ih); w, h = iw * k, ih * k
            c.drawImage(r, (W - w) / 2, H - 566.5 + (518 - h) / 2, w, h)
        else:
            for i, f in enumerate(files):
                r = ImageReader(os.path.join(IMG, f)); c.drawImage(r, 54.7, H - (303.5 if i == 0 else 562.5), 376.6, 251)
        c.setFont('Mono', 6.6); c.drawCentredString(W / 2, H - 588, smart(f'EXHIBIT {n:02d} · {CH[n]}').upper())
    return fn

def ledgerpage(c):
    c.drawImage(ImageReader(os.path.join(IMG, 'logo.png')), 191, H - 153, 104, 108.9)
    cb(c, 'THE RECEIPTS LEDGER', 474.9, 'Mono-Bold', 7.5)
    cb(c, 'CHECK THE RECEIPTS', 430.1, 'Anton', 30)
    c.rect(222, H - 221.4, 42, 1.4, stroke=0, fill=1)
    ids = sorted(int(r['fac'][4:]) for r in LED); hi = max(ids); retired = hi - len(ids)
    cb(c, f'{len(LED)} documented events.', 398.6, 'Lora', 11)
    cb(c, f'FAC-001 through FAC-{hi:03d}' + (f'; {retired} numbers retired.' if retired else '.'), 383.1, 'Lora', 11)
    rows = [('ESTABLISHED', 'Fixed by a primary document: court record, guilty plea, IG report, sworn testimony, or authenticated record.'),
            ('STRONG', 'Documented in primary records with limited interpretive distance.'),
            ('SUPPORTED', 'Rests on pattern-based or secondary corroboration rather than a single flagship document.')]
    y = 283; st = ParagraphStyle('lt', fontName='Lora', fontSize=8.6, leading=12)
    for i, (k, v) in enumerate(rows):
        c.setFont('Mono-Bold', 7); c.drawString(82, H - y - 7, k)
        h = para_at(c, v, st, 164, y - 1, 236)
        if i < 2:
            c.setStrokeColor(colors.Color(.55, .55, .55)); c.setLineWidth(.5); c.line(82, H - (y + 30.4), 404, H - (y + 30.4)); c.setStrokeColor(colors.black)
        y += 35
    w = qr.QrCodeWidget('https://thenarrativeforgery.github.io/#ledger'); b = w.getBounds(); sz = 64
    d = Drawing(sz, sz, transform=[sz / (b[2] - b[0]), 0, 0, sz / (b[3] - b[1]), 0, 0]); d.add(w)
    renderPDF.draw(d, c, W / 2 - sz / 2, H - 467)
    cb(c, 'thenarrativeforgery.github.io', 154.5, 'Mono-Bold', 10.5)
    para_at(c, 'The full ledger lives online: search by event, chapter, FAC number, or notes, and filter by tier and chapter.',
            ParagraphStyle('o', fontName='Mono', fontSize=7, leading=9.5, alignment=TA_CENTER), 40, 497, 406)
    cb(c, 'THE RECEIPTS ARE THE ARGUMENT', 102.0, 'Anton', 11)
    cb(c, 'The Narrative Forgery — A Book of Receipts, 2016–2026', 88.2, 'Mono', 7)
    cb(c, f'Compiled {COMPILED} from the live text of thenarrativeforgery.github.io.', 71.7, 'Mono', 7)
    cb(c, '© 2026 The Narrative Forgery. All rights reserved.', 55.2, 'Mono', 7)

# ───────────────────────────── prose → flowables ─────────────────────────────
def prose(text, skip_first_label=False):
    out = []; lead = False
    paras = [p.strip() for p in re.split(r'\n\n+', text) if p.strip()]
    for i, raw in enumerate(paras):
        lines = [l.strip() for l in raw.split('\n')]
        if all(re.match(r'^\*\s', l) for l in lines):
            for l in lines: out.append(Paragraph(linkify(esc(re.sub(r'^\*\s+', '', l))), ST['bullet'], bulletText='•'))
            continue
        p = ' '.join(lines)
        label = len(p) < 100 and re.sub(r'\bMc(?=[A-Z])', 'MC', p) == p.upper() and re.search('[A-Z]', p)
        if label and i == 0:
            if not skip_first_label: out.append(Paragraph(esc(p), ST['dateline']))
            continue
        if label:
            out.append(CondPageBreak(90)); out.append(Spacer(1, 10)); out.append(Rule()); out.append(Paragraph(esc(p), ST['sub'])); continue
        if re.match(r'^["“]', p) and re.search(r'["”][\s.]*$', p) and len(p) < 400:
            out.append(Paragraph(linkify(esc(p)), ST['quote'])); continue
        if not lead:
            lead = True; out.append(Paragraph(linkify(esc(p)), ST['lead'])); continue
        out.append(Paragraph(linkify(esc(p)), ST['body']))
    return out

def opening(kicker, title, box=None, mark=None, header=None, vol=None):
    f = [State(title=header or title, vol=vol, opening=True, mark=mark), Spacer(1, 48),
         Paragraph(esc(kicker), ST['kicker']), Spacer(1, 4), Paragraph(esc(title.upper()), ST['title']), Spacer(1, 4), Rule(30, 2, 6)]
    if box: f += [Spacer(1, 8), box, Spacer(1, 12)]
    else: f += [Spacer(1, 14)]
    return f

def mech_names_for(n):
    return [m['title'] for m in MS if n in m['chapters']]

PREFATORY = ["This compendium exists because the preceding eighteen chapters have documented something more significant than a series of political disputes or media failures. They showed the systematic deployment of specific, named, academically documented psychological mechanisms against the minds, and resulting worldview, of an entire population — mechanisms whose effects are not metaphorical but neurobiological, whose consequences are not merely political but structural, and whose reversal requires understanding not merely what was done but precisely how it was done and why the brain could not resist it.",
             "The mechanisms described here are not theories invented to explain the preceding chapters’ findings. They are established constructs from cognitive psychology, social psychology, behavioral neuroscience, and radicalization research — documented in peer-reviewed literature, replicated across experimental conditions, and cited in academic contexts entirely unrelated to the political events this document examines. They are presented as an analytical framework for understanding why the operations documented in the preceding chapters worked — why millions of intelligent, educated, engaged citizens processed fabricated narratives as established fact, why documented primary source contradictions failed to dislodge entrenched beliefs, and why the most analytically sophisticated individuals were in many cases the most resistant to correction.",
             "Understanding the machinery’s psychological architecture is not an academic exercise. It is the prerequisite for dismantling it."]

EXHIBITS = {n: [f'exhibit-{n:02d}.jpg'] for n in range(1, 19)}
EXHIBITS[11] = ['exhibit-11a.jpg', 'exhibit-11b.jpg']
MECH_IMG = {n: f'mechanism-{n:02d}.jpg' for n in (1, 2, 3, 4, 5, 6, 7, 9)}

def story():
    f = [FullPage(cover), PageBreak(), FullPage(titlepage), PageBreak()]
    # contents
    f += [State(title=None, vol=1), Spacer(1, 14), Paragraph('TABLE OF CONTENTS', ParagraphStyle('toc', fontName='Anton', fontSize=20, leading=26)), Spacer(1, 18)]
    f += [TOCLine('Introduction', 'intro', bold=True, gap=13), TOCLine('Volume One — The Narrative Forgery', 'vol1', bold=True)]
    for n in range(1, 19): f.append(TOCLine(f'Chapter {n:02d} · {CH[n]}', f'ch{n}', indent=12))
    f.append(PageBreak())
    f += [TOCLine('Volume Two — The Neural Architecture of Deception', 'vol2', bold=True), TOCLine('Prefatory Note', 'pref', indent=12)]
    for m in MS: f.append(TOCLine(f'Mechanism {m["n"]:02d} · {m["title"]}', f'm{m["n"]}', indent=12))
    f += [Spacer(1, 14), TOCLine('Check the Receipts', 'ledger', bold=True), PageBreak()]
    # introduction
    f += opening('FRONT MATTER', 'Introduction', mark='intro', vol=1) + prose(INTRO, skip_first_label=True)
    f += [Img(os.path.join(IMG, 'seal.png'), 62, 62, 22), PageBreak()]
    # volume one
    f += [State(mark='vol1'), FullPage(vol1page), PageBreak()]
    for n in range(1, 19):
        f += [FullPage(exhibit(n, EXHIBITS[n])), PageBreak()]
        names = ' · '.join(esc(x) for x in mech_names_for(n))
        box = Box('MECHANISMS DEPLOYED', names, ST['boxtext']) if names else None
        f += opening(f'CHAPTER {n:02d}', CH[n], box, mark=f'ch{n}', header=CH[n], vol=1) + prose(CT[str(n)]) + [PageBreak()]
    # volume two
    f += [State(mark='vol2', vol=2), FullPage(vol2cover), PageBreak()]
    f += opening('VOLUME TWO · THE NEURAL ARCHITECTURE OF DECEPTION', 'Prefatory Note', mark='pref', header='Prefatory Note', vol=2)
    f += [Paragraph(esc(PREFATORY[0]), ST['lead'])] + [Paragraph(esc(p), ST['body']) for p in PREFATORY[1:]] + [PageBreak()]
    for m in MS:
        n = m['n']; d = MF[str(n)]
        box = Box('CROSS-REFERENCED IN', 'Chapters ' + ' · '.join(f'{c:02d}' for c in m['chapters']), ST['boxtext2'])
        f += opening(f'MECHANISM {n:02d}', m['title'], box, mark=f'm{n}', header=m['title'], vol=2)
        if n in MECH_IMG: f.append(Img(os.path.join(IMG, MECH_IMG[n]), 234, 290, 4))
        f += [Paragraph(linkify(esc(p)), ST['body']) for p in d['def']]
        for head, items, st in [('NEURAL BASIS', [d['neural']], ST['body']),
                                ('CHAPTER DOCUMENTATION & REAL-WORLD APPLICATION', d['chapterDocs'], ST['body']),
                                ('PRIMARY ACADEMIC SOURCES', d['sources'], ST['src'])]:
            f += [CondPageBreak(90), Spacer(1, 10), Rule(), Paragraph(esc(head), ST['sub'])]
            f += [Paragraph(linkify(esc(x)), st) for x in items]
        f.append(PageBreak())
    f += [State(mark='ledger', title=None), FullPage(ledgerpage)]
    return f

def vol1page(c):
    cb(c, 'VOLUME ONE', 481.2, 'Mono-Bold', 7.5)
    cb(c, 'THE NARRATIVE', 427.7, 'Anton', 32); cb(c, 'FORGERY', 391.7, 'Anton', 32)
    cmix(c, [('A Book ', 'Lora'), ('of', 'Lora-Italic'), (' Receipts · 18 Chapters', 'Lora')], 376.2, 11)
    c.rect(228, H - 287.2, 30, 1.4, stroke=0, fill=1)
    c.drawImage(ImageReader(os.path.join(IMG, 'logo.png')), 158, H - 487.2, 170, 178)

MARKS = {}; PAGES = {}
def build(path):
    doc = BaseDocTemplate(path, pagesize=(W, H), leftMargin=LM, rightMargin=W - RM, topMargin=62, bottomMargin=73,
                          title='The Narrative Forgery: A Book of Receipts (2016–2026)', author='Zach',
                          subject='A primary-source book on convergent institutional narrative management, with the Neural Architecture of Deception compendium',
                          keywords='The Narrative Forgery, receipts, compendium, mechanisms', creator='The Narrative Forgery')
    frame = Frame(LM, 73, RM - LM, H - 62 - 73, id='body', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate('main', frames=[frame], onPageEnd=on_page_end)])
    doc.build(story())

tmp = OUT + '.pass1.pdf'
build(tmp); PAGES.update(MARKS); MARKS.clear()
build(OUT); os.remove(tmp)
assert MARKS == PAGES, 'pagination moved between passes'
print(f'Wrote {OUT}: {MARKS["ledger"]} pages, {len(LED)} receipts, compiled {COMPILED}.')
