#!/usr/bin/env python3
"""Re-extracts ABIs from `forge build` output into app/chain/abis/, so the backend ships
its own copy and never needs the contracts/ checkout at runtime. Run after any contract
change: `cd contracts && forge build && cd ../backend && uv run python scripts/sync_abis.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_OUT = REPO_ROOT / "contracts" / "out"
DEST = Path(__file__).resolve().parents[1] / "app" / "chain" / "abis"

ARTIFACTS = {
    "Vault": "Vault.sol/Vault.json",
    "Inbox": "Inbox.sol/Inbox.json",
    "VaultFactory": "VaultFactory.sol/VaultFactory.json",
    "YieldPool": "YieldPool.sol/YieldPool.json",
    "MockUSDC": "MockUSDC.sol/MockUSDC.json",
    "MockYieldSource": "MockYieldSource.sol/MockYieldSource.json",
}


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for name, relpath in ARTIFACTS.items():
        artifact = json.loads((CONTRACTS_OUT / relpath).read_text())
        out_path = DEST / f"{name}.json"
        out_path.write_text(json.dumps(artifact["abi"], indent=2) + "\n")
        print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(artifact['abi'])} entries)")


if __name__ == "__main__":
    main()
