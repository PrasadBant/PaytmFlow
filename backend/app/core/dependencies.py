from collections import defaultdict, deque
from typing import Any

from app.packs.contract import DependencyEdge, JourneyPackManifest


class DependencyGraph:
    def __init__(self, manifest: JourneyPackManifest, goal: dict[str, Any] | None = None):
        self.manifest = manifest
        self.goal = goal or {}
        self.field_keys: set[str] = {f.key for f in manifest.state_schema}
        self.adj: dict[str, list[str]] = defaultdict(list)
        self.rev_adj: dict[str, list[str]] = defaultdict(list)
        self.edges: list[DependencyEdge] = []
        self._build_graph()

    def _eval_condition(self, condition: dict[str, Any] | None) -> bool:
        if not condition:
            return True
        for key, pred in condition.items():
            actual = self.goal.get(key)
            if isinstance(pred, dict):
                if "eq" in pred and actual != pred["eq"]:
                    return False
                if "neq" in pred and actual == pred["neq"]:
                    return False
                if "in" in pred and actual not in pred["in"]:
                    return False
                if "nin" in pred and actual in pred["nin"]:
                    return False
            elif actual != pred:
                return False
        return True

    def _build_graph(self) -> None:
        for dep in self.manifest.dependencies:
            if dep.source in self.field_keys and dep.target in self.field_keys:
                if self._eval_condition(dep.condition):
                    self.adj[dep.source].append(dep.target)
                    self.rev_adj[dep.target].append(dep.source)
                    self.edges.append(dep)

    def get_topological_order(self) -> list[str]:
        in_degree = {k: len(self.rev_adj[k]) for k in self.field_keys}
        queue = deque(sorted([k for k, d in in_degree.items() if d == 0]))
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for nxt in sorted(self.adj[node]):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
        return order

    def get_direct_prerequisites(self, field: str) -> list[str]:
        return list(self.rev_adj.get(field, []))

    def get_direct_dependents(self, field: str) -> list[str]:
        return list(self.adj.get(field, []))

    def get_all_transitive_dependents(self, field: str) -> set[str]:
        visited = set()
        queue = deque(self.adj.get(field, []))
        while queue:
            curr = queue.popleft()
            if curr not in visited:
                visited.add(curr)
                for nxt in self.adj.get(curr, []):
                    if nxt not in visited:
                        queue.append(nxt)
        return visited

    def get_all_transitive_prerequisites(self, field: str) -> set[str]:
        visited = set()
        queue = deque(self.rev_adj.get(field, []))
        while queue:
            curr = queue.popleft()
            if curr not in visited:
                visited.add(curr)
                for prv in self.rev_adj.get(curr, []):
                    if prv not in visited:
                        queue.append(prv)
        return visited
