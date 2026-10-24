import os
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

def build_presentation():
    prs = pptx.Presentation()
    # 16:9 Widescreen standard
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Color Palette - Command Center Theme
    BG_COLOR = RGBColor(7, 10, 19)          # #070A13
    CARD_BG = RGBColor(15, 23, 42)          # #0F172A
    CARD_BORDER = RGBColor(33, 49, 79)      # #21314F
    CYAN = RGBColor(0, 240, 255)            # #00F0FF
    BLUE = RGBColor(56, 189, 248)           # #38BDF8
    PURPLE = RGBColor(167, 139, 250)        # #A78BFA
    GREEN = RGBColor(52, 211, 153)          # #34D399
    RED = RGBColor(239, 68, 68)             # #EF4444
    AMBER = RGBColor(251, 191, 36)          # #FBBF24
    TEXT_WHITE = RGBColor(248, 250, 252)    # #F8FAFC
    TEXT_MUTED = RGBColor(148, 163, 184)    # #94A3B8
    TEXT_DARK = RGBColor(100, 116, 139)     # #64748B

    def set_slide_background(slide):
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = BG_COLOR

    def add_header(slide, section_tag, page_str):
        # Logo dot
        dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.8), Inches(0.42), Inches(0.12), Inches(0.12))
        dot.fill.solid()
        dot.fill.fore_color.rgb = CYAN
        dot.line.fill.background()

        # Logo text
        tx = slide.shapes.add_textbox(Inches(1.0), Inches(0.32), Inches(2.5), Inches(0.35))
        tf = tx.text_frame
        tf.word_wrap = False
        p = tf.paragraphs[0]
        p.text = "TRACEHEAL"
        p.font.name = "Arial"
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE

        # Section Pill
        pill = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5.2), Inches(0.35), Inches(2.9), Inches(0.32))
        pill.fill.solid()
        pill.fill.fore_color.rgb = RGBColor(18, 28, 48)
        pill.line.color.rgb = CARD_BORDER
        ptx = pill.text_frame
        ptx.word_wrap = False
        pp = ptx.paragraphs[0]
        pp.alignment = PP_ALIGN.CENTER
        pp.text = section_tag
        pp.font.name = "Arial"
        pp.font.size = Pt(9.5)
        pp.font.bold = True
        pp.font.color.rgb = TEXT_MUTED

        # Page Counter
        ctx = slide.shapes.add_textbox(Inches(11.8), Inches(0.32), Inches(0.8), Inches(0.35))
        cp = ctx.text_frame.paragraphs[0]
        cp.alignment = PP_ALIGN.RIGHT
        cp.text = page_str
        cp.font.name = "Consolas"
        cp.font.size = Pt(11)
        cp.font.bold = True
        cp.font.color.rgb = CYAN

        # Top divider line
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(0.78), Inches(11.733), Inches(0.015))
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(26, 38, 64)
        line.line.fill.background()

    def add_footer(slide, sub_label):
        # Bottom divider line
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(6.85), Inches(11.733), Inches(0.015))
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(26, 38, 64)
        line.line.fill.background()

        # Left footer text
        tx_left = slide.shapes.add_textbox(Inches(0.8), Inches(6.92), Inches(4.5), Inches(0.3))
        p_left = tx_left.text_frame.paragraphs[0]
        p_left.text = "TRACEHEAL ARCHITECTURAL WHITEPAPER"
        p_left.font.name = "Arial"
        p_left.font.size = Pt(9)
        p_left.font.color.rgb = TEXT_DARK

        # Center footer text
        tx_mid = slide.shapes.add_textbox(Inches(4.5), Inches(6.92), Inches(4.3), Inches(0.3))
        p_mid = tx_mid.text_frame.paragraphs[0]
        p_mid.alignment = PP_ALIGN.CENTER
        p_mid.text = sub_label.upper()
        p_mid.font.name = "Arial"
        p_mid.font.size = Pt(9)
        p_mid.font.color.rgb = TEXT_DARK

        # Right footer text
        tx_rt = slide.shapes.add_textbox(Inches(9.2), Inches(6.92), Inches(3.33), Inches(0.3))
        p_rt = tx_rt.text_frame.paragraphs[0]
        p_rt.alignment = PP_ALIGN.RIGHT
        p_rt.text = "HACKYARD BUILD 2026 • IIT GUWAHATI"
        p_rt.font.name = "Arial"
        p_rt.font.size = Pt(9)
        p_rt.font.color.rgb = TEXT_DARK

    def add_titles(slide, badge_str, title_str, subtitle_str):
        # Badge
        badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(0.95), Inches(2.8), Inches(0.28))
        badge.fill.solid()
        badge.fill.fore_color.rgb = RGBColor(0, 40, 60)
        badge.line.color.rgb = CYAN
        bp = badge.text_frame.paragraphs[0]
        bp.alignment = PP_ALIGN.CENTER
        bp.text = badge_str
        bp.font.name = "Arial"
        bp.font.size = Pt(8.5)
        bp.font.bold = True
        bp.font.color.rgb = CYAN

        # Title
        ttx = slide.shapes.add_textbox(Inches(0.8), Inches(1.28), Inches(11.733), Inches(0.55))
        tp = ttx.text_frame.paragraphs[0]
        tp.text = title_str
        tp.font.name = "Arial"
        tp.font.size = Pt(22)
        tp.font.bold = True
        tp.font.color.rgb = TEXT_WHITE

        # Subtitle
        stx = slide.shapes.add_textbox(Inches(0.8), Inches(1.85), Inches(11.733), Inches(0.38))
        sp = stx.text_frame.paragraphs[0]
        sp.text = subtitle_str
        sp.font.name = "Arial"
        sp.font.size = Pt(11)
        sp.font.color.rgb = TEXT_MUTED

    # =========================================================================
    # SLIDE 1: COVER
    # =========================================================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_background(s1)

    # Top brand bar
    dot1 = s1.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.8), Inches(0.5), Inches(0.14), Inches(0.14))
    dot1.fill.solid()
    dot1.fill.fore_color.rgb = CYAN
    dot1.line.fill.background()

    htx = s1.shapes.add_textbox(Inches(1.05), Inches(0.42), Inches(4.0), Inches(0.35))
    hp = htx.text_frame.paragraphs[0]
    hp.text = "HACKYARD BUILD 2026"
    hp.font.name = "Consolas"
    hp.font.size = Pt(11)
    hp.font.bold = True
    hp.font.color.rgb = TEXT_MUTED

    tag1 = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(10.2), Inches(0.42), Inches(2.333), Inches(0.32))
    tag1.fill.solid()
    tag1.fill.fore_color.rgb = RGBColor(18, 28, 48)
    tag1.line.color.rgb = CARD_BORDER
    tag1.text_frame.paragraphs[0].text = "ROUND 1 IDEA SUBMISSION"
    tag1.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    tag1.text_frame.paragraphs[0].font.size = Pt(9)
    tag1.text_frame.paragraphs[0].font.bold = True
    tag1.text_frame.paragraphs[0].font.color.rgb = TEXT_MUTED

    # Center Hero
    hero_badge = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(4.7), Inches(1.3), Inches(3.933), Inches(0.32))
    hero_badge.fill.solid()
    hero_badge.fill.fore_color.rgb = RGBColor(0, 40, 60)
    hero_badge.line.color.rgb = CYAN
    hero_badge.text_frame.paragraphs[0].text = "AUTONOMOUS CLOUD RELIABILITY SYSTEM"
    hero_badge.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    hero_badge.text_frame.paragraphs[0].font.size = Pt(9.5)
    hero_badge.text_frame.paragraphs[0].font.bold = True
    hero_badge.text_frame.paragraphs[0].font.color.rgb = CYAN

    title_box = s1.shapes.add_textbox(Inches(1.5), Inches(1.75), Inches(10.333), Inches(1.0))
    tp1 = title_box.text_frame.paragraphs[0]
    tp1.alignment = PP_ALIGN.CENTER
    tp1.text = "TRACEHEAL"
    tp1.font.name = "Arial"
    tp1.font.size = Pt(48)
    tp1.font.bold = True
    tp1.font.color.rgb = TEXT_WHITE

    sub_box = s1.shapes.add_textbox(Inches(1.5), Inches(2.75), Inches(10.333), Inches(0.45))
    sp1 = sub_box.text_frame.paragraphs[0]
    sp1.alignment = PP_ALIGN.CENTER
    sp1.text = "Autonomous Incident Investigation & Shadow-Verified Remediation for Microservices"
    sp1.font.name = "Arial"
    sp1.font.size = Pt(14)
    sp1.font.color.rgb = TEXT_MUTED

    # Mantra pill
    mantra = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(4.3), Inches(3.3), Inches(4.733), Inches(0.42))
    mantra.fill.solid()
    mantra.fill.fore_color.rgb = RGBColor(15, 23, 42)
    mantra.line.color.rgb = CYAN
    mp = mantra.text_frame.paragraphs[0]
    mp.alignment = PP_ALIGN.CENTER
    mp.text = "Trace it.   •   Reproduce it.   •   Verify it.   •   Heal it."
    mp.font.name = "Arial"
    mp.font.size = Pt(12)
    mp.font.bold = True
    mp.font.color.rgb = CYAN

    # Flow Cards on Cover (5 cards)
    flow_items = [
        ("ALERT", "Microservices", "Incident Storm", RED),
        ("OTel", "Distributed", "Span DAG Tree", BLUE),
        ("AGENT", "Causal Engine", "Hypothesis Gen", CYAN),
        ("TEST", "Shadow", "Docker Sandbox", PURPLE),
        ("PR", "Verified", "Safe Patch Delivery", GREEN),
    ]
    card_w = Inches(2.1)
    card_h = Inches(1.4)
    gap = Inches(0.3)
    start_x = Inches(0.8)
    for i, (tag, t1, t2, col) in enumerate(flow_items):
        cx = start_x + i * (card_w + gap)
        c_shape = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(4.1), card_w, card_h)
        c_shape.fill.solid()
        c_shape.fill.fore_color.rgb = CARD_BG
        c_shape.line.color.rgb = col
        c_shape.line.width = Pt(1.5)

        tf = c_shape.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p0 = tf.paragraphs[0]
        p0.alignment = PP_ALIGN.CENTER
        p0.text = tag
        p0.font.name = "Consolas"
        p0.font.size = Pt(12)
        p0.font.bold = True
        p0.font.color.rgb = col

        p1 = tf.add_paragraph()
        p1.alignment = PP_ALIGN.CENTER
        p1.text = t1
        p1.font.name = "Arial"
        p1.font.size = Pt(10)
        p1.font.bold = True
        p1.font.color.rgb = TEXT_WHITE

        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        p2.text = t2
        p2.font.name = "Arial"
        p2.font.size = Pt(8.5)
        p2.font.color.rgb = TEXT_MUTED

    # Bottom Meta Cards (3 columns)
    meta_box = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(5.8), Inches(11.733), Inches(0.9))
    meta_box.fill.solid()
    meta_box.fill.fore_color.rgb = RGBColor(12, 19, 36)
    meta_box.line.color.rgb = CARD_BORDER

    # Column 1
    m1 = s1.shapes.add_textbox(Inches(1.1), Inches(5.9), Inches(3.6), Inches(0.65))
    m1.text_frame.paragraphs[0].text = "TRACK ALIGNMENT"
    m1.text_frame.paragraphs[0].font.size = Pt(8.5)
    m1.text_frame.paragraphs[0].font.bold = True
    m1.text_frame.paragraphs[0].font.color.rgb = TEXT_DARK
    p = m1.text_frame.add_paragraph()
    p.text = "AI Agents • Developer Tools • Cloud SRE"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = TEXT_WHITE

    # Column 2
    m2 = s1.shapes.add_textbox(Inches(5.0), Inches(5.9), Inches(3.6), Inches(0.65))
    m2.text_frame.paragraphs[0].text = "PHYSICAL FINALE"
    m2.text_frame.paragraphs[0].font.size = Pt(8.5)
    m2.text_frame.paragraphs[0].font.bold = True
    m2.text_frame.paragraphs[0].font.color.rgb = TEXT_DARK
    p = m2.text_frame.add_paragraph()
    p.text = "IIT Guwahati (24–25 Oct 2026)"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = TEXT_WHITE

    # Column 3
    m3 = s1.shapes.add_textbox(Inches(9.2), Inches(5.9), Inches(3.0), Inches(0.65))
    m3.text_frame.paragraphs[0].text = "TEAM CODE"
    m3.text_frame.paragraphs[0].font.size = Pt(8.5)
    m3.text_frame.paragraphs[0].font.bold = True
    m3.text_frame.paragraphs[0].font.color.rgb = TEXT_DARK
    p = m3.text_frame.add_paragraph()
    p.text = "HYB-BUILD2026"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = CYAN

    # =========================================================================
    # SLIDE 2: THE PROBLEM
    # =========================================================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_background(s2)
    add_header(s2, "01 • THE PROBLEM", "02 / 12")
    add_titles(s2, "CRITICAL ENTERPRISE PAIN POINT", "When Production Breaks, Engineers Don't Get One Alert.", "A single downstream failure triggers a cascading alert storm across distributed architectures, paralyzing on-call teams.")
    add_footer(s2, "Systemic Operational Deficits")

    # Flow Banner showing microservice chain
    chain_w = Inches(2.1)
    chain_h = Inches(0.9)
    chain_items = [
        ("Client Web", "Ingress Traffic", CARD_BORDER, TEXT_MUTED),
        ("API Gateway", "504 Gateway T/O", RED, RED),
        ("Order Service", "500 Internal Err", RED, RED),
        ("Payment API", "Retry Storm", RED, RED),
        ("Postgres DB", "ROOT CAUSE: Pool Full", RED, AMBER),
    ]
    for i, (svc, err, border_c, txt_c) in enumerate(chain_items):
        cx = Inches(0.8) + i * (chain_w + Inches(0.3))
        box = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(2.35), chain_w, chain_h)
        box.fill.solid()
        box.fill.fore_color.rgb = CARD_BG
        box.line.color.rgb = border_c
        box.line.width = Pt(1.5)
        tf = box.text_frame
        tf.paragraphs[0].text = svc
        tf.paragraphs[0].font.size = Pt(10)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].font.color.rgb = TEXT_WHITE
        p = tf.add_paragraph()
        p.text = err
        p.font.size = Pt(8.5)
        p.font.color.rgb = txt_c

    # Blast Radius Red Banner
    blast = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(3.4), Inches(11.733), Inches(0.55))
    blast.fill.solid()
    blast.fill.fore_color.rgb = RGBColor(40, 15, 20)
    blast.line.color.rgb = RED
    btf = blast.text_frame
    btf.paragraphs[0].alignment = PP_ALIGN.CENTER
    btf.paragraphs[0].text = "ALERT BLAST RADIUS: 48 CRITICAL ALERTS FIRED SIMULTANEOUSLY ACROSS 4 SERVICES"
    btf.paragraphs[0].font.name = "Consolas"
    btf.paragraphs[0].font.size = Pt(10)
    btf.paragraphs[0].font.bold = True
    btf.paragraphs[0].font.color.rgb = RED
    bp2 = btf.add_paragraph()
    bp2.alignment = PP_ALIGN.CENTER
    bp2.text = "Engineers spend 45+ minutes determining: 'Which alert is the symptom, and which is the root cause?'"
    bp2.font.size = Pt(9)
    bp2.font.color.rgb = TEXT_MUTED

    # 3 Problem Cards
    card_w3 = Inches(3.75)
    card_h3 = Inches(1.75)
    p_cards = [
        ("1. Cascading Fallouts", "Alert Storm", "Modern architectures are tightly coupled. When one microservice throttles, upstream callers queue requests, trigger retry storms, and throw secondary 504 timeouts. The engineer sees 50 screaming monitors.", RED),
        ("2. Symptom ≠ Cause", "Noise & Latency", "The service reporting the alert is almost never where the problem originated. SREs waste critical minutes inspecting API gateway logs when the true bug is a connection leak four network hops deep.", RED),
        ("3. The MTTR Clock", "High Downtime Cost", "During an active outage, downtime costs thousands of dollars per minute. Manual log grepping and trace correlation is slow, stressful, and leads to extreme team fatigue and repeated regressions.", RED),
    ]
    for i, (head, badge_t, desc, col) in enumerate(p_cards):
        cx = Inches(0.8) + i * (card_w3 + Inches(0.24))
        c = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(4.1), card_w3, card_h3)
        c.fill.solid()
        c.fill.fore_color.rgb = CARD_BG
        c.line.color.rgb = col
        ctf = c.text_frame
        ctf.paragraphs[0].text = head + f"  [{badge_t}]"
        ctf.paragraphs[0].font.size = Pt(11)
        ctf.paragraphs[0].font.bold = True
        ctf.paragraphs[0].font.color.rgb = TEXT_WHITE
        p = ctf.add_paragraph()
        p.text = desc
        p.font.size = Pt(9.5)
        p.font.color.rgb = TEXT_MUTED

    # Bottom SRE stat callout
    stat = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(6.0), Inches(11.733), Inches(0.7))
    stat.fill.solid()
    stat.fill.fore_color.rgb = RGBColor(12, 19, 36)
    stat.line.color.rgb = RED
    stf = stat.text_frame
    stf.paragraphs[0].text = "THE SRE REALITY TODAY:  Out of an average 45-minute incident, 40+ minutes are spent locating the root cause. Applying the fix takes only 3 minutes."
    stf.paragraphs[0].font.size = Pt(10)
    stf.paragraphs[0].font.bold = True
    stf.paragraphs[0].font.color.rgb = TEXT_WHITE
    sp2 = stf.add_paragraph()
    sp2.text = "88% OF MTTR is pure manual investigation toil that can be automated through causal trace parsing."
    sp2.font.size = Pt(9)
    sp2.font.color.rgb = CYAN

    # =========================================================================
    # SLIDE 3: THE GAP
    # =========================================================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_background(s3)
    add_header(s3, "02 • THE INDUSTRY GAP", "03 / 12")
    add_titles(s3, "WHY AIOPS CURRENTLY FALLS SHORT", "The Problem With 'AI-Powered' Incident Response", "Diagnosis is not the same as verified diagnosis. Treating probabilistic text as ground truth endangers mission-critical systems.")
    add_footer(s3, "Industry Deficiencies & The Verification Gap")

    # 2 Comparison Columns
    col_w = Inches(5.75)
    col_h = Inches(3.1)

    # Left: Traditional AI
    left_c = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.35), col_w, col_h)
    left_c.fill.solid()
    left_c.fill.fore_color.rgb = CARD_BG
    left_c.line.color.rgb = RED
    ltf = left_c.text_frame
    ltf.paragraphs[0].text = "TRADITIONAL AIOPS PIPELINE  [Unverified / High Risk]"
    ltf.paragraphs[0].font.size = Pt(11.5)
    ltf.paragraphs[0].font.bold = True
    ltf.paragraphs[0].font.color.rgb = RED

    lines_l = [
        "• Alert Storm Triggered across microservices",
        "• Raw logs and metrics concatenated into an LLM prompt",
        "• AI Summarizes Text: 'Looks like a database deadlock'",
        "• Unverified Advice: 'Restart the primary PostgreSQL node'",
        "• SRE executes recommendation in production ➔ OUTAGE WORSENS",
        "",
        "THE FATAL FLAW: HALLUCINATED REMEDIATION",
        "Incumbents (Datadog Bits AI, PagerDuty Advance) remain strictly read-only chatbots because unverified execution introduces existential enterprise liability.",
    ]
    for line in lines_l:
        p = ltf.add_paragraph()
        p.text = line
        p.font.size = Pt(9)
        p.font.color.rgb = TEXT_MUTED if not line.startswith("THE FATAL") else AMBER

    # Right: TraceHeal Closed Loop
    rt_c = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.78), Inches(2.35), col_w, col_h)
    rt_c.fill.solid()
    rt_c.fill.fore_color.rgb = CARD_BG
    rt_c.line.color.rgb = GREEN
    rtf = rt_c.text_frame
    rtf.paragraphs[0].text = "TRACEHEAL VERIFICATION PIPELINE  [Empirical / Closed-Loop]"
    rtf.paragraphs[0].font.size = Pt(11.5)
    rtf.paragraphs[0].font.bold = True
    rtf.paragraphs[0].font.color.rgb = GREEN

    lines_r = [
        "• Alert + OpenTelemetry Distributed Span DAG ingested",
        "• Topological Causal Analysis isolates earliest failing span",
        "• Causal Hypothesis formulated & bound to git commit context",
        "• Ephemeral Docker Sandbox spun up with synthetic failure payload",
        "• Empirical Verification: Container exits with 500 error ➔ BUG REPRODUCED",
        "• Patch tested inside sandbox ➔ Unit/regression tests return 200 OK",
        "",
        "THE TRACEHEAL ADVANTAGE: PROOF BEFORE TOUCH",
        "An AI diagnosis is treated as an unconfirmed hypothesis until proven in an isolated container. Compilers and test runners act as ground truth arbiters.",
    ]
    for line in lines_r:
        p = rtf.add_paragraph()
        p.text = line
        p.font.size = Pt(9)
        p.font.color.rgb = TEXT_MUTED if not line.startswith("THE TRACEHEAL") else CYAN

    # Bottom Incumbent Matrix Summary
    matrix = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(5.6), Inches(11.733), Inches(1.1))
    matrix.fill.solid()
    matrix.fill.fore_color.rgb = RGBColor(12, 19, 36)
    matrix.line.color.rgb = CYAN
    mtf = matrix.text_frame
    mtf.paragraphs[0].alignment = PP_ALIGN.CENTER
    mtf.paragraphs[0].text = "CORE TENET:  DIAGNOSIS ≠ VERIFIED DIAGNOSIS"
    mtf.paragraphs[0].font.name = "Consolas"
    mtf.paragraphs[0].font.size = Pt(12)
    mtf.paragraphs[0].font.bold = True
    mtf.paragraphs[0].font.color.rgb = CYAN
    mp = mtf.add_paragraph()
    mp.alignment = PP_ALIGN.CENTER
    mp.text = "\"AI can suggest a diagnosis. TraceHeal tests it before trusting it.\""
    mp.font.size = Pt(11)
    mp.font.italic = True
    mp.font.color.rgb = TEXT_WHITE

    # =========================================================================
    # SLIDE 4: MEET TRACEHEAL
    # =========================================================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_background(s4)
    add_header(s4, "03 • OUR SOLUTION", "04 / 12")
    add_titles(s4, "INTRODUCING TRACEHEAL", "Meet TraceHeal: Autonomous SRE Grounded in Evidence", "TraceHeal bridges the gap between distributed runtime tracing and isolated code execution to verify failures before remediation.")
    add_footer(s4, "Core Architectural Pillars")

    # 3 Pillar Cards
    p_w = Inches(3.75)
    p_h = Inches(3.1)
    pillars = [
        ("1. UNDERSTAND", "OpenTelemetry Standard", [
            "• Direct OTLP trace, metric, and log ingestion",
            "• W3C tracecontext parent-child span traversal",
            "• Zero vendor lock-in; works with any cloud stack",
            "• Reconstructs causal execution DAGs in real time",
            "• Pinpoints earliest failing boundary automatically"
        ], BLUE),
        ("2. VERIFY", "The Shadow Sandbox", [
            "• Ephemeral Docker container dynamically spawned",
            "• Synthesized minimal reproduction workload injected",
            "• Observes process exit codes, error logs, and metrics",
            "• Falsifies hallucinated hypotheses immediately",
            "• Backtracks to alternative candidates if refuted"
        ], PURPLE),
        ("3. SAFE ACTION", "Policy-Gated Delivery", [
            "• Candidate fix synthesized and tested in sandbox",
            "• Regression suite runs to verify zero side-effects",
            "• Delivered as a ready-to-merge GitHub Pull Request",
            "• Attached execution logs provide empirical proof",
            "• Zero direct production writes without human gate"
        ], GREEN),
    ]

    for i, (title_p, sub_p, bullets, col) in enumerate(pillars):
        cx = Inches(0.8) + i * (p_w + Inches(0.24))
        card = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(2.35), p_w, p_h)
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = col
        card.line.width = Pt(1.5)
        ctf = card.text_frame
        ctf.paragraphs[0].text = title_p
        ctf.paragraphs[0].font.size = Pt(13)
        ctf.paragraphs[0].font.bold = True
        ctf.paragraphs[0].font.color.rgb = col

        p = ctf.add_paragraph()
        p.text = sub_p
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE

        for b in bullets:
            bp = ctf.add_paragraph()
            bp.text = b
            bp.font.size = Pt(9)
            bp.font.color.rgb = TEXT_MUTED

    # Bottom Capabilities Grid
    grid_b = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(5.6), Inches(11.733), Inches(1.1))
    grid_b.fill.solid()
    grid_b.fill.fore_color.rgb = RGBColor(12, 19, 36)
    grid_b.line.color.rgb = CARD_BORDER
    gtf = grid_b.text_frame
    gtf.paragraphs[0].text = "CORE PLATFORM PRINCIPLE:"
    gtf.paragraphs[0].font.size = Pt(9.5)
    gtf.paragraphs[0].font.bold = True
    gtf.paragraphs[0].font.color.rgb = CYAN
    gp = gtf.add_paragraph()
    gp.text = "\"Don't just explain the incident. Verify the explanation.\" — TraceHeal turns SRE from reactive log reading into automated scientific inquiry."
    gp.font.size = Pt(11)
    gp.font.color.rgb = TEXT_WHITE

    # =========================================================================
    # SLIDE 5: HOW IT WORKS
    # =========================================================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_background(s5)
    add_header(s5, "04 • WORKFLOW LIFECYCLE", "05 / 12")
    add_titles(s5, "END-TO-END EXECUTION", "From Incident to Verified Recovery: The 8-Step Lifecycle", "An 8-stage closed-loop lifecycle that takes an unhandled production alert through rigorous empirical validation.")
    add_footer(s5, "System Execution Pipeline")

    # 8 Steps in 2 rows of 4 cards
    s_w = Inches(2.78)
    s_h = Inches(1.8)
    steps_data = [
        ("01", "DETECT", "Anomaly Ingestion", "Ingests streaming metric anomalies and alerts exceeding dynamic error thresholds.", CYAN),
        ("02", "CORRELATE", "Alert Deduplication", "Groups cascading multi-service alerts across dependency trees into a single incident.", CYAN),
        ("03", "TRACE", "Span DAG Traversal", "Traverses distributed trace DAGs to pinpoint the earliest failing span boundary.", CYAN),
        ("04", "HYPOTHESIZE", "Causal Reasoning", "Cross-references span metadata with recent Git commits to draft causal candidates.", AMBER),
        ("05", "REPRODUCE", "Shadow Sandbox", "Spins up an ephemeral Docker container and replays a synthetic failing workload.", PURPLE),
        ("06", "VERIFY", "Empirical Check", "Evaluates if the reproduction matches the failure signature; backtracks if disproven.", GREEN),
        ("07", "REMEDIATE", "Patch Synthesis", "Synthesizes a policy-controlled configuration update or targeted code patch.", GREEN),
        ("08", "VALIDATE", "Zero-Regression Gate", "Re-runs tests inside the sandbox to prove resolution before human PR creation.", GREEN),
    ]

    for i, (num, name, tag, desc, col) in enumerate(steps_data):
        row = i // 4
        c_idx = i % 4
        cx = Inches(0.8) + c_idx * (s_w + Inches(0.2))
        cy = Inches(2.35) + row * (s_h + Inches(0.2))

        c = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, cy, s_w, s_h)
        c.fill.solid()
        c.fill.fore_color.rgb = CARD_BG
        c.line.color.rgb = col
        c.line.width = Pt(1.3)

        ctf = c.text_frame
        ctf.paragraphs[0].text = f"{num} • {name}"
        ctf.paragraphs[0].font.name = "Consolas"
        ctf.paragraphs[0].font.size = Pt(11)
        ctf.paragraphs[0].font.bold = True
        ctf.paragraphs[0].font.color.rgb = col

        p1 = ctf.add_paragraph()
        p1.text = tag
        p1.font.size = Pt(9)
        p1.font.bold = True
        p1.font.color.rgb = TEXT_WHITE

        p2 = ctf.add_paragraph()
        p2.text = desc
        p2.font.size = Pt(8.5)
        p2.font.color.rgb = TEXT_MUTED

    # Bottom Flow bar
    flow_b = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(6.0), Inches(11.733), Inches(0.7))
    flow_b.fill.solid()
    flow_b.fill.fore_color.rgb = RGBColor(12, 19, 36)
    flow_b.line.color.rgb = CARD_BORDER
    ftf = flow_b.text_frame
    ftf.paragraphs[0].alignment = PP_ALIGN.CENTER
    ftf.paragraphs[0].text = "DETERMINISTIC CONVERGENCE GUARANTEE:"
    ftf.paragraphs[0].font.name = "Consolas"
    ftf.paragraphs[0].font.size = Pt(9.5)
    ftf.paragraphs[0].font.bold = True
    ftf.paragraphs[0].font.color.rgb = CYAN
    fp = ftf.add_paragraph()
    fp.alignment = PP_ALIGN.CENTER
    fp.text = "If Step 06 (Verify) fails to reproduce the bug in the sandbox, the engine backtracks to Step 04 (Hypothesize) to test the next candidate in the causal graph."
    fp.font.size = Pt(9.5)
    fp.font.color.rgb = TEXT_WHITE

    # =========================================================================
    # SLIDE 6: AGENTIC ARCHITECTURE
    # =========================================================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_background(s6)
    add_header(s6, "05 • AGENTIC SYSTEM DESIGN", "06 / 12")
    add_titles(s6, "MULTI-AGENT COORDINATION", "A Team of Specialized AI Agents", "A monolithic LLM cannot handle incident response. TraceHeal coordinates specialized agents over a shared blackboard state graph.")
    add_footer(s6, "Multi-Agent State Orchestration")

    # Blackboard Banner
    bb = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.35), Inches(11.733), Inches(0.65))
    bb.fill.solid()
    bb.fill.fore_color.rgb = RGBColor(11, 19, 43)
    bb.line.color.rgb = CYAN
    bbtf = bb.text_frame
    bbtf.paragraphs[0].alignment = PP_ALIGN.CENTER
    bbtf.paragraphs[0].text = "SHARED INCIDENT BLACKBOARD (LangGraph StateGraph)"
    bbtf.paragraphs[0].font.name = "Consolas"
    bbtf.paragraphs[0].font.size = Pt(11)
    bbtf.paragraphs[0].font.bold = True
    bbtf.paragraphs[0].font.color.rgb = CYAN
    bbp = bbtf.add_paragraph()
    bbp.alignment = PP_ALIGN.CENTER
    bbp.text = "telemetry_graph (Traces/Spans)  •  sandbox_state (Container ID & Exit Codes)  •  remediation_diff (Patch & PR URL)"
    bbp.font.size = Pt(9)
    bbp.font.color.rgb = TEXT_WHITE

    # 4 Analysis Agents + 3 Action Agents
    ag_w = Inches(3.75)
    ag_h = Inches(1.55)
    agents_info = [
        ("Triage Agent", "Alert Ingestion", "Deduplicates alert storms, suppresses redundant warnings, and initializes incident boundaries.", BLUE),
        ("Trace Intelligence Agent", "Span Traversal", "Queries OTel collector, walks the span tree backward, and flags the earliest failing service boundary.", BLUE),
        ("Root Cause Agent", "Causal Hypothesis", "Cross-references failing span metadata with recent Git commits to formulate ranked hypotheses.", BLUE),
        ("Sandbox Agent", "Ephemeral Docker", "Provisions container via Docker SDK, injects synthetic payload, and monitors stdout/stderr.", PURPLE),
        ("Remediation Agent", "Patch Drafting", "Synthesizes code edits, config tweaks, or resource updates directly inside the sandbox.", GREEN),
        ("Validation Agent", "Regression Tests", "Executes unit and integration test suites against patched container to confirm 200 OK recovery.", GREEN),
    ]

    for i, (aname, arole, adesc, col) in enumerate(agents_info):
        row = i // 3
        c_idx = i % 3
        cx = Inches(0.8) + c_idx * (ag_w + Inches(0.24))
        cy = Inches(3.15) + row * (ag_h + Inches(0.15))

        c = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, cy, ag_w, ag_h)
        c.fill.solid()
        c.fill.fore_color.rgb = CARD_BG
        c.line.color.rgb = col
        ctf = c.text_frame
        ctf.paragraphs[0].text = aname
        ctf.paragraphs[0].font.size = Pt(11)
        ctf.paragraphs[0].font.bold = True
        ctf.paragraphs[0].font.color.rgb = col

        p1 = ctf.add_paragraph()
        p1.text = f"Role: {arole}"
        p1.font.size = Pt(8.5)
        p1.font.bold = True
        p1.font.color.rgb = TEXT_WHITE

        p2 = ctf.add_paragraph()
        p2.text = adesc
        p2.font.size = Pt(8.5)
        p2.font.color.rgb = TEXT_MUTED

    # Bottom Agentic definition callout
    ag_callout = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(6.35), Inches(11.733), Inches(0.42))
    ag_callout.fill.solid()
    ag_callout.fill.fore_color.rgb = RGBColor(12, 19, 36)
    ag_callout.line.color.rgb = CYAN
    agtf = ag_callout.text_frame
    agtf.paragraphs[0].text = "WHY GENUINELY AGENTIC:  Not a single prompt. Agents execute an active perception-action loop against real execution environments."
    agtf.paragraphs[0].font.size = Pt(9)
    agtf.paragraphs[0].font.bold = True
    agtf.paragraphs[0].font.color.rgb = CYAN

    # =========================================================================
    # SLIDE 7: CORE INNOVATION
    # =========================================================================
    s7 = prs.slides.add_slide(blank_layout)
    set_slide_background(s7)
    add_header(s7, "06 • CORE INNOVATION", "07 / 12")
    add_titles(s7, "OUR UNFAIR ADVANTAGE", "The 'Proof Before Fix' Layer", "TraceHeal never assumes an AI diagnosis is correct. Every hypothesis must prove itself inside an isolated execution sandbox.")
    add_footer(s7, "Empirical Sandbox Falsification")

    # 4-Stage Horizontal Pipeline Card
    pipe_box = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.35), Inches(11.733), Inches(2.1))
    pipe_box.fill.solid()
    pipe_box.fill.fore_color.rgb = CARD_BG
    pipe_box.line.color.rgb = CYAN
    pipe_box.line.width = Pt(1.5)

    ptf = pipe_box.text_frame
    ptf.paragraphs[0].text = "THE SCIENTIFIC FALSIFICATION PIPELINE"
    ptf.paragraphs[0].font.name = "Consolas"
    ptf.paragraphs[0].font.size = Pt(11)
    ptf.paragraphs[0].font.bold = True
    ptf.paragraphs[0].font.color.rgb = CYAN

    # 4 Inner stages
    st_w = Inches(2.7)
    st_h = Inches(1.3)
    stages = [
        ("1. AI HYPOTHESIS", "\"Database connection pool exhausted due to unhandled timeout.\"", AMBER),
        ("2. THE QUESTION MARK", "Is it a hallucination or true root cause? Test required.", TEXT_WHITE),
        ("3. DOCKER SANDBOX", "$ replay --payload=burst.json\n[FAIL] 500 Connection Timeout", PURPLE),
        ("4. ROOT CAUSE PROVEN", "Error reproduced in isolation.\nHypothesis verified. Safe to patch.", GREEN),
    ]
    for i, (shead, sdesc, scol) in enumerate(stages):
        cx = Inches(1.0) + i * (st_w + Inches(0.2))
        sb = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(2.9), st_w, st_h)
        sb.fill.solid()
        sb.fill.fore_color.rgb = RGBColor(7, 10, 19)
        sb.line.color.rgb = scol
        stf = sb.text_frame
        stf.paragraphs[0].text = shead
        stf.paragraphs[0].font.size = Pt(9.5)
        stf.paragraphs[0].font.bold = True
        stf.paragraphs[0].font.color.rgb = scol
        sp = stf.add_paragraph()
        sp.text = sdesc
        sp.font.size = Pt(8.5)
        sp.font.color.rgb = TEXT_MUTED

    # 2 Explanatory Cards
    ec_w = Inches(5.75)
    ec_h = Inches(1.9)

    e1 = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(4.65), ec_w, ec_h)
    e1.fill.solid()
    e1.fill.fore_color.rgb = CARD_BG
    e1.line.color.rgb = CARD_BORDER
    e1.text_frame.paragraphs[0].text = "Compilers as Ground Truth Arbiters"
    e1.text_frame.paragraphs[0].font.size = Pt(11.5)
    e1.text_frame.paragraphs[0].font.bold = True
    e1.text_frame.paragraphs[0].font.color.rgb = TEXT_WHITE
    p = e1.text_frame.add_paragraph()
    p.text = "LLMs can invent nonexistent configuration keys or hallucinate APIs. But a Docker container executing the service's real binary cannot be tricked. If the generated test passes, it works; if it fails, the AI is immediately corrected."
    p.font.size = Pt(9.5)
    p.font.color.rgb = TEXT_MUTED

    e2 = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.78), Inches(4.65), ec_w, ec_h)
    e2.fill.solid()
    e2.fill.fore_color.rgb = CARD_BG
    e2.line.color.rgb = CARD_BORDER
    e2.text_frame.paragraphs[0].text = "Automatic Backtracking on Refutation"
    e2.text_frame.paragraphs[0].font.size = Pt(11.5)
    e2.text_frame.paragraphs[0].font.bold = True
    e2.text_frame.paragraphs[0].font.color.rgb = TEXT_WHITE
    p = e2.text_frame.add_paragraph()
    p.text = "When a sandbox test fails to reproduce the observed failure, TraceHeal does not force a fix. It marks the hypothesis REFUTED, iterates backward through the causal span graph, and tests the next candidate in line (maximum 3 cycles)."
    p.font.size = Pt(9.5)
    p.font.color.rgb = TEXT_MUTED

    # =========================================================================
    # SLIDE 8: SAFE REMEDIATION
    # =========================================================================
    s8 = prs.slides.add_slide(blank_layout)
    set_slide_background(s8)
    add_header(s8, "07 • SAFETY & GOVERNANCE", "08 / 12")
    add_titles(s8, "PRODUCTION SAFETY CONTROLS", "Self-Healing — Built With Enterprise Guardrails", "TraceHeal does not touch production unassisted. Every remediation passes through strict policy gates and canary validations.")
    add_footer(s8, "Enterprise Governance & Safety Controls")

    # Guardrail Flow Chart (Banner)
    g_box = s8.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.35), Inches(11.733), Inches(1.3))
    g_box.fill.solid()
    g_box.fill.fore_color.rgb = CARD_BG
    g_box.line.color.rgb = GREEN
    gtf = g_box.text_frame
    gtf.paragraphs[0].text = "THE ZERO-RISK DELIVERY PIPELINE"
    gtf.paragraphs[0].font.name = "Consolas"
    gtf.paragraphs[0].font.size = Pt(11)
    gtf.paragraphs[0].font.bold = True
    gtf.paragraphs[0].font.color.rgb = GREEN

    # 4 Flow steps inside
    gw = Inches(2.7)
    gh = Inches(0.7)
    gsteps = [
        ("1. AI Proposes Fix", "Config / Code Patch", CYAN),
        ("2. Policy Check", "Whitelisted operations", AMBER),
        ("3. Sandbox Gate", "100% tests pass in container", PURPLE),
        ("4. Human Approval", "Delivered as GitHub PR", GREEN),
    ]
    for i, (h, sub, col) in enumerate(gsteps):
        cx = Inches(1.0) + i * (gw + Inches(0.2))
        b = s8.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(2.8), gw, gh)
        b.fill.solid()
        b.fill.fore_color.rgb = RGBColor(7, 10, 19)
        b.line.color.rgb = col
        btf = b.text_frame
        btf.paragraphs[0].text = h
        btf.paragraphs[0].font.size = Pt(9.5)
        btf.paragraphs[0].font.bold = True
        btf.paragraphs[0].font.color.rgb = col
        p = btf.add_paragraph()
        p.text = sub
        p.font.size = Pt(8)
        p.font.color.rgb = TEXT_MUTED

    # 4 Safety Pillars
    sp_w = Inches(2.78)
    sp_h = Inches(2.6)
    spillars = [
        ("Pillar 1", "Sandbox First", "Zero code touches production without prior sandbox execution and regression test passes. High-risk actions occur only in ephemeral containers.", CYAN),
        ("Pillar 2", "Policy Bounds", "Destructive operations (table drops, volume deletions, IAM alterations) are blocked at the engine level. Only whitelisted actions are allowed.", AMBER),
        ("Pillar 3", "Human-Gated", "Delivered as a Pull Request. Requires explicit 1-click human merge or operator authorization. Truth is transparent and auditable.", GREEN),
        ("Pillar 4", "Instant Rollback", "Canary deployments monitor error rates and automatically roll back within milliseconds if anomalies recur in production.", RED),
    ]

    for i, (pnum, phead, pdesc, col) in enumerate(spillars):
        cx = Inches(0.8) + i * (sp_w + Inches(0.2))
        c = s8.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(3.85), sp_w, sp_h)
        c.fill.solid()
        c.fill.fore_color.rgb = CARD_BG
        c.line.color.rgb = col
        ctf = c.text_frame
        ctf.paragraphs[0].text = f"[{pnum}]"
        ctf.paragraphs[0].font.size = Pt(9)
        ctf.paragraphs[0].font.bold = True
        ctf.paragraphs[0].font.color.rgb = col
        p1 = ctf.add_paragraph()
        p1.text = phead
        p1.font.size = Pt(11.5)
        p1.font.bold = True
        p1.font.color.rgb = TEXT_WHITE
        p2 = ctf.add_paragraph()
        p2.text = pdesc
        p2.font.size = Pt(9)
        p2.font.color.rgb = TEXT_MUTED

    # =========================================================================
    # SLIDE 9: DEMO SCENARIO
    # =========================================================================
    s9 = prs.slides.add_slide(blank_layout)
    set_slide_background(s9)
    add_header(s9, "08 • 24-HOUR DEMO PROOF", "09 / 12")
    add_titles(s9, "REALISTIC LIVE DEMONSTRATION", "One Incident. End-to-End.", "A realistic demonstration resolving a payment service database connection pool bottleneck in under 90 seconds.")
    add_footer(s9, "Validation Benchmarks & Reference Demo")

    # Top Demo Topology Description
    top_c = s9.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(2.35), Inches(11.733), Inches(0.85))
    top_c.fill.solid()
    top_c.fill.fore_color.rgb = CARD_BG
    top_c.line.color.rgb = CYAN
    tctf = top_c.text_frame
    tctf.paragraphs[0].text = "DEMO TOPOLOGY & FAILURE INJECTION"
    tctf.paragraphs[0].font.name = "Consolas"
    tctf.paragraphs[0].font.size = Pt(10)
    tctf.paragraphs[0].font.bold = True
    tctf.paragraphs[0].font.color.rgb = CYAN
    p = tctf.add_paragraph()
    p.text = "A burst load of 10 concurrent transactions is fired at the Checkout API. The downstream Payment Service has a database connection pool limit of 2, leading to rapid pool starvation and cascading HTTP 500 errors across upstream services."
    p.font.size = Pt(9.5)
    p.font.color.rgb = TEXT_WHITE

    # Before vs After Metrics Cards
    m_w = Inches(5.75)
    m_h = Inches(1.6)

    # Before
    b_card = s9.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(3.35), m_w, m_h)
    b_card.fill.solid()
    b_card.fill.fore_color.rgb = CARD_BG
    b_card.line.color.rgb = RED
    btf = b_card.text_frame
    btf.paragraphs[0].text = "BEFORE TRACEHEAL  [Active Outage]"
    btf.paragraphs[0].font.size = Pt(11)
    btf.paragraphs[0].font.bold = True
    btf.paragraphs[0].font.color.rgb = RED
    p1 = btf.add_paragraph()
    p1.text = "HTTP 500 Errors: 38.4%   |   p99 Latency: 1,420ms   |   DB Pool: 100% (Locked)"
    p1.font.name = "Consolas"
    p1.font.size = Pt(10.5)
    p1.font.bold = True
    p1.font.color.rgb = RED
    p2 = btf.add_paragraph()
    p2.text = "*Illustrative demo metrics during simulated traffic burst"
    p2.font.size = Pt(8)
    p2.font.color.rgb = TEXT_DARK

    # After
    a_card = s9.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.78), Inches(3.35), m_w, m_h)
    a_card.fill.solid()
    a_card.fill.fore_color.rgb = CARD_BG
    a_card.line.color.rgb = GREEN
    atf = a_card.text_frame
    atf.paragraphs[0].text = "AFTER TRACEHEAL RESOLUTION  [Recovered & Verified]"
    atf.paragraphs[0].font.size = Pt(11)
    atf.paragraphs[0].font.bold = True
    atf.paragraphs[0].font.color.rgb = GREEN
    p1 = atf.add_paragraph()
    p1.text = "HTTP 500 Errors: 0.0%    |   p99 Latency: 42ms     |   DB Pool: 22% (Normal)"
    p1.font.name = "Consolas"
    p1.font.size = Pt(10.5)
    p1.font.bold = True
    p1.font.color.rgb = GREEN
    p2 = atf.add_paragraph()
    p2.text = "*Verified recovery confirmed by regression test suite inside sandbox"
    p2.font.size = Pt(8)
    p2.font.color.rgb = TEXT_DARK

    # Chronological Timeline
    time_c = s9.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(5.1), Inches(11.733), Inches(1.5))
    time_c.fill.solid()
    time_c.fill.fore_color.rgb = RGBColor(12, 19, 36)
    time_c.line.color.rgb = CARD_BORDER
    ttf = time_c.text_frame
    ttf.paragraphs[0].text = "CHRONOLOGICAL EXECUTION TIMELINE (90-SECOND RESOLUTION):"
    ttf.paragraphs[0].font.name = "Consolas"
    ttf.paragraphs[0].font.size = Pt(9.5)
    ttf.paragraphs[0].font.bold = True
    ttf.paragraphs[0].font.color.rgb = CYAN

    t_lines = [
        "[T+05s] Alert Ingested: Order Service reporting cascading HTTP 504 Gateway Timeouts.",
        "[T+18s] Trace Agent traverses OTel span graph: root exception pinned to Payment DB query.",
        "[T+34s] Sandbox Agent provisions isolated Docker replica of Payment Service.",
        "[T+52s] Replay reproduces exact connection pool timeout error in container stdout.",
        "[T+68s] Remediation Agent increases pool capacity and patches timeout handler in sandbox.",
        "[T+82s] Validation Agent executes regression test: 100% requests pass HTTP 200 OK.",
        "[T+90s] Ready-to-merge GitHub PR opened; Next.js dashboard topology turns green.",
    ]
    for tl in t_lines:
        p = ttf.add_paragraph()
        p.text = tl
        p.font.name = "Consolas"
        p.font.size = Pt(8.5)
        p.font.color.rgb = TEXT_MUTED if not tl.startswith("[T+90s]") else GREEN

    # =========================================================================
    # SLIDE 10: TECHNICAL ARCHITECTURE
    # =========================================================================
    s10 = prs.slides.add_slide(blank_layout)
    set_slide_background(s10)
    add_header(s10, "09 • SYSTEM ARCHITECTURE", "10 / 12")
    add_titles(s10, "ENGINEERING SPECIFICATION", "Under the Hood: Enterprise Cloud-Native Stack", "A standards-compliant architecture connecting OpenTelemetry collectors with Python agent runtimes and container sandboxes.")
    add_footer(s10, "Technical Stack & Cloud-Native Design")

    # 4 Architectural Blocks
    ab_w = Inches(2.78)
    ab_h = Inches(1.6)
    arch_blocks = [
        ("TELEMETRY LAYER", "OpenTelemetry (OTel)", "Collects traces, metrics, and logs via OTLP. Walks W3C tracecontext parent-child span DAGs.", BLUE),
        ("ORCHESTRATION", "LangGraph StateGraph", "Python 3.11 / FastAPI. Coordinates multi-agent state machines, tooling, and backtracking.", CYAN),
        ("SHADOW SANDBOX", "Docker SDK (Python)", "Spawns ephemeral, isolated container runtimes for safe replay and regression testing.", PURPLE),
        ("CONTROL PLANE", "Next.js 14 & GitHub", "React Flow interactive node topology dashboard and automated GitHub PR delivery gate.", GREEN),
    ]

    for i, (bhead, btech, bdesc, col) in enumerate(arch_blocks):
        cx = Inches(0.8) + i * (ab_w + Inches(0.2))
        c = s10.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(2.35), ab_w, ab_h)
        c.fill.solid()
        c.fill.fore_color.rgb = CARD_BG
        c.line.color.rgb = col
        ctf = c.text_frame
        ctf.paragraphs[0].text = bhead
        ctf.paragraphs[0].font.size = Pt(9.5)
        ctf.paragraphs[0].font.bold = True
        ctf.paragraphs[0].font.color.rgb = col
        p1 = ctf.add_paragraph()
        p1.text = btech
        p1.font.size = Pt(11)
        p1.font.bold = True
        p1.font.color.rgb = TEXT_WHITE
        p2 = ctf.add_paragraph()
        p2.text = bdesc
        p2.font.size = Pt(8.5)
        p2.font.color.rgb = TEXT_MUTED

    # Table of Tech Stack
    table_shape = s10.shapes.add_table(5, 3, Inches(0.8), Inches(4.15), Inches(11.733), Inches(2.3))
    table = table_shape.table
    table.columns[0].width = Inches(2.5)
    table.columns[1].width = Inches(3.2)
    table.columns[2].width = Inches(6.033)

    table_data = [
        ("SYSTEM LAYER", "TECHNOLOGY CHOSEN", "ARCHITECTURAL ROLE"),
        ("Frontend & Dashboard", "Next.js 14 / React / Tailwind CSS", "Real-time incident response console and human approval interface"),
        ("Topology Visualization", "React Flow", "Interactive node graph with dynamic service state rendering (Red/Green)"),
        ("Agent Orchestration", "LangGraph / StateGraph (Python 3.11)", "Stateful multi-agent DAG execution and backtracking state machine"),
        ("Sandboxing & Delivery", "Docker SDK & GitHub REST API", "Ephemeral container lifecycle management and verified PR automation"),
    ]

    for row_idx, row in enumerate(table_data):
        for col_idx, cell_value in enumerate(row):
            cell = table.cell(row_idx, col_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(12, 19, 36) if row_idx == 0 else CARD_BG
            p = cell.text_frame.paragraphs[0]
            p.text = cell_value
            p.font.name = "Arial"
            p.font.size = Pt(9) if row_idx > 0 else Pt(9.5)
            p.font.bold = (row_idx == 0 or col_idx == 0)
            p.font.color.rgb = CYAN if row_idx == 0 else (TEXT_WHITE if col_idx < 2 else TEXT_MUTED)

    # =========================================================================
    # SLIDE 11: IMPACT + FUTURE SCOPE
    # =========================================================================
    s11 = prs.slides.add_slide(blank_layout)
    set_slide_background(s11)
    add_header(s11, "10 • VALUE & EVOLUTION", "11 / 12")
    add_titles(s11, "COMMERCIAL IMPACT & ROADMAP", "From Hackathon Prototype to Enterprise Platform", "A phased evolutionary trajectory moving from local Docker validation to Kubernetes-native autonomous reliability engineering.")
    add_footer(s11, "Value Creation & Roadmap")

    # 4 Impact Quadrants
    iq_w = Inches(5.75)
    iq_h = Inches(1.55)
    impacts = [
        ("For SRE & On-Call Teams", "Cuts Mean Time to Investigate (MTTI) from 45+ minutes to under 90 seconds. Eradicates 2 AM alert fatigue by distilling cascading alerts into a single verified incident dossier.", BLUE),
        ("For Engineering Organizations", "Prevents costly outages and reduces developer toil. Replaces subjective debugging debates with reproducible Docker integration tests.", CYAN),
        ("For Cloud-Native Enterprises", "Protects top-line transactional revenue during peak retail/financial spikes. Seamlessly integrates with existing OpenTelemetry telemetry investments.", PURPLE),
        ("For Applied AI Trust", "Sets a new industry benchmark for mission-critical AI: AI recommendations are never permitted to touch production until verified by an isolated sandbox test suite.", GREEN),
    ]

    for i, (ihead, idesc, col) in enumerate(impacts):
        row = i // 2
        c_idx = i % 2
        cx = Inches(0.8) + c_idx * (iq_w + Inches(0.23))
        cy = Inches(2.35) + row * (iq_h + Inches(0.15))

        c = s11.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, cy, iq_w, iq_h)
        c.fill.solid()
        c.fill.fore_color.rgb = CARD_BG
        c.line.color.rgb = col
        ctf = c.text_frame
        ctf.paragraphs[0].text = ihead
        ctf.paragraphs[0].font.size = Pt(11)
        ctf.paragraphs[0].font.bold = True
        ctf.paragraphs[0].font.color.rgb = col
        p = ctf.add_paragraph()
        p.text = idesc
        p.font.size = Pt(9)
        p.font.color.rgb = TEXT_MUTED

    # Roadmap Bar
    rm_box = s11.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(5.65), Inches(11.733), Inches(1.05))
    rm_box.fill.solid()
    rm_box.fill.fore_color.rgb = RGBColor(12, 19, 36)
    rm_box.line.color.rgb = CYAN
    rtf = rm_box.text_frame
    rtf.paragraphs[0].text = "PRODUCT EXPANSION ROADMAP:"
    rtf.paragraphs[0].font.name = "Consolas"
    rtf.paragraphs[0].font.size = Pt(9.5)
    rtf.paragraphs[0].font.bold = True
    rtf.paragraphs[0].font.color.rgb = CYAN

    # 4 Roadmap phases
    pw = Inches(2.7)
    phases = [
        ("PHASE 1 (NOW)", "3-Tier Docker reference architecture & local sandbox replay.", CYAN),
        ("PHASE 2 (NEXT)", "Kubernetes operator & ephemeral debug namespaces.", BLUE),
        ("PHASE 3 (THEN)", "eBPF kernel telemetry & automated ArgoCD canary testing.", PURPLE),
        ("PHASE 4 (FUTURE)", "Enterprise incident memory over historical post-mortems.", GREEN),
    ]
    for i, (p_t, p_d, col) in enumerate(phases):
        cx = Inches(1.0) + i * (pw + Inches(0.2))
        p_shape = s11.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(6.0), pw, Inches(0.6))
        p_shape.fill.solid()
        p_shape.fill.fore_color.rgb = RGBColor(7, 10, 19)
        p_shape.line.color.rgb = col
        ptf = p_shape.text_frame
        ptf.paragraphs[0].text = p_t
        ptf.paragraphs[0].font.size = Pt(8.5)
        ptf.paragraphs[0].font.bold = True
        ptf.paragraphs[0].font.color.rgb = col
        p = ptf.add_paragraph()
        p.text = p_d
        p.font.size = Pt(7.5)
        p.font.color.rgb = TEXT_MUTED

    # =========================================================================
    # SLIDE 12: FINAL CLOSE
    # =========================================================================
    s12 = prs.slides.add_slide(blank_layout)
    set_slide_background(s12)
    add_header(s12, "11 • CLOSING MANIFESTO", "12 / 12")
    add_footer(s12, "Why TraceHeal • Closing Statement")

    # Center Hero Manifesto
    c_badge = s12.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(4.7), Inches(1.35), Inches(3.933), Inches(0.32))
    c_badge.fill.solid()
    c_badge.fill.fore_color.rgb = RGBColor(0, 40, 60)
    c_badge.line.color.rgb = CYAN
    c_badge.text_frame.paragraphs[0].text = "THE FUTURE OF PRODUCTION RELIABILITY"
    c_badge.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    c_badge.text_frame.paragraphs[0].font.size = Pt(9.5)
    c_badge.text_frame.paragraphs[0].font.bold = True
    c_badge.text_frame.paragraphs[0].font.color.rgb = CYAN

    c_title = s12.shapes.add_textbox(Inches(1.5), Inches(1.8), Inches(10.333), Inches(0.9))
    cp1 = c_title.text_frame.paragraphs[0]
    cp1.alignment = PP_ALIGN.CENTER
    cp1.text = "TRACEHEAL"
    cp1.font.name = "Arial"
    cp1.font.size = Pt(46)
    cp1.font.bold = True
    cp1.font.color.rgb = TEXT_WHITE

    c_mantra = s12.shapes.add_textbox(Inches(1.5), Inches(2.75), Inches(10.333), Inches(0.4))
    cmp = c_mantra.text_frame.paragraphs[0]
    cmp.alignment = PP_ALIGN.CENTER
    cmp.text = "Trace it.   •   Reproduce it.   •   Verify it.   •   Heal it."
    cmp.font.name = "Arial"
    cmp.font.size = Pt(13)
    cmp.font.bold = True
    cmp.font.color.rgb = CYAN

    # Manifesto Box
    m_box = s12.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.8), Inches(3.3), Inches(9.733), Inches(1.5))
    m_box.fill.solid()
    m_box.fill.fore_color.rgb = CARD_BG
    m_box.line.color.rgb = CYAN
    m_box.line.width = Pt(1.5)
    mtf = m_box.text_frame
    mtf.vertical_anchor = MSO_ANCHOR.MIDDLE
    mp = mtf.paragraphs[0]
    mp.alignment = PP_ALIGN.CENTER
    mp.text = "\"Modern distributed systems do not need another dashboard that tells engineers something went wrong. They need an intelligent system that can investigate the evidence, test its own hypothesis, and help engineers recover safely.\""
    mp.font.name = "Arial"
    mp.font.size = Pt(13.5)
    mp.font.italic = True
    mp.font.color.rgb = TEXT_WHITE

    # 4 Bottom Core Pillars
    cp_w = Inches(2.78)
    cp_h = Inches(1.1)
    cpillars = [
        ("FOUNDATION", "OpenTelemetry", "Native OTLP span graphs", BLUE),
        ("GROUND TRUTH", "Docker Sandbox", "Compilers enforce truth", CYAN),
        ("GOVERNANCE", "Human-Gated PR", "Zero blind prod execution", PURPLE),
        ("OUTCOME", "Verified SRE", "Minutes to resolution", GREEN),
    ]
    for i, (tag, head, desc, col) in enumerate(cpillars):
        cx = Inches(0.8) + i * (cp_w + Inches(0.2))
        c = s12.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(5.1), cp_w, cp_h)
        c.fill.solid()
        c.fill.fore_color.rgb = RGBColor(12, 19, 36)
        c.line.color.rgb = col
        ctf = c.text_frame
        ctf.paragraphs[0].text = tag
        ctf.paragraphs[0].font.size = Pt(8)
        ctf.paragraphs[0].font.color.rgb = TEXT_DARK
        p1 = ctf.add_paragraph()
        p1.text = head
        p1.font.size = Pt(11)
        p1.font.bold = True
        p1.font.color.rgb = col
        p2 = ctf.add_paragraph()
        p2.text = desc
        p2.font.size = Pt(8.5)
        p2.font.color.rgb = TEXT_MUTED

    # Bottom Tagline
    tag_bot = s12.shapes.add_textbox(Inches(1.5), Inches(6.35), Inches(10.333), Inches(0.35))
    tp_bot = tag_bot.text_frame.paragraphs[0]
    tp_bot.alignment = PP_ALIGN.CENTER
    tp_bot.text = "AUTONOMOUS INVESTIGATION  •  VERIFIED REMEDIATION  •  SAFER SRE"
    tp_bot.font.name = "Consolas"
    tp_bot.font.size = Pt(10)
    tp_bot.font.bold = True
    tp_bot.font.color.rgb = TEXT_MUTED

    # Save presentation
    output_path = os.path.abspath("TraceHeal_Idea_Submission.pptx")
    prs.save(output_path)
    print(f"Presentation saved successfully to: {output_path}")
    print(f"File size: {os.path.getsize(output_path)} bytes")

if __name__ == "__main__":
    build_presentation()
