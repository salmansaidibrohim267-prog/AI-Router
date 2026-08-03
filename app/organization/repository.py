from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from .models import Invitation, Member, Organization, Project, Team, Workspace

T = TypeVar("T")


class BaseInMemoryRepository(Generic[T], ABC):
    def __init__(self):
        self._lock = threading.Lock()
        self._items: dict[str, T] = {}

    @abstractmethod
    def _item_id(self, item: T) -> str: ...

    def create(self, item: T) -> T:
        with self._lock:
            self._items[self._item_id(item)] = item
            return item

    def get(self, item_id: str) -> T | None:
        with self._lock:
            return self._items.get(item_id)

    def update(self, item: T) -> T:
        with self._lock:
            self._items[self._item_id(item)] = item
            return item

    def delete(self, item_id: str) -> bool:
        with self._lock:
            return self._items.pop(item_id, None) is not None

    def list_all(self) -> list[T]:
        with self._lock:
            return list(self._items.values())


class OrganizationRepository(BaseInMemoryRepository[Organization]):
    def _item_id(self, item: Organization) -> str:
        return item.id

    def get_by_slug(self, slug: str, tenant_id: str) -> Organization | None:
        with self._lock:
            for org in self._items.values():
                if org.slug == slug and org.tenant_id == tenant_id:
                    return org
        return None

    def list_for_tenant(self, tenant_id: str) -> list[Organization]:
        with self._lock:
            items = [o for o in self._items.values() if o.tenant_id == tenant_id]
        return sorted(items, key=lambda o: o.created_at)

    def count_for_tenant(self, tenant_id: str) -> int:
        return len(self.list_for_tenant(tenant_id))


class WorkspaceRepository(BaseInMemoryRepository[Workspace]):
    def _item_id(self, item: Workspace) -> str:
        return item.id

    def get_by_slug(self, slug: str, organization_id: str) -> Workspace | None:
        with self._lock:
            for ws in self._items.values():
                if ws.slug == slug and ws.organization_id == organization_id:
                    return ws
        return None

    def list_for_organization(self, organization_id: str) -> list[Workspace]:
        with self._lock:
            items = [w for w in self._items.values() if w.organization_id == organization_id]
        return sorted(items, key=lambda w: w.created_at)

    def list_for_tenant(self, tenant_id: str) -> list[Workspace]:
        with self._lock:
            items = [w for w in self._items.values() if w.tenant_id == tenant_id]
        return sorted(items, key=lambda w: w.created_at)

    def count_for_organization(self, organization_id: str) -> int:
        return len(self.list_for_organization(organization_id))


class TeamRepository(BaseInMemoryRepository[Team]):
    def _item_id(self, item: Team) -> str:
        return item.id

    def list_for_organization(self, organization_id: str) -> list[Team]:
        with self._lock:
            items = [t for t in self._items.values() if t.organization_id == organization_id]
        return sorted(items, key=lambda t: t.created_at)

    def count_for_organization(self, organization_id: str) -> int:
        return len(self.list_for_organization(organization_id))


class MemberRepository(BaseInMemoryRepository[Member]):
    def _item_id(self, item: Member) -> str:
        return item.id

    def get_by_user(self, organization_id: str, user_id: str) -> Member | None:
        with self._lock:
            for member in self._items.values():
                if member.organization_id == organization_id and member.user_id == user_id:
                    return member
        return None

    def list_for_organization(self, organization_id: str) -> list[Member]:
        with self._lock:
            items = [m for m in self._items.values() if m.organization_id == organization_id]
        return sorted(items, key=lambda m: m.created_at)

    def count_for_organization(self, organization_id: str) -> int:
        return len(self.list_for_organization(organization_id))

    def delete_for_organization(self, organization_id: str) -> int:
        with self._lock:
            ids = [mid for mid, m in self._items.items() if m.organization_id == organization_id]
            for mid in ids:
                del self._items[mid]
            return len(ids)


class ProjectRepository(BaseInMemoryRepository[Project]):
    def _item_id(self, item: Project) -> str:
        return item.id

    def get_by_name(self, workspace_id: str, name: str) -> Project | None:
        with self._lock:
            for project in self._items.values():
                if project.workspace_id == workspace_id and project.name == name:
                    return project
        return None

    def list_for_workspace(self, workspace_id: str) -> list[Project]:
        with self._lock:
            items = [p for p in self._items.values() if p.workspace_id == workspace_id]
        return sorted(items, key=lambda p: p.created_at)

    def count_for_workspace(self, workspace_id: str) -> int:
        return len(self.list_for_workspace(workspace_id))


class InvitationRepository(BaseInMemoryRepository[Invitation]):
    def _item_id(self, item: Invitation) -> str:
        return item.id

    def get_by_token(self, token: str) -> Invitation | None:
        with self._lock:
            for invite in self._items.values():
                if invite.token == token:
                    return invite
        return None

    def list_for_organization(self, organization_id: str, status: str = "") -> list[Invitation]:
        with self._lock:
            items = [i for i in self._items.values() if i.organization_id == organization_id]
        if status:
            items = [i for i in items if i.status.value == status]
        return sorted(items, key=lambda i: i.created_at)

    def count_pending_for_organization(self, organization_id: str) -> int:
        return len(self.list_for_organization(organization_id, status="pending"))
