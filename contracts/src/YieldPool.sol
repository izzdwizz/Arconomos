// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IYieldSource} from "./interfaces/IYieldSource.sol";

/// @notice One pool for every vault's USYC exposure: USYC only allowlists a handful of
/// addresses on testnet, so vaults share this pool instead of each seeking its own allowlisting.
contract YieldPool {
    using SafeERC20 for IERC20;

    IERC20 public immutable usdc;
    IYieldSource public source;
    address public admin;

    mapping(address => bool) public registeredVaults;
    mapping(address => uint256) public sharesOf;
    uint256 public totalShares;

    event YieldSourceUpdated(address indexed source);
    event VaultRegistered(address indexed vault);
    event YieldDeposited(address indexed vault, uint256 usdcAmount, uint256 shares);
    event YieldRedeemed(address indexed vault, uint256 usdcAmount, uint256 shares);

    modifier onlyAdmin() {
        require(msg.sender == admin, "YieldPool: not admin");
        _;
    }

    modifier onlyRegistered() {
        require(registeredVaults[msg.sender], "YieldPool: not registered");
        _;
    }

    constructor(IERC20 _usdc, address _admin) {
        usdc = _usdc;
        admin = _admin;
    }

    function setYieldSource(IYieldSource _source) external onlyAdmin {
        source = _source;
        emit YieldSourceUpdated(address(_source));
    }

    function registerVault(address vault) external onlyAdmin {
        registeredVaults[vault] = true;
        emit VaultRegistered(vault);
    }

    function deposit(uint256 amount) external onlyRegistered returns (uint256 shares) {
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        usdc.forceApprove(address(source), amount);
        shares = source.deposit(amount);
        sharesOf[msg.sender] += shares;
        totalShares += shares;
        emit YieldDeposited(msg.sender, amount, shares);
    }

    function redeem(uint256 shares) external onlyRegistered returns (uint256 amount) {
        require(sharesOf[msg.sender] >= shares, "YieldPool: insufficient shares");
        amount = source.redeem(shares);
        sharesOf[msg.sender] -= shares;
        totalShares -= shares;
        usdc.safeTransfer(msg.sender, amount);
        emit YieldRedeemed(msg.sender, amount, shares);
    }

    function valueOf(address vault) external view returns (uint256) {
        uint256 shares = sharesOf[vault];
        if (shares == 0) return 0;
        return (shares * source.pricePerShare()) / 1e6;
    }
}
