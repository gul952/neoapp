from functools import wraps
import csv
import io

from flask import Blueprint, render_template, redirect, url_for, request, flash, Response
from flask_login import login_required, current_user
from datetime import datetime

from models import db, User, ConsentRecord, PatientAssessment, CdsOutput, RuleChangeSuggestion

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    """Route decorator: must be logged in AND have the admin role."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin():
            flash("That page is restricted to admin accounts.")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/users")
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin_users.html", users=users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def new_user():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "doctor")

        if not full_name or not username or not password:
            flash("All fields are required.")
            return redirect(url_for("admin.new_user"))

        if User.query.filter_by(username=username).first():
            flash("That username is already taken.")
            return redirect(url_for("admin.new_user"))

        user = User(full_name=full_name, username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Account created for {full_name}. Give them the username and password to log in.")
        return redirect(url_for("admin.list_users"))

    return render_template("admin_new_user.html")


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["GET", "POST"])
@admin_required
def reset_password(user_id):
    target = User.query.get_or_404(user_id)

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        if len(new_password) < 8:
            flash("New password must be at least 8 characters.")
            return redirect(url_for("admin.reset_password", user_id=user_id))

        target.set_password(new_password)
        db.session.commit()
        flash(f"Password reset for {target.full_name}. Give them the new password directly.")
        return redirect(url_for("admin.list_users"))

    return render_template("admin_reset_password.html", target=target)


@admin_bp.route("/patients")
@admin_required
def patients():
    """Cross-patient view for the PI/admin. Deliberately keyed by study_id
    only - guardian names/contacts live solely in ConsentRecord and are not
    surfaced here, consistent with keeping identity separate from clinical
    data throughout the app."""
    records = ConsentRecord.query.order_by(ConsentRecord.consented_at.desc()).all()
    rows = []
    for r in records:
        latest = (
            PatientAssessment.query.filter_by(study_id=r.study_id)
            .order_by(PatientAssessment.created_at.desc())
            .first()
        )
        output = CdsOutput.query.filter_by(assessment_id=latest.id).first() if latest else None
        count = PatientAssessment.query.filter_by(study_id=r.study_id).count()
        rows.append(
            {
                "study_id": r.study_id,
                "consented_at": r.consented_at,
                "assessment_count": count,
                "latest": latest,
                "output": output,
            }
        )
    return render_template("admin_patients.html", rows=rows)


@admin_bp.route("/export/csv")
@admin_required
def export_csv():
    """Exports clinical/assessment data only - never guardian names, contacts,
    or signatures, which live solely in ConsentRecord and are deliberately
    excluded here, consistent with keeping identity separate from clinical
    data everywhere else in the app."""
    assessments = PatientAssessment.query.order_by(PatientAssessment.created_at.asc()).all()

    # Different encounters may fill in different subsets of A-E fields, so
    # collect the union of every raw_inputs key ever used, sorted for a
    # stable column order - every row gets every column, blank where unused.
    raw_keys = set()
    for a in assessments:
        if a.raw_inputs:
            raw_keys.update(a.raw_inputs.keys())
    raw_keys = sorted(raw_keys)

    fixed_columns = [
        "study_id", "assessment_id", "entered_at", "entered_by",
        "system_classification", "observation_only", "mat_risk_score", "clinical_sign_count", "lab_score",
        "regimen", "duration_days",
        "doctor_agreed", "doctor_classification", "doctor_notes", "doctor_reviewed_at",
        "confirmed_outcome", "outcome_entered_at", "outcome_entered_by",
    ]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(fixed_columns + raw_keys)

    for a in assessments:
        output = CdsOutput.query.filter_by(assessment_id=a.id).first()
        row = [
            a.study_id,
            a.id,
            a.created_at.isoformat() if a.created_at else "",
            a.entered_by.full_name if a.entered_by else "",
            output.classification if output else "",
            output.observation_only if output else "",
            output.mat_risk_score if output else "",
            output.clinical_sign_count if output else "",
            output.lab_score if output else "",
            "; ".join(output.regimen_json.get("regimen", [])) if output and output.regimen_json else "",
            output.duration_days if output else "",
            output.doctor_agreed if output else "",
            output.doctor_classification if output else "",
            output.doctor_notes if output else "",
            output.doctor_reviewed_at.isoformat() if output and output.doctor_reviewed_at else "",
            output.confirmed_outcome if output else "",
            output.outcome_entered_at.isoformat() if output and output.outcome_entered_at else "",
            output.outcome_entered_by.full_name if output and output.outcome_entered_by else "",
        ]
        raw = a.raw_inputs or {}
        row += [raw.get(k, "") for k in raw_keys]
        writer.writerow(row)

    filename = f"neosepsis_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@admin_bp.route("/disagreements")
@admin_required
def disagreements():
    """Cases where the doctor's own clinical judgment differed from the
    system's classification. This is the raw signal that eventually feeds
    proposed rule-threshold changes - a human (PI) still has to review and
    draft any actual change; nothing here modifies scoring.py automatically."""
    total_reviewed = CdsOutput.query.filter(CdsOutput.doctor_reviewed_at.isnot(None)).count()
    disagreed_outputs = (
        CdsOutput.query.filter_by(doctor_agreed=False)
        .order_by(CdsOutput.doctor_reviewed_at.desc())
        .all()
    )
    rows = []
    for o in disagreed_outputs:
        assessment = PatientAssessment.query.get(o.assessment_id)
        rows.append({"output": o, "assessment": assessment})

    total_disagreed = len(rows)
    agreement_rate = None
    if total_reviewed:
        agreement_rate = round((total_reviewed - total_disagreed) / total_reviewed * 100, 1)

    return render_template(
        "admin_disagreements.html",
        rows=rows,
        total_reviewed=total_reviewed,
        total_disagreed=total_disagreed,
        agreement_rate=agreement_rate,
    )


@admin_bp.route("/suggestions")
@login_required
def suggestions():
    pending = (
        RuleChangeSuggestion.query.filter_by(status="pending")
        .order_by(RuleChangeSuggestion.proposed_at.desc())
        .all()
    )
    decided = (
        RuleChangeSuggestion.query.filter(RuleChangeSuggestion.status != "pending")
        .order_by(RuleChangeSuggestion.reviewed_at.desc())
        .all()
    )
    return render_template("admin_suggestions.html", pending=pending, decided=decided)


@admin_bp.route("/suggestions/new", methods=["GET", "POST"])
@login_required
def new_suggestion():
    if request.method == "POST":
        flowchart = request.form.get("flowchart", "").strip()
        node_id = request.form.get("node_id", "").strip()
        description = request.form.get("description", "").strip()
        rationale = request.form.get("rationale", "").strip()

        if not description:
            flash("A description of the proposed change is required.")
            return redirect(url_for("admin.new_suggestion"))

        suggestion = RuleChangeSuggestion(
            flowchart=flowchart or None,
            node_id=node_id or None,
            description=description,
            rationale=rationale or None,
            proposed_by_id=current_user.id,
        )
        db.session.add(suggestion)
        db.session.commit()
        flash("Suggestion recorded as pending review.")
        return redirect(url_for("admin.suggestions"))

    return render_template("admin_suggestion_new.html")


@admin_bp.route("/suggestions/<int:suggestion_id>/decide", methods=["POST"])
@admin_required
def decide_suggestion(suggestion_id):
    """Records the PI's decision. IMPORTANT: this does not modify scoring.py -
    accepting a suggestion here is a logged decision, not a code change. A
    developer still has to apply the actual threshold edit deliberately."""
    suggestion = RuleChangeSuggestion.query.get_or_404(suggestion_id)
    decision = request.form.get("decision")
    if decision not in ("accept", "decline"):
        flash("Invalid decision.")
        return redirect(url_for("admin.suggestions"))

    suggestion.status = "accepted" if decision == "accept" else "declined"
    suggestion.reviewed_by_id = current_user.id
    suggestion.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f"Suggestion marked as {suggestion.status}.")
    return redirect(url_for("admin.suggestions"))


@admin_bp.route("/suggestions/<int:suggestion_id>/mark-applied", methods=["POST"])
@admin_required
def mark_applied(suggestion_id):
    """Confirms a developer has actually gone and edited scoring.py for this
    accepted suggestion - separate from the accept/decline decision itself."""
    suggestion = RuleChangeSuggestion.query.get_or_404(suggestion_id)
    if suggestion.status != "accepted":
        flash("Only accepted suggestions can be marked as applied.")
        return redirect(url_for("admin.suggestions"))

    suggestion.applied_to_scoring = True
    suggestion.applied_at = datetime.utcnow()
    suggestion.applied_by_id = current_user.id
    db.session.commit()
    flash("Marked as applied to scoring.py.")
    return redirect(url_for("admin.suggestions"))
