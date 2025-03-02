const { ethers } = require("hardhat");
require("dotenv").config();

async function main() {
  // Get the private key from .env
  const privateKey = process.env.PRIVATE_KEY;
  
  // Create a wallet from the private key
  const wallet = new ethers.Wallet(privateKey, ethers.provider);
  
  // Get the address
  const address = wallet.address;
  console.log(`Wallet address: ${address}`);
  
  // Get the balance
  const balance = await ethers.provider.getBalance(address);
  console.log(`Balance: ${balance.toString()} wei`);
  
  // Get the network information
  const network = await ethers.provider.getNetwork();
  console.log(`Network: ${network.name} (chainId: ${network.chainId})`);
  
  // Get the RPC URL being used
  console.log(`RPC URL: ${process.env.ETH_RPC_URL}`);
}

main()
  .then(() => process.exit(0))
  .catch(error => {
    console.error(error);
    process.exit(1);
  });
