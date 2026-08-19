"""
Seeds default roles and permissions.

WHY these three roles specifically: they map to the three real personas
this platform is designed for — someone who can only look at dashboards
(viewer), someone who operates the system day-to-day (operator: ack
alerts, trigger manual scaling), and someone who administers the platform
itself (admin: manage users/roles/config). This is a deliberate minimal
set — more granular roles can be added later via the API without a code
change, since roles/permissions are data, not enum values.

Usage: python scripts/seed_rbac.py
"""

import asyncio

from platform_common.db import Database

from app.core.config import AuthServiceSettings
from app.models.auth import Permission, Role

PERMISSIONS = [
    ("service:read", "service", "read"),
    ("service:create", "service", "create"),
    ("service:update", "service", "update"),
    ("service:delete", "service", "delete"),
    ("alert:read", "alert", "read"),
    ("alert:acknowledge", "alert", "acknowledge"),
    ("metrics:read", "metrics", "read"),
    ("metrics:write", "metrics", "write"),
    ("logs:read", "logs", "read"),
    ("logs:write", "logs", "write"),
    ("notifications:send", "notifications", "send"),
    ("storage:read", "storage", "read"),
    ("storage:write", "storage", "write"),
    ("scaling:trigger", "scaling", "trigger"),
    ("dashboard:read", "dashboard", "read"),
    ("user:manage", "user", "manage"),
    ("config:manage", "config", "manage"),
    ("admin:*", "*", "*"),  # superuser wildcard, checked explicitly in require_permission()
]

ROLES = {
    "viewer": ["service:read", "alert:read", "dashboard:read", "metrics:read", "logs:read", "storage:read"],
    "operator": [
        "service:read",
        "service:update",
        "alert:read",
        "alert:acknowledge",
        "metrics:read",
        "metrics:write",
        "logs:read",
        "logs:write",
        "notifications:send",
        "storage:read",
        "storage:write",
        "scaling:trigger",
        "dashboard:read",
    ],
    "admin": ["admin:*"],
}


async def seed() -> None:
    settings = AuthServiceSettings()
    db = Database(settings.DATABASE_URL)

    async with db.session_scope() as session:
        from sqlalchemy import select

        perm_objs: dict[str, Permission] = {}
        for name, resource, action in PERMISSIONS:
            result = await session.execute(select(Permission).where(Permission.name == name))
            perm = result.scalar_one_or_none()
            if perm is None:
                perm = Permission(name=name, resource=resource, action=action)
                session.add(perm)
                await session.flush()
            perm_objs[name] = perm

        for role_name, perm_names in ROLES.items():
            result = await session.execute(select(Role).where(Role.name == role_name))
            role = result.scalar_one_or_none()
            if role is None:
                role = Role(name=role_name, description=f"Default '{role_name}' role")
                session.add(role)
                await session.flush()
            # Explicitly populate the relationship via `refresh` before
            # assigning to it — without this, SQLAlchemy's async ORM tries
            # to lazily load the CURRENT collection (to diff against the
            # new one) outside of the greenlet-wrapped async context,
            # raising MissingGreenlet. `refresh` performs that load
            # properly through the async session first.
            await session.refresh(role, attribute_names=["permissions"])
            role.permissions = [perm_objs[p] for p in perm_names]

    await db.dispose()
    print("RBAC seed complete: roles =", list(ROLES.keys()))


if __name__ == "__main__":
    asyncio.run(seed())
