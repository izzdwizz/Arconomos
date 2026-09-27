// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {Vault} from "./Vault.sol";
import {Inbox} from "./Inbox.sol";

/// @notice Deploys a Vault plus its two Inbox clones per user via CREATE2, so the app can show
/// deposit addresses to a user before anything is actually deployed. Called by our relayer, so
/// a brand-new user needs no gas of their own.
contract VaultFactory {
    IERC20 public immutable usdc;
    address public immutable inboxImplementation;
    address public admin;

    event VaultDeployed(address indexed owner, address vault, address incomeInbox, address topupInbox);

    modifier onlyAdmin() {
        require(msg.sender == admin, "VaultFactory: not admin");
        _;
    }

    constructor(IERC20 _usdc, address _admin) {
        usdc = _usdc;
        admin = _admin;
        inboxImplementation = address(new Inbox());
    }

    struct DeployRequest {
        address user;
        address operator;
        address payoutAddress;
        address yieldPool;
        uint256 minTaxBps;
        uint256 maxSplitChangeBpsPerWeek;
        uint256 taxWithdrawDelay;
        uint256 ownerPayCapPerPeriod;
        uint256 ownerPayPeriod;
        uint256 bufferFloor;
    }

    function predictVaultAddress(DeployRequest calldata req) external view returns (address) {
        bytes32 salt = _vaultSalt(req.user);
        bytes memory bytecode = abi.encodePacked(type(Vault).creationCode, abi.encode(_toDeployParams(req)));
        return _computeCreate2Address(salt, keccak256(bytecode));
    }

    function predictInboxAddress(address user, bool income) external view returns (address) {
        bytes32 salt = _inboxSalt(user, income);
        return Clones.predictDeterministicAddress(inboxImplementation, salt, address(this));
    }

    function deployVault(DeployRequest calldata req)
        external
        onlyAdmin
        returns (address vaultAddr, address incomeInbox, address topupInbox)
    {
        bytes32 vaultSalt = _vaultSalt(req.user);
        Vault vault = new Vault{salt: vaultSalt}(_toDeployParams(req));
        vaultAddr = address(vault);

        incomeInbox = Clones.cloneDeterministic(inboxImplementation, _inboxSalt(req.user, true));
        topupInbox = Clones.cloneDeterministic(inboxImplementation, _inboxSalt(req.user, false));

        Inbox(incomeInbox).initialize(usdc, vault, req.user, Vault.DepositKind.Income);
        Inbox(topupInbox).initialize(usdc, vault, req.user, Vault.DepositKind.Transfer);

        vault.setInboxes(incomeInbox, topupInbox);

        emit VaultDeployed(req.user, vaultAddr, incomeInbox, topupInbox);
    }

    function _toDeployParams(DeployRequest calldata req) internal view returns (Vault.DeployParams memory) {
        return Vault.DeployParams({
            usdc: usdc,
            owner: req.user,
            operator: req.operator,
            payoutAddress: req.payoutAddress,
            yieldPool: req.yieldPool,
            minTaxBps: req.minTaxBps,
            maxSplitChangeBpsPerWeek: req.maxSplitChangeBpsPerWeek,
            taxWithdrawDelay: req.taxWithdrawDelay,
            ownerPayCapPerPeriod: req.ownerPayCapPerPeriod,
            ownerPayPeriod: req.ownerPayPeriod,
            bufferFloor: req.bufferFloor
        });
    }

    function _vaultSalt(address user) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("vault", user));
    }

    function _inboxSalt(address user, bool income) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("inbox", user, income));
    }

    function _computeCreate2Address(bytes32 salt, bytes32 bytecodeHash) internal view returns (address) {
        return address(uint160(uint256(keccak256(abi.encodePacked(bytes1(0xff), address(this), salt, bytecodeHash)))));
    }
}
