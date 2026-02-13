import re
from datetime import datetime
from app.extractors.base import BaseExtractor


class VTExtractor(BaseExtractor):
    """Extract data from Visual Testing (VT) inspection reports."""

    def parse(self):
        """Parse VT report and return structured data dict."""
        text = self.get_full_text()

        header = self._parse_header(text)
        weld_entries = self._parse_weld_table(text)

        return {
            'header': header,
            'weld_entries': weld_entries,
        }

    def _parse_header(self, text):
        """Extract header fields from VT report text."""
        header = {}

        # AET Job No.
        m = re.search(r'AET Job No\.?:?\s*([A-Z0-9-]+)', text)
        if m:
            header['job_number'] = m.group(1).strip()

        # Purchase Order No.
        m = re.search(r'Purchase Order No\.?:?\s*(\S+)', text)
        if m:
            header['po_number'] = m.group(1).strip()

        # Date of Inspection
        m = re.search(r'Date of Inspection:?\s*(.+?)(?:\n|$)', text)
        if m:
            date_str = m.group(1).strip()
            header['inspection_date'] = self._parse_date(date_str)

        # Project and Job #
        m = re.search(r'Project:?\s*(.+?)(?:Job\s*#|Job\s*No|$)', text)
        if m:
            header['project_name'] = m.group(1).strip().rstrip(':')

        m = re.search(r'Job\s*#?:?\s*(\d+)', text)
        if m:
            header['project_job_number'] = m.group(1).strip()

        # Client
        m = re.search(r'Client:?\s*(.+?)(?:\n|$)', text)
        if m:
            header['client'] = m.group(1).strip()

        # Location
        m = re.search(r'Location of Inspection:?\s*(.+?)(?:\n|$)', text)
        if m:
            header['location'] = m.group(1).strip()

        # Type of Equipment
        m = re.search(r'Type of Equipment:?\s*(.+?)(?:\n|$)', text)
        if m:
            header['equipment'] = m.group(1).strip()

        # Code Requirements
        m = re.search(r'Code Requirements:?\s*(.+?)(?:AET|$)', text)
        if m:
            header['specification'] = m.group(1).strip()

        # AET Procedure
        m = re.search(r'AET Procedure:?\s*(.+?)(?:\n|$)', text)
        if m:
            header['procedure_number'] = m.group(1).strip()

        # Inspector - clean up underscores from signature line artifacts
        m = re.search(r'Inspector:?\s*(.+?)(?:Assistant|CWI|$)', text)
        if m:
            name = m.group(1).strip()
            name = re.sub(r'[_]+', '', name)  # Remove underscores
            name = re.sub(r'\s+', ' ', name).strip()  # Normalize whitespace
            header['inspector_name'] = name

        # CWI #
        m = re.search(r'CWI\s*#?\s*(\d+)', text)
        if m:
            header['inspector_cert'] = f'CWI# {m.group(1)}'

        # Overall result
        if re.search(r'Accepted', text, re.IGNORECASE):
            header['result_summary'] = 'Accepted'
        elif re.search(r'Rejected', text, re.IGNORECASE):
            header['result_summary'] = 'Rejected'

        header['inspection_type'] = 'VT'
        return header

    def _parse_weld_table(self, text):
        """Extract weld entries from the VT report table."""
        entries = []

        # Try pdfplumber tables first
        if self.tables:
            for table in self.tables:
                entries.extend(self._parse_table_rows(table))

        # Fallback: regex-based extraction from text
        if not entries:
            entries = self._parse_weld_text(text)

        return entries

    def _parse_table_rows(self, table):
        """Parse rows from a pdfplumber-extracted table."""
        entries = []
        for row in table:
            if not row or not row[0]:
                continue
            cell = str(row[0]).strip()
            # Look for ISO numbers like TWS-189, TWR-152
            if re.match(r'^TW[A-Z]-\d+', cell):
                iso_number = cell
                weld_info = str(row[1]).strip() if len(row) > 1 and row[1] else ''
                result = str(row[2]).strip() if len(row) > 2 and row[2] else ''

                # Parse "Weld 3" → expand to individual entries
                weld_count = self._get_weld_count(weld_info)
                evaluation = 'Accept' if 'accept' in result.lower() else 'Reject' if 'reject' in result.lower() else result

                for i in range(1, weld_count + 1):
                    entries.append({
                        'iso_number': iso_number,
                        'weld_number': f'Weld {i}',
                        'evaluation': evaluation,
                        'remarks': result if evaluation not in ('Accept', 'Reject') else '',
                    })
        return entries

    def _parse_weld_text(self, text):
        """Fallback: parse weld entries from plain text using regex."""
        entries = []
        # Match lines with ISO numbers followed by Weld info
        pattern = r'(TW[A-Z]-\d+)\s+Weld\s+(\d+)'
        for m in re.finditer(pattern, text):
            iso_number = m.group(1)
            weld_count = int(m.group(2))

            # Determine result from context
            evaluation = 'Accept' if 'accepted' in text.lower() else 'Unknown'

            for i in range(1, weld_count + 1):
                entries.append({
                    'iso_number': iso_number,
                    'weld_number': f'Weld {i}',
                    'evaluation': evaluation,
                    'remarks': '',
                })
        return entries

    def _get_weld_count(self, weld_info):
        """Extract weld count from text like 'Weld 3'."""
        m = re.search(r'Weld\s+(\d+)', weld_info)
        return int(m.group(1)) if m else 1

    def _parse_date(self, date_str):
        """Try parsing various date formats."""
        formats = [
            '%B %d, %Y',      # October 01, 2025
            '%m-%d-%Y',       # 10-01-2025
            '%m/%d/%Y',       # 10/01/2025
            '%m-%d-%y',       # 10-01-25
            '%Y-%m-%d',       # 2025-10-01
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None
