from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from auth_store import AUTH_DB_PATH, authenticate, create_invite, create_owner, list_members, revoke_invite, set_member_status


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Park Research private-beta members")
    parser.add_argument("--db", type=Path, default=AUTH_DB_PATH)
    commands = parser.add_subparsers(dest="command", required=True)

    owner = commands.add_parser("create-owner")
    owner.add_argument("--email", required=True)
    owner.add_argument("--name", default="Park")

    invite = commands.add_parser("create-invite")
    invite.add_argument("--owner-email", required=True)
    invite.add_argument("--tier", choices=("preview", "member", "paid"), default="member")
    invite.add_argument("--max-uses", type=int, default=1)
    invite.add_argument("--valid-days", type=int, default=7)

    members = commands.add_parser("list-members")
    members.add_argument("--owner-email", required=True)

    status = commands.add_parser("set-status")
    status.add_argument("--owner-email", required=True)
    status.add_argument("--member-email", required=True)
    status.add_argument("--status", choices=("active", "suspended"), required=True)

    revoke = commands.add_parser("revoke-invite")
    revoke.add_argument("--owner-email", required=True)
    revoke.add_argument("--invite-id", required=True)

    args = parser.parse_args()
    password = getpass.getpass("Password: ")
    if args.command == "create-owner":
        result = create_owner(args.email, password, args.name, args.db)
    elif args.command == "create-invite":
        member = authenticate(args.owner_email, password, args.db)
        if not member or member["role"] != "owner":
            raise SystemExit("owner authentication failed")
        result = create_invite(member["id"], args.tier, args.db, max_uses=args.max_uses, valid_days=args.valid_days)
    else:
        member = authenticate(args.owner_email, password, args.db)
        if not member or member["role"] != "owner":
            raise SystemExit("owner authentication failed")
        if args.command == "list-members":
            result = {"members": list_members(member["id"], args.db)}
        elif args.command == "set-status":
            result = set_member_status(member["id"], args.member_email, args.status, args.db)
        else:
            result = revoke_invite(member["id"], args.invite_id, args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
