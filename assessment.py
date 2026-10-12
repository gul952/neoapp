from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
import json
from datetime import datetime

from models import db, ConsentRecord, PatientAssessment, CdsOutput, ScoringParameter
import scoring

assessment_bp = Blueprint("assessment", __name__, url_prefix="/assessment")


@assessment_bp.route("/lookup", methods=["GET", "POST"])
@login_required
def lookup():
    if request.method == "POST":
        sid = request.form.get("study_id", "").strip().upper()
        record = ConsentRecord.query.filter_by(study_id=sid).first()
        if not record:
            flash("No patient found with that study ID. Double-check it and try again.")
            return redirect(url_for("assessment.lookup"))
        return redirect(url_for("assessment.history", study_id=sid))

    return render_template("assessment_lookup.html")


@assessment_bp.route("/<study_id>/history")
@login_required
def history(study_id):
    record = ConsentRecord.query.filter_by(study_id=study_id).first_or_404()
    assessments = (
        PatientAssessment.query.filter_by(study_id=study_id)
        .order_by(PatientAssessment.created_at.desc())
        .all()
    )
    entries = []
    for pa in assessments:
        output = CdsOutput.query.filter_by(assessment_id=pa.id).first()
        entries.append({"assessment": pa, "output": output})
    return render_template("assessment_history.html", study_id=study_id, entries=entries)


@assessment_bp.route("/<study_id>/view/<int:assessment_id>")
@login_required
def view(study_id, assessment_id):
    assessment = PatientAssessment.query.filter_by(id=assessment_id, study_id=study_id).first_or_404()
    output = CdsOutput.query.filter_by(assessment_id=assessment.id).first()
    return render_template(
        "assessment_view.html",
        study_id=study_id,
        assessment=assessment,
        output=output,
        raw_inputs=assessment.raw_inputs or {},
    )


VALID_OUTCOMES = {"sepsis_confirmed", "sepsis_ruled_out", "indeterminate"}


@assessment_bp.route("/<study_id>/outcome/<int:assessment_id>", methods=["POST"])
@login_required
def set_outcome(study_id, assessment_id):
    """Records the real clinical outcome, once known (culture finalized,
    NICU course concluded, etc.) - independent of both the system's
    classification and the doctor's earlier agree/disagree call. This is
    the third leg of the eventual system-vs-doctor-vs-reality comparison."""
    assessment = PatientAssessment.query.filter_by(id=assessment_id, study_id=study_id).first_or_404()
    output = CdsOutput.query.filter_by(assessment_id=assessment.id).first_or_404()

    outcome = request.form.get("confirmed_outcome")
    if outcome not in VALID_OUTCOMES:
        flash("Please select a valid outcome.")
        return redirect(url_for("assessment.view", study_id=study_id, assessment_id=assessment_id))

    output.confirmed_outcome = outcome
    output.outcome_entered_at = datetime.utcnow()
    output.outcome_entered_by_id = current_user.id
    db.session.commit()
    flash("Outcome recorded.")
    return redirect(url_for("assessment.view", study_id=study_id, assessment_id=assessment_id))


@assessment_bp.route("/<study_id>")
@login_required
def form(study_id):
    record = ConsentRecord.query.filter_by(study_id=study_id).first_or_404()
    latest = (
        PatientAssessment.query.filter_by(study_id=study_id)
        .order_by(PatientAssessment.created_at.desc())
        .first()
    )
    prefill = latest.raw_inputs if latest else None
    return render_template(
        "assessment.html",
        study_id=record.study_id,
        prefill_json=json.dumps(prefill) if prefill else "null",
        prefill_date=latest.created_at.strftime("%Y-%m-%d %H:%M") if latest else None,
    )


@assessment_bp.route("/<study_id>/submit", methods=["POST"])
@login_required
def submit(study_id):
    record = ConsentRecord.query.filter_by(study_id=study_id).first()
    if not record:
        return jsonify({"error": "Unknown study ID - no consent record found for this patient."}), 404

    state = request.get_json(silent=True)
    if state is None or not isinstance(state, dict):
        return jsonify({"error": "Invalid or missing data in request."}), 400

    params = {
        p.node_id: {"threshold": p.threshold, "points": p.points}
        for p in ScoringParameter.query.all()
    }
    result = scoring.run_pipeline(state, params)
    A, B, C, D, E = result["A"], result["B"], result["C"], result["D"], result["E"]

    assessment = PatientAssessment(
        study_id=study_id,
        entered_by_id=current_user.id,
        raw_inputs=state,
    )
    db.session.add(assessment)
    db.session.flush()  # assigns assessment.id before we reference it below

    cds_output = CdsOutput(
        assessment_id=assessment.id,
        rules_version=scoring.RULES_VERSION,
        classification=E["classification"],
        mat_risk_score=A["MAT_RISK_SCORE"],
        clinical_sign_count=B["CLINICAL_SIGN_COUNT"],
        lab_score=C["LAB_SCORE"],
        regimen_json={"regimen": E["regimen"], "regimen_detail": E["regimen_detail"]},
        duration_days=E["duration_days"],
        observation_only=E["observation_only"],
        triggered_nodes=result["triggered_nodes"],
    )
    db.session.add(cds_output)
    db.session.commit()

    return jsonify(
        {
            "assessment_id": assessment.id,
            "classification": E["classification"],
            "duration_days": E["duration_days"],
            "timing": E["timing"],
            "triggered_nodes": result["triggered_nodes"],
        }
    )


VALID_CLASSIFICATIONS = {"PROVEN", "PROBABLE", "POSSIBLE", "NONE"}


@assessment_bp.route("/<study_id>/review", methods=["POST"])
@login_required
def review(study_id):
    """Records the doctor's own independent clinical judgment for a given
    saved assessment, alongside (never overwriting) the system's
    classification already stored on that CdsOutput row."""
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        return jsonify({"error": "Invalid or missing data in request."}), 400

    assessment_id = body.get("assessment_id")
    agreed = body.get("agreed")
    doctor_classification = body.get("doctor_classification")
    doctor_notes = body.get("doctor_notes")

    assessment = PatientAssessment.query.filter_by(id=assessment_id, study_id=study_id).first()
    if not assessment:
        return jsonify({"error": "Assessment not found for this patient."}), 404

    cds_output = CdsOutput.query.filter_by(assessment_id=assessment.id).first()
    if not cds_output:
        return jsonify({"error": "No system classification found for this assessment."}), 404

    if agreed:
        cds_output.doctor_agreed = True
        cds_output.doctor_classification = cds_output.classification
    else:
        if doctor_classification not in VALID_CLASSIFICATIONS:
            return jsonify({"error": "doctor_classification must be one of PROVEN, PROBABLE, POSSIBLE, NONE."}), 400
        cds_output.doctor_agreed = False
        cds_output.doctor_classification = doctor_classification

    cds_output.doctor_notes = (doctor_notes or "").strip() or None
    cds_output.doctor_reviewed_at = db.func.now()
    db.session.commit()

    return jsonify({"status": "saved", "doctor_classification": cds_output.doctor_classification})
