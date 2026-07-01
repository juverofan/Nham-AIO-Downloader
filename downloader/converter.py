import os
import re
import shutil
from io import BytesIO
from urllib.parse import urlparse

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

try:
    from ebooklib import epub
    HAS_EPUBLIB = True
except ImportError:
    HAS_EPUBLIB = False


_UNICODE_FONT_CACHE = None


def _get_unicode_font() -> str:
    global _UNICODE_FONT_CACHE
    if _UNICODE_FONT_CACHE and os.path.exists(_UNICODE_FONT_CACHE):
        return _UNICODE_FONT_CACHE

    bundled = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
    if os.path.exists(bundled):
        _UNICODE_FONT_CACHE = bundled
        return bundled

    candidates = [
        # Windows system fonts
        os.path.expandvars(r"%WINDIR%\Fonts\arial.ttf"),
        os.path.expandvars(r"%WINDIR%\Fonts\segoeui.ttf"),
        os.path.expandvars(r"%WINDIR%\Fonts\segoeui.ttf"),
        os.path.expandvars(r"%WINDIR%\Fonts\calibri.ttf"),
        os.path.expandvars(r"%WINDIR%\Fonts\tahoma.ttf"),
        os.path.expandvars(r"%WINDIR%\Fonts\DejaVuSans.ttf"),
    ]

    for c in candidates:
        expanded = os.path.expandvars(c)
        if os.path.exists(expanded):
            _UNICODE_FONT_CACHE = expanded
            return expanded

    # Download DejaVuSans to cache
    try:
        cache_dir = os.path.join(os.path.dirname(__file__), "fonts")
        os.makedirs(cache_dir, exist_ok=True)
        font_path = os.path.join(cache_dir, "DejaVuSans.ttf")

        if not os.path.exists(font_path):
            import requests
            url = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
            print(f"Downloading Unicode font: {url}")
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            with open(font_path, "wb") as f:
                f.write(resp.content)

        _UNICODE_FONT_CACHE = font_path
        return font_path
    except Exception:
        pass

    return None


def _init_pdf(pdf: FPDF):
    font_path = _get_unicode_font()
    if font_path:
        pdf.add_font("Unicode", "", font_path, uni=True)
        # Try to find a bold variant
        bold_path = None
        base, ext = os.path.splitext(font_path)
        for bname in [base + "bd" + ext, base + "b" + ext, base.replace("Sans", "Sans-Bold") + ext,
                       base.replace("Sans", "SansBold") + ext, base.replace("-Regular", "-Bold") + ext,
                       font_path.replace(".ttf", "Bold.ttf"), font_path.replace(".ttf", "bd.ttf"),
                       font_path.replace("arial", "arialbd"), font_path.replace("Arial", "Arialbd")]:
            if os.path.exists(bname):
                bold_path = bname
                break
        if bold_path:
            pdf.add_font("Unicode", "B", bold_path, uni=True)
        else:
            # Use regular as fallback
            pdf.add_font("Unicode", "B", font_path, uni=True)
        return "Unicode"
    return "Helvetica"


def clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def text_to_pdf(text: str, output_path: str, title: str = "Story",
                author: str = "Unknown", cover_url: str = None):
    if not HAS_FPDF:
        raise ImportError("fpdf2 is required for PDF generation. Install: pip install fpdf2")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    font_name = _init_pdf(pdf)
    fallback = font_name == "Helvetica"

    # Title page
    pdf.add_page()
    pdf.set_font(font_name, "B", 24)
    pdf.ln(60)
    pdf.cell(0, 15, title[:80], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font_name, "", 14)
    pdf.ln(10)
    pdf.cell(0, 10, f"By: {author}", align="C", new_x="LMARGIN", new_y="NEXT")

    if cover_url and (cover_url.startswith("http://") or cover_url.startswith("https://")):
        try:
            import requests
            resp = requests.get(cover_url, timeout=10)
            if resp.status_code == 200:
                img_data = BytesIO(resp.content)
                pdf.image(img_data, x=60, y=100, w=90)
        except Exception:
            pass

    pdf.add_page()
    pdf.set_font(font_name, "B", 16)
    pdf.cell(0, 10, "Table of Contents", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    chapters = re.split(r"^##\s+", text, flags=re.MULTILINE)
    for i, section in enumerate(chapters):
        if not section.strip():
            continue
        lines = section.split("\n", 1)
        ch_title = lines[0].strip().rstrip("#").strip() if lines else ""
        ch_body = lines[1] if len(lines) > 1 else ""

        if i == 0 and not ch_title:
            ch_title = title

        pdf.add_page()
        pdf.set_font(font_name, "B", 18)
        pdf.cell(0, 15, ch_title[:80], align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

        pdf.set_font(font_name, "", 11)
        for paragraph in ch_body.split("\n\n"):
            para = clean_text(paragraph)
            if para:
                try:
                    pdf.multi_cell(0, 6, para)
                except Exception as e:
                    # Remove problematic characters and retry
                    clean_para = para.encode("ascii", errors="replace").decode("ascii")
                    if clean_para.strip():
                        pdf.multi_cell(0, 6, clean_para)
                pdf.ln(3)

    pdf.output(output_path)
    return output_path


def text_to_epub(text: str, output_path: str, title: str = "Story",
                 author: str = "Unknown", cover_url: str = None):
    if not HAS_EPUBLIB:
        raise ImportError("ebooklib is required for EPUB generation. Install: pip install ebooklib")

    book = epub.EpubBook()
    book.set_identifier(str(hash(title + author) % (2**31)))
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    if cover_url and (cover_url.startswith("http://") or cover_url.startswith("https://")):
        try:
            import requests
            resp = requests.get(cover_url, timeout=10)
            if resp.status_code == 200:
                book.set_cover("cover.jpg", resp.content)
        except Exception:
            pass

    chapters = re.split(r"^##\s+", text, flags=re.MULTILINE)
    spine = ["nav"]

    for i, section in enumerate(chapters):
        if not section.strip():
            continue
        lines = section.split("\n", 1)
        ch_title = lines[0].strip().rstrip("#").strip() if lines else ""
        ch_body = lines[1] if len(lines) > 1 else ""

        if i == 0 and not ch_title:
            ch_title = "Introduction"

        html_content = f"<h1>{ch_title}</h1>"
        for paragraph in ch_body.split("\n\n"):
            para = clean_text(paragraph)
            if para:
                html_content += f"<p>{para.replace(chr(10), '<br/>')}</p>"

        chapter = epub.EpubHtml(
            title=ch_title,
            file_name=f"chap_{i}.xhtml",
            lang="en"
        )
        chapter.content = html_content
        book.add_item(chapter)
        spine.append(chapter)

    book.toc = spine[1:]
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(output_path, book)
    return output_path
