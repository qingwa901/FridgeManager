from __future__ import annotations

from fastapi import APIRouter

from api.schemas import GroupIn
from function.group_service import GroupService


class GroupApi:
    """食材大类。"""

    def __init__(self, groups: GroupService):
        self.groups = groups
        self.router = APIRouter(prefix="/api/groups")
        r = self.router
        r.add_api_route("", self.list_groups, methods=["GET"])
        r.add_api_route("", self.add_group, methods=["POST"], status_code=201)
        r.add_api_route("/{group_id}", self.update_group, methods=["PUT"])
        r.add_api_route("/{group_id}", self.delete_group, methods=["DELETE"], status_code=204)

    def list_groups(self):
        """食材大类。expanded = 展开嵌套大类后的全部名字。"""
        return self.groups.list()

    def add_group(self, body: GroupIn):
        return self.groups.add(body)

    def update_group(self, group_id: int, body: GroupIn):
        """修改大类。改名时，其他大类里引用旧名字的地方一起改。"""
        return self.groups.update(group_id, body)

    def delete_group(self, group_id: int):
        self.groups.delete(group_id)
