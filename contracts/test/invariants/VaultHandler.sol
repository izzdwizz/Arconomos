// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {CommonBase} from "forge-std/Base.sol";
import {StdCheats} from "forge-std/StdCheats.sol";
import {StdUtils} from "forge-std/StdUtils.sol";
import {MockUSDC} from "../../src/mocks/MockUSDC.sol";
import {Vault} from "../../src/Vault.sol";
import {Inbox} from "../../src/Inbox.sol";
import {YieldPool} from "../../src/YieldPool.sol";

/// @notice Drives a vault through the actions available to its owner and operator, in
/// pseudo-random order and amounts, so VaultInvariants can check the accounting invariants
/// still hold no matter what sequence of legal actions occurred.
contract VaultHandler is CommonBase, StdCheats, StdUtils {
    MockUSDC public usdc;
    Vault public vault;
    Inbox public incomeInbox;
    Inbox public topupInbox;
    YieldPool public yieldPool;
    address public owner;
    address public operator;

    uint256 public ghost_taxEverDecreasedByOperator;

    constructor(
        MockUSDC _usdc,
        Vault _vault,
        Inbox _incomeInbox,
        Inbox _topupInbox,
        YieldPool _yieldPool,
        address _owner,
        address _operator
    ) {
        usdc = _usdc;
        vault = _vault;
        incomeInbox = _incomeInbox;
        topupInbox = _topupInbox;
        yieldPool = _yieldPool;
        owner = _owner;
        operator = _operator;
    }

    function depositIncome(uint256 amount) public {
        amount = bound(amount, 0, 1_000_000 * 1e6);
        if (amount == 0) return;
        usdc.mint(address(incomeInbox), amount);
        incomeInbox.sweep();
    }

    function depositTransfer(uint256 amount) public {
        amount = bound(amount, 0, 1_000_000 * 1e6);
        if (amount == 0) return;
        usdc.mint(address(topupInbox), amount);
        topupInbox.sweep();
    }

    function rebalance(uint8 fromRaw, uint8 toRaw, uint256 amount) public {
        Vault.Bucket from = Vault.Bucket(fromRaw % 6);
        Vault.Bucket to = Vault.Bucket(toRaw % 6);
        uint256 balance = vault.bucketBalances(from);
        if (balance == 0) return;
        amount = bound(amount, 0, balance);

        vm.prank(operator);
        try vault.rebalance(from, to, amount, bytes32(0)) {} catch {}
    }

    function sweepToYield(uint8 bucketRaw, uint256 amount) public {
        Vault.Bucket bucket = Vault.Bucket(bucketRaw % 6);
        uint256 balance = vault.bucketBalances(bucket);
        if (balance == 0) return;
        amount = bound(amount, 0, balance);

        vm.prank(operator);
        try vault.sweepToYield(bucket, amount) {} catch {}
    }

    function redeemFromYield(uint8 bucketRaw, uint256 shares) public {
        Vault.Bucket bucket = Vault.Bucket(bucketRaw % 6);
        uint256 held = vault.bucketYieldShares(bucket);
        if (held == 0) return;
        shares = bound(shares, 0, held);

        vm.prank(operator);
        try vault.redeemFromYield(bucket, shares) {} catch {}
    }

    function adjustSplitAsOperator(uint256 seed) public {
        uint256[6] memory bps = vault.getSplitBps();
        uint256 i = seed % 6;
        uint256 j = (seed / 6) % 6;
        if (i == j) return;
        uint256 delta = bound(seed, 0, 200);
        if (bps[i] < delta) return;

        bps[i] -= delta;
        bps[j] += delta;

        vm.prank(operator);
        try vault.adjustSplit(bps, bytes32(0)) {} catch {}
    }

    function payOwner(uint256 amount) public {
        amount = bound(amount, 0, vault.bucketBalances(Vault.Bucket.Buffer));
        vm.prank(operator);
        try vault.payOwner(amount) {} catch {}
    }

    function warp(uint256 secondsForward) public {
        secondsForward = bound(secondsForward, 0, 10 days);
        vm.warp(block.timestamp + secondsForward);
    }
}
