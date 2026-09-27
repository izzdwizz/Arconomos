// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test} from "forge-std/Test.sol";
import {MockUSDC} from "../../src/mocks/MockUSDC.sol";
import {MockYieldSource} from "../../src/mocks/MockYieldSource.sol";
import {YieldPool} from "../../src/YieldPool.sol";
import {Vault} from "../../src/Vault.sol";
import {Inbox} from "../../src/Inbox.sol";
import {VaultFactory} from "../../src/VaultFactory.sol";

contract TestBase is Test {
    uint256 internal constant USDC_ONE = 1e6;

    MockUSDC internal usdc;
    VaultFactory internal factory;

    uint256 internal ownerPk = 0xA11CE;
    address internal owner;
    address internal operator = address(0xEF0F1CE);
    address internal payoutAddress = address(0xFEE);
    address internal admin = address(this);

    uint256 internal constant MIN_TAX_BPS = 2000;
    uint256 internal constant MAX_SPLIT_CHANGE_BPS = 1000;
    uint256 internal constant TAX_WITHDRAW_DELAY = 72 hours;
    uint256 internal constant OWNER_PAY_CAP = 500 * 1e6;
    uint256 internal constant OWNER_PAY_PERIOD = 7 days;
    uint256 internal constant BUFFER_FLOOR = 0;

    Vault internal vault;
    Inbox internal incomeInbox;
    Inbox internal topupInbox;
    YieldPool internal yieldPool;
    MockYieldSource internal yieldSource;

    function setUp() public virtual {
        owner = vm.addr(ownerPk);
        usdc = new MockUSDC();
        factory = new VaultFactory(usdc, admin);

        yieldPool = new YieldPool(usdc, admin);
        yieldSource = new MockYieldSource(usdc, address(yieldPool));
        yieldPool.setYieldSource(yieldSource);

        VaultFactory.DeployRequest memory req = VaultFactory.DeployRequest({
            user: owner,
            operator: operator,
            payoutAddress: payoutAddress,
            yieldPool: address(yieldPool),
            minTaxBps: MIN_TAX_BPS,
            maxSplitChangeBpsPerWeek: MAX_SPLIT_CHANGE_BPS,
            taxWithdrawDelay: TAX_WITHDRAW_DELAY,
            ownerPayCapPerPeriod: OWNER_PAY_CAP,
            ownerPayPeriod: OWNER_PAY_PERIOD,
            bufferFloor: BUFFER_FLOOR
        });
        (address vaultAddr, address income, address topup) = factory.deployVault(req);
        vault = Vault(vaultAddr);
        incomeInbox = Inbox(income);
        topupInbox = Inbox(topup);

        yieldPool.registerVault(address(vault));

        uint256[6] memory bps = [uint256(2000), 2000, 2000, 1500, 1500, 1000];
        vm.prank(owner);
        vault.adjustSplit(bps, bytes32("setup"));
    }

    function _mintTo(address to, uint256 amount) internal {
        usdc.mint(to, amount);
    }

    function _depositIncome(uint256 amount) internal {
        _mintTo(address(incomeInbox), amount);
        incomeInbox.sweep();
    }

    function _depositTransfer(uint256 amount) internal {
        _mintTo(address(topupInbox), amount);
        topupInbox.sweep();
    }
}
