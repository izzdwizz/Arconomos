// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @notice Behind this interface: USYC on testnet/mainnet, or MockYieldSource in tests.
interface IYieldSource {
    function deposit(uint256 usdcAmount) external returns (uint256 sharesMinted);
    function redeem(uint256 shares) external returns (uint256 usdcAmount);
    /// @dev USDC value of one share, scaled by 1e6.
    function pricePerShare() external view returns (uint256);
}
