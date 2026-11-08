"""Resolve plugin-created session ownership without guessing between bot accounts."""

def resolve_session_route(platform, scope, descriptors):
    candidates = {
        (str(d.account_id).strip(), d.scope)
        for d in descriptors
        if d.platform == platform and d.account_id and str(d.account_id).strip()
        and (scope is None or d.scope == scope)
    }
    if len(candidates) > 1:
        raise ValueError("Multiple adapter routes; provide account_id and scope explicitly")
    if candidates:
        account_id, route_scope = next(iter(candidates))
        return account_id, scope if scope is not None else route_scope
    if platform == "qq":
        raise ValueError("No active QQ account; cannot create an unowned session")
    return None, scope
