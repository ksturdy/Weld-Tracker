from datetime import datetime
from flask import Blueprint, render_template, request
from app import db
from app.models import InspectionReport, WeldEntry

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    # Parse filters
    filters = {
        'type': request.args.get('type', ''),
        'date_from': request.args.get('date_from', ''),
        'date_to': request.args.get('date_to', ''),
        'result': request.args.get('result', ''),
    }

    # Build query
    query = db.session.query(WeldEntry, InspectionReport).join(
        InspectionReport, WeldEntry.report_id == InspectionReport.id
    )

    if filters['type']:
        query = query.filter(InspectionReport.inspection_type == filters['type'])
    if filters['date_from']:
        try:
            date_from = datetime.strptime(filters['date_from'], '%Y-%m-%d').date()
            query = query.filter(InspectionReport.inspection_date >= date_from)
        except ValueError:
            pass
    if filters['date_to']:
        try:
            date_to = datetime.strptime(filters['date_to'], '%Y-%m-%d').date()
            query = query.filter(InspectionReport.inspection_date <= date_to)
        except ValueError:
            pass
    if filters['result']:
        query = query.filter(WeldEntry.evaluation.ilike(f"%{filters['result']}%"))

    entries = query.order_by(InspectionReport.inspection_date.desc()).all()

    # Stats
    total = len(entries)
    accepted = sum(1 for e, r in entries if e.evaluation and 'accept' in e.evaluation.lower())
    rejected = sum(1 for e, r in entries if e.evaluation and 'reject' in e.evaluation.lower())
    report_count = InspectionReport.query.count()

    stats = {
        'total': total,
        'accepted': accepted,
        'rejected': rejected,
        'reports': report_count,
    }

    return render_template('dashboard.html', entries=entries, filters=filters, stats=stats)


@dashboard_bp.route('/report/<int:report_id>')
def report_detail(report_id):
    report = InspectionReport.query.get_or_404(report_id)
    weld_entries = report.weld_entries.all()
    ut_details = report.ut_details

    return render_template('report_detail.html',
                           report=report,
                           weld_entries=weld_entries,
                           ut_details=ut_details)
