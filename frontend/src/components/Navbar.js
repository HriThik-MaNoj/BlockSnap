import React from 'react';
import {
  Box,
  Flex,
  Button,
  Text,
  useColorModeValue,
  HStack,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  useToast,
} from '@chakra-ui/react';
import { useWeb3React } from '@web3-react/core';
import { injected } from '../utils/connectors';
import { ChevronDownIcon } from '@chakra-ui/icons';

function Navbar() {
  const { active, account, activate, deactivate } = useWeb3React();
  const toast = useToast();

  const connectWallet = async () => {
    console.log('Attempting to connect wallet...');
    try {
      // Check if MetaMask is installed
      if (!window.ethereum) {
        throw new Error('Please install MetaMask to connect your wallet');
      }

      // Request account access first
      await window.ethereum.request({ method: 'eth_requestAccounts' });

      // Try to switch to local Hardhat network
      try {
        await window.ethereum.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: '0x539' }], // Hardhat chainId in hex (1337)
        });
      } catch (switchError) {
        // This error code indicates that the chain has not been added to MetaMask
        if (switchError.code === 4902) {
          try {
            await window.ethereum.request({
              method: 'wallet_addEthereumChain',
              params: [
                {
                  chainId: '0x539',
                  chainName: 'Hardhat Local',
                  nativeCurrency: {
                    name: 'ETH',
                    symbol: 'ETH',
                    decimals: 18
                  },
                  rpcUrls: ['http://127.0.0.1:8545'],
                  blockExplorerUrls: null
                },
              ],
            });
          } catch (addError) {
            console.error('Error adding network:', addError);
            throw new Error('Failed to add Hardhat network to MetaMask');
          }
        } else {
          console.error('Error switching network:', switchError);
          throw switchError;
        }
      }

      // Wait a bit for MetaMask to update
      await new Promise(resolve => setTimeout(resolve, 1000));

      // Activate the injected connector (MetaMask)
      await activate(injected, async (error) => {
        console.error('Activation error:', error);
        if (error.code === -32002) {
          toast({
            title: 'Pending Request',
            description: 'Please check MetaMask for pending requests',
            status: 'warning',
            duration: 5000,
            isClosable: true,
          });
        } else {
          throw error;
        }
      });

      console.log('Wallet connected successfully');
      
      toast({
        title: 'Wallet Connected',
        description: 'Successfully connected to MetaMask',
        status: 'success',
        duration: 3000,
        isClosable: true,
      });
    } catch (error) {
      console.error('Connection error:', error);
      toast({
        title: 'Connection Error',
        description: error.message || 'Failed to connect wallet',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const disconnectWallet = async () => {
    try {
      deactivate();
      toast({
        title: 'Wallet Disconnected',
        status: 'info',
        duration: 3000,
        isClosable: true,
      });
    } catch (error) {
      console.error('Error disconnecting wallet:', error);
      toast({
        title: 'Error',
        description: 'Failed to disconnect wallet',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  };

  return (
    <Box bg={useColorModeValue('gray.800', 'gray.900')} px={4} borderBottom="1px" borderColor="gray.700">
      <Flex h={16} alignItems={'center'} justifyContent={'space-between'}>
        <Text fontSize="xl" fontWeight="bold" color="white">
          BlockSnap
        </Text>

        <HStack spacing={4}>
          {active ? (
            <Menu>
              <MenuButton
                as={Button}
                rightIcon={<ChevronDownIcon />}
                bg="blue.500"
                color="white"
                _hover={{ bg: 'blue.600' }}
              >
                {account ? `${account.substring(0, 6)}...${account.substring(38)}` : 'Connected'}
              </MenuButton>
              <MenuList bg="gray.800" borderColor="gray.700">
                <MenuItem
                  onClick={disconnectWallet}
                  _hover={{ bg: 'gray.700' }}
                  color="white"
                >
                  Disconnect
                </MenuItem>
              </MenuList>
            </Menu>
          ) : (
            <Button
              onClick={connectWallet}
              bg="blue.500"
              color="white"
              _hover={{ bg: 'blue.600' }}
            >
              Connect Wallet
            </Button>
          )}
        </HStack>
      </Flex>
    </Box>
  );
}

export default Navbar;