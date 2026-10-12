"""
Seeds the scoring_parameters registry with Flowchart A's current values,
extracted exactly from the hardcoded logic in scoring.py so behavior is
identical before and after this migration. Run after init_db.py:

    python seed_parameters.py

Flowcharts B-D are not seeded yet - scoring.py still uses hardcoded values
for those, falling back safely to hardcoded defaults for any node not
present here (see scoring.get_param()).
"""
from app import create_app
from models import db, ScoringParameter

app = create_app()

FLOWCHART_A_PARAMS = [
    # node_id, label, threshold, unit, points, notes
    ("A2b", "Maternal low-grade fever 38.0-38.4C", 38.0, "C", 1, None),
    ("A2c", "Maternal moderate fever 38.5-38.9C", 38.5, "C", 2, None),
    ("A2d", "Maternal high fever >=39.0C", 39.0, "C", 3, None),
    ("A4", "Maternal UTI during pregnancy", None, None, 2, None),
    ("A5", "Maternal pneumonia during pregnancy", None, None, 2, None),
    ("A6", "Other systemic maternal infection", None, None, 1, None),
    ("A7b", "Maternal TLC mildly elevated", 13.0, "x10^9/L", 1, None),
    ("A7c", "Maternal TLC markedly elevated", 18.0, "x10^9/L", 2, None),
    ("A8", "Documented maternal infection / +ve culture", None, None, 2, None),
    ("A9", "Maternal GBS colonization/infection", None, None, 2, None),
    ("A11a", "Preterm ROM 12-18h", 12.0, "hours", 1, None),
    ("A11b", "Preterm ROM >18h", 18.0, "hours", 2, None),
    ("A12a", "Term ROM 18-24h", 18.0, "hours", 1, None),
    ("A12b", "Term ROM >24h", 24.0, "hours", 2, None),
    ("A13", "Prolonged PV leaking regardless of GA", None, None, 2, None),
    ("A14", "Prolonged labor", None, None, 1, None),
    ("A15", "Complicated labor", None, None, 1, None),
    ("A16", "Frequent vaginal examinations (>=5)", None, None, 1, None),
    ("A17b", "Thin/light MSAF Grade I", None, None, 1, None),
    ("A17c", "Thick/particulate MSAF Grade II-III", None, None, 2, None),
    ("A19", "PPROM (prelabor rupture <37wk)", None, None, 2, None),
    ("A20", "Maternal gonorrhea documented", None, None, 2, None),
    ("A24", "Antepartum fever episode", None, None, 1, None),
]

with app.app_context():
    created, skipped = 0, 0
    for node_id, label, threshold, unit, points, notes in FLOWCHART_A_PARAMS:
        if ScoringParameter.query.filter_by(node_id=node_id).first():
            skipped += 1
            continue
        db.session.add(ScoringParameter(
            node_id=node_id, flowchart="A", label=label,
            threshold=threshold, threshold_unit=unit, points=points, notes=notes,
        ))
        created += 1
    db.session.commit()
    print(f"Seeded {created} Flowchart A scoring parameters ({skipped} already existed).")
