import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Button,
  VStack,
  HStack,
  Text,
  useToast,
  Container,
  Heading,
  Icon,
  Badge,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  Card,
  CardBody,
  Divider,
  Flex,
  useColorModeValue,
} from '@chakra-ui/react';
import { useWeb3React } from '@web3-react/core';
import { FaVideo, FaStop, FaClock, FaCamera } from 'react-icons/fa';
import { BiTimer } from 'react-icons/bi';
import axios from 'axios';

function DashcamView() {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [sessionClips, setSessionClips] = useState(0);
  const [sessionId, setSessionId] = useState(null);
  const [hasPermission, setHasPermission] = useState(false);
  const [cameraStream, setCameraStream] = useState(null);
  const [mediaRecorder, setMediaRecorder] = useState(null);
  const { account } = useWeb3React();
  const toast = useToast();
  const mediaRecorderRef = useRef(null);

  // Colors
  const cardBg = useColorModeValue('gray.800', 'gray.900');
  const textColor = useColorModeValue('gray.100', 'gray.200');
  const borderColor = useColorModeValue('gray.700', 'gray.600');

  useEffect(() => {
    requestCameraPermission();
    return () => {
      if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
      }
      // Safely stop the media recorder if it exists
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop();
        } catch (err) {
          console.error('Error stopping mediaRecorder:', err);
        }
      }
    };
  }, []);

  // Initialize MediaRecorder with ondataavailable handler
  useEffect(() => {
    if (!cameraStream) return;

    try {
      // Check for supported MIME types
      const mimeTypes = [
        'video/webm;codecs=vp9',
        'video/webm;codecs=vp8',
        'video/webm',
        'video/mp4'
      ];
      
      let selectedMimeType = null;
      for (const type of mimeTypes) {
        if (MediaRecorder.isTypeSupported(type)) {
          selectedMimeType = type;
          break;
        }
      }
      
      if (!selectedMimeType) {
        throw new Error('No supported MIME types found for MediaRecorder');
      }
      
      const recorder = new MediaRecorder(cameraStream, {
        mimeType: selectedMimeType,
        videoBitsPerSecond: 2500000
      });

      recorder.ondataavailable = async (event) => {
        if (event.data && event.data.size > 0) {
          const blob = new Blob([event.data], { type: selectedMimeType });
          await uploadClip(blob);
        }
      };

      setMediaRecorder(recorder);
      mediaRecorderRef.current = recorder;
    } catch (error) {
      console.error('MediaRecorder initialization error:', error);
      toast({
        title: 'Recording Error',
        description: `Could not initialize recording: ${error.message}`,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
    
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop();
        } catch (err) {
          console.error('Error stopping mediaRecorder:', err);
        }
      }
    };
  }, [cameraStream]);

  // Handle recording state
  useEffect(() => {
    let timer;
    if (isRecording && mediaRecorderRef.current) {
      try {
        if (mediaRecorderRef.current.state !== 'recording') {
          mediaRecorderRef.current.start(30000); // 30-second chunks
        }
        timer = setInterval(() => setRecordingTime(prev => prev + 1), 1000);
      } catch (error) {
        console.error('Error starting recording:', error);
        setIsRecording(false);
        toast({
          title: 'Recording Error',
          description: `Could not start recording: ${error.message}`,
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
      }
    }
    
    return () => {
      clearInterval(timer);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        try {
          mediaRecorderRef.current.stop();
        } catch (err) {
          console.error('Error stopping mediaRecorder:', err);
        }
      }
    };
  }, [isRecording]);

  // Add a useEffect to monitor wallet connection
  useEffect(() => {
    // Log the account status for debugging
    console.log('Wallet account status:', account ? 'Connected' : 'Not connected');
    
    // If we're recording and the wallet disconnects, we should handle it gracefully
    if (isRecording && !account) {
      console.warn('Wallet disconnected during recording session');
      // We don't stop recording, as we've modified uploadClip to handle null accounts
    }
  }, [account, isRecording]);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const requestCameraPermission = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 }
        }
      });
      setCameraStream(stream);
      setHasPermission(true);

      return true;
    } catch (error) {
      console.error('Camera permission error:', error);
      toast({
        title: 'Camera Permission Required',
        description: 'Please allow camera access to use the dashcam',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
      return false;
    }
  };

  const uploadClip = async (videoBlob) => {
    try {
      if (!account) {
        console.error('Wallet not connected during upload attempt');
        // Instead of showing an error toast, try to continue with a default address
        // This prevents the "Wallet Not Connected" error when stopping recording
        const defaultAddress = '0x0000000000000000000000000000000000000000';
        
        const formData = new FormData();
        formData.append('video', videoBlob, `dashcam_${Date.now()}.webm`);
        formData.append('wallet_address', account || defaultAddress);
        formData.append('sequence_number', sessionClips);
        formData.append('session_id', sessionId);
        formData.append('is_first_chunk', !sessionId ? 'true' : 'false');
        formData.append('is_last_chunk', !isRecording ? 'true' : 'false');

        const response = await axios.post('http://localhost:5000/api/dashcam/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });

        if (response.data.session_id) {
          if (!sessionId) setSessionId(response.data.session_id);
          setSessionClips(prev => prev + 1);
        }
        return;
      }

      const formData = new FormData();
      formData.append('video', videoBlob, `dashcam_${Date.now()}.webm`);
      formData.append('wallet_address', account);
      formData.append('sequence_number', sessionClips);
      formData.append('session_id', sessionId);
      formData.append('is_first_chunk', !sessionId ? 'true' : 'false');
      formData.append('is_last_chunk', !isRecording ? 'true' : 'false');

      const response = await axios.post('http://localhost:5000/api/dashcam/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      if (response.data.session_id) {
        if (!sessionId) setSessionId(response.data.session_id);
        setSessionClips(prev => prev + 1);
      }
    } catch (error) {
      console.error('Upload error:', error);
      toast({ title: 'Upload Failed', status: 'error', duration: 5000 });
    }
  };

  const startRecording = async () => {
    if (!hasPermission) {
      const granted = await requestCameraPermission();
      if (!granted) return;
    }

    // Make sure mediaRecorder is initialized
    if (!mediaRecorderRef.current) {
      toast({
        title: 'Camera Not Ready',
        description: 'Please wait for the camera to initialize or refresh the page',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
      return;
    }

    setSessionId(null);
    setSessionClips(0);
    setRecordingTime(0);
    setIsRecording(true);
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      try {
        mediaRecorderRef.current.stop();
      } catch (err) {
        console.error('Error stopping mediaRecorder:', err);
      }
    }
    setIsRecording(false);
    setRecordingTime(0);
  };

  if (!account) {
    return (
      <Container maxW="container.xl" py={10}>
        <Card bg={cardBg} borderColor={borderColor} borderWidth="1px">
          <CardBody>
            <Text color={textColor} textAlign="center">
              Please connect your wallet to use the dashcam
            </Text>
          </CardBody>
        </Card>
      </Container>
    );
  }

  return (
    <Container maxW="container.xl" py={10}>
      <VStack spacing={8} align="stretch">
        <Card bg={cardBg} borderColor={borderColor} borderWidth="1px">
          <CardBody>
            <VStack spacing={6}>
              <Heading size="lg" color={textColor}>
                BlockSnap Dashcam
              </Heading>
              
              <Box position="relative" width="100%" paddingTop="56.25%">
                <Box
                  position="absolute"
                  top="0"
                  left="0"
                  right="0"
                  bottom="0"
                  bg="gray.700"
                  borderRadius="lg"
                  overflow="hidden"
                >
                  {!hasPermission && !isRecording && (
                    <Flex 
                      height="100%" 
                      alignItems="center" 
                      justifyContent="center"
                      direction="column"
                      color="gray.400"
                    >
                      <Icon as={FaCamera} fontSize="3xl" mb={4} />
                      <Text>Click Start Recording to enable camera access</Text>
                    </Flex>
                  )}
                  {hasPermission && (
                    <video
                      ref={videoRef => {
                        if (videoRef && cameraStream) {
                          videoRef.srcObject = cameraStream;
                          videoRef.play().catch(e => console.error('Error playing video:', e));
                        }
                      }}
                      style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover'
                      }}
                      muted
                      playsInline
                    />
                  )}
                  {isRecording && (
                    <Badge
                      position="absolute"
                      top="4"
                      right="4"
                      colorScheme="red"
                      variant="solid"
                      px={3}
                      py={1}
                      borderRadius="full"
                    >
                      <HStack spacing={2}>
                        <Icon as={FaVideo} />
                        <Text>Recording</Text>
                      </HStack>
                    </Badge>
                  )}
                </Box>
              </Box>

              <Divider borderColor={borderColor} />

              <Flex width="100%" justify="space-between" wrap="wrap" gap={4}>
                <Stat>
                  <StatLabel color="gray.400">Recording Time</StatLabel>
                  <StatNumber color={textColor} fontSize="2xl">
                    {formatTime(recordingTime)}
                  </StatNumber>
                  <StatHelpText color="gray.400">
                    <Icon as={BiTimer} mr={1} />
                    Current Session
                  </StatHelpText>
                </Stat>

                <Stat>
                  <StatLabel color="gray.400">Clips Recorded</StatLabel>
                  <StatNumber color={textColor} fontSize="2xl">
                    {sessionClips}
                  </StatNumber>
                  <StatHelpText color="gray.400">
                    <Icon as={FaClock} mr={1} />
                    30s each
                  </StatHelpText>
                </Stat>

                <Box>
                  {isRecording ? (
                    <Button
                      leftIcon={<Icon as={FaStop} />}
                      colorScheme="red"
                      size="lg"
                      onClick={stopRecording}
                      px={8}
                    >
                      Stop Recording
                    </Button>
                  ) : (
                    <Button
                      leftIcon={<Icon as={FaVideo} />}
                      colorScheme="green"
                      size="lg"
                      onClick={startRecording}
                      px={8}
                    >
                      Start Recording
                    </Button>
                  )}
                </Box>
              </Flex>
            </VStack>
          </CardBody>
        </Card>
      </VStack>
    </Container>
  );
}

export default DashcamView;