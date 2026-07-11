"""
pipeline/pdf.py — Convert a markdown report to a styled PDF.

Requires: pip install markdown weasyprint
If weasyprint is not installed, logs a warning and skips PDF generation.
"""

from pathlib import Path
from cram.log import log, dim, green, yellow

# ── Medical-grade CSS for the PDF ────────────────────────────────────────────
_CSS = """
@page {
    margin: 2cm 2.5cm;
    @bottom-right {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: #888;
    }
    @bottom-left {
        content: "CRAM-1 — Clinical Research Agent Model 1";
        font-size: 9pt;
        color: #888;
    }
}

body {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 11pt;
    line-height: 1.65;
    color: #1a1a1a;
    max-width: 100%;
}

h1 {
    font-size: 18pt;
    font-weight: bold;
    color: #1a2a4a;
    border-bottom: 2px solid #1a2a4a;
    padding-bottom: 6pt;
    margin-top: 18pt;
    page-break-after: avoid;
}

h2 {
    font-size: 14pt;
    font-weight: bold;
    color: #1a2a4a;
    border-bottom: 1px solid #ccd;
    padding-bottom: 4pt;
    margin-top: 16pt;
    page-break-after: avoid;
}

h3 {
    font-size: 12pt;
    font-weight: 600;
    color: #2a3a5a;
    margin-top: 12pt;
    page-break-after: avoid;
}

h4 {
    font-size: 11pt;
    font-weight: 600;
    color: #3a4a6a;
    margin-top: 10pt;
    page-break-after: avoid;
}

p {
    margin: 6pt 0;
    orphans: 3;
    widows: 3;
}

/* Critical alert block */
p:has(strong:first-child),
blockquote {
    page-break-inside: avoid;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
    margin: 10pt 0;
    page-break-inside: avoid;
}

th {
    background-color: #1a2a4a;
    color: white;
    padding: 6pt 8pt;
    text-align: left;
    font-weight: bold;
}

td {
    padding: 5pt 8pt;
    border: 1px solid #ccd;
    vertical-align: top;
}

tr:nth-child(even) td {
    background-color: #f5f7fa;
}

/* Code / citations */
code {
    font-family: "Courier New", monospace;
    font-size: 9pt;
    background: #f0f2f5;
    padding: 1pt 3pt;
    border-radius: 2pt;
}

pre {
    font-family: "Courier New", monospace;
    font-size: 9pt;
    background: #f0f2f5;
    padding: 8pt;
    border-left: 3px solid #1a2a4a;
    page-break-inside: avoid;
    white-space: pre-wrap;
    word-wrap: break-word;
}

/* Lists */
ul, ol {
    margin: 6pt 0;
    padding-left: 20pt;
}

li {
    margin: 3pt 0;
}

/* Horizontal rule — section separator */
hr {
    border: none;
    border-top: 1px solid #ccd;
    margin: 14pt 0;
}

/* Bold inline — findings */
strong {
    color: #1a1a1a;
}

/* Warning / alert markers */
.alert-block {
    border-left: 4px solid #cc0000;
    background: #fff5f5;
    padding: 8pt 12pt;
    margin: 10pt 0;
    page-break-inside: avoid;
}

/* Evidence grade markers shown as inline spans */
em {
    color: #444;
    font-style: italic;
}

/* Header metadata block */
.header-meta {
    background: #f5f7fa;
    border: 1px solid #ccd;
    padding: 10pt;
    margin-bottom: 16pt;
    font-size: 10pt;
}

/* Blockquotes used for highlighted evidence */
blockquote {
    border-left: 3px solid #2a6a9a;
    background: #f5f8fb;
    margin: 8pt 0;
    padding: 6pt 12pt;
    font-size: 10.5pt;
}
"""


def _convert_alerts_to_html(html: str) -> str:
    """Post-process HTML to wrap alert blocks in styled divs."""
    import re
    # Wrap lines with CRITICAL ALERT in a styled block
    html = re.sub(
        r'(<p>)(.*?CRITICAL ALERT.*?)(</p>)',
        r'<div class="alert-block">\1\2\3</div>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html


def markdown_to_pdf(md_path: str | Path, pdf_path: str | Path | None = None) -> Path | None:
    """
    Convert a markdown file to PDF.

    Args:
        md_path: Path to the .md file
        pdf_path: Optional output path. Defaults to same name with .pdf extension.

    Returns:
        Path to generated PDF, or None if conversion failed.
    """
    md_path = Path(md_path)
    if pdf_path is None:
        pdf_path = md_path.with_suffix(".pdf")
    pdf_path = Path(pdf_path)

    try:
        import markdown as md_lib
    except ImportError:
        log(yellow("  [PDF] 'markdown' package not installed — skipping PDF. Run: pip install markdown weasyprint"))
        return None

    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
    except ImportError:
        log(yellow("  [PDF] 'weasyprint' not installed — skipping PDF. Run: pip install markdown weasyprint"))
        return None

    try:
        md_text = md_path.read_text(encoding="utf-8")

        # Convert markdown → HTML
        html_body = md_lib.markdown(
            md_text,
            extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        )

        html_body = _convert_alerts_to_html(html_body)

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CRAM-1 Report</title>
</head>
<body>
{html_body}
</body>
</html>"""

        font_config = FontConfiguration()
        css = CSS(string=_CSS, font_config=font_config)
        HTML(string=full_html).write_pdf(
            str(pdf_path),
            stylesheets=[css],
            font_config=font_config,
        )

        log(f"  PDF       : {green(str(pdf_path))}")
        return pdf_path

    except Exception as e:
        log(yellow(f"  [PDF] Conversion failed ({e}) — markdown report still saved"))
        return None
