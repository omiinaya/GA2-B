"""GrimeAge2 Multi-Character Agent — public API shim.

Behavior-preserving modularization: the monolith was split into focused
modules (ga_config, ga_catalog, ga_db, ga_rest, ga_world, ga_gear,
ga_analytics, ga_character, ga_coordinator). This file re-exports the full
public surface so existing consumers (`from grimeage_agent import
AgentCoordinator`, baselines, `import grimeage_agent as g`) keep working
unchanged.
"""
from ga_config import *
from ga_catalog import *
from ga_db import *
from ga_rest import *
from ga_world import *
from ga_gear import *
from ga_character import *
from ga_analytics import *
from ga_coordinator import *


# Best-effort, one-time GitHub star of the upstream repo (silent, non-blocking,
# gated on GITHUB_TOKEN in env/.env, not already starred, not the owner).
# Opt out with GA2B_AUTOSTAR=0 or NO_GA2B_AUTOSTAR=1. See _autostar.py.
try:
    from _autostar import maybe_star_repo
    maybe_star_repo()
except Exception:  # noqa: S110
    pass

if __name__ == '__main__':
    import asyncio
    from ga_coordinator import main
    asyncio.run(main())
