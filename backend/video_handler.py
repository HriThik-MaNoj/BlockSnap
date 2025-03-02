#!/usr/bin/env python3

import cv2
import time
import threading
import queue
import logging
import os
import numpy as np
from datetime import datetime
from typing import Optional, Generator, Dict
from pathlib import Path

class VideoChunk:
    def __init__(self, start_time: float, data: bytes, sequence_number: int):
        self.start_time = start_time
        self.data = data
        self.sequence_number = sequence_number
        self.duration = 15  # seconds
        self.timestamp = datetime.fromtimestamp(start_time)

    def get_metadata(self) -> Dict:
        return {
            "start_time": self.start_time,
            "sequence_number": self.sequence_number,
            "duration": self.duration,
            "timestamp": self.timestamp.isoformat()
        }

class DashcamRecorder:
    def __init__(self, 
                 chunk_duration: int = 15,
                 resolution: tuple = (1280, 720),  
                 fps: int = 30,
                 temp_dir: str = "temp_chunks"):
        """
        Initialize the dashcam recorder
        
        Args:
            chunk_duration: Duration of each video chunk in seconds
            resolution: Video resolution (width, height)
            fps: Frames per second
            temp_dir: Directory to store temporary chunks
        """
        self.logger = logging.getLogger(__name__)
        self.chunk_duration = chunk_duration
        self.resolution = resolution
        self.fps = fps
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        
        # Initialize state
        self.is_recording = False
        self.sequence_number = 0
        self.chunk_frames = []
        self.chunk_start_time = 0
        self.current_chunk = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.record_thread: Optional[threading.Thread] = None
        
        # Preview frame
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        
        # Video configuration
        self.fourcc = cv2.VideoWriter_fourcc(*'MJPG')  
        self.frame_size = (int(resolution[0]), int(resolution[1]))

    def _init_camera(self) -> bool:
        """Initialize the camera"""
        try:
            self.cap = cv2.VideoCapture(0)  # Just use the default camera
            if not self.cap.isOpened():
                return False

            # Set essential properties only
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            
            return True
        except Exception as e:
            self.logger.error(f"Camera initialization failed: {e}")
            return False

    def start_recording(self) -> bool:
        """Start recording video in chunks"""
        try:
            if not self._init_camera():
                raise RuntimeError("Failed to initialize camera")
                
            # Initialize recording state
            self.is_recording = True
            self.chunk_start_time = time.time()
            
            # Start recording thread
            self.record_thread = threading.Thread(target=self._record_loop)
            self.record_thread.daemon = True  # Make thread daemon so it exits when main program exits
            self.record_thread.start()
            
            self.logger.info("Started recording")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start recording: {str(e)}")
            if self.cap is not None:
                self.cap.release()
            return False

    def _record_loop(self):
        """Main recording loop"""
        while self.is_recording:
            try:
                if self.cap is None or not self.cap.isOpened():
                    self.logger.error("Camera disconnected, attempting to reinitialize...")
                    if not self._init_camera():
                        self.is_recording = False
                        break

                ret, frame = self.cap.read()
                if not ret:
                    self.logger.warning("Failed to read frame, retrying...")
                    time.sleep(0.1)
                    continue

                # Add timestamp overlay
                frame_with_timestamp = self._add_timestamp(frame)
                
                # Update preview frame
                with self.frame_lock:
                    self.latest_frame = frame_with_timestamp.copy()
                
                # Add frame to current chunk
                self.chunk_frames.append(frame_with_timestamp)
                
                # Check if it's time to finalize the current chunk
                current_time = time.time()
                if current_time - self.chunk_start_time >= self.chunk_duration:
                    self._finalize_chunk()
                    self.chunk_start_time = current_time
                    
            except Exception as e:
                self.logger.error(f"Error in recording loop: {str(e)}")
                time.sleep(0.1)

    def _finalize_chunk(self):
        """Finalize current chunk and prepare for next one"""
        try:
            if not self.chunk_frames:
                return
                
            # Create temporary file for the chunk
            chunk_path = self.temp_dir / f"chunk_{self.sequence_number}.mp4"
            
            # Initialize video writer
            out = cv2.VideoWriter(
                str(chunk_path),
                self.fourcc,
                self.fps,
                self.resolution
            )
            
            # Write frames
            for frame in self.chunk_frames:
                out.write(frame)
            
            # Release writer
            out.release()
            
            # Create chunk object
            with open(chunk_path, 'rb') as f:
                chunk_data = f.read()
            
            self.current_chunk = VideoChunk(
                start_time=self.chunk_start_time,
                data=chunk_data,
                sequence_number=self.sequence_number
            )
            
            # Reset for next chunk
            self.chunk_frames = []
            self.sequence_number += 1
            
        except Exception as e:
            self.logger.error(f"Error finalizing chunk: {str(e)}")

    def get_next_chunk(self) -> Optional[VideoChunk]:
        """Get the next available chunk"""
        chunk = self.current_chunk
        self.current_chunk = None
        return chunk

    def delete_chunk(self, sequence_number: int):
        """Delete a chunk file"""
        try:
            chunk_path = self.temp_dir / f"chunk_{sequence_number}.mp4"
            if chunk_path.exists():
                chunk_path.unlink()
                self.logger.info(f"Deleted chunk {sequence_number}")
        except Exception as e:
            self.logger.error(f"Error deleting chunk {sequence_number}: {str(e)}")

    def stop_recording(self) -> bool:
        """Stop recording"""
        try:
            self.is_recording = False
            if self.record_thread:
                self.record_thread.join()
            
            if self.cap:
                self.cap.release()
            
            # Finalize last chunk if needed
            if self.chunk_frames:
                self._finalize_chunk()
            
            self.logger.info("Stopped recording")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping recording: {str(e)}")
            return False

    def get_preview_frame(self) -> Optional[np.ndarray]:
        """Get the latest preview frame with timestamp overlay"""
        with self.frame_lock:
            if self.latest_frame is not None:
                return self._add_timestamp(self.latest_frame)
        return None

    def _add_timestamp(self, frame: np.ndarray) -> np.ndarray:
        """Add timestamp overlay to frame"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Create a copy to avoid modifying original
        frame_with_overlay = frame.copy()
        
        # Get frame dimensions
        height, width = frame_with_overlay.shape[:2]
        
        # Configure text properties
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = min(width, height) / 1000.0  # Scale based on frame size
        thickness = max(1, int(font_scale * 2))
        color = (255, 255, 255)  # White text
        
        # Add black background for better readability
        text_size = cv2.getTextSize(timestamp, font, font_scale, thickness)[0]
        padding = 10
        
        # Draw background rectangle
        cv2.rectangle(
            frame_with_overlay,
            (width - text_size[0] - padding * 2, height - text_size[1] - padding * 2),
            (width - padding, height - padding),
            (0, 0, 0),
            -1
        )
        
        # Add timestamp text
        cv2.putText(
            frame_with_overlay,
            timestamp,
            (width - text_size[0] - padding, height - padding - 5),
            font,
            font_scale,
            color,
            thickness
        )
        
        # Add GPS coordinates if available
        if hasattr(self, 'gps_coords'):
            gps_text = f"GPS: {self.gps_coords}"
            gps_size = cv2.getTextSize(gps_text, font, font_scale * 0.8, thickness)[0]
            
            # Draw background for GPS
            cv2.rectangle(
                frame_with_overlay,
                (width - gps_size[0] - padding * 2, height - text_size[1] - gps_size[1] - padding * 4),
                (width - padding, height - text_size[1] - padding * 2),
                (0, 0, 0),
                -1
            )
            
            # Add GPS text
            cv2.putText(
                frame_with_overlay,
                gps_text,
                (width - gps_size[0] - padding, height - text_size[1] - padding * 2 - 5),
                font,
                font_scale * 0.8,
                color,
                thickness
            )
        
        return frame_with_overlay

    def cleanup(self) -> None:
        """Clean up resources"""
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()

    def get_status(self) -> Dict:
        """Get current recording status"""
        return {
            "is_recording": self.is_recording,
            "sequence_number": self.sequence_number,
            "resolution": self.resolution,
            "fps": self.fps,
            "chunk_duration": self.chunk_duration
        }
