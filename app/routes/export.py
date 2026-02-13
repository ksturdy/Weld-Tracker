from datetime import datetime
from flask import Blueprint, render_template, request, send_file
from app.services.excel_export import export_to_excel

export_bp = Blueprint('export', __name__)


@export_bp.route('/export')
def export_page():
    return render_template('export.html')


@export_bp.route('/export', methods=['POST'])
def export_excel():
    filters = {}

    inspection_type = request.form.get('inspection_type', '').strip()
    if inspection_type:
        filters['inspection_type'] = inspection_type

    date_from = request.form.get('date_from', '').strip()
    if date_from:
        try:
            filters['date_from'] = datetime.strptime(date_from, '%Y-%m-%d').date()
        except ValueError:
            pass

    date_to = request.form.get('date_to', '').strip()
    if date_to:
        try:
            filters['date_to'] = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            pass

    project = request.form.get('project', '').strip()
    if project:
        filters['project'] = project

    result = request.form.get('result', '').strip()
    if result:
        filters['result'] = result

    buffer = export_to_excel(filters if filters else None)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'weld_tracker_export_{timestamp}.xlsx'

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
