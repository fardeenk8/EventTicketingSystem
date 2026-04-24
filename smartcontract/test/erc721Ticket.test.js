const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TicketNFT ERC-721 core flows", function () {
  async function deployFixture() {
    const [owner, user1, user2] = await ethers.getSigners();
    const ticket = await ethers.deployContract("TicketNFT");
    await ticket.waitForDeployment();
    return { ticket, owner, user1, user2 };
  }

  it("mints a ticket", async function () {
    const { ticket, owner, user1 } = await deployFixture();

    await expect(ticket.connect(owner).mintTicket(user1.address, 1))
      .to.emit(ticket, "TicketMinted")
      .withArgs(1, user1.address, 1, "", "", "", "");

    expect(await ticket.totalMinted()).to.equal(1n);
  });

  it("verifies ownership after mint", async function () {
    const { ticket, owner, user1 } = await deployFixture();
    await ticket.connect(owner).mintTicket(user1.address, 1);

    expect(await ticket.ownerOf(1)).to.equal(user1.address);
    const stored = await ticket.tickets(1);
    expect(stored.owner).to.equal(user1.address);
    expect(stored.isUsed).to.equal(false);
  });

  it("transfers ticket using transferFrom", async function () {
    const { ticket, owner, user1, user2 } = await deployFixture();
    await ticket.connect(owner).mintTicket(user1.address, 1);

    await ticket.connect(user1).transferFrom(user1.address, user2.address, 1);

    expect(await ticket.ownerOf(1)).to.equal(user2.address);
    const stored = await ticket.tickets(1);
    expect(stored.owner).to.equal(user2.address);
  });

  it("redeems a ticket by owner", async function () {
    const { ticket, owner, user1 } = await deployFixture();
    await ticket.connect(owner).mintTicket(user1.address, 1);

    await expect(ticket.connect(user1).redeemTicket(1))
      .to.emit(ticket, "TicketRedeemed")
      .withArgs(1, user1.address, 1);

    const stored = await ticket.tickets(1);
    expect(stored.isUsed).to.equal(true);
  });

  it("prevents ticket reuse after redemption", async function () {
    const { ticket, owner, user1, user2 } = await deployFixture();
    await ticket.connect(owner).mintTicket(user1.address, 1);
    await ticket.connect(user1).redeemTicket(1);

    await expect(ticket.connect(user1).redeemTicket(1)).to.be.revertedWith("Ticket already redeemed");
    await expect(
      ticket.connect(user1).transferFrom(user1.address, user2.address, 1)
    ).to.be.revertedWith("Used ticket cannot be transferred");
  });
});
