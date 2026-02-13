import re
from datetime import datetime
from app.extractors.base import BaseExtractor


class UTExtractor(BaseExtractor):
    """Extract data from Ultrasonic Testing (UT) inspection reports.

    Supports multiple report formats:
    - AET (American Engineering Testing): "ULTRASONIC TESTING FIELD SHEET"
    - GLT (Great Lakes Testing): "ASME ULTRASONIC EXAMINATION REPORT"
    """

    def parse(self):
        """Parse UT report and return structured data dict."""
        text = self.get_full_text()

        header = self._parse_header(text)
        ut_details = self._parse_ut_details(text)
        weld_entries = self._parse_indication_table(text)

        # Update result_summary based on weld evaluations
        if weld_entries and any(
            e.get('evaluation', '').lower() == 'reject' for e in weld_entries
        ):
            header['result_summary'] = 'Rejected'

        return {
            'header': header,
            'ut_details': ut_details,
            'weld_entries': weld_entries,
        }

    @staticmethod
    def _clean_ocr(value):
        """Clean common OCR artifacts from extracted text."""
        if not value:
            return value
        value = value.strip().lstrip('_').lstrip(';').lstrip(':').lstrip(',').strip()
        value = re.sub(r'\s+', ' ', value)
        value = re.sub(r'[\s_\-—>]+$', '', value)
        return value

    def _parse_header(self, text):
        """Extract header fields from UT report (handles multiple formats)."""
        header = {}

        # --- Job/Project Number ---
        # AET: "Project No.: P-0046928"
        m = re.search(r'Project No\.?:?\s*([A-Z0-9-]+)', text)
        if m:
            header['job_number'] = m.group(1).strip()
        # GLT: "Project/Job Number: 44085"
        if 'job_number' not in header:
            m = re.search(r'(?:Project/?Job\s*Number|Job\s*Number):?\s*(\S+)', text)
            if m:
                header['job_number'] = m.group(1).strip()
                header['project_job_number'] = m.group(1).strip()

        # --- PO Number ---
        # AET: "P.O. No.: --"
        m = re.search(r'P\.?O\.?\s*No\.?:?\s*(\S+)', text)
        if not m:
            # GLT: "PO Number: 44085-01"
            m = re.search(r'PO\s*Number:?\s*(\S+)', text)
        if m:
            po = m.group(1).strip().rstrip(':')
            po = re.sub(r'^[_\-]+$', '', po)
            if po and po not in ('--', '---', 'N/A'):
                header['po_number'] = po

        # --- Date ---
        # AET: "Date of Inspection: 09-26-2025"
        m = re.search(r'Date of Inspection:?\s*_?([0-9/-]+)', text)
        if not m:
            # GLT: "Date: 11-11-2025"
            m = re.search(r'(?:^|\s)Date:?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', text, re.MULTILINE)
        if m:
            header['inspection_date'] = self._parse_date(m.group(1).strip())

        # --- Project Name ---
        # AET: "Project: QTS Project for Baker Group Job#: 44085"
        m = re.search(r'Project:?\s*(.+?)(?:Customer|Client)', text)
        if m:
            proj = m.group(1).strip()
            jm = re.search(r'Job\s*#?:?\s*(\d+)', proj)
            if jm:
                header['project_job_number'] = jm.group(1)
                proj_name = re.sub(r'Job\s*#?:?\s*\d+', '', proj).strip().rstrip(',').strip()
                if proj_name:
                    proj = proj_name
            header['project_name'] = self._clean_ocr(proj)

        # --- Customer/Client ---
        # GLT: "Customer Name: TWEET GAROT" (try specific pattern first)
        m = re.search(r'Customer\s*Name:?\s*(.+?)(?:Revision|Project|Address|\n)', text)
        if m:
            client = self._clean_ocr(m.group(1))
            if client and len(client) > 2:
                header['client'] = client
        # AET: "Customer: Tweet-Garot"
        if 'client' not in header:
            m = re.search(r'Customer:?\s*(.+?)(?:Revision|Project|Address|\n)', text)
            if m:
                client = self._clean_ocr(m.group(1))
                # Skip if it captured "Address:" or "Name:" as part of value
                if client and len(client) > 2 and 'Name:' not in client and 'Address:' not in client:
                    header['client'] = client

        # --- Location ---
        m = re.search(r'(?:Inspection\s*)?Location:?\s*(.+?)(?:Specification|Spec|Exam|\n)', text)
        if m:
            loc = self._clean_ocr(m.group(1))
            # Skip garbage values from form templates
            if loc and 'Selected at Bottom' not in loc and len(loc) > 2:
                header['location'] = loc

        # --- Specification ---
        # AET: "Specification: ASME B31.3 - Category D"
        m = re.search(r'Specification[;:]?\s*(.+?)(?:\n|$)', text)
        if not m:
            # GLT: "Acceptance Standard: ASME B31.3 CATEGORY D"
            m = re.search(r'Acceptance Standard:?\s*(.+?)(?:\n|$)', text)
        if m:
            header['specification'] = self._clean_ocr(m.group(1))

        # --- Procedure ---
        # AET: "Procedure No. 06-NDT-614"
        m = re.search(r'Procedure No\.?\s*([A-Z0-9-]+)', text)
        if not m:
            # GLT: "NDE Procedure: GLT-UT-1 REV. 11"
            m = re.search(r'NDE Procedure:?\s*(.+?)(?:Revision Change|\n|$)', text)
        if m:
            header['procedure_number'] = self._clean_ocr(m.group(1))

        # --- Inspector ---
        # Try "Inspected By (Print):" first (GLT format)
        m = re.search(r'Inspected By\s*\(Print\):?\s*(.+?)(?:\n|$)', text)
        if not m:
            # AET: "Inspected By: Chris Lorentz"
            m = re.search(r'Inspected By\s*\(?(?:Print|Signature)?\)?:?\s*(.+?)(?:\s+Level\b|\s+Test|\n|$)', text)
        if m:
            name = m.group(1).strip()
            name = re.sub(r'[_\-—\s>\.]+$', '', name)
            name = re.sub(r'[\ufffd]+', '', name)  # Remove OCR replacement chars
            name = re.sub(r'\s+[A-Z]\d+\.?\s*$', '', name)  # Remove cert stamps (e.g. S20.)
            name = re.sub(r'\s+', ' ', name).strip()
            if name and len(name) > 1:
                header['inspector_name'] = name

        # --- Level (certification) ---
        m = re.search(r'(?:Certification|Level)\s*:?\s*.{0,20}?(Level\s+I{1,3}|Level\s+IV|Level\s+[1-4])', text, re.IGNORECASE)
        if not m:
            m = re.search(r'Level\s+(I{1,3}|IV|[1-4])\b', text)
        if m:
            cert = m.group(1) if m.group(1).startswith('Level') else f'Level {m.group(1)}'
            header['inspector_cert'] = cert

        header['inspection_type'] = 'UT'
        header['result_summary'] = 'Accepted'
        return header

    def _parse_ut_details(self, text):
        """Extract UT-specific technical details (handles multiple formats)."""
        details = {}

        # Instrument S/N
        # AET: "Instrument Used: S/N 120246802"
        # GLT: "Instrument Serial Number: 242089110"
        m = re.search(r'Instrument\s+Serial\s*Number:?\s*(\S+)', text)
        if not m:
            m = re.search(r'Instrument\s+(?:Used|Serial\s*Number):?\s*(?:S/N\s*)?(\S+)', text)
        if m:
            details['instrument_sn'] = self._clean_ocr(m.group(1))

        # Member Identification
        m = re.search(r'Member Identification:?\s*(.+?)(?:\n|$)', text)
        if m:
            details['member_identification'] = m.group(1).strip()

        # Material Thickness - must have a value on the same line
        m = re.search(r'Material Thickness:?\s*(\S+)', text)
        if m:
            val = m.group(1).strip()
            # Skip if we captured the next field name
            if val.lower() not in ('weld', 'size', 'joint'):
                details['material_thickness'] = val

        # Size (GLT format - may have thickness as Size)
        if 'material_thickness' not in details:
            m = re.search(r'Size:?\s*(\.\d+"|[\d.]+\s*")', text)
            if m:
                details['material_thickness'] = m.group(1).strip()

        # Weld Joint Design
        m = re.search(r'Weld Joint Design:?\s*(.+?)(?:\n|$)', text)
        if m:
            val = m.group(1).strip()
            if val and len(val) > 1:
                details['weld_joint_design'] = val

        # Weld Process / Welding Process
        m = re.search(r'Weld(?:ing)?\s*Process:?\s*(\S+)', text)
        if m:
            val = m.group(1).strip()
            # Skip if we captured the next field name
            if val.lower() not in ('surface', 'material', 'condition'):
                details['weld_process'] = val

        # Material Type
        m = re.search(r'Material Type:?\s*(\S+)', text)
        if m:
            details['material_type'] = m.group(1).strip()

        # Volume Scanned / Sampling Plan
        m = re.search(r'(?:Volume Scanned|Sampling Plan).*?(\d+)\s*%', text)
        if m:
            details['volume_scanned_pct'] = int(m.group(1))

        # Surface Condition
        m = re.search(r'Surface Condition:?\s*(.+?)(?:\n|$)', text)
        if m:
            details['surface_condition'] = m.group(1).strip()

        # Reference Level Gain
        m = re.search(r'(?:Reference Level )?Gain:?\s*(\S+\s*dB)', text)
        if m:
            details['reference_level_gain'] = m.group(1).strip()

        return details

    def _parse_indication_table(self, text):
        """Extract weld indication entries from the UT table."""
        entries = []

        # Try pdfplumber tables first
        if self.tables:
            for table in self.tables:
                entries.extend(self._parse_table_rows(table))

        # Fallback: regex from text (handles OCR text from both formats)
        if not entries:
            entries = self._parse_indication_text(text)

        return entries

    def _parse_table_rows(self, table):
        """Parse indication rows from pdfplumber table."""
        entries = []
        for row in table:
            if not row or not row[0]:
                continue
            cell = str(row[0]).strip()
            if not re.match(r'^TW[A-Z]-\d+', cell):
                continue

            iso_number = cell
            indication = self._parse_indication_row(row)
            indication['iso_number'] = iso_number
            entries.append(indication)

        return entries

    def _parse_indication_row(self, row):
        """Parse a single indication row into a dict."""
        entry = {
            'weld_number': '',
            'evaluation': 'Accept',
            'remarks': '',
            'ut_indication': {},
        }

        def safe_float(val):
            try:
                v = str(val).strip().replace('--', '').replace('---', '')
                return float(v) if v else None
            except (ValueError, TypeError):
                return None

        def safe_int(val):
            try:
                v = str(val).strip().replace('--', '').replace('---', '')
                return int(v) if v else None
            except (ValueError, TypeError):
                return None

        if len(row) > 1:
            entry['ut_indication']['probe_angle'] = safe_int(row[1])
        if len(row) > 2:
            entry['ut_indication']['node'] = str(row[2]).strip() if row[2] else None
        if len(row) > 4:
            entry['ut_indication']['reference_level'] = safe_float(row[4])

        # Look for Accept/Reject in any column
        for i, cell in enumerate(row):
            if cell and re.search(r'accept|reject', str(cell), re.IGNORECASE):
                entry['evaluation'] = 'Accept' if 'accept' in str(cell).lower() else 'Reject'
                break

        # Look for remarks/weld info in last columns
        if len(row) > 11 and row[11]:
            entry['remarks'] = str(row[11]).strip()
            entry['weld_number'] = entry['remarks']

        return entry

    def _parse_indication_text(self, text):
        """Parse indications from OCR text - supports multiple formats.

        Tries clean regex patterns first, then falls back to fuzzy OCR parsing.
        Returns whichever method produces the most results.
        """
        best = []

        # Pattern for clean full weld labels: TWR-804-1, TWR-804-2, etc.
        clean_entries = []
        full_label_pattern = r'(TW[A-Z]-\d+-\d+)\s+.*?(\d{2})\s+.*?(ACCEPT|REJECT)\w*'
        for m in re.finditer(full_label_pattern, text, re.IGNORECASE):
            label = m.group(1)
            parts = label.rsplit('-', 1)
            iso_number = parts[0]
            weld_suffix = parts[1] if len(parts) > 1 else ''

            clean_entries.append({
                'iso_number': iso_number,
                'weld_number': f'Weld {weld_suffix}' if weld_suffix else '',
                'evaluation': 'Accept' if 'accept' in m.group(3).lower() else 'Reject',
                'remarks': '',
                'ut_indication': {
                    'probe_angle': int(m.group(2)) if m.group(2) else None,
                },
            })

        if len(clean_entries) > len(best):
            best = clean_entries

        # AET-style pattern (TWR-157 without weld suffix)
        simple_entries = []
        simple_pattern = r'(TW[A-Z]-\d+)\s+(\d+)\s+.*?(Accept|Reject)\w*\s*(Weld\s*\d+)?'
        for m in re.finditer(simple_pattern, text, re.IGNORECASE):
            simple_entries.append({
                'iso_number': m.group(1),
                'weld_number': m.group(4) or '',
                'evaluation': 'Accept' if 'accept' in m.group(3).lower() else 'Reject',
                'remarks': m.group(4) or '',
                'ut_indication': {
                    'probe_angle': int(m.group(2)) if m.group(2) else None,
                },
            })

        if len(simple_entries) > len(best):
            best = simple_entries

        # Fuzzy OCR table parsing for garbled text
        fuzzy_entries = self._parse_fuzzy_ocr_table(text)
        if len(fuzzy_entries) > len(best):
            best = fuzzy_entries

        return best

    def _parse_fuzzy_ocr_table(self, text):
        """Parse weld entries from garbled OCR table text.

        Handles common OCR errors like 0/o confusion, missing dashes,
        doubled characters, and partial word matches for ACCEPT/REJECT.
        """
        entries = []
        lines = text.split('\n')

        in_table = False
        for line in lines:
            line_upper = line.upper()

            # Detect table start
            if 'SPOOL/WELD' in line_upper or 'WELD#' in line_upper:
                in_table = True
                continue

            # Detect table end
            if in_table and (
                'ACCEPTED EVALUATION' in line_upper
                or 'ADDITIONAL REMARK' in line_upper
                or 'INSPECTED BY' in line_upper
            ):
                break

            if not in_table:
                continue

            # Skip short/empty lines
            stripped = line.strip().lstrip('|').lstrip('[').strip()
            if len(stripped) < 8:
                continue

            # Try to find a TW-like label in the line
            # Pattern handles: TWR-804-1, TWwR-804-1, Twe-go4-9, TWR-80417, TWR772-1
            iso_digits = None
            weld_suffix = None

            # Pattern 1: With separator between ISO and suffix, ISO is 2-4 chars
            # Handles TWR-804-1, Twe-go4-9, TWR772- 1
            label_match = re.search(
                r'T[Ww][A-Za-z]{0,2}'               # TW + up to 2 more chars (TWR, TWwR, Twe)
                r'[-_.\s]*'                     # optional separator before ISO digits
                r'([0-9A-Za-z]{2,4})'           # ISO number digits (2-4 chars)
                r'[-_.\s]+'                     # separator between ISO and suffix (REQUIRED)
                r'([0-9A-Za-z]{1,3})',          # weld suffix
                stripped, re.IGNORECASE
            )
            if label_match:
                norm_iso = self._normalize_ocr_digits(label_match.group(1))
                norm_suffix = self._normalize_ocr_digits(label_match.group(2))
                # Both ISO digits and suffix must be purely numeric after normalization
                if norm_iso.isdigit() and norm_suffix.isdigit():
                    iso_digits = label_match.group(1)
                    weld_suffix = label_match.group(2)

            # Pattern 2: No separator (TWR-80417 → 804 + 17)
            if not iso_digits:
                label_match = re.search(
                    r'T[Ww][A-Za-z]{0,2}'
                    r'[-_.\s]*'
                    r'(\d{3})'                  # 3-digit ISO number
                    r'(\d{1,2})\b',             # 1-2 digit suffix
                    stripped, re.IGNORECASE
                )
                if label_match:
                    iso_digits = label_match.group(1)
                    weld_suffix = label_match.group(2)

            if not iso_digits or not weld_suffix:
                continue

            # Normalize OCR digit errors
            iso_digits = self._normalize_ocr_digits(iso_digits)
            weld_suffix = self._normalize_ocr_digits(weld_suffix)

            # Skip if weld suffix doesn't look numeric after normalization
            try:
                int(weld_suffix)
            except ValueError:
                continue

            iso_number = f'TW_-{iso_digits}'  # placeholder prefix, normalized later
            weld_num = f'Weld {weld_suffix}'

            # Determine evaluation from the line
            evaluation = self._fuzzy_eval(line)

            entries.append({
                'iso_number': iso_number,
                'weld_number': weld_num,
                'evaluation': evaluation,
                'remarks': '',
                'ut_indication': {},
            })

        # Post-process: normalize garbled ISO numbers and weld suffixes
        normalized = self._normalize_ocr_entries(entries)

        # Deduplicate AFTER normalization (different raw ISOs may normalize to same)
        # When duplicates exist, prefer Accept (OCR artifacts like RESECT may
        # be garbled ACCEPT, and report summaries typically confirm acceptance)
        seen = {}
        for e in normalized:
            key = (e['iso_number'], e['weld_number'])
            if key not in seen:
                seen[key] = e
            elif e['evaluation'] == 'Accept' and seen[key]['evaluation'] != 'Accept':
                seen[key] = e  # prefer Accept over garbled Reject

        return list(seen.values())

    def _normalize_ocr_entries(self, entries):
        """Post-process OCR entries to fix garbled ISO numbers and weld suffixes.

        Uses position-wise majority voting to determine canonical ISO numbers,
        then normalizes all entries to the canonical values.
        """
        if not entries:
            return entries

        from collections import Counter

        # Step 1: Extract normalized digit portions from all ISO numbers
        norm_digits_list = []
        for e in entries:
            iso = e['iso_number']
            raw_digits = re.sub(r'^TW.?[-_.]?', '', iso, flags=re.IGNORECASE)
            norm = self._normalize_ocr_digits(raw_digits)
            norm_digits_list.append(norm)

        # Step 2: Group by length AND first digit (separates e.g., 804 from 772)
        cluster_groups = {}
        for i, nd in enumerate(norm_digits_list):
            # Use (length, first_digit) as cluster key
            key = (len(nd), nd[0] if nd else '?')
            if key not in cluster_groups:
                cluster_groups[key] = []
            cluster_groups[key].append((i, nd))

        # Step 3: For each cluster, find canonical by majority vote per position
        canonical_map = {}  # index -> canonical digits
        cluster_canonicals = {}  # cluster_key -> (canonical_str, count)
        for cluster_key, items in cluster_groups.items():
            length = cluster_key[0]

            if len(items) < 2:
                canonical_str = items[0][1]
            else:
                canonical = []
                for pos in range(length):
                    chars_at_pos = [nd[pos] for _, nd in items if pos < len(nd)]
                    most_common_char = Counter(chars_at_pos).most_common(1)[0][0]
                    canonical.append(most_common_char)
                canonical_str = ''.join(canonical)

            cluster_canonicals[cluster_key] = (canonical_str, len(items))
            for idx, _ in items:
                canonical_map[idx] = canonical_str

        # Step 3b: Merge small clusters (≤2 entries) into the largest same-length cluster
        for cluster_key, items in cluster_groups.items():
            if len(items) > 2:
                continue  # Only merge small clusters
            length = cluster_key[0]
            # Find the largest cluster with the same length
            best_key = None
            best_count = 0
            for other_key, (_, count) in cluster_canonicals.items():
                if other_key != cluster_key and other_key[0] == length and count > best_count:
                    best_key = other_key
                    best_count = count
            if best_key and best_count > 2:
                # Merge: use the larger cluster's canonical
                large_canonical = cluster_canonicals[best_key][0]
                for idx, _ in items:
                    canonical_map[idx] = large_canonical

        # Step 4: Determine the TW prefix letter (R, S, etc.) - most common
        prefix_letter = 'R'  # default

        # Step 5: Normalize each entry
        for i, e in enumerate(entries):
            if i in canonical_map:
                e['iso_number'] = f'TW{prefix_letter}-{canonical_map[i]}'

            # Fix weld suffixes - truncate numbers that are too large
            weld = e.get('weld_number', '')
            wm = re.match(r'Weld\s+(\d+)', weld)
            if wm:
                num_str = wm.group(1)
                num = int(num_str)
                # Most weld numbers are 1-25; larger numbers likely have OCR garbage
                if num > 25 and len(num_str) > 1:
                    num = int(num_str[0])
                    if num == 0 and len(num_str) > 1:
                        num = int(num_str[:2])
                e['weld_number'] = f'Weld {num}'

        return entries

    @staticmethod
    def _normalize_ocr_digits(s):
        """Normalize common OCR digit errors."""
        char_map = {
            'o': '0', 'O': '0', 'D': '0',
            's': '5', 'S': '5',
            'g': '9', 'q': '9',
            't': '1', 'l': '1', 'I': '1', 'i': '1',
            'Z': '2', 'z': '2',
            'a': '4', 'A': '4',
            'b': '6', 'G': '6',
            'B': '8',
            'e': '8',  # common in context like "8ode" for "804"
        }
        return ''.join(char_map.get(c, c) for c in s)

    @staticmethod
    def _fuzzy_eval(line):
        """Determine Accept/Reject from a line with OCR errors."""
        line_lower = line.lower()
        # Clear reject indicators
        if re.search(r'\breject\b|\bresect\b|\brej\b', line_lower):
            return 'Reject'
        # Accept indicators (partial matches for garbled OCR)
        if re.search(r'\baccept\b|\bacce\w*\b|\banc\w*\b|\bace\w*\b|\bpace\b|\bface\b', line_lower):
            return 'Accept'
        # Default to Accept (most entries in UT reports are accepted)
        return 'Accept'

    def _parse_date(self, date_str):
        """Try parsing various date formats."""
        formats = [
            '%m-%d-%Y',       # 09-26-2025
            '%m-%d-%y',       # 09-26-25
            '%m/%d/%Y',       # 09/26/2025
            '%B %d, %Y',     # September 26, 2025
            '%Y-%m-%d',       # 2025-09-26
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None
