"""
Database schema for the NeoSepsis data collection app.

Design principle: identifying information and clinical information are kept
in separate tables, linked only by a random, non-identifying study_id.
A doctor entering clinical data never needs to see the guardian's name/contact
on the same screen as the clinical fields.
"""
from datetime import datetime
import secrets

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """A doctor or admin account. Kept intentionally simple - no email
    verification, no password reset flow - since this runs on a private
    network for a known, small group of clinicians."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="doctor")  # "doctor" or "admin"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == "admin"


class ConsentRecord(db.Model):
    """One row per consenting guardian/patient. This is the ONLY table that
    holds identifying information. Everything else refers to the patient
    only by study_id."""
    __tablename__ = "consent_records"

    id = db.Column(db.Integer, primary_key=True)
    study_id = db.Column(db.String(20), unique=True, nullable=False, index=True)

    guardian_name = db.Column(db.String(200), nullable=False)
    guardian_contact = db.Column(db.String(200))
    relationship_to_infant = db.Column(db.String(80))

    consent_form_version = db.Column(db.String(20), nullable=False)
    signature_data = db.Column(db.Text, nullable=False)  # base64 PNG from signature pad

    consented_at = db.Column(db.DateTime, default=datetime.utcnow)
    witnessed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    witnessed_by = db.relationship("User")

    @staticmethod
    def generate_study_id():
        return "NS-" + secrets.token_hex(4).upper()


class PatientAssessment(db.Model):
    """One row per clinical data-entry session for a consented patient.

    Raw clinical inputs (all the Flowchart A-E fields) are stored as a single
    JSON blob rather than one database column per field. This is a deliberate
    simplicity trade-off: if a clinical field is added, renamed, or removed
    later, that's a change to the intake form only - not a database migration.
    """
    __tablename__ = "patient_assessments"

    id = db.Column(db.Integer, primary_key=True)
    study_id = db.Column(db.String(20), db.ForeignKey("consent_records.study_id"), nullable=False, index=True)
    entered_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    raw_inputs = db.Column(db.JSON, nullable=False)

    entered_by = db.relationship("User")


class CdsOutput(db.Model):
    """The classification/regimen the rule engine produced for a given
    assessment, saved as a permanent snapshot - plus a place to record the
    real-world outcome later, once known. That pairing (prediction vs.
    actual outcome) is what eventually powers the rule-change suggestions."""
    __tablename__ = "cds_outputs"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("patient_assessments.id"), nullable=False, index=True)

    rules_version = db.Column(db.String(20), nullable=False)  # which ruleset produced this
    classification = db.Column(db.String(20))  # PROVEN / PROBABLE / POSSIBLE / NONE
    mat_risk_score = db.Column(db.Integer)
    clinical_sign_count = db.Column(db.Integer)
    lab_score = db.Column(db.Integer)
    regimen_json = db.Column(db.JSON)
    duration_days = db.Column(db.Integer)
    observation_only = db.Column(db.Boolean, default=False)  # mild Possible cases: monitor, don't treat yet
    triggered_nodes = db.Column(db.JSON)  # list of {flowchart, node_id, label, points, override}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Filled in later, once the real clinical outcome is known
    confirmed_outcome = db.Column(db.String(20), nullable=True)  # e.g. "sepsis_confirmed" / "sepsis_ruled_out"
    outcome_entered_at = db.Column(db.DateTime, nullable=True)
    outcome_entered_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    outcome_entered_by = db.relationship("User", foreign_keys=[outcome_entered_by_id])

    # The doctor's own independent clinical judgment, captured separately
    # from the system's classification above - this side-by-side pairing
    # (system says X, doctor says Y) is what eventually drives rule-change
    # suggestions. Neither value overwrites the other.
    doctor_agreed = db.Column(db.Boolean, nullable=True)  # True = doctor agreed with system's classification
    doctor_classification = db.Column(db.String(20), nullable=True)  # doctor's own call, if they disagreed
    doctor_notes = db.Column(db.Text, nullable=True)
    doctor_reviewed_at = db.Column(db.DateTime, nullable=True)


class ScoringParameter(db.Model):
    """Structured, tunable registry of scoring thresholds/point values, keyed
    by the same node_id scheme already used for 'Why This Decision' tracking.

    This is what makes rule-change suggestions safe to auto-apply: instead of
    a doctor writing free text like "raise the ROM threshold" and someone
    having to guess what that means in code, they pick a node, see its
    current threshold/points pulled from here, and propose new numbers. If
    accepted, applying the change is just updating this row - not editing
    Python source.

    Only nodes with a genuinely tunable numeric threshold and/or point value
    belong here. Pure override nodes (e.g. seizures, chorioamnionitis) don't
    have a "threshold" to tune in the same sense and aren't included -
    changing what counts as an override is a structural change, not a
    numeric recalibration, and still requires a developer.
    """
    __tablename__ = "scoring_parameters"

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.String(30), unique=True, nullable=False, index=True)
    flowchart = db.Column(db.String(5), nullable=False)
    label = db.Column(db.String(300), nullable=False)
    threshold = db.Column(db.Float, nullable=True)
    threshold_unit = db.Column(db.String(30), nullable=True)  # display only, e.g. "\u00b0C", "hours"
    points = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)  # rationale / literature citation for the current value

    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by = db.relationship("User")


class RuleChangeSuggestion(db.Model):
    """A proposed edit to an A-E flowchart threshold/weight, generated from
    aggregate analysis of assessments vs. confirmed outcomes. Nothing writes
    to this table automatically yet - the workflow (and its accept/decline
    review screen) is built now so the analysis piece can be plugged in
    later without a schema change."""
    __tablename__ = "rule_change_suggestions"

    id = db.Column(db.Integer, primary_key=True)
    proposed_at = db.Column(db.DateTime, default=datetime.utcnow)
    proposed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # null = system-generated
    proposed_by = db.relationship("User", foreign_keys=[proposed_by_id])

    flowchart = db.Column(db.String(5))   # "A","B","C","D","E"
    node_id = db.Column(db.String(30))    # e.g. "A12b"
    description = db.Column(db.Text, nullable=False)   # what the change is
    rationale = db.Column(db.Text)                     # why it's being proposed
    supporting_data = db.Column(db.JSON)                # numbers backing the suggestion

    # Structured proposal, only meaningful when node_id matches a row in
    # scoring_parameters - this is what lets "accept -> apply" safely update
    # the registry instead of requiring a developer to interpret free text.
    proposed_new_threshold = db.Column(db.Float, nullable=True)
    proposed_new_points = db.Column(db.Float, nullable=True)

    status = db.Column(db.String(20), default="pending")  # pending / accepted / declined
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    # Accepting a suggestion only records the PI's decision - it does not
    # touch scoring.py. This separately tracks whether a developer has since
    # gone and actually applied the threshold edit in code.
    applied_to_scoring = db.Column(db.Boolean, default=False)
    applied_at = db.Column(db.DateTime, nullable=True)
    applied_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    applied_by = db.relationship("User", foreign_keys=[applied_by_id])

    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
