// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {TestBase} from "./helpers/TestBase.sol";
import {Vault} from "../src/Vault.sol";

contract YieldPoolTest is TestBase {
    function test_YieldSweepAndRedeemAccounting() public {
        _depositIncome(1000 * USDC_ONE);
        uint256 billsBalance = vault.bucketBalances(Vault.Bucket.Bills);

        vm.prank(operator);
        vault.sweepToYield(Vault.Bucket.Bills, billsBalance);

        assertEq(vault.bucketBalances(Vault.Bucket.Bills), 0);
        assertGt(vault.bucketYieldShares(Vault.Bucket.Bills), 0);
        assertEq(yieldPool.valueOf(address(vault)), billsBalance);

        // Simulate yield accruing while the funds sit in the pool.
        _mintTo(address(this), 10 * USDC_ONE);
        usdc.approve(address(yieldSource), 10 * USDC_ONE);
        yieldSource.accrueYield(10 * USDC_ONE);

        uint256 shares = vault.bucketYieldShares(Vault.Bucket.Bills);
        vm.prank(operator);
        vault.redeemFromYield(Vault.Bucket.Bills, shares);

        assertEq(vault.bucketYieldShares(Vault.Bucket.Bills), 0);
        assertGt(vault.bucketBalances(Vault.Bucket.Bills), billsBalance, "should have captured yield");
    }

    function test_ValueOfUnregisteredVaultIsZero() public {
        assertEq(yieldPool.valueOf(address(0xdead)), 0);
    }

    function test_OnlyRegisteredVaultCanDeposit() public {
        vm.expectRevert("YieldPool: not registered");
        yieldPool.deposit(1);
    }
}
