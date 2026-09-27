// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IYieldSource} from "../interfaces/IYieldSource.sol";

/// @notice Stands in for USYC while Circle allowlisting is pending; same interface, same accounting shape.
contract MockYieldSource is IYieldSource {
    using SafeERC20 for IERC20;

    IERC20 public immutable usdc;
    address public immutable pool;

    uint256 public totalShares;
    uint256 public totalAssets;

    modifier onlyPool() {
        require(msg.sender == pool, "MockYieldSource: not pool");
        _;
    }

    constructor(IERC20 _usdc, address _pool) {
        usdc = _usdc;
        pool = _pool;
    }

    function deposit(uint256 amount) external onlyPool returns (uint256 shares) {
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        shares = totalShares == 0 ? amount : (amount * totalShares) / totalAssets;
        totalShares += shares;
        totalAssets += amount;
    }

    function redeem(uint256 shares) external onlyPool returns (uint256 amount) {
        amount = (shares * totalAssets) / totalShares;
        totalShares -= shares;
        totalAssets -= amount;
        usdc.safeTransfer(msg.sender, amount);
    }

    function pricePerShare() external view returns (uint256) {
        return totalShares == 0 ? 1e6 : (totalAssets * 1e6) / totalShares;
    }

    /// @dev Test-only knob to simulate yield accrual between deposit and redeem.
    function accrueYield(uint256 amount) external {
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        totalAssets += amount;
    }
}
