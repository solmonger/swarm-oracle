// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {CalibrationRegistry} from "./CalibrationRegistry.sol";

/**
 * @title AgentIdentity
 * @notice Soulbound ERC-721 token representing an AI agent's on-chain identity.
 *         Non-transferable by design — reputation is earned, not bought.
 *
 *         Each token stores:
 *           - Agent name/label (set at mint)
 *           - Link to CalibrationRegistry for live stats
 *           - Creation timestamp
 *           - Metadata URI (IPFS or data URI for off-chain display)
 *
 *         Implements a minimal ERC-721 interface (balanceOf, ownerOf, tokenURI)
 *         but BLOCKS all transfer functions (approve, transferFrom, etc.).
 *
 * @dev    This is a hackathon-scope soulbound token. A production version
 *         would use ERC-5192 (Minimal Soulbound Interface) and ERC-4906
 *         (Metadata Update Extension).
 */
contract AgentIdentity {
    // -----------------------------------------------------------------------
    // ERC-721 metadata
    // -----------------------------------------------------------------------

    // ERC-721 metadata fields (lowercase to match ERC-721 interface).
    // Lint exception: the ERC-721 spec mandates these exact identifiers, so
    // SCREAMING_SNAKE_CASE would break interface conformance.
    // solhint-disable-next-line const-name-snakecase
    string public constant NAME = "Swarm Oracle Agent";
    // solhint-disable-next-line const-name-snakecase
    string public constant SYMBOL = "SWARM-AGENT";

    /// @notice ERC-721 compatibility getters (lower-case as required by spec).
    function name() external pure returns (string memory) { return NAME; }
    function symbol() external pure returns (string memory) { return SYMBOL; }

    // -----------------------------------------------------------------------
    // Storage
    // -----------------------------------------------------------------------

    CalibrationRegistry public immutable REGISTRY;
    address public owner;

    struct AgentToken {
        address agentAddress;     // The agent's identity address
        string  label;            // Human-readable name (e.g., "agent-oracle")
        string  metadataURI;      // Optional IPFS/data URI
        uint256 mintedAt;         // block.timestamp
        bool    exists;
    }

    /// @notice tokenId → token data
    mapping(uint256 => AgentToken) public tokens;

    /// @notice agentAddress → tokenId (one token per agent)
    mapping(address => uint256) public agentToToken;

    /// @notice address → number of tokens owned (always 0 or 1 per agent)
    mapping(address => uint256) private _balances;

    uint256 public totalSupply;
    uint256 private _nextTokenId;

    // -----------------------------------------------------------------------
    // Events (ERC-721 compatible)
    // -----------------------------------------------------------------------

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event AgentMinted(uint256 indexed tokenId, address indexed agent, string label);
    event MetadataUpdated(uint256 indexed tokenId, string newURI);

    // -----------------------------------------------------------------------
    // Modifiers
    // -----------------------------------------------------------------------

    modifier onlyOwner() {
        _onlyOwner();
        _;
    }

    function _onlyOwner() internal view {
        require(msg.sender == owner, "AgentIdentity: not owner");
    }

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    constructor(address _registry) {
        REGISTRY = CalibrationRegistry(_registry);
        owner = msg.sender;
        _nextTokenId = 1;  // Token IDs start at 1
    }

    // -----------------------------------------------------------------------
    // Mint — create a new agent identity token
    // -----------------------------------------------------------------------

    /**
     * @notice Mint a soulbound token for an agent.
     * @param agentAddress  The agent's on-chain identity address.
     * @param label         Human-readable label (e.g., "agent-oracle").
     * @param metadataURI   Optional URI for off-chain metadata.
     * @return tokenId      The newly minted token's ID.
     */
    function mint(
        address agentAddress,
        string calldata label,
        string calldata metadataURI
    ) external onlyOwner returns (uint256 tokenId) {
        require(agentAddress != address(0), "AgentIdentity: zero address");
        require(agentToToken[agentAddress] == 0, "AgentIdentity: already minted");

        tokenId = _nextTokenId++;
        totalSupply++;

        tokens[tokenId] = AgentToken({
            agentAddress: agentAddress,
            label: label,
            metadataURI: metadataURI,
            mintedAt: block.timestamp,
            exists: true
        });

        agentToToken[agentAddress] = tokenId;
        _balances[agentAddress] = 1;

        emit Transfer(address(0), agentAddress, tokenId);
        emit AgentMinted(tokenId, agentAddress, label);
    }

    /**
     * @notice Batch mint for multiple agents.
     */
    function mintBatch(
        address[] calldata agentAddresses,
        string[] calldata labels,
        string[] calldata metadataUris
    ) external onlyOwner returns (uint256[] memory tokenIds) {
        require(
            agentAddresses.length == labels.length &&
            labels.length == metadataUris.length,
            "AgentIdentity: length mismatch"
        );

        tokenIds = new uint256[](agentAddresses.length);
        for (uint256 i = 0; i < agentAddresses.length; i++) {
            require(agentAddresses[i] != address(0), "AgentIdentity: zero address");
            require(agentToToken[agentAddresses[i]] == 0, "AgentIdentity: already minted");

            uint256 tokenId = _nextTokenId++;
            totalSupply++;

            tokens[tokenId] = AgentToken({
                agentAddress: agentAddresses[i],
                label: labels[i],
                metadataURI: metadataUris[i],
                mintedAt: block.timestamp,
                exists: true
            });

            agentToToken[agentAddresses[i]] = tokenId;
            _balances[agentAddresses[i]] = 1;

            emit Transfer(address(0), agentAddresses[i], tokenId);
            emit AgentMinted(tokenId, agentAddresses[i], labels[i]);

            tokenIds[i] = tokenId;
        }
    }

    // -----------------------------------------------------------------------
    // Update metadata
    // -----------------------------------------------------------------------

    function updateMetadata(uint256 tokenId, string calldata newURI) external onlyOwner {
        require(tokens[tokenId].exists, "AgentIdentity: nonexistent token");
        tokens[tokenId].metadataURI = newURI;
        emit MetadataUpdated(tokenId, newURI);
    }

    // -----------------------------------------------------------------------
    // ERC-721 read interface (minimal)
    // -----------------------------------------------------------------------

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    function ownerOf(uint256 tokenId) external view returns (address) {
        require(tokens[tokenId].exists, "AgentIdentity: nonexistent token");
        return tokens[tokenId].agentAddress;
    }

    function tokenURI(uint256 tokenId) external view returns (string memory) {
        require(tokens[tokenId].exists, "AgentIdentity: nonexistent token");
        AgentToken storage t = tokens[tokenId];

        // If a custom URI is set, return it
        if (bytes(t.metadataURI).length > 0) {
            return t.metadataURI;
        }

        // Otherwise generate a minimal on-chain JSON
        // (Production would use Base64-encoded JSON with SVG image)
        return string(abi.encodePacked(
            '{"name":"', t.label,
            '","description":"Swarm Oracle Agent Identity (Soulbound)"',
            ',"attributes":[{"trait_type":"Agent Address","value":"',
            _toHexString(t.agentAddress),
            '"}]}'
        ));
    }

    /**
     * @notice Get full agent profile: token data + live calibration stats.
     */
    function getAgentProfile(address agentAddress)
        external
        view
        returns (
            uint256 tokenId,
            string memory label,
            uint256 mintedAt,
            uint256 brierScore,
            uint256 numPredictions,
            uint256 calibrationWeight,
            bool hasToken,
            bool registeredInCalibration
        )
    {
        tokenId = agentToToken[agentAddress];
        hasToken = tokens[tokenId].exists;

        if (hasToken) {
            label = tokens[tokenId].label;
            mintedAt = tokens[tokenId].mintedAt;
        }

        // Pull live stats from CalibrationRegistry
        (brierScore, numPredictions, , registeredInCalibration) = REGISTRY.getAgent(agentAddress);
        calibrationWeight = REGISTRY.computeWeight(agentAddress);
    }

    // -----------------------------------------------------------------------
    // SOULBOUND — block all transfers
    // -----------------------------------------------------------------------

    /**
     * @notice BLOCKED. Soulbound tokens cannot be transferred.
     */
    function transferFrom(address, address, uint256) external pure {
        revert("AgentIdentity: soulbound, transfer blocked");
    }

    function safeTransferFrom(address, address, uint256) external pure {
        revert("AgentIdentity: soulbound, transfer blocked");
    }

    function safeTransferFrom(address, address, uint256, bytes calldata) external pure {
        revert("AgentIdentity: soulbound, transfer blocked");
    }

    function approve(address, uint256) external pure {
        revert("AgentIdentity: soulbound, approval blocked");
    }

    function setApprovalForAll(address, bool) external pure {
        revert("AgentIdentity: soulbound, approval blocked");
    }

    function getApproved(uint256) external pure returns (address) {
        return address(0);
    }

    function isApprovedForAll(address, address) external pure returns (bool) {
        return false;
    }

    // -----------------------------------------------------------------------
    // ERC-165 — interface detection
    // -----------------------------------------------------------------------

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return
            interfaceId == 0x80ac58cd ||  // ERC-721
            interfaceId == 0x01ffc9a7;     // ERC-165
    }

    // -----------------------------------------------------------------------
    // Internal helpers
    // -----------------------------------------------------------------------

    function _toHexString(address addr) internal pure returns (string memory) {
        bytes memory alphabet = "0123456789abcdef";
        bytes20 data = bytes20(addr);
        bytes memory str = new bytes(42);
        str[0] = "0";
        str[1] = "x";
        for (uint256 i = 0; i < 20; i++) {
            str[2 + i * 2] = alphabet[uint8(data[i] >> 4)];
            str[3 + i * 2] = alphabet[uint8(data[i] & 0x0f)];
        }
        return string(str);
    }
}
