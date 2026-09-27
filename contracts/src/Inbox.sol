// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Vault} from "./Vault.sol";

/// @notice Deployed as a minimal proxy clone per user (income and top-up). Anyone can call
/// `sweep()`; the tag it forwards with is fixed at creation, so it can't be spoofed by whoever
/// calls sweep. Kind changes take effect at the start of the next period, never mid-flight.
contract Inbox {
    using SafeERC20 for IERC20;

    uint256 public constant KIND_CHANGE_DELAY = 30 days;

    IERC20 public usdc;
    Vault public vault;
    address public owner;
    Vault.DepositKind public kind;
    bool private initialized;

    bool public hasPendingKindChange;
    Vault.DepositKind public pendingKind;
    uint256 public pendingKindEffectiveAt;

    event Swept(uint256 amount, Vault.DepositKind kind);
    event KindChangeScheduled(Vault.DepositKind newKind, uint256 effectiveAt);
    event KindChangeApplied(Vault.DepositKind newKind);

    modifier onlyOwner() {
        require(msg.sender == owner, "Inbox: not owner");
        _;
    }

    function initialize(IERC20 _usdc, Vault _vault, address _owner, Vault.DepositKind _kind) external {
        require(!initialized, "Inbox: already initialized");
        initialized = true;
        usdc = _usdc;
        vault = _vault;
        owner = _owner;
        kind = _kind;
    }

    function sweep() external returns (uint256 amount) {
        _applyPendingKindChangeIfDue();
        amount = usdc.balanceOf(address(this));
        if (amount == 0) return 0;
        usdc.safeTransfer(address(vault), amount);
        vault.notifyDeposit(kind, amount, bytes32(0));
        emit Swept(amount, kind);
    }

    function scheduleKindChange(Vault.DepositKind newKind) external onlyOwner {
        hasPendingKindChange = true;
        pendingKind = newKind;
        pendingKindEffectiveAt = block.timestamp + KIND_CHANGE_DELAY;
        emit KindChangeScheduled(newKind, pendingKindEffectiveAt);
    }

    function _applyPendingKindChangeIfDue() internal {
        if (hasPendingKindChange && block.timestamp >= pendingKindEffectiveAt) {
            kind = pendingKind;
            hasPendingKindChange = false;
            emit KindChangeApplied(kind);
        }
    }
}
