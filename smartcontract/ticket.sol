// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "@openzeppelin/contracts/utils/Strings.sol";

/// @title TicketNFT - ERC721 compliant ticket contract
/// @notice Each ticket is represented as a unique NFT.
contract TicketNFT is ERC721, Ownable {
    using Counters for Counters.Counter;
    using Strings for uint256;

    Counters.Counter private _tokenIdCounter;

    struct TicketData {
        uint256 eventId;
        string eventName;
        string date;
        string venue;
        string seatNumber;
        string metadataURI; // Optional: IPFS/HTTP JSON metadata URI
    }

    struct Ticket {
        uint256 eventId;
        address owner;
        bool isUsed; // Redemption flag
    }

    // tokenId => ticket payload
    mapping(uint256 => TicketData) public ticketInfo;
    // tokenId => core ticket state for business logic
    mapping(uint256 => Ticket) public tickets;
    string private _baseTokenURI;

    event TicketMinted(
        uint256 indexed tokenId,
        address indexed to,
        uint256 indexed eventId,
        string eventName,
        string date,
        string venue,
        string seatNumber
    );
    event TicketVerified(
        uint256 indexed tokenId,
        address indexed owner,
        uint256 indexed eventId,
        bool isUsed,
        bool isValid
    );
    event TicketRedeemed(uint256 indexed tokenId, address indexed owner, uint256 indexed eventId);
    event BaseURIUpdated(string baseURI);

    constructor() ERC721("TicketNFT", "TNFT") Ownable() {}

    function _mintTicketInternal(
        address to,
        uint256 eventId,
        string memory eventName,
        string memory date,
        string memory venue,
        string memory seatNumber,
        string memory metadataURI
    ) internal returns (uint256 tokenId) {
        require(to != address(0), "Invalid recipient");
        require(eventId > 0, "Invalid event id");

        _tokenIdCounter.increment();
        tokenId = _tokenIdCounter.current();

        _safeMint(to, tokenId);
        ticketInfo[tokenId] = TicketData({
            eventId: eventId,
            eventName: eventName,
            date: date,
            venue: venue,
            seatNumber: seatNumber,
            metadataURI: metadataURI
        });
        tickets[tokenId] = Ticket({
            eventId: eventId,
            owner: to,
            isUsed: false
        });

        emit TicketMinted(tokenId, to, eventId, eventName, date, venue, seatNumber);
    }

    /// @notice Required mint function: one ticket NFT per call.
    /// @param to Receiver of the NFT.
    /// @param eventId Related event id.
    /// @return tokenId Newly minted token id.
    function mintTicket(
        address to,
        uint256 eventId
    ) external onlyOwner returns (uint256 tokenId) {
        tokenId = _mintTicketInternal(to, eventId, "", "", "", "", "");
    }

    /// @notice Optional helper to mint with rich ticket metadata and optional IPFS URI.
    function mintTicketWithDetails(
        address to,
        uint256 eventId,
        string memory eventName,
        string memory date,
        string memory venue,
        string memory seatNumber,
        string memory metadataURI
    ) external onlyOwner returns (uint256 tokenId) {
        tokenId = _mintTicketInternal(
            to,
            eventId,
            eventName,
            date,
            venue,
            seatNumber,
            metadataURI
        );
    }

    /// @notice Set shared base URI used when token-specific metadataURI is not set.
    function setBaseURI(string memory baseURI_) external onlyOwner {
        _baseTokenURI = baseURI_;
        emit BaseURIUpdated(baseURI_);
    }

    function _baseURI() internal view override returns (string memory) {
        return _baseTokenURI;
    }

    /// @notice tokenURI resolution:
    /// 1) return per-token metadataURI if present (IPFS JSON supported)
    /// 2) else return baseURI + tokenId
    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        require(_ownerOf(tokenId) != address(0), "ERC721: invalid token ID");
        string memory customURI = ticketInfo[tokenId].metadataURI;
        if (bytes(customURI).length > 0) {
            return customURI;
        }
        return string(abi.encodePacked(_baseURI(), tokenId.toString()));
    }

    /// @notice Verify ticket status and emit verification event.
    /// @dev Emits an event for off-chain logs/audit trails.
    function verifyTicket(uint256 tokenId)
        external
        returns (bool isValid, address owner, bool isUsed, uint256 eventId)
    {
        require(_ownerOf(tokenId) != address(0), "Ticket does not exist");

        Ticket memory t = tickets[tokenId];
        owner = ownerOf(tokenId);
        isUsed = t.isUsed;
        eventId = t.eventId;
        isValid = !isUsed;

        emit TicketVerified(tokenId, owner, eventId, isUsed, isValid);
    }

    /// @notice Redeem a ticket once. Only current owner can redeem.
    function redeemTicket(uint256 tokenId) external {
        require(_ownerOf(tokenId) != address(0), "Ticket does not exist");
        require(ownerOf(tokenId) == msg.sender, "Only owner can redeem");
        require(!tickets[tokenId].isUsed, "Ticket already redeemed");

        tickets[tokenId].isUsed = true;
        emit TicketRedeemed(tokenId, msg.sender, tickets[tokenId].eventId);
    }

    /// @dev Keep `tickets[tokenId].owner` aligned with ERC721 ownership.
    function _beforeTokenTransfer(
        address from,
        address to,
        uint256 firstTokenId,
        uint256 batchSize
    ) internal override {
        // Optional transfer restriction:
        // block regular transfers when ticket has already been redeemed.
        // (mint: from == address(0), burn: to == address(0))
        if (from != address(0) && to != address(0)) {
            require(!tickets[firstTokenId].isUsed, "Used ticket cannot be transferred");
        }

        super._beforeTokenTransfer(from, to, firstTokenId, batchSize);
        if (to != address(0) && _ownerOf(firstTokenId) != address(0)) {
            tickets[firstTokenId].owner = to;
        }
    }

    /// @notice Expose total minted supply count.
    function totalMinted() external view returns (uint256) {
        return _tokenIdCounter.current();
    }

    // ownerOf(tokenId) and transferFrom(from, to, tokenId) are inherited from ERC721.
}
