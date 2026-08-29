# -*- coding: utf-8 -*-
from collections import defaultdict


def migrate(cr, version):
    from odoo.api import Environment

    env = Environment(cr, 1, {})
    versions = env["hjig.programme.template.version"].search([
        ("template_id.code", "in", ["LGC", "LGD", "LGV", "TLC", "TLL"]),
        ("state", "in", ["draft", "review"]),
    ])
    for programme_version in versions:
        rules_by_pair = defaultdict(lambda: env["hjig.programme.template.dependency.rule"])
        for rule in programme_version.dependency_rule_ids:
            pair = (rule.predecessor_activity_id.id, rule.successor_activity_id.id)
            rules_by_pair[pair] |= rule
        for pair_rules in rules_by_pair.values():
            if len(pair_rules) <= 1:
                continue
            redundant_barriers = pair_rules.filtered(lambda rule: rule.rule_type == "gate_barrier")
            if redundant_barriers and len(pair_rules - redundant_barriers):
                redundant_barriers.unlink()
    versions._sync_authoritative_gate_checklists()
