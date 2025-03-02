const { ethers } = require("hardhat");
require("dotenv").config();

async function main() {
  // Get the private key from .env
  const privateKey = process.env.PRIVATE_KEY;
  
  // Create a wallet from the private key
  const wallet = new ethers.Wallet(privateKey, ethers.provider);
  
  // Get the address
  const address = wallet.address;
  console.log(`Wallet address to fund: ${address}`);
  
  // Get the first account from hardhat (which has 10000 ETH by default)
  const [signer] = await ethers.getSigners();
  console.log(`Funding from: ${signer.address}`);
  
  // Check signer balance
  const signerBalance = await ethers.provider.getBalance(signer.address);
  console.log(`Signer balance: ${signerBalance.toString()} wei`);
  
  // Send 1 ETH to the wallet
  const tx = await signer.sendTransaction({
    to: address,
    value: ethers.utils.parseEther("1.0")
  });
  
  console.log(`Transaction hash: ${tx.hash}`);
  await tx.wait();
  
  // Check the new balance
  const newBalance = await ethers.provider.getBalance(address);
  console.log(`New wallet balance: ${newBalance.toString()} wei`);
}

main()
  .then(() => process.exit(0))
  .catch(error => {
    console.error(error);
    process.exit(1);
  });
