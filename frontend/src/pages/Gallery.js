import React, { useState, useEffect } from 'react';
import {
  Box,
  SimpleGrid,
  Image,
  Text,
  VStack,
  HStack,
  Spinner,
  Center,
  useToast,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalCloseButton,
  useDisclosure,
  Icon,
  Divider,
  IconButton,
  Tabs,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
} from '@chakra-ui/react';
import { useWeb3React } from '@web3-react/core';
import { ChevronUpIcon, ChevronDownIcon, CopyIcon } from '@chakra-ui/icons';
import axios from 'axios';

function Gallery() {
  const [media, setMedia] = useState({ photos: [], videos: [], videoSessions: [] });
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState(null);
  const [imageErrors, setImageErrors] = useState({});
  const { isOpen, onOpen, onClose } = useDisclosure();
  const { active, account } = useWeb3React();
  const toast = useToast();

  const handleImageError = (tokenId) => {
    setImageErrors(prev => ({ ...prev, [tokenId]: true }));
  };

  const handleImageClick = (nft) => {
    setSelectedImage(nft);
    onOpen();
  };

  const fetchMedia = async () => {
    if (!active) return;
    
    setLoading(true);
    try {
      // Fetch NFTs
      const nftsResponse = await axios.get(`http://localhost:5000/nfts/${account}`);
      const allNfts = nftsResponse.data.nfts || [];
      
      // Fetch video sessions
      const sessionsResponse = await axios.get(`http://localhost:5000/video-sessions/${account}`);
      
      // Sort video chunks by sequence number
      const sortedSessions = (sessionsResponse.data.sessions || []).map(session => ({
        ...session,
        chunks: session.chunks.sort((a, b) => a.sequence_number - b.sequence_number)
      }));
      
      // Filter NFTs into photos and videos based on type field
      const photos = allNfts.filter(nft => nft.type === 'photo');
      const videos = allNfts.filter(nft => nft.type === 'video');
      
      setMedia({
        photos,
        videos,
        videoSessions: sortedSessions
      });
      
    } catch (error) {
      console.error('Error fetching media:', error);
      toast({
        title: 'Error',
        description: 'Failed to fetch media',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setLoading(false);
    }
  };

  const renderInfoRow = (label, value) => (
    <Box w="100%" py={1}>
      <Text fontSize="xs" color="gray.500" mb={1}>
        {label}
      </Text>
      <HStack justify="space-between" align="center" 
        bg="gray.800" 
        p={2} 
        borderRadius="md"
        borderWidth="1px"
        borderColor="gray.700"
        _hover={{ bg: 'gray.700' }}
      >
        <Text fontSize="sm" color="gray.300" isTruncated maxW="70%" fontFamily="mono">
          {value}
        </Text>
        <IconButton
          icon={<CopyIcon />}
          size="sm"
          variant="ghost"
          colorScheme="blue"
          color="gray.300"
          _hover={{ bg: 'gray.600' }}
          onClick={() => handleCopy(value, label)}
          aria-label={`Copy ${label}`}
        />
      </HStack>
    </Box>
  );

  const handleCopy = (text, type) => {
    navigator.clipboard.writeText(text);
    toast({
      title: 'Copied!',
      description: `${type} copied to clipboard`,
      status: 'success',
      duration: 2000,
    });
  };

  const renderVideoSession = (session) => {
    const isActive = true;
    
    return (
      <Box 
        key={session.id}
        borderWidth="1px"
        borderRadius="lg"
        overflow="hidden"
        bg="gray.900"
        shadow="md"
        mb={4}
      >
        <Box p={4}>
          <HStack justify="space-between">
            <VStack align="start" spacing={1}>
              <Text fontWeight="bold" color="gray.100">
                Session #{session.id}
              </Text>
              <Text fontSize="sm" color="gray.400">
                {new Date(parseInt(session.start_time) * 1000).toLocaleString()}
              </Text>
              <Text fontSize="sm" color="gray.400">
                {session.chunks.length} clips
              </Text>
            </VStack>
            <IconButton
              aria-label="Toggle session"
              icon={<ChevronDownIcon />}
              variant="ghost"
              colorScheme="blue"
            />
          </HStack>
        </Box>
        
        <SimpleGrid columns={[1, 2, 3]} spacing={4} p={4}>
          {session.chunks.map((chunk) => (
            <Box 
              key={chunk.sequence_number}
              borderWidth="1px"
              borderRadius="md"
              overflow="hidden"
              bg="gray.800"
            >
              <video
                controls
                width="100%"
                src={`http://127.0.0.1:8080/ipfs/${chunk.video_cid}`}
                style={{ borderRadius: '0.375rem' }}
                muted
                preload="metadata"
                playsInline
              />
              <Box p={3}>
                <Text fontSize="sm" color="gray.300" mb={2}>
                  Clip {chunk.sequence_number + 1}
                </Text>
                <VStack spacing={2} align="stretch">
                  {renderInfoRow('IPFS CID', chunk.video_cid)}
                  <Text fontSize="xs" color="gray.500">
                    {new Date(parseInt(chunk.timestamp) * 1000).toLocaleString()}
                  </Text>
                </VStack>
              </Box>
            </Box>
          ))}
        </SimpleGrid>
      </Box>
    );
  };

  // Fetch media on wallet change
  useEffect(() => {
    fetchMedia();
  }, [active, account, toast]); 

  if (!active) {
    return (
      <Center h="200px">
        <Text>Please connect your wallet to view your media</Text>
      </Center>
    );
  }

  if (loading) {
    return (
      <Center h="200px">
        <Spinner />
      </Center>
    );
  }

  return (
    <Box p={8} bg="gray.900">
      <Tabs>
        <TabList>
          <Tab>Photos</Tab>
          <Tab>Videos</Tab>
        </TabList>

        <TabPanels>
          <TabPanel>
            {media.photos.length === 0 ? (
              <Center h="200px">
                <Text>No photos found</Text>
              </Center>
            ) : (
              <SimpleGrid columns={[1, 2, 3]} spacing={8}>
                {media.photos.map((nft) => (
                  <Box
                    key={nft.tokenId}
                    borderWidth="1px"
                    borderRadius="lg"
                    overflow="hidden"
                    shadow="md"
                  >
                    {imageErrors[nft.tokenId] ? (
                      <Center h="200px" bg="gray.100">
                        <Text color="gray.500">Image not available</Text>
                      </Center>
                    ) : (
                      <Box position="relative" cursor="pointer" onClick={() => handleImageClick(nft)}>
                        <Image 
                          src={`http://127.0.0.1:8080/ipfs/${nft.image_cid}`}
                          alt={`Photo ${nft.tokenId}`}
                          fallback={<Center h="200px"><Spinner /></Center>}
                          onError={() => handleImageError(nft.tokenId)}
                          objectFit="cover"
                          h="200px"
                          w="100%"
                        />
                      </Box>
                    )}
                    <Box p={4} bg="gray.900">
                      <Divider mb={3} borderColor="gray.700" />
                      <VStack spacing={3} align="stretch">
                        {renderInfoRow('IPFS CID', nft.image_cid)}
                        {renderInfoRow('Transaction Hash', nft.transaction_hash)}
                      </VStack>
                    </Box>
                  </Box>
                ))}
              </SimpleGrid>
            )}
          </TabPanel>

          <TabPanel>
            {media.videos.length === 0 && media.videoSessions.length === 0 ? (
              <Center h="200px">
                <Text>No videos found</Text>
              </Center>
            ) : (
              <VStack spacing={4} align="stretch">
                {media.videos.map((nft) => (
                  <Box
                    key={nft.tokenId}
                    borderWidth="1px"
                    borderRadius="lg"
                    overflow="hidden"
                    shadow="md"
                  >
                    <Box>
                      {imageErrors[nft.tokenId] ? (
                        <Center h="200px" bg="gray.100">
                          <Text color="gray.500">Video not available</Text>
                        </Center>
                      ) : (
                        <video
                          controls
                          width="100%"
                          height="200px"
                          src={`http://127.0.0.1:8080/ipfs/${nft.image_cid}`}
                          poster={`http://127.0.0.1:8080/ipfs/${nft.image_cid}?preview=true`}
                          style={{ borderRadius: '0.375rem', backgroundColor: 'black' }}
                          onError={() => handleImageError(nft.tokenId)}
                          muted
                          preload="metadata"
                        />
                      )}
                    </Box>
                    <Box p={4} bg="gray.900">
                      <Text fontSize="lg" mb={2} color="white">
                        {nft.name}
                      </Text>
                      <Divider mb={3} borderColor="gray.700" />
                      <VStack spacing={3} align="stretch">
                        {renderInfoRow('IPFS CID', nft.image_cid)}
                        {renderInfoRow('Transaction Hash', nft.transaction_hash)}
                        {renderInfoRow('Type', 'Video Recording')}
                      </VStack>
                    </Box>
                  </Box>
                ))}
                {media.videoSessions.map(renderVideoSession)}
              </VStack>
            )}
          </TabPanel>
        </TabPanels>
      </Tabs>

      {/* Full-screen Image Modal */}
      <Modal isOpen={isOpen} onClose={onClose} size="full">
        <ModalOverlay bg="rgba(0, 0, 0, 0.9)" />
        <ModalContent bg="transparent" boxShadow="none">
          <ModalCloseButton color="white" size="lg" />
          <ModalBody display="flex" alignItems="center" justifyContent="center" p={0}>
            {selectedImage && (
              <Image
                src={`http://127.0.0.1:8080/ipfs/${selectedImage.image_cid}`}
                alt={`Photo ${selectedImage.tokenId}`}
                maxH="90vh"
                objectFit="contain"
                borderRadius="md"
                onClick={(e) => e.stopPropagation()}
              />
            )}
          </ModalBody>
        </ModalContent>
      </Modal>
    </Box>
  );
}

export default Gallery;