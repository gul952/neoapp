from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user

from models import db, ConsentRecord

consent_bp = Blueprint("consent", __name__, url_prefix="/consent")

# Bump this whenever the wording of the consent form changes, so every saved
# consent record stays permanently tied to the exact version the guardian
# actually saw and agreed to.
CONSENT_FORM_VERSION = "v1.0"


@consent_bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        guardian_name = request.form.get("guardian_name", "").strip()
        guardian_contact = request.form.get("guardian_contact", "").strip()
        relationship = request.form.get("relationship", "").strip()
        agreed = request.form.get("agreed")

        if not guardian_name or not relationship or not agreed:
            flash("Guardian name, relationship, and the confirmation checkbox are all required.")
            return redirect(url_for("consent.new"))

        # Held only in the signed session cookie for the short gap between
        # this step and the signature step - nothing is written to the
        # database until the signature itself is captured.
        session["pending_consent"] = {
            "guardian_name": guardian_name,
            "guardian_contact": guardian_contact,
            "relationship": relationship,
        }
        return redirect(url_for("consent.sign"))

    return render_template("consent_start.html")


@consent_bp.route("/sign", methods=["GET", "POST"])
@login_required
def sign():
    pending = session.get("pending_consent")
    if not pending:
        flash("Please start the consent process from the beginning.")
        return redirect(url_for("consent.new"))

    if request.method == "POST":
        signature_data = request.form.get("signature_data", "")
        if not signature_data or len(signature_data) < 100:
            flash("A signature is required before submitting.")
            return redirect(url_for("consent.sign"))

        record = ConsentRecord(
            study_id=ConsentRecord.generate_study_id(),
            guardian_name=pending["guardian_name"],
            guardian_contact=pending["guardian_contact"],
            relationship_to_infant=pending["relationship"],
            consent_form_version=CONSENT_FORM_VERSION,
            signature_data=signature_data,
            witnessed_by_id=current_user.id,
        )
        db.session.add(record)
        db.session.commit()

        session.pop("pending_consent", None)
        return redirect(url_for("consent.done", study_id=record.study_id))

    return render_template("consent_sign.html", guardian_name=pending["guardian_name"])


@consent_bp.route("/<study_id>/done")
@login_required
def done(study_id):
    record = ConsentRecord.query.filter_by(study_id=study_id).first_or_404()
    return render_template("consent_done.html", record=record)
