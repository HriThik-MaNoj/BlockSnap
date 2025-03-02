#!/usr/bin/env python3

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import logging
from pathlib import Path
import os
import platform
from dotenv import load_dotenv
from datetime import datetime
import json
import cv2
import time

# Import our custom modules
try:
    # Try to import Raspberry Pi specific modules
    from hardware.camera import BlockSnapCamera
    IS_RASPBERRY_PI = True
except (ImportError, RuntimeError):
    # If import fails, use mock camera
    from hardware.mock_camera import MockCamera
    IS_RASPBERRY_PI = False

from backend.ipfs_handler import IPFSHandler
from backend.blockchain_handler import BlockchainHandler
from backend.dashcam_manager import DashcamManager  # Import DashcamManager

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize components
try:
    # Initialize camera based on platform
    if IS_RASPBERRY_PI:
        logger.info("Initializing Raspberry Pi camera")
        camera = BlockSnapCamera()
    else:
        logger.info("Initializing mock camera for testing")
        camera = MockCamera()
    
    ipfs_handler = IPFSHandler()
    blockchain_handler = BlockchainHandler()
    dashcam_manager = DashcamManager()  # Initialize dashcam manager
    logger.info("All components initialized successfully")
except Exception as e:
    logger.error(f"Error initializing components: {str(e)}")
    raise

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'platform': 'Raspberry Pi' if IS_RASPBERRY_PI else 'Test Environment'
    })

@app.route('/capture', methods=['POST'])
def capture_photo():
    """
    Capture a photo and store it on IPFS
    Required JSON body: {
        "wallet_address": "0x...",
        "image_data": "base64_encoded_image_data"
    }
    """
    try:
        # Validate request
        data = request.get_json()
        if not data or 'wallet_address' not in data or 'image_data' not in data:
            return jsonify({'error': 'wallet_address and image_data are required'}), 400
        
        wallet_address = data['wallet_address']
        image_data = data['image_data']
        
        # Save base64 image data to a temporary file
        import base64
        import tempfile
        
        # Remove the data URL prefix if present
        if image_data.startswith('data:image'):
            image_data = image_data.split(',')[1]
        
        # Decode base64 and save to temp file
        image_bytes = base64.b64decode(image_data)
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
            temp_file.write(image_bytes)
            filepath = temp_file.name
        
        # Create metadata
        metadata = {
            'timestamp': datetime.now().isoformat(),
            'platform': platform.system(),
            'source': 'web_capture'
        }
        
        # Upload to IPFS
        file_cid, metadata_cid = ipfs_handler.upload_to_ipfs(filepath, metadata)
        
        # Clean up temp file
        os.unlink(filepath)
        
        # Create metadata URI (IPFS gateway URL)
        metadata_uri = ipfs_handler.get_ipfs_url(metadata_cid)
        
        # Mint NFT
        tx_hash, token_id = blockchain_handler.mint_photo_nft(
            wallet_address,
            file_cid,
            metadata_uri
        )
        
        # Prepare response
        response = {
            'status': 'success',
            'data': {
                'file_cid': file_cid,
                'metadata_cid': metadata_cid,
                'token_id': token_id,
                'transaction_hash': tx_hash,
                'metadata_uri': metadata_uri,
                'image_url': ipfs_handler.get_ipfs_url(file_cid)
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in capture endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/verify/<image_cid>', methods=['GET'])
def verify_photo(image_cid):
    """Verify a photo's authenticity and ownership"""
    try:
        # Check if content exists on IPFS
        ipfs_exists = ipfs_handler.verify_content(image_cid)
        
        # Check blockchain records
        blockchain_exists, owner = blockchain_handler.verify_photo(image_cid)
        
        response = {
            'exists_on_ipfs': ipfs_exists,
            'exists_on_blockchain': blockchain_exists,
            'owner': owner if blockchain_exists else None,
            'ipfs_url': ipfs_handler.get_ipfs_url(image_cid) if ipfs_exists else None
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in verify endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/token/<int:token_id>', methods=['GET'])
def get_token_info(token_id):
    """Get information about a specific token"""
    try:
        metadata_uri = blockchain_handler.get_token_uri(token_id)
        image_cid = blockchain_handler.get_image_cid(token_id)
        
        response = {
            'token_id': token_id,
            'metadata_uri': metadata_uri,
            'image_cid': image_cid,
            'image_url': ipfs_handler.get_ipfs_url(image_cid)
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in token info endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/nfts/<wallet_address>', methods=['GET'])
def get_nfts_by_wallet(wallet_address):
    """Get all NFTs owned by a wallet address"""
    try:
        # Get the event signature for PhotoMinted
        event_signature_hash = blockchain_handler.w3.keccak(text="PhotoMinted(uint256,address,string,string)").hex()
        
        # Get logs for the PhotoMinted event
        logs = blockchain_handler.w3.eth.get_logs({
            'address': blockchain_handler.contract.address,
            'topics': [event_signature_hash],
            'fromBlock': 0,
            'toBlock': 'latest'
        })
        
        app.logger.info(f"Found {len(logs)} total PhotoMinted events")
        
        nfts = []
        # Check each token from logs
        for log in logs:
            try:
                # Decode the log data
                decoded_log = blockchain_handler.contract.events.PhotoMinted().process_log(log)
                token_id = decoded_log['args']['tokenId']
                
                # Check if this wallet owns the token
                owner = blockchain_handler.contract.functions.ownerOf(token_id).call()
                if owner.lower() == wallet_address.lower():
                    # Get token details
                    metadata_uri = blockchain_handler.get_token_uri(token_id)
                    image_cid = blockchain_handler.get_image_cid(token_id)
                    
                    # Get transaction hash from the event log
                    transaction_hash = decoded_log.transactionHash.hex()
                    
                    # Get metadata from IPFS if available
                    try:
                        metadata = ipfs_handler.get_json(metadata_uri)
                    except:
                        metadata = {
                            'name': f'BlockSnap #{token_id}',
                            'description': 'A photo captured using BlockSnap'
                        }
                    
                    # Determine if this is a video based on metadata attributes
                    is_video = False
                    if metadata.get('attributes'):
                        for attr in metadata['attributes']:
                            if attr.get('trait_type') == 'Content Type' and attr.get('value') == 'video':
                                is_video = True
                                break
                    
                    nft = {
                        'tokenId': token_id,
                        'name': metadata.get('name', f'BlockSnap #{token_id}'),
                        'description': metadata.get('description', 'A photo captured using BlockSnap'),
                        'image': ipfs_handler.get_ipfs_url(image_cid),
                        'image_cid': image_cid,
                        'metadata_uri': metadata_uri,
                        'transaction_hash': transaction_hash,
                        'metadata': metadata,  # Include full metadata for frontend filtering
                        'type': 'video' if is_video else 'photo'  # Add explicit type field
                    }
                    nfts.append(nft)
                    app.logger.info(f"Found NFT {token_id} owned by {wallet_address}")
            except Exception as e:
                app.logger.error(f"Error processing log: {str(e)}")
                continue
        
        return jsonify({'nfts': nfts})
        
    except Exception as e:
        app.logger.error(f"Error in get NFTs endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashcam/start', methods=['POST'])
def start_dashcam():
    """Start dashcam recording"""
    try:
        success = dashcam_manager.start_recording()
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Recording started',
                'session_id': dashcam_manager.session_id
            })
        return jsonify({
            'status': 'error',
            'message': 'Failed to start recording'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/dashcam/stop', methods=['POST'])
def stop_dashcam():
    """Stop dashcam recording"""
    try:
        dashcam_manager.stop_recording()
        return jsonify({
            'status': 'success',
            'message': 'Recording stopped'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/dashcam/status', methods=['GET'])
def get_dashcam_status():
    """Get dashcam status"""
    try:
        status = dashcam_manager.get_status()
        return jsonify({
            'status': 'success',
            'data': status
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/dashcam/preview', methods=['GET'])
def get_preview_stream():
    """Get video preview stream"""
    try:
        def generate_frames():
            while dashcam_manager.is_recording:
                frame = dashcam_manager.recorder.get_preview_frame()
                if frame is not None:
                    # Encode frame to JPEG
                    ret, buffer = cv2.imencode('.jpg', frame)
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                time.sleep(1/30)  # 30 FPS

        return Response(
            generate_frames(),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )
    except Exception as e:
        app.logger.error(f"Error in preview stream: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashcam/latest-chunk', methods=['GET'])
def get_latest_chunk():
    """Get latest recorded chunk URL"""
    try:
        if not dashcam_manager.is_recording:
            return jsonify({
                'status': 'error',
                'message': 'Not recording'
            }), 400

        latest = dashcam_manager.get_latest_chunk()
        if latest:
            return jsonify({
                'status': 'success',
                'data': {
                    'video_url': f"{ipfs_handler.ipfs_gateway}/ipfs/{latest['video_cid']}",
                    'metadata_url': f"{ipfs_handler.ipfs_gateway}/ipfs/{latest['metadata_cid']}",
                    'sequence_number': latest['sequence_number']
                }
            })
        return jsonify({
            'status': 'error',
            'message': 'No chunks available'
        }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/dashcam/upload', methods=['POST'])
def upload_dashcam_video():
    video_path = None
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400
            
        video_file = request.files['video']
        wallet_address = request.form.get('wallet_address')
        sequence_number = int(request.form.get('sequence_number', 0))
        session_id = request.form.get('session_id')
        is_first_chunk = request.form.get('is_first_chunk') == 'true'
        is_last_chunk = request.form.get('is_last_chunk') == 'true'
        
        if not video_file.filename or not wallet_address:
            return jsonify({'error': 'Missing required data'}), 400

        # Validate wallet address format
        if not wallet_address.startswith('0x') or len(wallet_address) != 42:
            return jsonify({'error': 'Invalid wallet address format'}), 400

        # Create uploads directory if it doesn't exist
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        # Save video file locally with unique name
        timestamp = int(time.time())
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], f'dashcam_{timestamp}.webm')
        video_file.save(video_path)
        
        # Start new session if this is the first chunk
        if is_first_chunk:
            session_id = blockchain_handler.start_video_session()
            logger.info(f"Started new video session: {session_id}")
        elif not session_id:
            logger.error("Missing session_id for non-first chunk")
            return jsonify({'error': 'Missing session_id for non-first chunk'}), 400
        else:
            try:
                session_id = int(session_id)
                # Verify session exists and is active
                if not blockchain_handler.contract.functions.isSessionActive(session_id).call():
                    logger.error(f"Session {session_id} is not active")
                    return jsonify({'error': f'Session {session_id} is not active'}), 400
            except ValueError:
                logger.error(f"Invalid session_id format: {session_id}")
                return jsonify({'error': 'Invalid session_id format'}), 400
        
        # Upload to IPFS and get CID
        video_cid = ipfs_handler.add_file(video_path)
        if not video_cid:
            raise Exception("Failed to upload to IPFS")
            
        # Create metadata for this chunk
        metadata = {
            "timestamp": timestamp,
            "sequence_number": sequence_number,
            "source": "dashcam",
            "content_type": "video/webm",
            "video_url": f"ipfs://{video_cid}",
            "session_id": session_id
        }
        metadata_cid = ipfs_handler.add_json(metadata)
        
        # Add chunk to session
        try:
            blockchain_handler.add_video_chunk(
                session_id,
                sequence_number,
                video_cid,
                metadata_cid,
                timestamp
            )
            logger.info(f"Added video chunk {sequence_number} to session {session_id}")
        except Exception as e:
            logger.error(f"Failed to add chunk to session: {str(e)}")
            raise
        
        # End session if this is the last chunk
        if is_last_chunk:
            try:
                blockchain_handler.end_video_session(session_id)
                logger.info(f"Ended video session: {session_id}")
            except Exception as e:
                logger.error(f"Failed to end session: {str(e)}")
                raise
        
        # Clean up local file after successful upload
        if os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"Cleaned up local file: {video_path}")
        
        return jsonify({
            'message': 'Video uploaded successfully',
            'cid': video_cid,
            'session_id': session_id,
            'sequence_number': sequence_number
        }), 200
        
    except Exception as e:
        logger.error(f"Error uploading video: {str(e)}")
        # Clean up local file in case of error
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"Cleaned up local file after error: {video_path}")
        return jsonify({'error': str(e)}), 500

@app.route('/video-sessions/<wallet_address>', methods=['GET'])
def get_video_sessions(wallet_address):
    """Get all video sessions for a wallet"""
    try:
        # Get sessions from blockchain
        sessions = blockchain_handler.get_video_sessions(wallet_address)
        
        # Enhance session data with IPFS metadata
        for session in sessions:
            for chunk in session['chunks']:
                # Get metadata from IPFS
                metadata = ipfs_handler.get_json(chunk['metadata_cid'])
                chunk.update(metadata)
                
                # Add IPFS gateway URL
                chunk['video_url'] = f"https://ipfs.io/ipfs/{chunk['video_cid']}"
        
        return jsonify({
            'success': True,
            'sessions': sessions
        })
        
    except Exception as e:
        logger.error(f"Failed to get video sessions: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def cleanup():
    """Cleanup resources on shutdown"""
    try:
        camera.cleanup()
        ipfs_handler.cleanup()
        logger.info("Cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")

if __name__ == "__main__":
    try:
        # Create required directories
        Path("captures").mkdir(exist_ok=True)
        
        # Start the Flask app
        port = int(os.getenv('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=not IS_RASPBERRY_PI)
    finally:
        cleanup() 