const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");
const { anyValue } = require("@nomicfoundation/hardhat-chai-matchers/withArgs");

describe("TicketNFT auction system", function () {
  async function deployFixture() {
    const [admin, bidder1, bidder2] = await ethers.getSigners();
    const ticket = await ethers.deployContract("TicketNFT");
    await ticket.waitForDeployment();

    // Mint one ticket so it can be auctioned.
    await ticket.connect(admin).mintTickets(1, 1);

    return { ticket, admin, bidder1, bidder2 };
  }

  it("creates an auction successfully", async function () {
    const { ticket, admin } = await deployFixture();
    const duration = 3600;

    await expect(ticket.connect(admin).createAuction(1, duration))
      .to.emit(ticket, "AuctionCreated")
      .withArgs(1, 1, admin.address, anyValue, anyValue);

    const auction = await ticket.auctions(1);
    expect(auction.ticketId).to.equal(1);
    expect(auction.seller).to.equal(admin.address);
    expect(auction.highestBid).to.equal(0n);
    expect(auction.highestBidder).to.equal(ethers.ZeroAddress);
    expect(auction.ended).to.equal(false);
  });

  it("accepts multiple bids and updates highest bidder", async function () {
    const { ticket, admin, bidder1, bidder2 } = await deployFixture();
    const oneEth = ethers.parseEther("1");
    const twoEth = ethers.parseEther("2");

    await ticket.connect(admin).createAuction(1, 3600);

    await expect(ticket.connect(bidder1).placeBid(1, { value: oneEth }))
      .to.emit(ticket, "BidPlaced")
      .withArgs(1, bidder1.address, oneEth);

    let auction = await ticket.auctions(1);
    expect(auction.highestBid).to.equal(oneEth);
    expect(auction.highestBidder).to.equal(bidder1.address);

    await expect(ticket.connect(bidder2).placeBid(1, { value: twoEth }))
      .to.emit(ticket, "BidPlaced")
      .withArgs(1, bidder2.address, twoEth);

    auction = await ticket.auctions(1);
    expect(auction.highestBid).to.equal(twoEth);
    expect(auction.highestBidder).to.equal(bidder2.address);
  });

  it("credits refund for previous highest bidder and allows withdraw", async function () {
    const { ticket, admin, bidder1, bidder2 } = await deployFixture();
    const oneEth = ethers.parseEther("1");
    const twoEth = ethers.parseEther("2");

    await ticket.connect(admin).createAuction(1, 3600);
    await ticket.connect(bidder1).placeBid(1, { value: oneEth });
    await ticket.connect(bidder2).placeBid(1, { value: twoEth });

    expect(await ticket.pendingWithdrawals(bidder1.address)).to.equal(oneEth);

    const balanceBefore = await ethers.provider.getBalance(bidder1.address);
    const tx = await ticket.connect(bidder1).withdraw();
    const receipt = await tx.wait();
    const gasCost = receipt.gasUsed * receipt.gasPrice;
    const balanceAfter = await ethers.provider.getBalance(bidder1.address);

    expect(balanceAfter).to.equal(balanceBefore + oneEth - gasCost);
    expect(await ticket.pendingWithdrawals(bidder1.address)).to.equal(0n);
  });

  it("ends auction correctly and transfers NFT to winner", async function () {
    const { ticket, admin, bidder1, bidder2 } = await deployFixture();
    const oneEth = ethers.parseEther("1");
    const twoEth = ethers.parseEther("2");
    const duration = 3600;

    await ticket.connect(admin).createAuction(1, duration);
    await ticket.connect(bidder1).placeBid(1, { value: oneEth });
    await ticket.connect(bidder2).placeBid(1, { value: twoEth });

    await time.increase(duration + 1);

    await expect(ticket.connect(admin).endAuction(1))
      .to.emit(ticket, "AuctionEnded")
      .withArgs(1, 1, bidder2.address, twoEth);

    const auction = await ticket.auctions(1);
    expect(auction.ended).to.equal(true);
    expect(await ticket.activeAuctionByTicket(1)).to.equal(0n);

    // NFT ownership moves to highest bidder.
    expect(await ticket.ownerOf(1)).to.equal(bidder2.address);

    // Seller receives proceeds via withdraw pattern.
    expect(await ticket.pendingWithdrawals(admin.address)).to.equal(twoEth);
  });
});

describe("TicketNFT dynamic pricing", function () {
  async function deployPricingFixture() {
    const [admin, user1, user2, user3] = await ethers.getSigners();
    const ticket = await ethers.deployContract("TicketNFT");
    await ticket.waitForDeployment();

    // Mint multiple tickets for primary sale on event 1.
    await ticket.connect(admin).mintTickets(1, 5);

    const basePrice = ethers.parseEther("0.1");
    const increment = ethers.parseEther("0.02");
    await ticket.connect(admin).setEventPricing(1, basePrice, increment);

    return { ticket, admin, user1, user2, user3, basePrice, increment };
  }

  it("starts with initial price equal to basePrice", async function () {
    const { ticket, basePrice } = await deployPricingFixture();
    const currentPrice = await ticket.getCurrentPrice(1);
    expect(currentPrice).to.equal(basePrice);
  });

  it("increases price after each purchase", async function () {
    const { ticket, user1, user2, basePrice, increment } = await deployPricingFixture();

    // First purchase at base price.
    await ticket.connect(user1).buyTicket(1, { value: basePrice });
    expect(await ticket.getCurrentPrice(1)).to.equal(basePrice + increment);

    // Second purchase at increased price.
    await ticket.connect(user2).buyTicket(2, { value: basePrice + increment });
    expect(await ticket.getCurrentPrice(1)).to.equal(basePrice + (increment * 2n));
  });

  it("handles multiple users buying tickets and updates ticketsSold correctly", async function () {
    const { ticket, user1, user2, user3, basePrice, increment } = await deployPricingFixture();

    await ticket.connect(user1).buyTicket(1, { value: basePrice });
    await ticket.connect(user2).buyTicket(2, { value: basePrice + increment });
    await ticket.connect(user3).buyTicket(3, { value: basePrice + (increment * 2n) });

    const pricing = await ticket.eventPricing(1);
    expect(pricing.ticketsSold).to.equal(3n);
    expect(await ticket.ownerOf(1)).to.equal(user1.address);
    expect(await ticket.ownerOf(2)).to.equal(user2.address);
    expect(await ticket.ownerOf(3)).to.equal(user3.address);
  });

  it("requires correct ETH amount for purchase", async function () {
    const { ticket, user1, user2, basePrice, increment } = await deployPricingFixture();

    await expect(ticket.connect(user1).buyTicket(1, { value: basePrice }))
      .to.emit(ticket, "TicketPurchased")
      .withArgs(1, 1, user1.address, basePrice, basePrice);

    const secondPrice = basePrice + increment;
    await expect(ticket.connect(user2).buyTicket(2, { value: secondPrice }))
      .to.emit(ticket, "TicketPurchased")
      .withArgs(2, 1, user2.address, secondPrice, secondPrice);
  });

  it("rejects underpayment", async function () {
    const { ticket, user1, basePrice } = await deployPricingFixture();
    const underpaid = basePrice - 1n;

    await expect(
      ticket.connect(user1).buyTicket(1, { value: underpaid })
    ).to.be.revertedWith("Insufficient payment");
  });
});
