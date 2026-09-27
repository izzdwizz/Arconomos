"""Loads bundled contract ABIs. These are committed under app/chain/abis/ (see
scripts/sync_abis.py) so the backend never needs the contracts/ checkout at runtime --
only the ABI, not the bytecode, since it only ever calls already-deployed contracts.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any


@cache
def load_abi(contract_name: str) -> list[dict[str, Any]]:
    raw = resources.files("app.chain.abis").joinpath(f"{contract_name}.json").read_text()
    result: list[dict[str, Any]] = json.loads(raw)
    return result
