import os
import re
import pdfplumber


def _get_poppler_path():
    """Get the Poppler bin path from config or environment."""
    poppler_path = os.environ.get('POPPLER_PATH')
    if poppler_path and os.path.isdir(poppler_path):
        return poppler_path
    # Default path relative to project root
    default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'poppler', 'poppler-25.12.0', 'Library', 'bin'
    )
    if os.path.isdir(default):
        return default
    return None


def _configure_tesseract():
    """Set Tesseract executable path if not in PATH."""
    import pytesseract
    tesseract_path = os.environ.get('TESSERACT_CMD')
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        return
    # Check common Windows install locations
    default = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    if os.path.isfile(default):
        pytesseract.pytesseract.tesseract_cmd = default


def _is_meaningful_text(text):
    """Check if extracted text contains real words, not garbled font encodings.

    Some PDFs have custom font mappings that produce lots of characters
    but no recognizable words. Detects this by looking for common English
    words that would appear in any document.
    """
    if len(text.strip()) < 50:
        return False
    text_lower = text.lower()
    # Common words that appear in virtually any English document
    common_words = [
        'the', 'and', 'for', 'number', 'date', 'name', 'type',
        'report', 'page', 'project', 'inspection', 'test',
        'accepted', 'rejected', 'weld', 'standard', 'procedure',
    ]
    found = sum(1 for w in common_words if w in text_lower)
    return found >= 3


class BaseExtractor:
    """Base class for PDF extraction with pdfplumber and OCR fallback."""

    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.pages_text = []
        self.tables = []

    def extract_text(self):
        """Extract text from all pages. Falls back to OCR if text is sparse or garbled."""
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ''
                self.pages_text.append(text)

                page_tables = page.extract_tables()
                if page_tables:
                    self.tables.extend(page_tables)

        # Check if we got meaningful text (not garbled font encodings)
        total_text = ' '.join(self.pages_text).strip()
        if not _is_meaningful_text(total_text):
            self._ocr_fallback()

        return self.pages_text

    def _ocr_fallback(self):
        """Use OCR to extract text from scanned/garbled PDFs.

        Processes one page at a time to keep memory usage low,
        which is critical for constrained environments like Render free tier.
        """
        try:
            from pdf2image import convert_from_path
            import pytesseract

            _configure_tesseract()

            poppler_path = _get_poppler_path()

            # Use lower DPI in production (memory-constrained) environments
            dpi = int(os.environ.get('OCR_DPI', '200'))

            base_kwargs = {}
            if poppler_path:
                base_kwargs['poppler_path'] = poppler_path

            # Get total page count without converting
            import pdfplumber
            with pdfplumber.open(self.pdf_path) as pdf:
                total_pages = len(pdf.pages)

            self.pages_text = []
            self.tables = []

            # Process one page at a time to limit memory usage
            for page_num in range(1, total_pages + 1):
                images = convert_from_path(
                    self.pdf_path,
                    dpi=dpi,
                    first_page=page_num,
                    last_page=page_num,
                    **base_kwargs,
                )
                if images:
                    text = pytesseract.image_to_string(images[0])
                    self.pages_text.append(text)
                    # Release image memory immediately
                    del images

        except ImportError:
            pass  # OCR dependencies not available
        except Exception:
            pass  # OCR failed, continue with what we have

    def get_full_text(self):
        """Return all pages concatenated."""
        if not self.pages_text:
            self.extract_text()
        return '\n'.join(self.pages_text)

    def parse(self):
        """Override in subclasses to return extracted data dict."""
        raise NotImplementedError
