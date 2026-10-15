# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Compte rendu PDF de référence (reportlab). Entrée : views.donnees_pdf(plan)."""
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether)

BLEU = colors.HexColor('#1F4E78')
MENTION = '© 2026 Geoazimut SàRL — geoazimut.com'   # identique à elpro_engine.COPYRIGHT / SITE_WEB


def ecrire_pdf(sections, chemin, titre_projet, sous_titre='Compte rendu de configuration radio ELPRO'):
    st = getSampleStyleSheet()
    p = ParagraphStyle('p', parent=st['BodyText'], fontSize=8, leading=10)
    h1 = ParagraphStyle('h1', parent=st['Heading1'], textColor=BLEU, fontSize=15)
    h2 = ParagraphStyle('h2', parent=st['Heading3'], textColor=BLEU, fontSize=10, spaceBefore=8)
    h3 = ParagraphStyle('h3', parent=st['Heading2'], fontSize=11, spaceBefore=10)
    larg = landscape(A4)[0] - 30 * mm

    def entete(c, d):
        c.saveState(); c.setFont('Helvetica', 7); c.setFillColor(colors.grey)
        c.drawString(15 * mm, 8 * mm, f'{titre_projet} — {sous_titre}')
        c.drawCentredString(landscape(A4)[0] / 2, 8 * mm, MENTION)
        c.drawRightString(landscape(A4)[0] - 15 * mm, 8 * mm, f'Page {d.page}'); c.restoreState()

    doc = BaseDocTemplate(chemin, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm,
                          topMargin=12 * mm, bottomMargin=14 * mm, title=titre_projet,
                          author='Geoazimut SàRL', creator='ELPRO Config — Geoazimut SàRL')
    doc.addPageTemplates([PageTemplate(frames=[Frame(15 * mm, 14 * mm, larg, landscape(A4)[1] - 26 * mm)], onPage=entete)])

    def tableau(col, lignes):
        data = [[Paragraph(f'<b>{c}</b>', ParagraphStyle('t', parent=p, textColor=colors.white)) for c in col]]
        data += [[Paragraph(str(v), p) for v in l] for l in lignes]
        t = Table(data, repeatRows=1, colWidths=[larg / len(col)] * len(col))
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), BLEU), ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
                               ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F2F2')]),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        return t

    E = [Spacer(1, 50 * mm), Paragraph(titre_projet, ParagraphStyle('c', parent=h1, fontSize=26)),
         Paragraph(sous_titre, st['Heading2']), PageBreak()]
    for sec in sections:
        E.append(Paragraph(sec['titre'], h1))
        for b in sec['blocs']:
            if b['type'] == 'formulaire':
                t = Table([[Paragraph(f'<b>{k}</b>', p), Paragraph(str(v), p)] for k, v in b['contenu']],
                          colWidths=[60 * mm, larg - 60 * mm])
                t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey)]))
                E += [t, Spacer(1, 4 * mm)]
            elif b['type'] == 'table':
                if b.get('titre'): E.append(Paragraph(b['titre'], h2))
                if b['lignes']: E += [tableau(b['colonnes'], b['lignes']), Spacer(1, 4 * mm)]
            elif b['type'] == 'sous_titre':
                E.append(Paragraph(b['texte'], h3))
            elif b['type'] == 'checklist':
                for it in b['items']:
                    E.append(KeepTogether(Paragraph(f'☐&nbsp;&nbsp;{it}', ParagraphStyle('ck', parent=p, fontSize=9, leading=14,
                                                                                          fontName='DejaVuSans' if _dejavu() else 'Helvetica'))))
        E.append(PageBreak())
    doc.build(E)
    return chemin


def _dejavu():
    """Police avec la case ☐ ; à embarquer dans resources/DejaVuSans.ttf."""
    import os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames():
        return True
    for f in (os.path.join(os.path.dirname(__file__), '..', 'resources', 'DejaVuSans.ttf'),
              '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/DejaVuSans.ttf'):
        if os.path.exists(f):
            pdfmetrics.registerFont(TTFont('DejaVuSans', f)); return True
    return False
