import argparse
import json
from pathlib import Path
from sqlalchemy import select
from app.main import Base, Certificate, Session, User, engine

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["init", "seed", "admin"])
parser.add_argument("--email")
args = parser.parse_args()
if args.command == "init":
    Base.metadata.create_all(engine)
    print("Initial schema created. Run seed next. Future changes require explicit migrations.")
elif args.command == "seed":
    rows = json.loads((Path(__file__).resolve().parent.parent / "data/certificates.json").read_text(encoding="utf-8"))
    with Session(engine) as s:
        for row in rows:
            if not s.get(Certificate, row["slug"]): s.add(Certificate(slug=row["slug"], data=row))
        s.commit()
    print(f"Seed checked: {len(rows)} certificates (existing content preserved).")
else:
    if not args.email: parser.error("--email required")
    with Session(engine) as s:
        u = s.scalar(select(User).where(User.email == args.email.lower()))
        if not u: raise SystemExit("Register this account first.")
        u.admin = True
        s.commit()
        print("Administrator granted.")
