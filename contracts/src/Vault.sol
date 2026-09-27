// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {YieldPool} from "./YieldPool.sol";

/// @notice Holds one user's USDC. The owner is the user's wallet; the operator is the
/// Oikonomos agent. The operator's powers are enforced here, not just in the agent's prompt:
/// it can never touch Tax, and it can never move USDC anywhere but the vault's own buckets,
/// the registered yield pool, or the owner's fixed payout address.
contract Vault is EIP712 {
    using SafeERC20 for IERC20;

    enum Bucket {
        Tax,
        Bills,
        Goals,
        OwnerPay,
        Buffer,
        Savings
    }

    enum DepositKind {
        Transfer,
        Income
    }

    uint256 public constant NUM_BUCKETS = 6;
    uint256 public constant BPS_DENOM = 10_000;
    uint256 public constant GUARDRAIL_WINDOW = 7 days;

    bytes32 private constant OWNER_INTENT_TYPEHASH =
        keccak256("OwnerIntent(address vault,uint8 action,bytes data,uint256 nonce,uint256 deadline)");

    enum OwnerAction {
        Withdraw,
        AdjustSplit,
        RequestTaxRelease
    }

    struct OwnerIntent {
        address vault;
        OwnerAction action;
        bytes data;
        uint256 nonce;
        uint256 deadline;
    }

    struct TaxRelease {
        uint256 amount;
        uint256 unlockAt;
        bool executed;
    }

    IERC20 public immutable usdc;
    address public immutable factory;
    address public owner;
    address public operator;
    address public payoutAddress;
    address public yieldPool;

    bool public paused;

    address public incomeInbox;
    address public topupInbox;

    uint256[NUM_BUCKETS] public splitBps;
    mapping(Bucket => uint256) public bucketBalances;
    mapping(Bucket => uint256) public bucketYieldShares;
    uint256 public unallocated;

    uint256 public minTaxBps;
    uint256 public maxSplitChangeBpsPerWeek;
    uint256 public taxWithdrawDelay;

    uint256 public guardrailWindowStart;
    uint256[NUM_BUCKETS] public guardrailCumulativeChange;

    uint256 public ownerPayCapPerPeriod;
    uint256 public ownerPayPeriod;
    uint256 public lastOwnerPayAt;
    uint256 public bufferFloor;

    mapping(uint256 => TaxRelease) public taxReleases;
    uint256 public taxReleaseNonce;
    uint256 public ownerIntentNonce;
    uint256 public depositNonce;

    event Deposited(address indexed inbox, DepositKind kind, uint256 amount, bytes32 srcTx);
    event Allocated(uint256 indexed depositId, DepositKind kind, uint256[NUM_BUCKETS] bucketAmounts);
    event SplitChanged(uint256[NUM_BUCKETS] oldBps, uint256[NUM_BUCKETS] newBps, address by);
    event Rebalanced(Bucket indexed from, Bucket indexed to, uint256 amount, bytes32 reasonHash);
    event YieldMoved(Bucket indexed bucket, uint256 usdcAmount, uint256 shares, bool toYield);
    event OwnerPaid(uint256 amount, uint256 period);
    event TaxReleaseRequested(uint256 indexed id, uint256 amount, uint256 unlockAt);
    event TaxReleased(uint256 indexed id, uint256 amount, address to);
    event OperatorChanged(address indexed newOperator);
    event Paused(bool paused);

    modifier onlyOwner() {
        require(msg.sender == owner, "Vault: not owner");
        _;
    }

    modifier onlyOperator() {
        require(msg.sender == operator, "Vault: not operator");
        _;
    }

    modifier onlyOwnerOrOperator() {
        require(msg.sender == owner || msg.sender == operator, "Vault: not owner or operator");
        _;
    }

    modifier onlyInbox() {
        require(msg.sender == incomeInbox || msg.sender == topupInbox, "Vault: not inbox");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Vault: paused");
        _;
    }

    /// @dev Owner-pay settings and the yield pool are also constructor args, not left as
    /// post-deploy onlyOwner calls, so the whole setup wizard needs zero gas from the
    /// user: everything the user configures at setup is known before this call, and the
    /// factory (our relayer) is the one paying to deploy.
    struct DeployParams {
        IERC20 usdc;
        address owner;
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

    constructor(DeployParams memory params) EIP712("OikonomosVault", "1") {
        usdc = params.usdc;
        factory = msg.sender;
        owner = params.owner;
        operator = params.operator;
        payoutAddress = params.payoutAddress;
        yieldPool = params.yieldPool;
        minTaxBps = params.minTaxBps;
        maxSplitChangeBpsPerWeek = params.maxSplitChangeBpsPerWeek;
        taxWithdrawDelay = params.taxWithdrawDelay;
        ownerPayCapPerPeriod = params.ownerPayCapPerPeriod;
        ownerPayPeriod = params.ownerPayPeriod;
        bufferFloor = params.bufferFloor;
        guardrailWindowStart = block.timestamp;

        splitBps[uint256(Bucket.Tax)] = params.minTaxBps;
        splitBps[uint256(Bucket.Buffer)] = BPS_DENOM - params.minTaxBps;
    }

    function setInboxes(address _incomeInbox, address _topupInbox) external {
        require(msg.sender == owner || msg.sender == factory, "Vault: not owner or factory");
        require(incomeInbox == address(0) && topupInbox == address(0), "Vault: inboxes set");
        incomeInbox = _incomeInbox;
        topupInbox = _topupInbox;
    }

    function setYieldPool(address _yieldPool) external onlyOwner {
        yieldPool = _yieldPool;
    }

    // ---------------------------------------------------------------------
    // Deposits
    // ---------------------------------------------------------------------

    /// @dev Called by an Inbox after it has already forwarded its USDC balance here.
    function notifyDeposit(DepositKind kind, uint256 amount, bytes32 srcTx) external onlyInbox whenNotPaused {
        emit Deposited(msg.sender, kind, amount, srcTx);
        _allocate(kind, amount);
    }

    /// @notice Direct-to-vault deposits arrive untagged; the operator allocates them per the
    /// user's rules (known-source, then default), recording the source tx for an audit trail.
    function allocateDirect(DepositKind kind, uint256 amount, bytes32 srcTx) external onlyOperator whenNotPaused {
        syncUnallocated();
        require(amount <= unallocated, "Vault: exceeds unallocated");
        unallocated -= amount;
        emit Deposited(address(0), kind, amount, srcTx);
        _allocate(kind, amount);
    }

    /// @notice Anyone may sync `unallocated` up to the vault's true untracked USDC balance.
    function syncUnallocated() public {
        uint256 tracked = unallocated + _sumBuckets();
        uint256 balance = usdc.balanceOf(address(this));
        if (balance > tracked) {
            unallocated += balance - tracked;
        }
    }

    function _allocate(DepositKind kind, uint256 amount) internal {
        uint256[NUM_BUCKETS] memory bps = splitBps;
        if (kind == DepositKind.Transfer) {
            bps[uint256(Bucket.Buffer)] += bps[uint256(Bucket.Tax)];
            bps[uint256(Bucket.Tax)] = 0;
        }

        uint256[NUM_BUCKETS] memory amounts;
        uint256 assigned;
        for (uint256 i = 0; i < NUM_BUCKETS; i++) {
            if (i == uint256(Bucket.Buffer)) continue;
            uint256 a = (amount * bps[i]) / BPS_DENOM;
            amounts[i] = a;
            assigned += a;
        }
        amounts[uint256(Bucket.Buffer)] = amount - assigned;

        for (uint256 i = 0; i < NUM_BUCKETS; i++) {
            bucketBalances[Bucket(i)] += amounts[i];
        }

        depositNonce++;
        emit Allocated(depositNonce, kind, amounts);
    }

    function _sumBuckets() internal view returns (uint256 total) {
        for (uint256 i = 0; i < NUM_BUCKETS; i++) {
            total += bucketBalances[Bucket(i)];
        }
    }

    // ---------------------------------------------------------------------
    // Splits and rebalancing
    // ---------------------------------------------------------------------

    function adjustSplit(
        uint256[NUM_BUCKETS] calldata newBps,
        bytes32 /* reasonHash */
    )
        external
        onlyOwnerOrOperator
    {
        _adjustSplit(newBps, msg.sender == operator);
    }

    function _adjustSplit(uint256[NUM_BUCKETS] memory newBps, bool isOperator) internal {
        uint256 sum;
        for (uint256 i = 0; i < NUM_BUCKETS; i++) {
            sum += newBps[i];
        }
        require(sum == BPS_DENOM, "Vault: split must sum to 10000");

        if (isOperator) {
            require(newBps[uint256(Bucket.Tax)] >= minTaxBps, "Vault: below tax floor");
            _rollGuardrailWindow();
            for (uint256 i = 0; i < NUM_BUCKETS; i++) {
                uint256 diff = newBps[i] > splitBps[i] ? newBps[i] - splitBps[i] : splitBps[i] - newBps[i];
                guardrailCumulativeChange[i] += diff;
                require(guardrailCumulativeChange[i] <= maxSplitChangeBpsPerWeek, "Vault: exceeds weekly guardrail");
            }
        }

        uint256[NUM_BUCKETS] memory oldBps = splitBps;
        splitBps = newBps;
        emit SplitChanged(oldBps, newBps, msg.sender);
    }

    function _rollGuardrailWindow() internal {
        if (block.timestamp >= guardrailWindowStart + GUARDRAIL_WINDOW) {
            guardrailWindowStart = block.timestamp;
            delete guardrailCumulativeChange;
        }
    }

    function rebalance(Bucket from, Bucket to, uint256 amount, bytes32 reasonHash) external onlyOwnerOrOperator {
        if (msg.sender == operator) {
            require(from != Bucket.Tax, "Vault: operator cannot draw down Tax");
        }
        require(bucketBalances[from] >= amount, "Vault: insufficient bucket balance");
        bucketBalances[from] -= amount;
        bucketBalances[to] += amount;
        emit Rebalanced(from, to, amount, reasonHash);
    }

    // ---------------------------------------------------------------------
    // Yield
    // ---------------------------------------------------------------------

    function sweepToYield(Bucket bucket, uint256 amount) external onlyOwnerOrOperator {
        require(yieldPool != address(0), "Vault: no yield pool");
        require(bucketBalances[bucket] >= amount, "Vault: insufficient bucket balance");
        bucketBalances[bucket] -= amount;
        usdc.forceApprove(yieldPool, amount);
        uint256 shares = YieldPool(yieldPool).deposit(amount);
        bucketYieldShares[bucket] += shares;
        emit YieldMoved(bucket, amount, shares, true);
    }

    function redeemFromYield(Bucket bucket, uint256 shares) external onlyOwnerOrOperator {
        require(yieldPool != address(0), "Vault: no yield pool");
        require(bucketYieldShares[bucket] >= shares, "Vault: insufficient yield shares");
        bucketYieldShares[bucket] -= shares;
        uint256 amount = YieldPool(yieldPool).redeem(shares);
        bucketBalances[bucket] += amount;
        emit YieldMoved(bucket, amount, shares, false);
    }

    // ---------------------------------------------------------------------
    // Owner pay
    // ---------------------------------------------------------------------

    function setOwnerPaySettings(uint256 cap, uint256 period, uint256 _bufferFloor) external onlyOwner {
        ownerPayCapPerPeriod = cap;
        ownerPayPeriod = period;
        bufferFloor = _bufferFloor;
    }

    function payOwner(uint256 amount) external onlyOperator whenNotPaused {
        require(block.timestamp >= lastOwnerPayAt + ownerPayPeriod, "Vault: pay period not elapsed");
        require(amount <= ownerPayCapPerPeriod, "Vault: exceeds pay cap");
        require(bucketBalances[Bucket.Buffer] >= amount, "Vault: insufficient buffer");
        require(bucketBalances[Bucket.Buffer] - amount >= bufferFloor, "Vault: breaches buffer floor");

        bucketBalances[Bucket.Buffer] -= amount;
        lastOwnerPayAt = block.timestamp;
        usdc.safeTransfer(payoutAddress, amount);
        emit OwnerPaid(amount, ownerPayPeriod);
    }

    // ---------------------------------------------------------------------
    // Withdrawals
    // ---------------------------------------------------------------------

    function withdraw(Bucket bucket, uint256 amount, address to) external onlyOwner {
        require(bucket != Bucket.Tax, "Vault: use tax release for Tax");
        _withdraw(bucket, amount, to);
    }

    function _withdraw(Bucket bucket, uint256 amount, address to) internal {
        require(bucketBalances[bucket] >= amount, "Vault: insufficient bucket balance");
        bucketBalances[bucket] -= amount;
        usdc.safeTransfer(to, amount);
    }

    function requestTaxRelease(uint256 amount) external onlyOwner returns (uint256 id) {
        id = _requestTaxRelease(amount);
    }

    function _requestTaxRelease(uint256 amount) internal returns (uint256 id) {
        require(bucketBalances[Bucket.Tax] >= amount, "Vault: insufficient tax balance");
        id = taxReleaseNonce++;
        uint256 unlockAt = block.timestamp + taxWithdrawDelay;
        taxReleases[id] = TaxRelease({amount: amount, unlockAt: unlockAt, executed: false});
        emit TaxReleaseRequested(id, amount, unlockAt);
    }

    function executeTaxRelease(uint256 id, address to) external onlyOwner {
        TaxRelease storage release = taxReleases[id];
        require(!release.executed, "Vault: already executed");
        require(block.timestamp >= release.unlockAt, "Vault: still timelocked");
        require(bucketBalances[Bucket.Tax] >= release.amount, "Vault: insufficient tax balance");

        release.executed = true;
        bucketBalances[Bucket.Tax] -= release.amount;
        usdc.safeTransfer(to, release.amount);
        emit TaxReleased(id, release.amount, to);
    }

    // ---------------------------------------------------------------------
    // Admin
    // ---------------------------------------------------------------------

    function setGuardrails(uint256 _minTaxBps, uint256 _maxSplitChangeBpsPerWeek) external onlyOwner {
        require(splitBps[uint256(Bucket.Tax)] >= _minTaxBps, "Vault: current tax below new floor");
        minTaxBps = _minTaxBps;
        maxSplitChangeBpsPerWeek = _maxSplitChangeBpsPerWeek;
    }

    function setPayoutAddress(address _payoutAddress) external onlyOwner {
        payoutAddress = _payoutAddress;
    }

    function setOperator(address _operator) external onlyOwner {
        operator = _operator;
        emit OperatorChanged(_operator);
    }

    function setPaused(bool _paused) external onlyOwner {
        paused = _paused;
        emit Paused(_paused);
    }

    // ---------------------------------------------------------------------
    // Owner intents (EIP-712, relayer-submitted so the owner never needs gas)
    // ---------------------------------------------------------------------

    function executeOwnerIntent(OwnerIntent calldata intent, bytes calldata signature) external {
        require(block.timestamp <= intent.deadline, "Vault: intent expired");
        require(intent.vault == address(this), "Vault: wrong vault");
        require(intent.nonce == ownerIntentNonce, "Vault: bad nonce");

        bytes32 structHash = keccak256(
            abi.encode(
                OWNER_INTENT_TYPEHASH,
                intent.vault,
                uint8(intent.action),
                keccak256(intent.data),
                intent.nonce,
                intent.deadline
            )
        );
        address signer = ECDSA.recover(_hashTypedDataV4(structHash), signature);
        require(signer == owner, "Vault: bad signature");
        ownerIntentNonce++;

        if (intent.action == OwnerAction.Withdraw) {
            (Bucket bucket, uint256 amount, address to) = abi.decode(intent.data, (Bucket, uint256, address));
            require(bucket != Bucket.Tax, "Vault: use tax release for Tax");
            _withdraw(bucket, amount, to);
        } else if (intent.action == OwnerAction.AdjustSplit) {
            uint256[NUM_BUCKETS] memory newBps = abi.decode(intent.data, (uint256[6]));
            _adjustSplit(newBps, false);
        } else if (intent.action == OwnerAction.RequestTaxRelease) {
            uint256 amount = abi.decode(intent.data, (uint256));
            _requestTaxRelease(amount);
        } else {
            revert("Vault: unknown action");
        }
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    function getSplitBps() external view returns (uint256[NUM_BUCKETS] memory) {
        return splitBps;
    }

    function getBucketBalances() external view returns (uint256[NUM_BUCKETS] memory balances) {
        for (uint256 i = 0; i < NUM_BUCKETS; i++) {
            balances[i] = bucketBalances[Bucket(i)];
        }
    }

    function totalOwnedUsdc() external view returns (uint256) {
        uint256 yieldValue = yieldPool == address(0) ? 0 : YieldPool(yieldPool).valueOf(address(this));
        return _sumBuckets() + unallocated + yieldValue;
    }
}
