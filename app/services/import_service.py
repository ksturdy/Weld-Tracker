import os
from app import db
from app.models import InspectionReport, WeldEntry, UTDetail, UTIndication
from app.extractors.classifier import classify_pdf
from app.extractors.vt_extractor import VTExtractor
from app.extractors.ut_extractor import UTExtractor
from app.services.stratus_import import lookup_package


def process_pdf(pdf_path, original_filename=None):
    """Process a PDF file: classify, extract, and save to database.

    Returns the created InspectionReport or raises an exception.
    """
    if original_filename is None:
        original_filename = os.path.basename(pdf_path)

    # Step 1: Classify the PDF
    doc_type = classify_pdf(pdf_path)

    if doc_type == 'VT':
        return _process_vt(pdf_path, original_filename)
    elif doc_type == 'UT':
        return _process_ut(pdf_path, original_filename)
    else:
        raise ValueError(f'Unsupported or unrecognized document type: {doc_type}')


def _check_scanned_pdf(pdf_path):
    """Check if a PDF is scanned (no embedded text). Returns True if scanned."""
    import pdfplumber
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                text = pdf.pages[0].extract_text() or ''
                return len(text.strip()) < 50
    except Exception:
        pass
    return True


def _process_vt(pdf_path, filename):
    """Process a VT inspection report."""
    is_scanned = _check_scanned_pdf(pdf_path)
    extractor = VTExtractor(pdf_path)
    data = extractor.parse()
    header = data['header']

    # Only reject if we got NO useful data at all (no header fields and no entries)
    if not data['weld_entries'] and not header.get('job_number') and not header.get('project_name'):
        raise ValueError(
            'Could not extract data from this PDF. If it is a scanned document, '
            'ensure Tesseract OCR and Poppler are installed.'
        )

    report = InspectionReport(
        job_number=header.get('job_number'),
        po_number=header.get('po_number'),
        inspection_type='VT',
        inspection_date=header.get('inspection_date'),
        project_name=header.get('project_name'),
        project_job_number=header.get('project_job_number'),
        client=header.get('client'),
        location=header.get('location'),
        specification=header.get('specification'),
        procedure_number=header.get('procedure_number'),
        inspector_name=header.get('inspector_name'),
        inspector_cert=header.get('inspector_cert'),
        result_summary=header.get('result_summary'),
        pdf_filename=filename,
        pdf_path=pdf_path,
    )
    db.session.add(report)
    db.session.flush()  # Get the report ID

    for entry_data in data['weld_entries']:
        iso = entry_data['iso_number']
        weld_num = entry_data['weld_number']
        entry = WeldEntry(
            report_id=report.id,
            iso_number=iso,
            weld_number=weld_num,
            package_number=lookup_package(iso, weld_num),
            evaluation=entry_data['evaluation'],
            remarks=entry_data.get('remarks', ''),
        )
        db.session.add(entry)

    db.session.commit()
    return report


def _process_ut(pdf_path, filename):
    """Process a UT inspection report."""
    is_scanned = _check_scanned_pdf(pdf_path)
    extractor = UTExtractor(pdf_path)
    data = extractor.parse()
    header = data['header']

    # Only reject if we got NO useful data at all
    if not data['weld_entries'] and not header.get('job_number') and not header.get('project_name'):
        raise ValueError(
            'Could not extract data from this PDF. If it is a scanned document, '
            'ensure Tesseract OCR and Poppler are installed.'
        )

    report = InspectionReport(
        job_number=header.get('job_number'),
        po_number=header.get('po_number'),
        inspection_type='UT',
        inspection_date=header.get('inspection_date'),
        project_name=header.get('project_name'),
        project_job_number=header.get('project_job_number'),
        client=header.get('client'),
        location=header.get('location'),
        specification=header.get('specification'),
        procedure_number=header.get('procedure_number'),
        inspector_name=header.get('inspector_name'),
        inspector_cert=header.get('inspector_cert'),
        result_summary=header.get('result_summary', 'Accepted'),
        pdf_filename=filename,
        pdf_path=pdf_path,
    )
    db.session.add(report)
    db.session.flush()

    # Save UT-specific details
    ut_data = data.get('ut_details', {})
    if ut_data:
        ut_detail = UTDetail(
            report_id=report.id,
            instrument_sn=ut_data.get('instrument_sn'),
            member_identification=ut_data.get('member_identification'),
            material_thickness=ut_data.get('material_thickness'),
            weld_joint_design=ut_data.get('weld_joint_design'),
            weld_process=ut_data.get('weld_process'),
            material_type=ut_data.get('material_type'),
            volume_scanned_pct=ut_data.get('volume_scanned_pct'),
            surface_condition=ut_data.get('surface_condition'),
            reference_level_gain=ut_data.get('reference_level_gain'),
        )
        db.session.add(ut_detail)

    # Save weld entries with UT indications
    has_reject = False
    for entry_data in data['weld_entries']:
        iso = entry_data['iso_number']
        weld_num = entry_data.get('weld_number', '')
        entry = WeldEntry(
            report_id=report.id,
            iso_number=iso,
            weld_number=weld_num,
            package_number=lookup_package(iso, weld_num),
            evaluation=entry_data.get('evaluation', 'Accept'),
            remarks=entry_data.get('remarks', ''),
        )
        db.session.add(entry)
        db.session.flush()

        if entry_data.get('evaluation', '').lower() == 'reject':
            has_reject = True

        # Save UT indication data if present
        ut_ind_data = entry_data.get('ut_indication', {})
        if ut_ind_data and any(v is not None for v in ut_ind_data.values()):
            ut_ind = UTIndication(
                weld_entry_id=entry.id,
                probe_angle=ut_ind_data.get('probe_angle'),
                node=ut_ind_data.get('node'),
                indication_level=ut_ind_data.get('indication_level'),
                reference_level=ut_ind_data.get('reference_level'),
                attenuation_factor=ut_ind_data.get('attenuation_factor'),
                indication_rating=ut_ind_data.get('indication_rating'),
                indication_length=ut_ind_data.get('indication_length'),
                sound_path_distance=ut_ind_data.get('sound_path_distance'),
                depth_from_surface=ut_ind_data.get('depth_from_surface'),
            )
            db.session.add(ut_ind)

    if has_reject:
        report.result_summary = 'Rejected'

    db.session.commit()
    return report
