import os
import re
import pdfplumber


def classify_pdf(pdf_path):
    """Detect the type of weld inspection PDF.

    Returns one of: 'VT', 'UT', 'WPS', 'PQR', or 'UNKNOWN'.
    Uses text content first, then falls back to OCR, then filename.
    """
    text = ''
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Try first few pages for text
            for page in pdf.pages[:3]:
                page_text = page.extract_text() or ''
                text += page_text + '\n'
    except Exception:
        pass

    # Classify from extracted text if sufficient
    if len(text.strip()) >= 50:
        result = _classify_from_text(text)
        if result != 'UNKNOWN':
            return result

    # Try OCR if text was sparse
    if len(text.strip()) < 50:
        try:
            from pdf2image import convert_from_path
            import pytesseract
            from app.extractors.base import _get_poppler_path, _configure_tesseract

            _configure_tesseract()

            kwargs = {'dpi': 200, 'first_page': 1, 'last_page': 1}
            poppler_path = _get_poppler_path()
            if poppler_path:
                kwargs['poppler_path'] = poppler_path

            images = convert_from_path(pdf_path, **kwargs)
            if images:
                ocr_text = pytesseract.image_to_string(images[0])
                result = _classify_from_text(ocr_text)
                if result != 'UNKNOWN':
                    return result
        except Exception:
            pass

    # Fallback: classify from filename
    return _classify_from_filename(pdf_path)


def _classify_from_text(text):
    """Classify document type from its text content."""
    text_upper = text.upper()

    if 'ULTRASONIC TESTING' in text_upper or 'ULTRASONIC TEST' in text_upper:
        return 'UT'
    if 'VISUAL INSPECTION' in text_upper or 'VISUAL TEST' in text_upper:
        return 'VT'
    if 'WELD PROCEDURE SPECIFICATION' in text_upper:
        return 'WPS'
    if 'PROCEDURE QUALIFICATION RECORD' in text_upper:
        return 'PQR'
    if 'SHOP/FIELD INSPECTION' in text_upper:
        return 'VT'
    if 'DECIBELS' in text_upper or 'INDICATION NUMBER' in text_upper:
        return 'UT'

    return 'UNKNOWN'


def _classify_from_filename(pdf_path):
    """Classify document type from its filename as a last resort."""
    filename = os.path.basename(pdf_path).upper()

    # Look for type indicators in the filename
    # Match UT/VT even when directly followed by digits (e.g. "UT11-11-25")
    if re.search(r'(?:^|[\b \-_])UT(?:[\b \-_.\d]|$)', filename):
        return 'UT'
    if re.search(r'(?:^|[\b \-_])VT(?:[\b \-_.\d]|$)', filename):
        return 'VT'
    if re.search(r'(?:^|[\b \-_])WPS(?:[\b \-_.\d]|$)', filename):
        return 'WPS'
    if re.search(r'(?:^|[\b \-_])PQR(?:[\b \-_.\d]|$)', filename):
        return 'PQR'

    return 'UNKNOWN'
