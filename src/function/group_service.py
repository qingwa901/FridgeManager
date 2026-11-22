from __future__ import annotations

from common_lib import Base

from api.schemas import GroupIn
from data import Database, Session
from function.group_resolver import GroupResolver
from function.service_error import ServiceError


class GroupService(Base):
    """食材大类的增删改查。"""

    def __init__(self, db: Database):
        self.db = db

    def resolver(self) -> GroupResolver:
        """当前大类的快照，用于匹配食材。"""
        with self.db.session() as s:
            return GroupResolver(s.groups.as_map())

    def list(self) -> list[dict]:
        """expanded = 展开嵌套大类后的全部名字。"""
        with self.db.session() as s:
            groups = s.groups.list_all()
            expanded = GroupResolver.expand(s.groups.as_map())
        return [{**g, "expanded": expanded.get(g["name"], [])} for g in groups]

    def add(self, body: GroupIn) -> dict:
        with self.db.session() as s:
            name, members, _ = self._check(s, body, None)
            group = self._view(s, s.groups.insert(name, members))
        self.get_logger().info("添加食材大类 #%d %s：%s", group["id"], name, "、".join(members))
        return group

    def update(self, group_id: int, body: GroupIn) -> dict:
        """修改大类。改名时，其他大类里引用旧名字的地方一起改（食谱里写的旧名字不会自动改）。"""
        with self.db.session() as s:
            name, members, old = self._check(s, body, group_id)
            s.groups.update(group_id, name, members)
            if old != name:
                s.groups.rename_member(old, name, exclude_id=group_id)
            group = self._view(s, group_id)
        self.get_logger().info("修改食材大类 #%d %s%s：%s", group_id, name, f"（原名 {old}）" if old != name else "", "、".join(members))
        return group

    def delete(self, group_id: int) -> None:
        with self.db.session() as s:
            group = s.groups.get(group_id)
            if group is None:
                raise ServiceError(ServiceError.NOT_FOUND, "大类不存在")
            s.groups.delete(group_id)
        self.get_logger().info("删除食材大类 #%d %s", group_id, group["name"])

    @staticmethod
    def _view(s: Session, group_id: int) -> dict:
        group = s.groups.get(group_id)
        return {**group, "expanded": GroupResolver.expand(s.groups.as_map()).get(group["name"], [])}

    @staticmethod
    def _check(s: Session, body: GroupIn, group_id: int | None) -> tuple[str, list[str], str | None]:
        """校验并整理大类：去空白、去重、不能包含自己、不能互相包含。返回 (名字, 成员, 旧名字)。"""
        name = body.name.strip()
        if not name:
            raise ServiceError(ServiceError.INVALID, "大类名不能为空")
        members = list(dict.fromkeys(m.strip() for m in body.members if m.strip() and m.strip() != name))
        if not members:
            raise ServiceError(ServiceError.INVALID, "至少包含一样食材")
        if s.groups.name_taken(name, exclude_id=group_id):
            raise ServiceError(ServiceError.CONFLICT, f"已经有叫「{name}」的大类了")
        groups = s.groups.as_map()
        old = None
        if group_id is not None:
            current = s.groups.get(group_id)
            if current is None:
                raise ServiceError(ServiceError.NOT_FOUND, "大类不存在")
            old = current["name"]
            groups.pop(old)
            groups = {g: [name if m == old else m for m in ms] for g, ms in groups.items()}   # 改名后的引用
        groups[name] = members
        expanded = GroupResolver.expand(groups)
        loop = next((m for m in members if name in expanded.get(m, [])), None)
        if loop:
            raise ServiceError(ServiceError.INVALID, f"「{loop}」里又包含了「{name}」，不能互相包含")
        return name, members, old
