// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {TestBase} from "./helpers/TestBase.sol";
import {Vault} from "../src/Vault.sol";

contract InboxTest is TestBase {
    function test_InboxSweepTagsIncome() public {
        _mintTo(address(incomeInbox), 100 * USDC_ONE);
        incomeInbox.sweep();

        // 20% tax on 100 USDC = 20 USDC, and Transfer-only skip does NOT apply.
        assertEq(vault.bucketBalances(Vault.Bucket.Tax), 20 * USDC_ONE);
        assertEq(usdc.balanceOf(address(incomeInbox)), 0);
    }

    function test_InboxSweepTagsTransfer() public {
        _mintTo(address(topupInbox), 100 * USDC_ONE);
        topupInbox.sweep();

        // Transfers skip tax entirely; that share is redirected to Buffer.
        assertEq(vault.bucketBalances(Vault.Bucket.Tax), 0);
        assertEq(usdc.balanceOf(address(topupInbox)), 0);
    }

    function test_SweepOfEmptyInboxIsNoop() public {
        uint256 amount = incomeInbox.sweep();
        assertEq(amount, 0);
    }

    function test_KindChangeTakesEffectAfterDelay() public {
        vm.prank(owner);
        topupInbox.scheduleKindChange(Vault.DepositKind.Income);

        _mintTo(address(topupInbox), 50 * USDC_ONE);
        topupInbox.sweep();
        assertEq(vault.bucketBalances(Vault.Bucket.Tax), 0, "kind change should not be effective yet");

        vm.warp(block.timestamp + 31 days);
        _mintTo(address(topupInbox), 50 * USDC_ONE);
        topupInbox.sweep();
        assertGt(vault.bucketBalances(Vault.Bucket.Tax), 0, "kind change should be effective now");
    }
}
