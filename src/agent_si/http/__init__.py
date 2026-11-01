"""K07NEXT served boundary package (split A owns it).

Mount-only boundary: agent_si.backend.app is never touched; tests call
mount() on the real create_app() app and drive every route over real
HTTP on loopback.
"""
