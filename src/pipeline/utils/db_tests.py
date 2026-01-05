from api.db import Database
from api.models import CallRecord, PipelineStatus


def update_call_record_status(db: Database, call_ids: list[str], status: PipelineStatus) -> None:
    with db.session() as session:
        call_records = CallRecord.get_from_id(session, call_ids)
        for call_id in call_ids:
            r = call_records[call_id].set_status(session, new_status=status, source="db_tester", force=True)
            if not r:
                raise Exception(f"Error when setting status for call_id {call_id}")
        session.commit()


def main():
    pass


if __name__ == "__main__":
    main()