# NeoSepsis Data Collection App — Full Handoff / Continuation Notes

**If you are Claude reading this in a new chat: read this entire file before
touching any code or answering the user.** This project has a lot of history
and several deliberate design decisions that are easy to accidentally
contradict if you don't know the reasoning behind them. The user will likely
just say "continue" - that means continue from the "What's in progress right
now" section below.

## What this app is

A Flask + SQLite web app for a NUST (Pakistan) student research project
under Dr. Fahad Ahmed Satti, in collaboration with Care+ Medical Center,
Islamabad. Doctors log in, get informed consent (bilingual EN/UR on the
consent screen, signature capture), collect structured neonatal sepsis
clinical data (Flowcharts A-E: maternal risk, clinical signs, labs, imaging,
classification), and the server authoritatively (re)computes the sepsis
classification/treatment recommendation - the browser's own JS computation
is shown for instant feedback only and is never trusted for what gets saved.

**The end goal the user has stated explicitly**, in their own words: *"a
self-correcting model that will keep improving its decision of detecting
neonatal sepsis."* The architecture below is how that's being achieved -
NOT via literal machine-learning/reinforcement learning (deliberately
rejected - see "Key research findings" below for why), but via a structured,
human-in-the-loop rule-recalibration system modeled on established clinical
prediction rule methodology and real regulatory frameworks for adaptive
medical AI.

## Architecture (all files under neosepsis_app/)

- `app.py` - app factory, registers blueprints, login manager, CSRF, rate limiter
- `config.py` - SQLite by default; auto-generates a random SECRET_KEY per
  installation on first run (saved to `.secret_key`, gitignore-style, never
  shared/committed)
- `models.py` - tables: User, ConsentRecord, PatientAssessment, CdsOutput,
  **ScoringParameter** (new - the rules registry, see below),
  RuleChangeSuggestion
- `extensions.py` - Flask-Login, CSRFProtect, Flask-Limiter instances
- `auth.py` - login (rate-limited 5/min), logout, self-service change-password
- `admin.py` - admin account creation/password reset, cross-patient dashboard,
  disagreements report, CSV export, rule-change suggestion queue
- `consent.py` - two-step consent flow (guardian info -> signature), creates
  ConsentRecord + generates study_id
- `scoring.py` - **the authoritative Python port of the A-E scoring logic**.
  Every single threshold check is tagged with its canonical node_id (matching
  IDs from the original flowchart data, e.g. "A12b", "B_R4", "C_CRP1b") so
  every classification is traceable to specific named nodes, not just a
  point total. This is the single source of truth for classification - the
  JS in assessment.html is instant-feedback only, kept in careful sync but
  never trusted for what's saved.
- `assessment.py` - routes: `/assessment/lookup` (resume by study ID),
  `/assessment/<id>/history` (list past visits for a patient, with a
  "pre-filled from most recent" or "start first" button depending on
  history), `/assessment/<id>/view/<assessment_id>` (read-only past-visit
  detail, shows "Why This Decision" node breakdown), `/assessment/<id>` (the
  data-entry wizard, GET, pre-fills from most recent prior assessment if one
  exists), `/assessment/<id>/submit` (POST, saves PatientAssessment+CdsOutput,
  loads the ScoringParameter registry and passes it into scoring.run_pipeline),
  `/assessment/<id>/review` (POST, doctor's agree/disagree verdict, never
  overwrites the system's classification), `/assessment/<id>/outcome/<id>`
  (POST, records the real confirmed clinical outcome once known - the third
  leg of system-vs-doctor-vs-reality comparison)
- `templates/assessment.html` - the data-entry wizard, originally copied
  byte-for-byte from the project's validated tool, then extended with: top
  banner (study ID/doctor/exit/home), server-save on Calculate, doctor
  agree/disagree review UI (one-tap agree, detail form only on disagreement),
  pre-fill-from-history, decluttered results (classification/regimen/
  duration/warnings visible by default, raw score chips/flags collapsed
  behind "Show scoring detail"), server-confirmed node breakdown after save,
  observation-only pathway messaging.

## Key design decisions already made - do not re-litigate these

1. **Server is authoritative, browser is not.** JS shows instant results for
   UX; the POST to `/submit` independently recomputes via scoring.py and
   THAT's what's saved. Verified via real jsdom DOM execution (not just code
   review) that the two stay in sync whenever logic changes.
2. **Confidentiality via separation.** Identifying info (guardian name/phone/
   signature) lives ONLY in ConsentRecord. Clinical tables key off a random
   `study_id`, never a name. The admin cross-patient dashboard and CSV export
   deliberately never surface guardian identity.
3. **Each assessment submission is a new snapshot row**, not an edit -
   matches the real clinical review schedule (6h/18-24h/36-48h/72h). Starting
   a new assessment for a patient who already has history now pre-fills the
   form from their most recent answers (via replaying each toggle button's
   own onclick handler, so any chained show/hide side effects fire correctly
   too) - the doctor updates what's changed rather than re-typing everything.
4. **Doctor review is separate from system classification, never overwrites
   it.** CdsOutput has both `classification` (system) and
   `doctor_classification`/`doctor_agreed`/`doctor_notes` (doctor's own call).
   Fast path: one tap "I agree." Detail form only appears on disagreement -
   that disagreement is the valuable signal.
5. **Real outcome tracking is a third, independent field**
   (`confirmed_outcome`/`outcome_entered_at`/`outcome_entered_by`) - never
   overwrites system or doctor classification either. This is what enables
   genuine system-vs-doctor-vs-reality comparison, not just system-vs-doctor.
6. **Any doctor can draft a rule-change suggestion; only admin/PI can
   accept/decline/mark-applied.** Verified this access split actually holds
   (not just hidden buttons - the routes themselves enforce it).
7. **Accepting a suggestion only records a decision - it does NOT
   automatically change scoring.py.** This is being made safe for genuinely
   numeric suggestions via the rules registry (see below), NOT by having an
   AI parse free text and edit Python source, which would be unsafe and
   unauditable for a clinical tool.
8. **Toggle button UX**: every button starts neutral (nothing looks
   pre-answered); a real click always gives clear, distinct feedback - green
   for affirmative, blue for negative, dimmed for whichever wasn't picked.
   Verified via jsdom, not just code review.
9. **Deployment is NOT yet solved.** Currently just a local SQLite file with
   no encryption/backup by default. For real patient data this needs: a
   designated always-on machine with disk encryption, a backup routine for
   that one file, and running on the clinic's private LAN rather than public
   internet exposure. This is a conversation for the user to have with their
   professor, not something to solve unilaterally in code.
10. **Consent form text is a placeholder**, marked with TODO comments - real
    IRB-approved wording must replace it before any real patient use.

## Key research findings (grounded via actual web search, not assumed)

- **Parameter completeness vs. established literature**: EOS coverage is
  strong and matches the Kaiser Permanente Neonatal EOS Calculator (GA,
  maternal temp, ROM duration, GBS status, IAP timing) and NICE NG195.
  **LOS coverage has a real, literature-confirmed gap**: central venous
  catheter presence/duration, mechanical ventilation duration, and
  parenteral nutrition duration are the dominant LOS risk factors in the
  literature (Canadian Neonatal Network study: CVC >4 days, TPN >7 days,
  prolonged NPO all significantly associated with LOS) and are **currently
  entirely absent** from the tool, despite the tool having an explicit
  EOS/LOS timing split. **This is the single most important content gap
  still open** - not yet implemented, deliberately, because exact point
  values/day-cutoffs need the clinical supervisor's (Dr. Misha Saleem's)
  validation, not an AI assistant's unilateral numbers.
- **Pakistan/South Asia-specific**: South Asia has a pooled neonatal sepsis
  incidence roughly 2-4x higher than elsewhere. A southern Pakistan study
  found *Acinetobacter spp* as the dominant EOS pathogen (22% of
  culture-positive cases), with 72% of those carbapenem-resistant - this is
  NOT reflected in the current empiric regimen logic (which covers GBS,
  E. coli, Klebsiella, S. aureus, Listeria, Candida, and a generic
  gram-negative fallback, but has no Acinetobacter-specific branch or
  carbapenem-resistance consideration). **Flagged for Dr. Saleem's review
  against the actual site antibiogram - not something to silently change.**
- **CDS design best practice**: the "Five Rights" framework (right info,
  right person, right format, right channel, right time) and documented
  alert-fatigue research (CDS alerts overridden 49-96% of the time) directly
  validated the earlier decision to declutter the results screen and keep
  doctor review to one-tap-agree by default.
- **Why not literal "reinforcement learning"**: RL learns an opaque policy;
  this tool's entire value is interpretability (every decision traces to a
  named node). What the user actually wants has an established name and
  methodology already: a **Learning Health System** (National Academy of
  Medicine, since 2007) combined with clinical prediction rule
  **recalibration/revision/extension** methodology (Moons et al.) - adjusting
  a cutoff/weight (recalibration), re-weighting a specific predictor
  (revision), or adding a new marker (extension, e.g. the LOS device
  factors above). This is more appropriate for small pilot sample sizes too
  (avoids overfitting noise in a dozens-to-low-hundreds dataset).
- **Why "auto-apply" is being built as bounded, not fully autonomous**: this
  mirrors the FDA's actual framework for adaptive medical AI
  (Predetermined Change Control Plans) - legitimate autonomous updates are
  possible, but only when changes are focused (clearly defined, verifiable),
  risk-based, and evidence-based. The rules registry (below) is designed to
  make ONLY narrow, well-defined operations (adjust an existing node's
  threshold/points) safely automatable - anything requiring a structurally
  new parameter still needs a developer, deliberately.

## Uploaded master flowchart cross-check (completed)

The user uploaded `flowchart_-_Sheet1.pdf`, a 143-row sequential flowchart
(if-yes/if-no branching to row numbers, not point values) representing the
original intended design. Cross-checked line by line against the current
implementation. **Four confirmed gaps were found and have been fixed and
tested**:

1. **Irritability/unexplained jitteriness** - added as a clinical sign field
   (node B_N7, +1 point).
2. **Urine culture for LOS/age>72h** - added; correctly only confirms a
   pathogen for catheter/suprapubic specimens (bag specimens are flagged as
   unreliable/non-diagnostic per literature, never confirm a pathogen even
   if "positive").
3. **Observation-only pathway** - the mildest Possible cases (CLINICAL_SIGN_
   COUNT <=2, LAB_SCORE <3, no override, term, no confirmed pathogen) now
   get a genuine "observe ~12h, no antibiotics yet" recommendation with a
   specific monitoring plan, instead of automatically getting a full
   antibiotic regimen. This was present in the original design (node
   E_POSS_OBS) and row 138 of the uploaded document but had never been
   implemented - previously ANY non-NONE classification always got a full
   drug regimen regardless of severity. Verified this correctly excludes
   anything with an override, preterm status, or confirmed pathogen. The JS
   instant-preview was updated in lockstep and verified via jsdom to match
   the server exactly.
4. **Early exclusive breastfeeding** - added as a Pakistan-specific
   supportive-care line item (row 143 of the uploaded document).

Everything else in the uploaded document was already correctly implemented,
or is a case where the current implementation is actually MORE clinically
rigorous than the uploaded document (e.g. the PCT logic correctly accounts
for the physiologic surge in the first 24h, which the uploaded document's
flat >0.5 cutoff would misfire on).

## What's in progress RIGHT NOW - the rules registry

This is the answer to three of the user's stated problems at once: "how will
a doctor know what threshold to suggest changing," "how will accepted
suggestions get applied without knowing which node to edit," and (partially)
the self-correction goal.

**Design**: pull tunable thresholds/point-values out of scoring.py's
hardcoded `if/elif` literals into a `ScoringParameter` database table, keyed
by the same node_id already used for "Why This Decision" tracking.
scoring.py reads from this table via a `get_param(params, node_id, key,
default)` helper that **falls back to the exact original hardcoded value**
if no params dict is passed or a node isn't in it - meaning this is
completely additive/non-breaking, verified by re-running the full existing
test suite with no params argument and getting byte-identical results.

**What's done and tested** (verified: default behavior unchanged; passing
custom params genuinely changes scoring output; full original regression
suite still passes):
- `ScoringParameter` model added to models.py
- `RuleChangeSuggestion` extended with `proposed_new_threshold` /
  `proposed_new_points` fields (structured, not just free text)
- `seed_parameters.py` - seeds ALL 23 tunable Flowchart A nodes with their
  exact current values (extracted directly from the pre-refactor hardcoded
  code, guaranteeing parity). **Must be run once, after `init_db.py`, before
  the registry has any data**: `python seed_parameters.py`
- `scoring.compute_a()` fully refactored to read every threshold/points value
  via `get_param()` instead of hardcoded literals (mat fever tiers, TLC
  tiers, ROM preterm/term tiers - every numeric Flowchart A node)
- `scoring.run_pipeline()` accepts an optional `params` dict and threads it
  into `compute_a`
- `assessment.py`'s `/submit` route now loads all `ScoringParameter` rows
  into a dict and passes them to `run_pipeline` - so if the registry is ever
  edited, the very next assessment submitted uses the new values automatically

**What's NOT done yet** (this is exactly where to resume):
1. **Flowcharts B, C, D still use hardcoded values** - compute_b/c/d have
   NOT been refactored to use get_param() yet. This is mechanical repetition
   of exactly the pattern just proven in compute_a (see the diff style: wrap
   each threshold/points literal in `get_param(params, "NODE_ID", "threshold"
   /"points", ORIGINAL_VALUE)`), and needs a `seed_parameters.py`-style seed
   for B/C/D's node values (extract from the current hardcoded code, exactly
   as was done for A).
2. **The suggestion-drafting UI (`admin_suggestion_new.html`) still only has
   free-text fields.** It needs a node picker (dropdown populated from
   `ScoringParameter.query.filter_by(flowchart="A")` initially, all
   flowcharts once B-D are migrated) that shows the CURRENT threshold/points
   when a node is selected, and lets the user propose specific new numbers
   into the new `proposed_new_threshold`/`proposed_new_points` fields -
   replacing vague prose with a structured proposal.
3. **`admin.mark_applied()` doesn't actually apply anything yet.** Right now
   it just sets `applied_to_scoring=True` as a manual confirmation flag. The
   real auto-apply needs: when marking a suggestion with a valid
   `node_id`/`proposed_new_threshold`/`proposed_new_points` as applied,
   actually UPDATE the matching `ScoringParameter` row (set `.threshold`,
   `.points`, `.updated_at`, `.updated_by_id`) inside that same route. This
   is the safe, bounded "auto-apply" moment - updating one database row,
   not editing Python source.
4. **No page to browse the current registry directly** (view all nodes and
   their live values at a glance) - would help doctors/PI understand "what
   does the system currently think" before drafting a suggestion. Simple
   admin-page addition once B-D are seeded too.
5. **Automated pattern-detection for suggestions** (system proposes
   candidates on its own by scanning outcome-confirmed disagreement cases,
   grouped by which node fired) - deliberately deferred until real data
   accumulates; needs the full registry (all flowcharts) in place first.
   Keep this SIMPLE (plain frequency counts, e.g. "3 of 4 outcome-confirmed
   disagreements involved node X") given small pilot sample sizes - do not
   reach for sophisticated statistical threshold optimization, which risks
   overfitting noise on a dataset this size.

## What's left after the registry (in priority order)

1. **LOS device/iatrogenic risk factors** (central line, ventilation, TPN,
   NPO days) - literature-confirmed gap, flagged for Dr. Saleem's input on
   exact point values before implementing.
2. **Acinetobacter/carbapenem-resistance regimen consideration** - needs Dr.
   Saleem's review against the real Care+ antibiogram.
3. **Whole-site EN/UR toggle** - currently only exists on the consent
   explanation screen (built with a hand-rolled data-t/JS-dictionary
   pattern). The user's professor wants this for the ENTIRE site. Recommend
   migrating to Flask-Babel (the standard Flask i18n tool) rather than
   extending the ad-hoc pattern to ~15 more templates - proper translation
   catalogs, one clean session-based locale switch, and RTL CSS handling.
   This is its own substantial, focused stage.
4. Real IRB-approved consent wording (needs the user's professor/ethics
   board - not something to draft unilaterally beyond the current
   placeholder).
5. Real deployment planning (dedicated machine, encryption, backups,
   private-network-only access).
6. Smaller polish: Urdu toggle on the signature screen too (currently only
   the consent explanation screen has it); no admin-side password reset
   flow existed before this session's security work (now fixed - check if
   already delivered); real physical tablet testing of the signature pad
   (only automated-tested so far, never on an actual touchscreen device).

## How to run it

```
cd neosepsis_app
pip install -r requirements.txt
python init_db.py          # creates neosepsis.db + prints default admin login
python seed_parameters.py  # NEW - seeds the Flowchart A rules registry
python app.py              # http://localhost:5000
```
Default login: `admin` / `changeme123` (change immediately via the
"Change password" link once logged in).

## Testing philosophy - keep this up

Every single feature in this app has been verified with real Flask
test-client integration tests (login, full flows, cross-patient security
checks) - never just "it loads." For JavaScript behavior changes
specifically (toggle button colors, pre-fill, observation-pathway
messaging), the actual rendered page was executed in a real DOM via jsdom
(`npm install jsdom`) and inspected after execution - not just eyeballing
the JS source. This caught real bugs before they shipped (a missing
translation key, a fetch-header CSRF gap). Keep doing this for every future
change, especially the registry work above, since it touches the core
scoring logic.

## File to hand off

The latest complete, tested zip should always be rebuilt fresh from
`/home/claude/neosepsis_app` and delivered via `present_files`. If starting
a brand new chat: the user will upload that zip; unzip it, `cd` into it, and
read this file (`PROJECT_STATUS.md`) in full before making any changes.
