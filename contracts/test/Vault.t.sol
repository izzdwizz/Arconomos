// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {TestBase} from "./helpers/TestBase.sol";
import {Vault} from "../src/Vault.sol";

contract VaultTest is TestBase {
    function test_AllocateIncomeAppliesSplit() public {
        // splitBps set in setUp: Tax 20, Bills 20, Goals 20, OwnerPay 15, Buffer 15, Savings 10
        _depositIncome(100 * USDC_ONE + 3); // +3 to force a rounding remainder into Buffer

        assertEq(vault.bucketBalances(Vault.Bucket.Tax), 20 * USDC_ONE);
        assertEq(vault.bucketBalances(Vault.Bucket.Bills), 20 * USDC_ONE);
        assertEq(vault.bucketBalances(Vault.Bucket.Goals), 20 * USDC_ONE);
        assertEq(vault.bucketBalances(Vault.Bucket.OwnerPay), 15 * USDC_ONE);
        assertEq(vault.bucketBalances(Vault.Bucket.Savings), 10 * USDC_ONE);
        // Buffer = 15% of 100_000003 + rounding remainder (the +3, since 3 < 10000/100 units)
        assertEq(vault.bucketBalances(Vault.Bucket.Buffer), 15 * USDC_ONE + 3);

        uint256 sum;
        uint256[6] memory balances = vault.getBucketBalances();
        for (uint256 i = 0; i < 6; i++) {
            sum += balances[i];
        }
        assertEq(sum, 100 * USDC_ONE + 3);
    }

    function test_AllocateTransferSkipsTax() public {
        _depositTransfer(100 * USDC_ONE);

        assertEq(vault.bucketBalances(Vault.Bucket.Tax), 0);
        // Tax's 20% is redirected into Buffer, on top of Buffer's own 15%: 35 USDC.
        assertEq(vault.bucketBalances(Vault.Bucket.Buffer), 35 * USDC_ONE);
    }

    function test_AllocateDirectRecordsSourceTx() public {
        _mintTo(address(vault), 42 * USDC_ONE);
        bytes32 srcTx = keccak256("some-tx");

        vm.recordLogs();
        vm.prank(operator);
        vault.allocateDirect(Vault.DepositKind.Income, 42 * USDC_ONE, srcTx);

        assertEq(vault.bucketBalances(Vault.Bucket.Tax), (42 * USDC_ONE * 2000) / 10_000);
    }

    function test_OperatorCannotWithdrawTax() public {
        _depositIncome(100 * USDC_ONE);
        vm.prank(operator);
        vm.expectRevert("Vault: operator cannot draw down Tax");
        vault.rebalance(Vault.Bucket.Tax, Vault.Bucket.Bills, 1, bytes32("x"));
    }

    function test_OperatorCannotSendToOutsider() public {
        // The operator has no function that accepts an arbitrary recipient at all:
        // withdraw() is onlyOwner, payOwner() always targets the fixed payoutAddress.
        _depositIncome(100 * USDC_ONE);
        address outsider = address(0xBADD);

        vm.prank(operator);
        vm.expectRevert();
        vault.withdraw(Vault.Bucket.Bills, 1, outsider);
    }

    function test_OperatorSplitChangeRespectsWeeklyCap() public {
        uint256[6] memory bps = vault.getSplitBps();
        bps[uint256(Vault.Bucket.Bills)] += 1001; // guardrail is 1000 bps/week
        bps[uint256(Vault.Bucket.Buffer)] -= 1001;

        vm.prank(operator);
        vm.expectRevert("Vault: exceeds weekly guardrail");
        vault.adjustSplit(bps, bytes32("plan"));
    }

    function test_OperatorSplitChangeWithinCapSucceeds() public {
        uint256[6] memory bps = vault.getSplitBps();
        bps[uint256(Vault.Bucket.Bills)] += 500;
        bps[uint256(Vault.Bucket.Buffer)] -= 500;

        vm.prank(operator);
        vault.adjustSplit(bps, bytes32("plan"));
        assertEq(vault.splitBps(uint256(Vault.Bucket.Bills)), 2500);
    }

    function test_TaxShareNeverBelowFloor() public {
        uint256[6] memory bps = vault.getSplitBps();
        bps[uint256(Vault.Bucket.Tax)] = MIN_TAX_BPS - 1;
        bps[uint256(Vault.Bucket.Buffer)] += 1;

        vm.prank(operator);
        vm.expectRevert("Vault: below tax floor");
        vault.adjustSplit(bps, bytes32("plan"));
    }

    function test_OwnerSplitChangeIgnoresGuardrails() public {
        uint256[6] memory bps = vault.getSplitBps();
        bps[uint256(Vault.Bucket.Tax)] = 0;
        bps[uint256(Vault.Bucket.Buffer)] += MIN_TAX_BPS;

        vm.prank(owner);
        vault.adjustSplit(bps, bytes32("owner override"));
        assertEq(vault.splitBps(uint256(Vault.Bucket.Tax)), 0);
    }

    function test_TaxReleaseNeedsDelay() public {
        _depositIncome(100 * USDC_ONE);

        vm.prank(owner);
        uint256 id = vault.requestTaxRelease(10 * USDC_ONE);

        vm.prank(owner);
        vm.expectRevert("Vault: still timelocked");
        vault.executeTaxRelease(id, owner);

        vm.warp(block.timestamp + TAX_WITHDRAW_DELAY);
        vm.prank(owner);
        vault.executeTaxRelease(id, owner);
        assertEq(usdc.balanceOf(owner), 10 * USDC_ONE);
    }

    function test_OwnerIntentSignatureAndNonce() public {
        _depositIncome(100 * USDC_ONE);

        bytes memory data = abi.encode(Vault.Bucket.Bills, 5 * USDC_ONE, owner);
        Vault.OwnerIntent memory intent = Vault.OwnerIntent({
            vault: address(vault),
            action: Vault.OwnerAction.Withdraw,
            data: data,
            nonce: 0,
            deadline: block.timestamp + 1 hours
        });

        bytes32 digest = _hashOwnerIntent(intent);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerPk, digest);
        bytes memory signature = abi.encodePacked(r, s, v);

        vault.executeOwnerIntent(intent, signature);
        assertEq(usdc.balanceOf(owner), 5 * USDC_ONE);

        // Replay must be rejected: nonce has already advanced.
        vm.expectRevert("Vault: bad nonce");
        vault.executeOwnerIntent(intent, signature);
    }

    function test_OwnerIntentRejectsForgedSignature() public {
        _depositIncome(100 * USDC_ONE);
        bytes memory data = abi.encode(Vault.Bucket.Bills, 5 * USDC_ONE, owner);
        Vault.OwnerIntent memory intent = Vault.OwnerIntent({
            vault: address(vault),
            action: Vault.OwnerAction.Withdraw,
            data: data,
            nonce: 0,
            deadline: block.timestamp + 1 hours
        });

        uint256 attackerPk = 0xBAD;
        bytes32 digest = _hashOwnerIntent(intent);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(attackerPk, digest);
        bytes memory signature = abi.encodePacked(r, s, v);

        vm.expectRevert("Vault: bad signature");
        vault.executeOwnerIntent(intent, signature);
    }

    function _hashOwnerIntent(Vault.OwnerIntent memory intent) internal view returns (bytes32) {
        bytes32 typehash =
            keccak256("OwnerIntent(address vault,uint8 action,bytes data,uint256 nonce,uint256 deadline)");
        bytes32 structHash = keccak256(
            abi.encode(
                typehash, intent.vault, uint8(intent.action), keccak256(intent.data), intent.nonce, intent.deadline
            )
        );
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes("OikonomosVault")),
                keccak256(bytes("1")),
                block.chainid,
                address(vault)
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
    }
}
