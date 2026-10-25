"""Team-created cases on a tiny synthetic dataset that mimics the REAL file formats
(JSON snapshot bundle, SQL with record_json, handover txt with '|' lines, key=value logs).
Run: python -m tests.test_synthetic"""
import json, hashlib, tempfile, textwrap
from pathlib import Path
from audit.pipeline import Auditor

H = lambda e: hashlib.sha256(e.encode()).hexdigest()


def build(root: Path):
    (root / "evidence").mkdir(parents=True)
    w = lambda n, s: (root / n).write_text(textwrap.dedent(s).lstrip(), encoding="utf-8")
    w("user_identities.csv", f"""\
        user_id,name,email,phone,email_hash,updated_at
        user_01,Amina El-Masri,amina.new@gmail.com,+971 50 482 7316,{H('amina.new@gmail.com')},2026-05-28T04:03:00Z
        user_02,Mateo Rios,mateo.rios@outlook.com,+34 612 847 593,{H('mateo.rios@outlook.com')},2026-04-24T07:44:00Z
        user_03,Carol Diaz,carol@x.com,+1 202 555 0103,{H('carol@x.com')},2026-04-24T07:44:00Z
        """)
    w("user_audit_log.csv", """\
        audit_id,user_id,event_time,field_name,old_value,new_value
        audit_01,user_01,2025-01-01T00:00:00Z,email,amina.old@gmail.com,amina.new@gmail.com
        """)
    w("deletion_rules.csv", """\
        rule_id,data_category,condition,required_action
        rule_01,USER_PROFILE,Always,DELETE
        rule_03,SEARCH_INDEX_ENTRY,Always,DELETE
        rule_07,ANALYTICS_PROFILE,Record is still attributable to a user,ANONYMIZE
        rule_12,SECURITY_AUDIT_LOG,Record is within the supplied retention period,RETAIN
        rule_14,BACKUP_ARCHIVE,Restore access can be blocked,RETAIN
        rule_15,ACCOUNT_TOMBSTONE,Account is deleted and only a stable internal user_id is needed,REDACT
        """)
    w("system_activity.csv", """\
        activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details
        activity_01,2026-09-10T00:00:00Z,DELETE_RECORD,deletion_worker,account_service,account_5684,SUCCESS,Deletion worker submitted primary profile account_5684 to account_service.
        activity_02,2026-09-12T00:00:00Z,SYNC_RECORD,account_service,account_service,account_5684,SUCCESS,Customer profile synchronization processed account_5684.
        activity_03,2026-09-10T00:00:00Z,DELETE_RECORD,deletion_worker,account_service,account_146,FAILED,Deletion worker received the final result for account_146.
        """)
    w("evidence_files.csv", """\
        file_id,file_path,origin,captured_at
        evidence_01,evidence/snap.json,bundle,2026-09-17T12:00:00Z
        evidence_02,evidence/replica.sql,sql,2026-09-21T10:00:00Z
        evidence_03,evidence/handover.txt,txt,2026-10-01T12:00:00Z
        evidence_04,evidence/svc.log,log,2026-09-15T12:00:00Z
        """)
    (root / "evidence/snap.json").write_text(json.dumps({"snapshots": [{
        "captured_at": "2026-09-09T12:00:00Z", "data_store": "account_service", "collection": "customer_profiles",
        "records": [{"resource_id": "account_5684", "customer_reference": "user_01", "full_name": "Amina El-Masri",
                     "email": "amina.old@gmail.com", "phone": "+971 50 482 7316"}]}]}))
    (root / "evidence/replica.sql").write_text(textwrap.dedent("""\
        -- Captured at: 2026-09-21T10:00:00Z
        BEGIN TRANSACTION;
        CREATE TABLE customer_data_primary (resource_id TEXT PRIMARY KEY, origin_system TEXT, collection_name TEXT, record_json TEXT, updated_at TEXT);
        INSERT INTO "customer_data_primary" VALUES('analytics_1738','analytics_platform','customer_analytics_reports','{"resource_id":"analytics_1738","user_id":"user_01","email":"amina.new@gmail.com"}','x');
        INSERT INTO "customer_data_primary" VALUES('analytics_2572','analytics_platform','customer_analytics_reports','{"resource_id":"analytics_2572","user_id":null,"email":null}','x');
        COMMIT;
        """))
    (root / "evidence/handover.txt").write_text(textwrap.dedent("""\
        CUSTOMER PLATFORM - SHIFT HANDOVER
        Snapshot: 2026-10-01T12:00:00Z
        - 2026-10-01T12:00:00Z | account_service | account_146 | USER_PROFILE | NOT_FOUND | mateo.rios@outlook.com
        - 2026-10-01T12:00:00Z | analytics_platform | analytics_6830 | ANALYTICS_PROFILE | ANONYMIZED | user_02
        - 2026-10-01T12:00:00Z | backup_service | backup_706 | BACKUP_ARCHIVE | BLOCKED | user_02
        - 2026-10-01T12:00:00Z | security_service | audit_record_2016 | SECURITY_AUDIT_LOG | RETAINED | user_02
        """))
    (root / "evidence/svc.log").write_text(
        '2026-09-15T08:51:45Z level=DEBUG service=search_service trace_id=tr-1 event=index_query_started match_key="amina.old@gmail.com"\n'
        '2026-09-15T08:51:57Z level=INFO service=search_service trace_id=tr-1 resource_id=search_1874 event=index_query_completed result=hit\n')


def main():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); build(root)
        a = Auditor(root)
        mk = lambda cid, em, txt="Please delete my account": dict(case_id=cid, email=em, audit_at="2026-09-25T00:00:00Z", request_text=txt)
        res = []
        s, steps, tr = a.run_case(mk("t1", "AMINA.OLD@gmail.com"))
        ops = {(x["operation"], x["resource_id"]) for x in steps}
        res.append(("Historical email -> sync recreated deleted account + search hit via log trace + attributable analytics",
                    s == "INCOMPLETE" and ("REPORT_REMAINING_RECORD", "account_5684") in ops
                    and ("REPORT_REMAINING_RECORD", "search_1874") in ops and ("ANONYMIZE_RECORD", "analytics_1738") in ops
                    and [x["step_no"] for x in steps] == list(range(1, len(steps) + 1)), f"status={s}, {len(steps)} steps"))
        a2 = Auditor(root)
        s, steps, tr = a2.run_case(dict(mk("t2", "mateo.rios@outlook.com"), audit_at="2026-10-02T00:00:00Z"))
        ops = {(x["operation"], x["resource_id"]) for x in steps}
        res.append(("All clean at audit time: absent profile, anonymized analytics, blocked backup, retained audit record cited",
                    s == "COMPLETE" and ("VERIFY_RECORD_ABSENT", "account_146") in ops and ("VERIFY_RESTORE_BLOCKED", "backup_706") in ops
                    and ("VERIFY_RECORD_ANONYMIZED", "analytics_6830") in ops and ("VERIFY_RECORD_PRESENT", "audit_record_2016") in ops
                    and all(x["evidence_id"] for x in steps), f"status={s}, {len(steps)} steps"))
        s, steps, _ = a.run_case(mk("t3", "carol@x.com", "My surname is misspelled. Can you correct it without removing any of my records?"))
        res.append(("Non-deletion request -> NOT_APPLICABLE and []", s == "NOT_APPLICABLE" and steps == [], f"status={s}"))
        for t_, ok, d in res:
            print("PASS" if ok else "FAIL", "-", t_, "|", d)
        if not all(r[1] for r in res):
            print(json.dumps(tr.get("resources"), indent=1)[:1500])
        return res


if __name__ == "__main__":
    r = main()
    raise SystemExit(0 if all(x[1] for x in r) else 1)
