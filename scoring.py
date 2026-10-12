"""
Server-side port of the Flowchart A-E scoring engine.

Every contributing check is tagged with its canonical node_id (matching the
IDs used in neonatal_sepsis_pipeline.html - e.g. "A12b", "B_R4", "C_CRP1b")
so a classification can be traced back to the exact named nodes that fired,
not just a point total. This is what makes the "why did this happen" view
possible, and is the foundation for grouping disagreement patterns by node
when generating rule-change suggestions.
"""

RULES_VERSION = "v1.0"


def n(state, key):
    val = state.get(key)
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def yes(state, key):
    return state.get(key) == "yes"


def _node(node_id, label, points=0, override=False):
    return {"node_id": node_id, "label": label, "points": points, "override": override}


def get_param(params, node_id, key, default):
    """Reads a tunable value from the params registry dict, falling back to
    the exact original hardcoded default if params is None, the node isn't
    present, or that particular field is unset. This means every existing
    caller that doesn't pass params (all prior tests, and any flowchart not
    yet migrated to the registry) behaves identically to before - the
    registry is additive, not a breaking change."""
    if params and node_id in params and params[node_id].get(key) is not None:
        return params[node_id][key]
    return default


def compute_a(state, params=None):
    score = 0
    override_flag = False
    nodes = []

    ga = n(state, "ga")
    if ga is None:
        ga = 40
    preterm_flag = ga < 37

    mt = n(state, "mat_temp")
    if mt is not None:
        t_a2d = get_param(params, "A2d", "threshold", 39.0)
        t_a2c = get_param(params, "A2c", "threshold", 38.5)
        t_a2b = get_param(params, "A2b", "threshold", 38.0)
        if mt >= t_a2d:
            pts = get_param(params, "A2d", "points", 3)
            score += pts
            nodes.append(_node("A2d", f"Maternal high fever >={t_a2d}C", pts))
        elif mt >= t_a2c:
            pts = get_param(params, "A2c", "points", 2)
            score += pts
            nodes.append(_node("A2c", f"Maternal moderate fever {t_a2c}-{t_a2d}C", pts))
        elif mt >= t_a2b:
            pts = get_param(params, "A2b", "points", 1)
            score += pts
            nodes.append(_node("A2b", f"Maternal low-grade fever {t_a2b}-{t_a2c}C", pts))

    if yes(state, "chorioamnionitis"):
        override_flag = True
        nodes.append(_node("A3", "Clinical chorioamnionitis confirmed", 0, override=True))

    if yes(state, "mat_uti"):
        pts = get_param(params, "A4", "points", 2)
        score += pts
        nodes.append(_node("A4", "Maternal UTI during pregnancy", pts))
    if yes(state, "mat_pneu"):
        pts = get_param(params, "A5", "points", 2)
        score += pts
        nodes.append(_node("A5", "Maternal pneumonia during pregnancy", pts))
    if yes(state, "mat_other_inf"):
        pts = get_param(params, "A6", "points", 1)
        score += pts
        nodes.append(_node("A6", "Other systemic maternal infection", pts))
    if yes(state, "mat_doc_inf"):
        pts = get_param(params, "A8", "points", 2)
        score += pts
        nodes.append(_node("A8", "Documented maternal infection / +ve culture", pts))

    tlc = n(state, "mat_tlc")
    if tlc is not None:
        t_a7c = get_param(params, "A7c", "threshold", 18.0)
        t_a7b = get_param(params, "A7b", "threshold", 13.0)
        if tlc > t_a7c:
            pts = get_param(params, "A7c", "points", 2)
            score += pts
            nodes.append(_node("A7c", f"Maternal TLC markedly elevated >{t_a7c}e9/L", pts))
        elif tlc > t_a7b:
            pts = get_param(params, "A7b", "points", 1)
            score += pts
            nodes.append(_node("A7b", f"Maternal TLC mildly elevated {t_a7b}-{t_a7c}e9/L", pts))

    if yes(state, "gbs"):
        pts = get_param(params, "A9", "points", 2)
        score += pts
        nodes.append(_node("A9", "Maternal GBS colonization/infection", pts))
    if yes(state, "gonorrhea"):
        pts = get_param(params, "A20", "points", 2)
        score += pts
        nodes.append(_node("A20", "Maternal gonorrhea documented", pts))

    if yes(state, "rom"):
        rom_h = n(state, "rom_hours") or 0
        if preterm_flag:
            t_a11b = get_param(params, "A11b", "threshold", 18.0)
            t_a11a = get_param(params, "A11a", "threshold", 12.0)
            if rom_h > t_a11b:
                pts = get_param(params, "A11b", "points", 2)
                score += pts
                nodes.append(_node("A11b", f"Preterm ROM >{t_a11b}h", pts))
            elif rom_h >= t_a11a:
                pts = get_param(params, "A11a", "points", 1)
                score += pts
                nodes.append(_node("A11a", f"Preterm ROM {t_a11a}-{t_a11b}h", pts))
        else:
            t_a12b = get_param(params, "A12b", "threshold", 24.0)
            t_a12a = get_param(params, "A12a", "threshold", 18.0)
            if rom_h > t_a12b:
                pts = get_param(params, "A12b", "points", 2)
                score += pts
                nodes.append(_node("A12b", f"Term ROM >{t_a12b}h", pts))
            elif rom_h >= t_a12a:
                pts = get_param(params, "A12a", "points", 1)
                score += pts
                nodes.append(_node("A12a", f"Term ROM {t_a12a}-{t_a12b}h", pts))

    if yes(state, "pv_leak"):
        pts = get_param(params, "A13", "points", 2)
        score += pts
        nodes.append(_node("A13", "Prolonged PV leaking regardless of GA", pts))
    if yes(state, "pprom"):
        pts = get_param(params, "A19", "points", 2)
        score += pts
        nodes.append(_node("A19", "PPROM (prelabor rupture <37wk)", pts))
    if yes(state, "prol_labor"):
        pts = get_param(params, "A14", "points", 1)
        score += pts
        nodes.append(_node("A14", "Prolonged labor", pts))
    if yes(state, "comp_labor"):
        pts = get_param(params, "A15", "points", 1)
        score += pts
        nodes.append(_node("A15", "Complicated labor", pts))
    if yes(state, "freq_ve"):
        pts = get_param(params, "A16", "points", 1)
        score += pts
        nodes.append(_node("A16", "Frequent vaginal examinations (>=5)", pts))

    msaf = state.get("msaf")
    if msaf == "thick":
        pts = get_param(params, "A17c", "points", 2)
        score += pts
        nodes.append(_node("A17c", "Thick/particulate MSAF Grade II-III", pts))
    elif msaf == "thin":
        pts = get_param(params, "A17b", "points", 1)
        score += pts
        nodes.append(_node("A17b", "Thin/light MSAF Grade I", pts))

    if yes(state, "antepartum_fever"):
        pts = get_param(params, "A24", "points", 1)
        score += pts
        nodes.append(_node("A24", "Antepartum fever episode", pts))

    if ga < 28:
        ga_band = "extremely_preterm"
    elif ga < 32:
        ga_band = "very_preterm"
    elif ga < 37:
        ga_band = "mod_preterm"
    else:
        ga_band = "term"

    return {
        "MAT_RISK_SCORE": score,
        "MAT_OVERRIDE_FLAG": override_flag,
        "PRETERM_FLAG": preterm_flag,
        "GA_BAND": ga_band,
        "IAP_GIVEN": yes(state, "iap_given"),
        "GA": ga,
        "nodes": nodes,
    }


def compute_b(state, A):
    score = 0
    override = False
    overrides = []
    nodes = []
    ga = A["GA"] or 40

    birth_cry = state.get("birth_cry")
    if birth_cry == "absent":
        override = True
        overrides.append("No cry at birth - absent respiratory effort")
        nodes.append(_node("B_CRY_ABSENT", "No cry at birth / absent respiratory effort", 0, override=True))
    elif birth_cry == "delayed":
        score += 2
        nodes.append(_node("B_CRY_DELAYED", "Delayed or weak cry at birth", 2))

    birth_tone = state.get("birth_tone")
    if birth_tone == "limp":
        score += 2
        nodes.append(_node("B_TONE_LIMP", "Limp tone at birth (APGAR Activity 0)", 2))
    elif birth_tone == "some":
        score += 1
        nodes.append(_node("B_TONE_SOME", "Reduced tone at birth (APGAR Activity 1)", 1))

    apgar1 = n(state, "apgar1")
    if apgar1 is not None:
        if apgar1 <= 3:
            override = True
            overrides.append("1-min APGAR 0-3: severe neonatal depression")
            nodes.append(_node("B_APGAR_SEVERE", "1-min APGAR 0-3: severe depression", 0, override=True))
        elif apgar1 <= 6:
            score += 3
            nodes.append(_node("B_APGAR_MOD", "1-min APGAR 4-6: moderate depression", 3))

    apgar5 = n(state, "apgar5")
    if apgar5 is not None and apgar1 is not None and apgar1 < 7:
        if apgar5 < 7:
            score += 2
            nodes.append(_node("B_APGAR5_LOW", "5-min APGAR still <7: persistent depression", 2))

    nt = n(state, "neo_temp")
    if nt is not None:
        if nt >= 38.5:
            override = True
            overrides.append("Neonatal temp >=38.5C")
            nodes.append(_node("B_T3", "Neonatal high fever >=38.5C", 0, override=True))
        elif nt >= 38.0:
            score += 2
            nodes.append(_node("B_T2", "Neonatal fever 38.0-38.4C", 2))
        elif nt >= 37.5:
            score += 1
            nodes.append(_node("B_T1", "Neonatal low-grade fever 37.5-37.9C", 1))
        if nt < 35.0:
            override = True
            overrides.append("Severe hypothermia <35C")
            nodes.append(_node("B_T5", "Moderate-severe hypothermia <35C", 0, override=True))
        elif nt < 36.0:
            score += 2
            nodes.append(_node("B_T4", "Mild hypothermia 35.0-35.9C", 2))
        elif nt < 36.5:
            score += 1
            nodes.append(_node("B_T0b", "Cold stress / borderline hypothermia 36.0-36.4C", 1))

    if yes(state, "temp_instab"):
        score += 2
        nodes.append(_node("B_TH1", "Temperature instability", 2))

    hr = n(state, "hr")
    if hr is not None:
        if hr >= 180:
            override = True
            overrides.append("HR >=180 bpm")
            nodes.append(_node("B_HR2", "Significant tachycardia >=180 bpm", 0, override=True))
        elif hr >= 160:
            score += 1
            nodes.append(_node("B_HR1", "Mild tachycardia 160-179 bpm", 1))
        if hr < 80:
            override = True
            overrides.append("HR <80 bpm")
            nodes.append(_node("B_HR4", "Severe bradycardia <80 bpm", 0, override=True))
        elif hr < 100:
            score += 2
            nodes.append(_node("B_HR3", "Mild bradycardia 80-99 bpm", 2))

    rr = n(state, "rr")
    if rr is not None:
        if rr >= 90:
            override = True
            overrides.append("RR >=90/min")
            nodes.append(_node("B_R3", "Severe tachypnea >=90/min", 0, override=True))
        elif rr >= 70:
            score += 2
            nodes.append(_node("B_R2", "Significant tachypnea 70-89/min", 2))
        elif rr >= 61:
            score += 1
            nodes.append(_node("B_R1", "Mild tachypnea 61-69/min", 1))

    if yes(state, "grunting"):
        score += 2
        nodes.append(_node("B_R4", "Grunting", 2))
    if yes(state, "flaring"):
        score += 1
        nodes.append(_node("B_R5", "Nasal flaring", 1))
    if yes(state, "retractions"):
        score += 2
        nodes.append(_node("B_R6", "Chest retractions", 2))
    if yes(state, "cyanosis"):
        override = True
        overrides.append("Central cyanosis")
        nodes.append(_node("B_R7", "Central cyanosis", 0, override=True))
    if yes(state, "o2_req"):
        score += 2
        nodes.append(_node("B_R8", "Oxygen requirement", 2))

    spo2 = n(state, "spo2")
    if spo2 is not None:
        if spo2 < 90:
            override = True
            overrides.append("SpO2 <90%")
            nodes.append(_node("B_SP2", "Severe desaturation SpO2 <90%", 0, override=True))
        elif spo2 < 95:
            score += 2
            nodes.append(_node("B_SP1", "Mild desaturation SpO2 90-94%", 2))

    ap = state.get("apnea")
    if ap == "severe":
        override = True
        overrides.append("Severe apnea")
        nodes.append(_node("B_AP3", "Severe apnea (>=30s or needs resuscitation)", 0, override=True))
    elif ap == "recurrent":
        score += 2
        nodes.append(_node("B_AP2", "Recurrent apnea", 2))
    elif ap == "brief":
        score += 1
        nodes.append(_node("B_AP1", "Brief apnea", 1))

    crt = n(state, "crt")
    if crt is not None:
        if crt > 4:
            override = True
            overrides.append("CRT >4s")
            nodes.append(_node("B_CV2", "Prolonged CRT >4s", 0, override=True))
        elif crt >= 3:
            score += 1
            nodes.append(_node("B_CV1", "Borderline CRT 3-4s", 1))

    if yes(state, "shock"):
        override = True
        overrides.append("Clinical shock")
        nodes.append(_node("B_CV5", "Clinical shock", 0, override=True))
    if yes(state, "weak_pulses"):
        score += 2
        nodes.append(_node("B_CV3", "Weak or absent peripheral pulses", 2))
    if yes(state, "mottled"):
        score += 2
        nodes.append(_node("B_CV6", "Mottled/marbled skin", 2))
    if yes(state, "sunk_font"):
        score += 2
        nodes.append(_node("B_SUNK_FONT", "Sunken fontanelle", 2))
    if yes(state, "edema"):
        score += 2
        nodes.append(_node("B_EDEMA", "Generalised oedema / capillary leak", 2))

    map_val = n(state, "map_val")
    if map_val is not None and map_val < ga:
        score += 2
        nodes.append(_node("B_CV4", "Hypotension (MAP < gestational age in weeks)", 2))

    uo = n(state, "urine_op")
    if uo is not None and uo < 1:
        score += 1
        nodes.append(_node("B_CV7", "Low urine output <1 mL/kg/h", 1))

    if yes(state, "seizures"):
        override = True
        overrides.append("Seizures")
        nodes.append(_node("B_N1", "Seizures", 0, override=True))
    if yes(state, "bulg_font"):
        override = True
        overrides.append("Bulging fontanelle")
        nodes.append(_node("B_N2", "Bulging fontanelle", 0, override=True))
    if yes(state, "alt_consc"):
        override = True
        overrides.append("Altered consciousness")
        nodes.append(_node("B_N4", "Altered consciousness", 0, override=True))
    if yes(state, "hp_cry"):
        score += 2
        nodes.append(_node("B_N3", "High-pitched cry", 2))
    if yes(state, "hypotonia"):
        score += 2
        nodes.append(_node("B_N5", "Generalised hypotonia", 2))
    if yes(state, "moro"):
        score += 1
        nodes.append(_node("B_N6", "Weak or absent Moro reflex", 1))
    if yes(state, "lethargy"):
        score += 2
        nodes.append(_node("B_LETHARGY", "Lethargy (drowsy, difficult to rouse)", 2))
    if yes(state, "weak_cry"):
        score += 1
        nodes.append(_node("B_WEAK_CRY", "Weak cry (ongoing examination finding)", 1))
    if yes(state, "irritability"):
        score += 1
        nodes.append(_node("B_N7", "Irritability or unexplained jitteriness", 1))

    if yes(state, "poor_feed"):
        score += 2
        nodes.append(_node("B_F1", "Poor feeding", 2))
    vom = state.get("vomiting")
    if vom in ("bilious", "persistent"):
        score += 2
        nodes.append(_node("B_F2", "Vomiting (bilious or persistent)", 2))
    if yes(state, "abd_dist"):
        score += 2
        nodes.append(_node("B_F3", "Abdominal distension", 2))
    if yes(state, "abd_erythema"):
        override = True
        overrides.append("Abdominal wall erythema")
        nodes.append(_node("B_F4", "Abdominal wall erythema", 0, override=True))
    if yes(state, "jaundice_24"):
        override = True
        overrides.append("Jaundice <24h")
        nodes.append(_node("B_SK1", "Jaundice within first 24h", 0, override=True))
    if yes(state, "petechiae"):
        score += 2
        nodes.append(_node("B_SK2", "Petechiae or unexplained bleeding", 2))
    if yes(state, "pallor"):
        score += 2
        nodes.append(_node("B_SK3", "Unexplained pallor", 2))
    if yes(state, "septic_facies"):
        score += 2
        nodes.append(_node("B_SK4", "Septic facies", 2))

    gluc = n(state, "glucose")
    if gluc is not None:
        if gluc < 20:
            override = True
            overrides.append("Severe hypoglycemia <20 mg/dL")
            nodes.append(_node("B_M3", "Severe hypoglycemia <20 mg/dL", 0, override=True))
        elif gluc < 36:
            score += 2
            nodes.append(_node("B_M2", "Significant hypoglycemia 20-35 mg/dL", 2))
        elif gluc < 45:
            score += 1
            nodes.append(_node("B_M1", "Mild hypoglycemia 36-44 mg/dL", 1))
        elif gluc >= 200:
            score += 2
            nodes.append(_node("B_M5", "Significant hyperglycemia >=200 mg/dL", 2))
        elif gluc >= 150:
            score += 1
            nodes.append(_node("B_M4", "Mild hyperglycemia 150-199 mg/dL", 1))

    bd = n(state, "base_def")
    if bd is not None:
        if bd >= 15:
            override = True
            overrides.append("Severe metabolic acidosis BD>=15")
            nodes.append(_node("B_M7", "Severe metabolic acidosis BD>=15", 0, override=True))
        elif bd >= 10:
            score += 2
            nodes.append(_node("B_M6", "Metabolic acidosis BD 10-14", 2))

    return {
        "CLINICAL_SIGN_COUNT": score,
        "CLINICAL_OVERRIDE": override,
        "overrides_B": overrides,
        "nodes": nodes,
    }


def compute_c(state, A):
    lab_score = 0
    lab_support_flag = False
    pathogen_confirmed = False
    csf_abnormal = False
    preterm = A["PRETERM_FLAG"]
    organism = state.get("organism", "") or ""
    nodes = []

    culture_result = state.get("culture_result")
    if culture_result == "pathogen":
        pathogen_confirmed = True
        nodes.append(_node("C_BC3", f"Confirmed pathogen isolated{': ' + organism if organism else ''}", 0, override=True))
    elif culture_result == "cons":
        cons_criteria = yes(state, "cons_two") or yes(state, "cons_cvc") or yes(state, "cons_det")
        if cons_criteria:
            pathogen_confirmed = True
            nodes.append(_node("C_BC4", "CoNS meeting true-infection criteria", 0, override=True))

    cbc_h = n(state, "cbc_hrs")
    wbc = n(state, "wbc")
    anc = n(state, "anc")
    it_r = n(state, "it_ratio")
    plt = n(state, "platelets")

    if cbc_h is not None and cbc_h >= 6:
        if wbc is not None:
            if wbc < 5000:
                lab_score += 3
                nodes.append(_node("C_WBC1", "Leukopenia WBC<5000", 3))
            elif wbc > 20000 and cbc_h <= 12:
                lab_score += 2
                nodes.append(_node("C_WBC2a", "Leukocytosis >20k at 6-12h", 2))
            elif wbc > 15000 and cbc_h > 12:
                lab_score += 2
                nodes.append(_node("C_WBC2b", "Leukocytosis >15k at >12h", 2))
        if anc is not None:
            if anc < 500:
                lab_score += 3
                nodes.append(_node("C_ANC2", "Severe neutropenia ANC<500", 3))
            elif not preterm and cbc_h <= 12 and anc < 1750:
                lab_score += 2
                nodes.append(_node("C_ANC1a", "Neutropenia (term) ANC<1750 at 6-12h", 2))
            elif not preterm and cbc_h > 12 and anc < 1000:
                lab_score += 2
                nodes.append(_node("C_ANC1a", "Neutropenia (term) ANC<1000 after 12h", 2))
            elif preterm and anc < 1000:
                lab_score += 2
                nodes.append(_node("C_ANC1b", "Neutropenia (preterm) ANC<1000", 2))
        if it_r is not None:
            if not preterm and it_r > 0.27:
                lab_score += 2
                nodes.append(_node("C_IT1", "Elevated I/T ratio >0.27 (term)", 2))
            elif preterm and it_r > 0.22:
                lab_score += 2
                nodes.append(_node("C_IT2", "Elevated I/T ratio >0.22 (preterm)", 2))
        if plt is not None:
            if plt < 50000:
                lab_score += 3
                nodes.append(_node("C_PLT3", "Severe thrombocytopenia <50k", 3))
            elif plt < 100000:
                lab_score += 2
                nodes.append(_node("C_PLT2", "Moderate thrombocytopenia 50-99k", 2))
            elif plt < 150000:
                lab_score += 1
                nodes.append(_node("C_PLT1", "Mild thrombocytopenia 100-149k", 1))
    elif cbc_h is not None and cbc_h < 6:
        if wbc is not None and wbc < 5000:
            lab_score += 3
            nodes.append(_node("C_WBC1", "Leukopenia (always significant, even <6h)", 3))

    crp_h = n(state, "crp_hrs")
    crp_v = n(state, "crp")
    crp_normal = False
    if crp_h is not None and crp_h >= 6 and crp_v is not None:
        if crp_v >= 100:
            lab_score += 3
            lab_support_flag = True
            nodes.append(_node("C_CRP1c", "CRP >=100 mg/L", 3))
        elif crp_v >= 50:
            lab_score += 3
            lab_support_flag = True
            nodes.append(_node("C_CRP1b", "CRP 50-99 mg/L", 3))
        elif crp_v >= 10:
            lab_score += 2
            nodes.append(_node("C_CRP1a", "CRP 10-49 mg/L", 2))
        else:
            crp_normal = True

    repeat_crp_done = yes(state, "repeat_crp_done")
    repeat_crp = n(state, "repeat_crp")
    repeat_crp_normal = False
    if repeat_crp_done and repeat_crp is not None:
        if repeat_crp >= 10 or (crp_v is not None and (repeat_crp - crp_v) > 10):
            lab_score += 3
            lab_support_flag = True
            nodes.append(_node("C_CRP2a", "Repeat CRP rising/>=10 mg/L at 18-24h", 3))
        else:
            repeat_crp_normal = True

    if yes(state, "pct_avail"):
        pct_h = n(state, "pct_hrs")
        pct_v = n(state, "pct")
        if pct_h is not None and pct_v is not None:
            if pct_h < 24:
                pass
            elif pct_h < 48:
                if pct_v >= 10:
                    lab_score += 3
                    lab_support_flag = True
                    nodes.append(_node("C_PCT2b", "PCT >=10 ng/mL at 24-48h", 3))
                elif pct_v >= 2:
                    lab_score += 2
                    nodes.append(_node("C_PCT2a", "PCT 2-9.9 ng/mL at 24-48h", 2))
            else:
                if pct_v >= 2.0:
                    lab_score += 3
                    lab_support_flag = True
                    nodes.append(_node("C_PCT3b", "PCT >=2.0 ng/mL after 48h", 3))
                elif pct_v >= 0.5:
                    lab_score += 2
                    nodes.append(_node("C_PCT3a", "PCT 0.5-1.9 ng/mL after 48h", 2))

    if state.get("lp_done") == "yes":
        csf_w = n(state, "csf_wbc")
        csf_p = n(state, "csf_prot")
        csf_g = n(state, "csf_gluc")
        ser_g = n(state, "serum_gluc")
        csf_r = (csf_g / ser_g) if (csf_g is not None and ser_g is not None and ser_g > 0) else None
        csf_cult = yes(state, "csf_cult")

        if preterm:
            if (
                (csf_w is not None and csf_w > 25)
                or (csf_p is not None and csf_p > 200)
                or (csf_g is not None and csf_g < 30)
                or (csf_r is not None and csf_r < 0.5)
                or csf_cult
            ):
                csf_abnormal = True
                pathogen_confirmed = True
                nodes.append(_node("C_CSF1b", "Abnormal CSF (preterm thresholds) - meningitis", 0, override=True))
        else:
            if (
                (csf_w is not None and csf_w > 20)
                or (csf_p is not None and csf_p > 150)
                or (csf_g is not None and csf_g < 40)
                or (csf_r is not None and csf_r < 0.6)
                or csf_cult
            ):
                csf_abnormal = True
                pathogen_confirmed = True
                nodes.append(_node("C_CSF1a", "Abnormal CSF (term thresholds) - meningitis", 0, override=True))

    # Urine culture - indicated for LOS workup (age >72h), not routine EOS.
    # Bag specimens have a high contamination rate and are never diagnostic,
    # even if "positive" - only catheter/suprapubic results can confirm a
    # urinary source. This was present in the original flowchart design
    # (C_UC_IND/C_UC1) but had never been implemented until now.
    urine_method = state.get("urine_method")
    urine_result = state.get("urine_result")
    if state.get("urine_culture_done") == "yes" and urine_result == "positive":
        if urine_method in ("catheter", "suprapubic"):
            pathogen_confirmed = True
            nodes.append(_node("C_UC1", f"Positive urine culture ({urine_method}) - valid method", 0, override=True))
        elif urine_method == "bag":
            nodes.append(_node("C_UC_BAG", "Urine culture positive via bag specimen - NOT diagnostic, unreliable method", 0))

    if lab_score >= 5:
        lab_support_flag = True

    antibiotic_safe_to_stop = (
        (culture_result == "neg_well")
        and crp_normal
        and repeat_crp_done
        and repeat_crp_normal
        and not pathogen_confirmed
        and not csf_abnormal
        and yes(state, "clin_well")
    )

    return {
        "LAB_SUPPORT_FLAG": lab_support_flag,
        "PATHOGEN_CONFIRMED": pathogen_confirmed,
        "LAB_SCORE": lab_score,
        "ANTIBIOTIC_SAFE_TO_STOP": antibiotic_safe_to_stop,
        "CSF_ABNORMAL": csf_abnormal,
        "CULTURE_OBTAINED": yes(state, "culture_obtained"),
        "ORGANISM": organism,
        "nodes": nodes,
    }


def compute_d(state):
    loc_flag = False
    findings = []
    nodes = []
    priority = ["ENDOCARDITIS", "ABSCESS", "NEC_PERFORATED", "NEC", "MENINGITIS_STRUCTURAL", "PNEUMONIA"]

    if yes(state, "cxr_done"):
        f = state.get("cxr_finding")
        if f == "consolidation":
            loc_flag = True
            findings.append("PNEUMONIA")
            nodes.append(_node("D_CXR1", "CXR: consolidation -> pneumonia", 0, override=True))

    if yes(state, "axr_done"):
        f = state.get("axr_finding")
        if f == "pneumatosis":
            loc_flag = True
            findings.append("NEC")
            nodes.append(_node("D_AXR1", "AXR: pneumatosis/portal venous gas -> NEC", 0, override=True))
        elif f == "freeair":
            loc_flag = True
            findings.append("NEC_PERFORATED")
            nodes.append(_node("D_AXR2", "AXR: free air -> NEC perforated (surgical)", 0, override=True))

    if yes(state, "head_done"):
        f = state.get("head_finding")
        if f == "ventriculitis":
            loc_flag = True
            findings.append("MENINGITIS_STRUCTURAL")
            nodes.append(_node("D_HEAD1", "Head imaging: ventriculitis", 0, override=True))
        elif f == "abscess":
            loc_flag = True
            findings.append("ABSCESS")
            nodes.append(_node("D_HEAD2", "Head imaging: intracranial abscess", 0, override=True))

    if yes(state, "echo_done"):
        f = state.get("echo_finding")
        if f == "vegetation":
            loc_flag = True
            findings.append("ENDOCARDITIS")
            nodes.append(_node("D_ECHO1", "Echo: vegetation -> endocarditis", 0, override=True))

    if yes(state, "aus_done"):
        f = state.get("aus_finding")
        if f in ("abscess", "bezoar"):
            loc_flag = True
            findings.append("ABSCESS")
            nodes.append(_node("D_AUS1", f"Abdominal US: {f} confirmed", 0, override=True))

    imaging_finding = "NONE"
    for p in priority:
        if p in findings:
            imaging_finding = p
            break

    return {"LOCALIZED_INFECTION_FLAG": loc_flag, "IMAGING_FINDING": imaging_finding, "nodes": nodes}


def compute_e(state, A, B, C, D):
    age_h = n(state, "age_hrs") or 0
    timing = "EOS" if age_h <= 72 else "LOS"

    cls = "NONE"
    if C["PATHOGEN_CONFIRMED"]:
        cls = "PROVEN"
    else:
        prob = (
            (B["CLINICAL_OVERRIDE"] and C["LAB_SUPPORT_FLAG"])
            or (B["CLINICAL_SIGN_COUNT"] >= 3 and C["LAB_SUPPORT_FLAG"])
            or (A["MAT_OVERRIDE_FLAG"] and B["CLINICAL_SIGN_COUNT"] >= 2 and C["LAB_SUPPORT_FLAG"])
            or (B["CLINICAL_OVERRIDE"] and A["MAT_OVERRIDE_FLAG"])
        )
        if prob:
            cls = "PROBABLE"
        else:
            poss = (
                (B["CLINICAL_SIGN_COUNT"] >= 2 and C["LAB_SCORE"] >= 2 and not C["LAB_SUPPORT_FLAG"])
                or B["CLINICAL_OVERRIDE"]
                or (A["MAT_OVERRIDE_FLAG"] and B["CLINICAL_SIGN_COUNT"] >= 1)
                or (A["MAT_RISK_SCORE"] >= 6 and B["CLINICAL_SIGN_COUNT"] >= 1)
                or (A["PRETERM_FLAG"] and B["CLINICAL_SIGN_COUNT"] >= 1 and A["MAT_RISK_SCORE"] >= 3)
            )
            if poss:
                cls = "POSSIBLE"

    # Observation-only pathway: for the mildest Possible cases, the original
    # flowchart design (and the uploaded master flowchart, row 138) calls for
    # close observation rather than immediate empiric antibiotics - this was
    # never implemented until now; every non-NONE case previously got a full
    # antibiotic recommendation regardless of how mild.
    observation_only = (
        cls == "POSSIBLE"
        and B["CLINICAL_SIGN_COUNT"] <= 2
        and C["LAB_SCORE"] < 3
        and not B["CLINICAL_OVERRIDE"]
        and not A["PRETERM_FLAG"]
        and not C["PATHOGEN_CONFIRMED"]
    )

    regimen = []
    regimen_detail = []
    if cls != "NONE" and not observation_only:
        org = C["ORGANISM"]
        if C["PATHOGEN_CONFIRMED"] and org:
            if org == "GBS":
                regimen = ["Penicillin G"]
                regimen_detail = [
                    "450,000 units/kg/day div q8h" if C["CSF_ABNORMAL"] else "100,000-150,000 units/kg/day div q12h"
                ]
            elif org == "listeria":
                regimen = ["Ampicillin", "Gentamicin"]
                regimen_detail = ["50 mg/kg/dose q6h IV", "4-5 mg/kg/day once daily"]
            elif org == "staph_aureus":
                regimen = ["Cloxacillin (if MSSA) OR Vancomycin (if MRSA)"]
                regimen_detail = ["MSSA: 50 mg/kg/dose q6h IV | MRSA: 15 mg/kg/dose q6-8h (trough 10-15)"]
            elif org == "candida":
                regimen = ["Fluconazole (if >1kg, no prior azole)", "OR Amphotericin B (<1kg or resistant)"]
                regimen_detail = ["12 mg/kg loading -> 6 mg/kg/day IV", "1 mg/kg/day IV"]
            else:
                regimen = ["Cefotaxime", "Gentamicin"] if timing == "EOS" else ["Cefotaxime", "Vancomycin"]
                regimen_detail = [
                    "50 mg/kg/dose q6-8h",
                    "4-5 mg/kg/day once daily" if timing == "EOS" else "15 mg/kg/dose q6-8h",
                ]
        else:
            if timing == "EOS":
                regimen = ["Ceftazidime OR Cefotaxime", "Amikacin OR Gentamicin"]
                regimen_detail = [
                    "Ceftazidime 50 mg/kg/dose q8-12h IV | Cefotaxime 50 mg/kg/dose q6-8h IV",
                    "Amikacin 15 mg/kg/day once daily | Gentamicin 4-5 mg/kg/day once daily",
                ]
                if C["CSF_ABNORMAL"]:
                    regimen.append("Cefotaxime")
                    regimen_detail.append("50 mg/kg/dose q6h IV (meningitis dose)")
            else:
                regimen = ["Vancomycin", "Gentamicin"]
                regimen_detail = ["15 mg/kg/dose q8-12h (adjust by GA/age)", "4-5 mg/kg/day IV once daily"]

    days = 0
    if observation_only:
        days = 0
    elif cls == "PROVEN":
        days = 10
    elif cls == "PROBABLE":
        days = 7
    elif cls == "POSSIBLE":
        days = 5

    ga_band = A["GA_BAND"]
    if A["PRETERM_FLAG"] and cls != "NONE" and not observation_only:
        if ga_band == "extremely_preterm":
            days += 4
        elif ga_band == "very_preterm":
            days += 3
        else:
            days += 2

    if not observation_only:
        if C["CSF_ABNORMAL"]:
            days = max(days, 21)
        if D["IMAGING_FINDING"] == "ENDOCARDITIS":
            days = max(days, 42)
        if D["IMAGING_FINDING"] in ("NEC", "NEC_PERFORATED"):
            days = max(days, 10)
        if D["IMAGING_FINDING"] == "ABSCESS":
            days = max(days, 28)

    stop_eligible = (
        C["ANTIBIOTIC_SAFE_TO_STOP"]
        and not D["LOCALIZED_INFECTION_FLAG"]
        and not C["CSF_ABNORMAL"]
        and D["IMAGING_FINDING"] == "NONE"
    )

    ga = A["GA"]
    antifungal = (ga < 32 or (not ga and A["PRETERM_FLAG"])) and cls != "NONE" and not observation_only

    return {
        "classification": cls,
        "timing": timing,
        "regimen": regimen,
        "regimen_detail": regimen_detail,
        "duration_days": days,
        "stop_eligible": stop_eligible,
        "antifungal": antifungal,
        "observation_only": observation_only,
    }


def run_pipeline(state, params=None):
    """Run the full A-E pipeline on a raw state dict. Returns everything
    needed to persist a CdsOutput record, including the flat list of every
    node that fired (across A-D) so the classification is fully traceable.

    params: optional dict of {node_id: {"threshold": x, "points": y}} loaded
    from the scoring_parameters registry (currently Flowchart A only). If
    omitted, every node falls back to its original hardcoded value - so
    existing callers and tests are completely unaffected."""
    A = compute_a(state, params)
    B = compute_b(state, A)
    C = compute_c(state, A)
    D = compute_d(state)
    E = compute_e(state, A, B, C, D)

    triggered_nodes = []
    for flowchart_key, result in (("A", A), ("B", B), ("C", C), ("D", D)):
        for node in result.get("nodes", []):
            triggered_nodes.append({**node, "flowchart": flowchart_key})

    return {"A": A, "B": B, "C": C, "D": D, "E": E, "triggered_nodes": triggered_nodes}
