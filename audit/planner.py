PHASE = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
OPS = ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK",
       "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD",
       "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED", "VERIFY_RECORD_ANONYMIZED",
       "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"]
STATE = {"REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT", "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
         "REPORT_RESTORE_RISK": "ACTIVE", "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED",
         "DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
         "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT", "VERIFY_RECORD_REDACTED": "REDACTED",
         "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
         "VERIFY_RESTORE_BLOCKED": "BLOCKED"}
PHASE_OF = {o: ("FINDING" if o.startswith("REPORT") else "VERIFICATION" if o.startswith("VERIFY") else "REMEDIATION")
            for o in OPS}
FIX_TO_VERIFY = {"DISABLE_DATA_FLOW": "VERIFY_DATA_FLOW_DISABLED", "BLOCK_RESTORE": "VERIFY_RESTORE_BLOCKED",
                 "DELETE_RECORD": "VERIFY_RECORD_ABSENT", "REDACT_RECORD": "VERIFY_RECORD_REDACTED",
                 "ANONYMIZE_RECORD": "VERIFY_RECORD_ANONYMIZED"}


def step(op, system, res, evidence=""):
    return dict(step_no=0, phase=PHASE_OF[op], system_id=system, resource_id=res, operation=op,
                state=STATE[op], evidence_id=evidence or "")


def finalize(steps):
    uniq = {}
    for s in steps:
        uniq.setdefault((s["operation"], s["system_id"], s["resource_id"]), s)
    out = sorted(uniq.values(), key=lambda s: (PHASE[s["phase"]], OPS.index(s["operation"]),
                                               s["system_id"], s["resource_id"]))
    for i, s in enumerate(out, 1):
        s["step_no"] = i
    return out


def plan(problems, verified, retained):
    """problems: [(finding_op, fix_op, system, res, evidence)]
       verified: [(verify_op, system, res, evidence)]  (already-correct state, cited)
       retained: [(system, res, evidence)]  (policy-required records that must remain)"""
    if not problems:
        return finalize([step(op, s, r, ev) for op, s, r, ev in verified] +
                        [step("VERIFY_RECORD_PRESENT", s, r, ev) for s, r, ev in retained])
    steps = []
    for f, fix, s, r, ev in problems:
        steps += [step(f, s, r, ev), step(fix, s, r), step(FIX_TO_VERIFY[fix], s, r)]
    steps += [step("VERIFY_RECORD_PRESENT", s, r) for s, r, _ in retained]
    return finalize(steps)
