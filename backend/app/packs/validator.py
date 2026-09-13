from collections import defaultdict, deque
from dataclasses import dataclass

from app.packs.contract import JourneyPackManifest
from app.schemas.enums import FieldStatus

CANONICAL_BANNED_WORDS = [
    "approved",
    "approval",
    "probability",
    "credit score",
    "eligibility score",
    "readiness score",
    "guaranteed",
]


@dataclass(frozen=True)
class PackViolation:
    code: str
    message: str
    field_or_id: str | None = None


class PackValidator:
    def __init__(self, manifest: JourneyPackManifest):
        self.manifest = manifest
        self.violations: list[PackViolation] = []
        self.field_keys = {f.key for f in manifest.state_schema}
        self.action_ids = {a.action_id for a in manifest.actions}

    def validate_all(self) -> list[PackViolation]:
        self.validate_referential_integrity()
        has_cycle = self.validate_cycles()
        self.validate_contract_floor()
        self.validate_planner_preconditions()
        if not has_cycle:
            self.validate_depth_quality()
        self.validate_claims()
        return self.violations

    def validate_referential_integrity(self):
        for dep in self.manifest.dependencies:
            if dep.source not in self.field_keys:
                self.violations.append(
                    PackViolation(
                        code="UNKNOWN_FIELD_REF",
                        message=f"Dependency source '{dep.source}' not found",
                        field_or_id=dep.source,
                    )
                )
            if dep.target not in self.field_keys:
                self.violations.append(
                    PackViolation(
                        code="UNKNOWN_FIELD_REF",
                        message=f"Dependency target '{dep.target}' not found",
                        field_or_id=dep.target,
                    )
                )

        for action in self.manifest.actions:
            for s in action.satisfies:
                if s not in self.field_keys:
                    self.violations.append(
                        PackViolation(
                            code="UNKNOWN_FIELD_REF",
                            message=f"Action '{action.action_id}' satisfies unknown field '{s}'",
                            field_or_id=s,
                        )
                    )
            for p in action.preconditions:
                if p not in self.field_keys:
                    self.violations.append(
                        PackViolation(
                            code="UNKNOWN_FIELD_REF",
                            message=f"Action '{action.action_id}' requires unknown pre '{p}'",
                            field_or_id=p,
                        )
                    )

        for em in self.manifest.evidence_mappings:
            if em.target_field not in self.field_keys:
                self.violations.append(
                    PackViolation(
                        code="UNKNOWN_FIELD_REF",
                        message=f"Evidence '{em.doc_type}' targets unknown '{em.target_field}'",
                        field_or_id=em.target_field,
                    )
                )
            if em.action_id not in self.action_ids:
                self.violations.append(
                    PackViolation(
                        code="UNKNOWN_FIELD_REF",
                        message=f"Evidence mapping references unknown action '{em.action_id}'",
                        field_or_id=em.action_id,
                    )
                )

        for amb in self.manifest.ambiguity_rules:
            if amb.field not in self.field_keys:
                self.violations.append(
                    PackViolation(
                        code="UNKNOWN_FIELD_REF",
                        message=f"Ambiguity '{amb.ambiguity_id}' references unknown '{amb.field}'",
                        field_or_id=amb.field,
                    )
                )

    def validate_cycles(self) -> bool:
        adj = defaultdict(list)
        in_degree = {k: 0 for k in self.field_keys}
        for dep in self.manifest.dependencies:
            if dep.source in self.field_keys and dep.target in self.field_keys:
                adj[dep.source].append(dep.target)
                in_degree[dep.target] += 1

        queue = deque([k for k, d in in_degree.items() if d == 0])
        visited_count = 0
        while queue:
            node = queue.popleft()
            visited_count += 1
            for nxt in adj[node]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if visited_count < len(self.field_keys):
            self.violations.append(
                PackViolation(
                    code="CYCLIC_DEPENDENCY",
                    message="Cycle detected in field dependencies graph",
                )
            )
            return True
        return False

    def validate_contract_floor(self):
        if (
            len(self.manifest.state_schema) < 5
            or len(self.manifest.dependencies) < 4
            or len(self.manifest.actions) < 5
            or len(self.manifest.evidence_mappings) < 3
            or len(self.manifest.ambiguity_rules) < 2
        ):
            self.violations.append(
                PackViolation(
                    code="BELOW_CONTRACT_FLOOR",
                    message=(
                        f"Manifest below floor: fields={len(self.manifest.state_schema)}/5, "
                        f"deps={len(self.manifest.dependencies)}/4, "
                        f"actions={len(self.manifest.actions)}/5, "
                        f"evidence={len(self.manifest.evidence_mappings)}/3, "
                        f"ambiguities={len(self.manifest.ambiguity_rules)}/2"
                    ),
                )
            )

    def validate_planner_preconditions(self):
        satisfiers_map: dict[str, list[str]] = defaultdict(list)
        for action in self.manifest.actions:
            for s in action.satisfies:
                satisfiers_map[s].append(action.action_id)

        groups = self.manifest.action_groups or {}
        for field, action_ids in satisfiers_map.items():
            if len(action_ids) > 1:
                group_names = set()
                for aid in action_ids:
                    action_obj = next(
                        (a for a in self.manifest.actions if a.action_id == aid), None
                    )
                    if action_obj and action_obj.action_group:
                        group_names.add(action_obj.action_group)
                    else:
                        group_names.add(None)

                if len(group_names) > 1 or None in group_names:
                    self.violations.append(
                        PackViolation(
                            code="DUPLICATE_SATISFIER",
                            message=f"Actions {action_ids} satisfy '{field}' without shared group",
                            field_or_id=field,
                        )
                    )

        for gname, gspec in groups.items():
            member_actions = [a for a in self.manifest.actions if a.action_id in gspec.members]
            if len(member_actions) != len(gspec.members):
                self.violations.append(
                    PackViolation(
                        code="INCONSISTENT_GROUP",
                        message=f"Group '{gname}' references non-existent member actions",
                        field_or_id=gname,
                    )
                )
            else:
                first_satisfies = set(member_actions[0].satisfies)
                for member in member_actions[1:]:
                    if set(member.satisfies) != first_satisfies:
                        self.violations.append(
                            PackViolation(
                                code="INCONSISTENT_GROUP",
                                message=f"Group '{gname}' member '{member.action_id}' differs",
                                field_or_id=gname,
                            )
                        )

        all_satisfied_fields = set()
        for action in self.manifest.actions:
            all_satisfied_fields.update(action.satisfies)

        for f in self.manifest.state_schema:
            if f.mandatory and not f.derived and f.default_status != FieldStatus.SATISFIED:
                if f.key not in all_satisfied_fields:
                    self.violations.append(
                        PackViolation(
                            code="UNREACHABLE_FIELD",
                            message=f"Mandatory non-derived field '{f.key}' has no action",
                            field_or_id=f.key,
                        )
                    )

    def validate_depth_quality(self):
        adj = defaultdict(list)
        for dep in self.manifest.dependencies:
            if dep.source in self.field_keys and dep.target in self.field_keys:
                adj[dep.source].append(dep.target)

        def max_path(node: str, memo: dict, visiting: set) -> int:
            if node in memo:
                return memo[node]
            if node in visiting:
                return 0
            visiting.add(node)
            res = 1
            for nxt in adj[node]:
                res = max(res, 1 + max_path(nxt, memo, visiting))
            visiting.remove(node)
            memo[node] = res
            return res

        memo: dict[str, int] = {}
        max_chain = max((max_path(k, memo, set()) for k in self.field_keys), default=0)
        if max_chain < 3:
            self.violations.append(
                PackViolation(
                    code="SHALLOW_CASCADE",
                    message=f"Longest cascade is {max_chain}, expected at least 3",
                )
            )

        initial_satisfied = {
            f.key for f in self.manifest.state_schema if f.default_status == FieldStatus.SATISFIED
        }

        visited_states: set[frozenset] = set()
        queue = deque([frozenset(initial_satisfied)])
        visited_states.add(frozenset(initial_satisfied))

        has_non_trivial_choice = False

        while queue:
            current_satisfied = queue.popleft()

            valid_actions = []
            for action in self.manifest.actions:
                if all(p in current_satisfied for p in action.preconditions):
                    if not all(s in current_satisfied for s in action.satisfies):
                        valid_actions.append(action)

            if len(valid_actions) >= 3:
                unblock_counts = set()
                for act in valid_actions:
                    hypothetical_satisfied = set(current_satisfied) | set(act.satisfies)
                    unlocked_actions = 0
                    for other_act in self.manifest.actions:
                        if other_act.action_id != act.action_id:
                            was_valid = all(p in current_satisfied for p in other_act.preconditions)
                            now_valid = all(
                                p in hypothetical_satisfied for p in other_act.preconditions
                            )
                            if now_valid and not was_valid:
                                unlocked_actions += 1
                    unblock_counts.add(unlocked_actions)

                if len(unblock_counts) >= 2:
                    has_non_trivial_choice = True

            for act in valid_actions:
                next_satisfied = frozenset(set(current_satisfied) | set(act.satisfies))
                if next_satisfied not in visited_states:
                    visited_states.add(next_satisfied)
                    queue.append(next_satisfied)

        if not has_non_trivial_choice:
            self.violations.append(
                PackViolation(
                    code="TRIVIAL_ORDERING",
                    message="No reachable state with >= 3 actions & >= 2 unblock counts",
                )
            )

        all_reachable_fields = set()
        for st in visited_states:
            all_reachable_fields.update(st)

        for amb in self.manifest.ambiguity_rules:
            if amb.field not in all_reachable_fields:
                self.violations.append(
                    PackViolation(
                        code="UNREACHABLE_AMBIGUITY",
                        message=f"Ambiguity rule '{amb.ambiguity_id}' on '{amb.field}' unreachable",
                        field_or_id=amb.ambiguity_id,
                    )
                )

    def validate_claims(self):
        text_corpus = [
            self.manifest.metadata.display_name,
            self.manifest.metadata.description,
        ]
        for v in self.manifest.ui_labels.values():
            text_corpus.append(v)
        for a in self.manifest.actions:
            text_corpus.append(a.title)
            if a.why:
                text_corpus.append(a.why)

        all_banned = set(CANONICAL_BANNED_WORDS) | set(self.manifest.prohibited_claims)
        joined_text = " ".join(text_corpus).lower()

        for term in all_banned:
            if term and term.lower() in joined_text:
                self.violations.append(
                    PackViolation(
                        code="PROHIBITED_CLAIM",
                        message=f"Pack text contains prohibited claim term: '{term}'",
                        field_or_id=term,
                    )
                )


def validate_manifest(manifest: JourneyPackManifest) -> list[PackViolation]:
    validator = PackValidator(manifest)
    return validator.validate_all()
