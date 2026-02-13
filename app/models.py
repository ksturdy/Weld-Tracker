from datetime import datetime, timezone
from app import db


class InspectionReport(db.Model):
    __tablename__ = 'inspection_reports'

    id = db.Column(db.Integer, primary_key=True)
    job_number = db.Column(db.String(50), index=True)
    po_number = db.Column(db.String(50))
    inspection_type = db.Column(db.String(20), index=True)  # VT, UT, WPS, PQR
    inspection_date = db.Column(db.Date, index=True)
    project_name = db.Column(db.String(200))
    project_job_number = db.Column(db.String(50))
    client = db.Column(db.String(200))
    location = db.Column(db.String(200))
    specification = db.Column(db.String(200))
    procedure_number = db.Column(db.String(100))
    inspector_name = db.Column(db.String(100))
    inspector_cert = db.Column(db.String(50))
    result_summary = db.Column(db.String(50))
    pdf_filename = db.Column(db.String(500))
    pdf_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    weld_entries = db.relationship('WeldEntry', backref='report', lazy='dynamic', cascade='all, delete-orphan')
    ut_details = db.relationship('UTDetail', backref='report', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<InspectionReport {self.job_number} {self.inspection_type} {self.inspection_date}>'


class WeldEntry(db.Model):
    __tablename__ = 'weld_entries'

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('inspection_reports.id'), nullable=False, index=True)
    iso_number = db.Column(db.String(50), index=True)
    weld_number = db.Column(db.String(20))
    package_number = db.Column(db.String(100), index=True)
    evaluation = db.Column(db.String(20))  # Accept / Reject
    remarks = db.Column(db.Text)

    ut_indication = db.relationship('UTIndication', backref='weld_entry', uselist=False, cascade='all, delete-orphan')

    @property
    def weld_label(self):
        """Full weld label as it appears in the Stratus map (e.g. TWS-189-1)."""
        if self.iso_number and self.weld_number:
            import re
            m = re.search(r'(\d+)', self.weld_number)
            if m:
                return f'{self.iso_number}-{m.group(1)}'
        return self.iso_number

    def __repr__(self):
        return f'<WeldEntry {self.iso_number} {self.weld_number} {self.evaluation}>'


class StratusMap(db.Model):
    __tablename__ = 'stratus_map'

    id = db.Column(db.Integer, primary_key=True)
    weld_label = db.Column(db.String(50), unique=True, index=True)  # e.g. TWR-001-1
    package_number = db.Column(db.String(100), index=True)  # e.g. CDU01_08.2
    size = db.Column(db.String(50))
    weld_type = db.Column(db.String(50))  # BW, FW, etc.
    description = db.Column(db.String(200))
    sheet_name = db.Column(db.String(50))  # DH1100, DH1300

    def __repr__(self):
        return f'<StratusMap {self.weld_label} -> {self.package_number}>'


class UTDetail(db.Model):
    __tablename__ = 'ut_details'

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('inspection_reports.id'), nullable=False, unique=True)
    instrument_sn = db.Column(db.String(50))
    member_identification = db.Column(db.String(200))
    material_thickness = db.Column(db.String(50))
    weld_joint_design = db.Column(db.String(50))
    weld_process = db.Column(db.String(50))
    material_type = db.Column(db.String(50))
    volume_scanned_pct = db.Column(db.Integer)
    surface_condition = db.Column(db.String(100))
    reference_level_gain = db.Column(db.String(20))

    def __repr__(self):
        return f'<UTDetail report={self.report_id} {self.material_type} {self.weld_process}>'


class UTIndication(db.Model):
    __tablename__ = 'ut_indications'

    id = db.Column(db.Integer, primary_key=True)
    weld_entry_id = db.Column(db.Integer, db.ForeignKey('weld_entries.id'), nullable=False, unique=True)
    probe_angle = db.Column(db.Integer)
    node = db.Column(db.String(20))
    indication_level = db.Column(db.Float)
    reference_level = db.Column(db.Float)
    attenuation_factor = db.Column(db.Float)
    indication_rating = db.Column(db.Float)
    indication_length = db.Column(db.Float)
    sound_path_distance = db.Column(db.Float)
    depth_from_surface = db.Column(db.Float)

    def __repr__(self):
        return f'<UTIndication weld={self.weld_entry_id} angle={self.probe_angle}>'
