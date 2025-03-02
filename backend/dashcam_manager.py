#!/usr/bin/env python3

import logging
import threading
from typing import Optional, Dict
from datetime import datetime
import time
from .video_handler import DashcamRecorder
from .ipfs_handler import IPFSHandler
from .blockchain_handler import BlockchainHandler
from .batch_processor import BatchProcessor

class DashcamManager:
    def __init__(self):
        """Initialize the dashcam manager"""
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.recorder = DashcamRecorder()
        self.ipfs = IPFSHandler()
        self.blockchain = BlockchainHandler()
        self.batch_processor = BatchProcessor(self.ipfs)
        
        # State
        self.session_id: Optional[int] = None
        self.is_recording = False
        self.upload_thread: Optional[threading.Thread] = None
        self.current_session_chunks = []
        self.session_start_time = None
        
        self.logger.info("DashcamManager initialized")

    def start_recording(self) -> bool:
        """Start recording and uploading"""
        try:
            # Start blockchain session
            self.session_id = self.blockchain.start_video_session()
            self.session_start_time = datetime.now()
            
            # Start video recording
            if not self.recorder.start_recording():
                raise RuntimeError("Failed to start recording")
            
            # Start batch processor
            self.batch_processor.start()
            
            # Start upload thread
            self.is_recording = True
            self.current_session_chunks = []
            self.upload_thread = threading.Thread(target=self._upload_loop)
            self.upload_thread.start()
            
            self.logger.info(f"Started recording with session ID: {self.session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start recording: {str(e)}")
            self.cleanup()
            return False

    def stop_recording(self) -> bool:
        """Stop recording and uploading"""
        try:
            # Stop recording
            if not self.recorder.stop_recording():
                raise RuntimeError("Failed to stop recording")
            
            # Wait for upload thread to finish
            self.is_recording = False
            if self.upload_thread:
                self.upload_thread.join()
            
            # End blockchain session
            if self.session_id is not None:
                self.blockchain.end_video_session(self.session_id)
            
            # Clean up
            self.session_id = None
            self.current_session_chunks = []
            self.session_start_time = None
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping recording: {str(e)}")
            return False

    def _upload_loop(self):
        """Background thread to handle chunk uploading"""
        while self.is_recording:
            try:
                # Get the next chunk from the recorder
                chunk = self.recorder.get_next_chunk()
                if not chunk:
                    time.sleep(1)
                    continue
                
                # Upload video to IPFS
                video_cid = self.ipfs.add_bytes(chunk.data)
                
                # Create and upload metadata
                metadata = {
                    "sequence_number": chunk.sequence_number,
                    "start_time": chunk.start_time,
                    "duration": chunk.duration,
                    "timestamp": chunk.timestamp.isoformat()
                }
                metadata_cid = self.ipfs.add_json(metadata)
                
                # Add chunk to blockchain
                self.blockchain.add_video_chunk(
                    self.session_id,
                    chunk.sequence_number,
                    video_cid,
                    metadata_cid,
                    int(chunk.start_time)
                )
                
                # Add to current session
                self.current_session_chunks.append({
                    "video_cid": video_cid,
                    "metadata_cid": metadata_cid,
                    "sequence_number": chunk.sequence_number,
                    "timestamp": chunk.timestamp.isoformat()
                })
                
                # Delete local file after successful upload
                self.recorder.delete_chunk(chunk.sequence_number)
                
                self.logger.info(f"Successfully processed chunk {chunk.sequence_number}")
                
            except Exception as e:
                self.logger.error(f"Error in upload loop: {str(e)}")
                time.sleep(1)
                
        self.logger.info("Upload loop ended")

    def get_current_session(self) -> Dict:
        """Get information about the current recording session"""
        if not self.is_recording or self.session_id is None:
            return None
            
        return {
            "id": self.session_id,
            "is_recording": self.is_recording,
            "start_time": self.session_start_time.isoformat() if self.session_start_time else None,
            "chunks": self.current_session_chunks
        }

    def get_status(self) -> Dict:
        """Get current status"""
        try:
            return {
                'is_recording': self.is_recording,
                'session_id': self.session_id,
                'recorder_status': self.recorder.get_status(),
                'processor_stats': self.batch_processor.get_stats(),
                'session_active': self.session_id is not None and 
                                self.blockchain.is_session_active(self.session_id)
            }
        except Exception as e:
            self.logger.error(f"Error getting status: {str(e)}")
            return {'error': str(e)}

    def cleanup(self) -> None:
        """Clean up resources"""
        self.recorder.cleanup()
        self.is_recording = False
        self.session_id = None
