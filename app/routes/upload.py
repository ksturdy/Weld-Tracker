import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from werkzeug.utils import secure_filename
from app.services.import_service import process_pdf
from app.services.excel_import import import_nde_dashboard
from app.services.stratus_import import import_stratus_map, assign_packages_to_entries

upload_bp = Blueprint('upload', __name__)


@upload_bp.route('/upload')
def upload_page():
    return render_template('upload.html')


@upload_bp.route('/upload', methods=['POST'])
def upload_file():
    if 'pdf_files' not in request.files:
        flash('No files selected.', 'error')
        return redirect(url_for('upload.upload_page'))

    files = request.files.getlist('pdf_files')
    if not files or all(f.filename == '' for f in files):
        flash('No files selected.', 'error')
        return redirect(url_for('upload.upload_page'))

    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)

    success_count = 0
    error_messages = []

    for file in files:
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            error_messages.append(f'{file.filename}: Not a PDF file.')
            continue

        filename = secure_filename(file.filename)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)

        try:
            report = process_pdf(filepath, file.filename)
            weld_count = report.weld_entries.count()
            success_count += 1
            flash(f'{file.filename}: Processed successfully - {report.inspection_type} report with {weld_count} weld entries.', 'success')
        except Exception as e:
            error_messages.append(f'{file.filename}: {str(e)}')

    for msg in error_messages:
        flash(msg, 'error')

    if success_count > 0:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('upload.upload_page'))


@upload_bp.route('/import-stratus', methods=['POST'])
def import_stratus():
    if 'stratus_file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('upload.upload_page'))

    file = request.files['stratus_file']
    if not file.filename:
        flash('No file selected.', 'error')
        return redirect(url_for('upload.upload_page'))

    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        flash('Please upload an Excel file (.xlsx or .xls).', 'error')
        return redirect(url_for('upload.upload_page'))

    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)

    filename = secure_filename(file.filename)
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    try:
        summary = import_stratus_map(filepath)
        # Also assign packages to any existing weld entries
        updated = assign_packages_to_entries()
        flash(
            f'Stratus map imported: {summary["sheets_processed"]} sheets, '
            f'{summary["entries_imported"]} new entries, '
            f'{summary["entries_updated"]} updated. '
            f'{updated} existing weld entries matched to packages.',
            'success'
        )
    except Exception as e:
        flash(f'Import error: {str(e)}', 'error')

    return redirect(url_for('dashboard.index'))
