import struct
import os
import hashlib
from typing import Dict, Union, Optional, TypedDict

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.exceptions import InvalidTag

class HexHeaderDict(TypedDict):
    algo_id: int
    salt: bytes
    iv: bytes
    encrypted_dek: bytes
    stored_checksum: bytes
    body_start: int

class HexHeader:
    """
    Defines the binary header structure for HexCore encrypted files (.hxc).
    
    The header contains metadata required for decryption, including the
    algorithm used, salt for key derivation, initialization vectors,
    the encrypted Data Encryption Key (DEK), and a checksum of the body.
    
    Structure (114 Bytes):
    - Magic (4b): File signature 'HEXC'.
    - Version (1b): Format version.
    - Algo (1b): Algorithm ID (0=AES, 1=ChaCha20).
    - Salt (16b): Random salt for KDF.
    - IV (12b): Nonce for the Key Encryption Key (AES-GCM).
    - Encrypted DEK (48b): The DEK encrypted with KEK (32b key + 16b tag).
    - Checksum (32b): SHA-256 hash of the encrypted body.
    """
    
    MAGIC: bytes = b'HEXC'
    VERSION: int = 1
    
    ALGO_AES: int = 0
    ALGO_CHACHA: int = 1
    
    # Size calculation: 4 + 1 + 1 + 16 + 12 + 48 + 32 = 114 bytes
    HEADER_SIZE: int = 114

    def __init__(self) -> None:
        """Initialize a new header with cryptographically strong random values."""
        self.salt: bytes = os.urandom(16)
        # NIST recommends 96-bit (12-byte) IV for AES-GCM to avoid extra processing
        self.iv: bytes = os.urandom(12) 

    def pack(self, algo_id: int, encrypted_dek: bytes, body_checksum: bytes) -> bytes:
        """
        Serialize the header fields into a binary bytes object.

        Args:
            algo_id (int): The encryption algorithm identifier.
            encrypted_dek (bytes): The encrypted DEK (including authentication tag).
            body_checksum (bytes): SHA-256 hash of the ciphertext body.

        Returns:
            bytes: The packed binary header.
        """
        # Format string: Little-endian
        # 4s: Magic, B: Version, B: Algo, 16s: Salt, 12s: IV, 48s: Enc DEK, 32s: Checksum
        header_fmt = f'<4sBB16s12s{len(encrypted_dek)}s32s'
        
        return struct.pack(
            header_fmt,
            self.MAGIC,
            self.VERSION,
            algo_id,
            self.salt,
            self.iv,
            encrypted_dek,
            body_checksum
        )

    @staticmethod
    def unpack(file_bytes: bytes) -> HexHeaderDict:
        """
        Parse a binary header from the beginning of a file.

        Args:
            file_bytes (bytes): The raw bytes read from the file start.

        Returns:
            Dict: A dictionary containing parsed header fields.

        Raises:
            ValueError: If the magic bytes do not match or data is truncated.
        """
        if len(file_bytes) < HexHeader.HEADER_SIZE:
            raise ValueError("INVALID FILE: Header truncated or insufficient data.")

        if file_bytes[:4] != HexHeader.MAGIC:
            raise ValueError("INVALID FILE: Missing HexCore signature.")
        
        magic, ver, algo, salt, iv, enc_dek, checksum = struct.unpack(
            '<4sBB16s12s48s32s', 
            file_bytes[:HexHeader.HEADER_SIZE]
        )
        
        return {
            "algo_id": algo,
            "salt": salt,
            "iv": iv,
            "encrypted_dek": enc_dek,
            "stored_checksum": checksum,
            "body_start": HexHeader.HEADER_SIZE
        }

class EncryptionManager:
    """
    Handles the cryptographic operations for file encryption, decryption, 
    and integrity verification.
    
    Implements a hybrid encryption scheme:
    1. A random Data Encryption Key (DEK) is generated.
    2. The file body is encrypted with the DEK using a stream cipher (AES-CTR or ChaCha20).
    3. The ciphertext body is hashed (SHA-256).
    4. The DEK is encrypted (wrapped) using a Key Encryption Key (KEK) derived from the user's password.
    5. The wrapping uses AES-GCM, with the body hash as Associated Data (AAD).
    
    This binds the integrity of the file body to the validity of the key decryption.
    """

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """
        Derive a 256-bit Key Encryption Key (KEK) from the password using Argon2id.

        Args:
            password (str): The user's password.
            salt (bytes): A random 16-byte salt.

        Returns:
            bytes: The derived 32-byte key.
        """
        # Argon2id is memory-hard, making GPU/ASIC attacks expensive.
        # Parameters chosen for a balance of security and interactive performance.
        kdf = Argon2id(
            salt=salt, 
            length=32, 
            iterations=1, 
            lanes=4, 
            memory_cost=65536, # 64MB RAM
            ad=None, 
            secret=None
        )
        return kdf.derive(password.encode())

    def encrypt_file(self, file_path: str, password: str, algo_id: int = HexHeader.ALGO_AES) -> str:
        """
        Encrypt a file and save it with a .hxc extension.

        Args:
            file_path (str): Path to the plaintext file.
            password (str): Password to secure the file.
            algo_id (int): Algorithm choice (0=AES-256-CTR, 1=ChaCha20).

        Returns:
            str: The path to the created encrypted file, or an error message.
        """
        new_path: Optional[str] = None

        try:
            # Pre-check: Ensure file exists and isn't already encrypted
            if not os.path.exists(file_path):
                return "ERROR: File not found."

            with open(file_path, 'rb') as f:
                # Peek at the first 4 bytes to check for magic signature
                if f.read(4) == HexHeader.MAGIC:
                    return "ERROR: File is already encrypted"
        except (IOError, OSError):
            return "ERROR: Could not read file."

        # 1. Generate Data Encryption Key (DEK)
        # AES-GCM key generation ensures high entropy.
        if algo_id == HexHeader.ALGO_AES:
            dek = AESGCM.generate_key(bit_length=256)
        else:
            dek = os.urandom(32)

        try:
            new_path = f"{file_path}.hxc"
            
            # 2. Encrypt Body & Calculate Checksum
            # We write to a temporary file structure.
            with open(file_path, 'rb') as in_f, open(new_path, 'wb') as out_f:
                # Reserve space for the header at the beginning of the file
                out_f.seek(HexHeader.HEADER_SIZE)
                
                # Generate a random IV for the stream cipher body
                body_iv = os.urandom(16)
                out_f.write(body_iv)
                
                # Initialize the stream cipher
                if algo_id == HexHeader.ALGO_AES:
                    cipher = Cipher(algorithms.AES(dek), modes.CTR(body_iv))
                else:
                    cipher = Cipher(algorithms.ChaCha20(dek, body_iv), mode=None)
                
                encryptor = cipher.encryptor()
                hasher = hashlib.sha256()
                
                # The IV is part of the data integrity scope
                hasher.update(body_iv)
                
                # Process file in chunks to handle large files memory-efficiently
                while True:
                    chunk = in_f.read(65536) # 64KB chunks
                    if not chunk:
                        break
                    
                    enc_chunk = encryptor.update(chunk)
                    out_f.write(enc_chunk)
                    hasher.update(enc_chunk) # Hash the ciphertext, not plaintext
                
                # Finalize encryption
                final_chunk = encryptor.finalize()
                out_f.write(final_chunk)
                hasher.update(final_chunk)
                
                checksum = hasher.digest()

                # 3. Key Wrapping (Encrypt the DEK)
                header = HexHeader()
                kek = self._derive_key(password, header.salt)
                aes_wrapper = AESGCM(kek)
                
                # Bind the body checksum to the key encryption.
                # If the body is tampered with, the checksum changes.
                # If the checksum changes, the DEK cannot be unwrapped (tag mismatch).
                encrypted_dek = aes_wrapper.encrypt(header.iv, dek, associated_data=checksum)
                
                header_bytes = header.pack(algo_id, encrypted_dek, checksum)
                
                # Write the header to the reserved space at the start
                out_f.seek(0)
                out_f.write(header_bytes)
                
            return new_path

        except Exception as e:
            # Cleanup partial file on crash
            if new_path and os.path.exists(new_path):
                try:
                    os.remove(new_path)
                except OSError:
                    pass
            return f"ENCRYPTION FAILED: {str(e)}"

    def decrypt_file(self, file_path: str, password: str) -> str:
        """
        Decrypt a .hxc file.

        Args:
            file_path (str): Path to the encrypted file.
            password (str): Password to unlock the file.

        Returns:
            str: "SUCCESS" or an error message.
        """
        orig_path: Optional[str] = None
        
        try:
            # Read the header first
            with open(file_path, 'rb') as f:
                header_bytes = f.read(HexHeader.HEADER_SIZE)
                
            info = HexHeader.unpack(header_bytes)
            
            # 1. Unwrap the Key (DEK)
            try:
                kek = self._derive_key(password, info['salt'])
                aes_wrapper = AESGCM(kek)
                
                # Attempt to decrypt the DEK.
                # This verifies the password AND the integrity of the body checksum simultaneously.
                dek = aes_wrapper.decrypt(
                    info['iv'], 
                    info['encrypted_dek'], 
                    associated_data=info['stored_checksum']
                )
            except InvalidTag:
                return "WRONG PASSWORD OR TAMPERED HEADER"
            
            # Determine output filename
            if file_path.endswith(".hxc"):
                orig_path = file_path[:-4]
            else:
                orig_path = f"{file_path}.decrypted"
            
            # 2. Decrypt Body
            with open(file_path, 'rb') as in_f, open(orig_path, 'wb') as out_f:
                in_f.seek(info['body_start'])
                
                # Read the Body IV
                body_iv = in_f.read(16)
                
                if info['algo_id'] == HexHeader.ALGO_AES:
                    cipher = Cipher(algorithms.AES(dek), modes.CTR(body_iv))
                else:
                    cipher = Cipher(algorithms.ChaCha20(dek, body_iv), mode=None)
                    
                decryptor = cipher.decryptor()
                hasher = hashlib.sha256()
                
                hasher.update(body_iv)
                
                while True:
                    chunk = in_f.read(65536)
                    if not chunk:
                        break
                    
                    # Hash the ciphertext as we read it to verify integrity later
                    hasher.update(chunk)
                    
                    dec_chunk = decryptor.update(chunk)
                    out_f.write(dec_chunk)
                
                final_chunk = decryptor.finalize()
                out_f.write(final_chunk)
            
            # 3. Verify Body Integrity
            # Compare the hash of the ciphertext we just read against the checksum in the header.
            if hasher.digest() != info['stored_checksum']:
                # Security failure: Delete the potentially dangerous output file
                if os.path.exists(orig_path):
                    os.remove(orig_path)
                return "ERROR: INTEGRITY CHECK FAILED (BODY CORRUPTED)"

            return "SUCCESS"
            
        except ValueError as ve:
            return str(ve)
        except Exception as e:
            # Cleanup partial file on crash
            if orig_path and os.path.exists(orig_path):
                try:
                    os.remove(orig_path)
                except OSError:
                    pass
            return f"DECRYPTION ERROR: {str(e)}"

    def verify_integrity(self, file_path: str) -> str:
        """
        Verify the structural integrity of an encrypted file without decrypting it.
        
        This calculates the hash of the file body and compares it to the 
        checksum stored in the header.

        Args:
            file_path (str): Path to the .hxc file.

        Returns:
            str: "INTEGRITY OK", "CORRUPTED", or "INVALID FILE".
        """
        try:
            with open(file_path, 'rb') as f:
                header_data = f.read(HexHeader.HEADER_SIZE)
                
                if len(header_data) < HexHeader.HEADER_SIZE:
                    return "INVALID FILE"

                if header_data[:4] != HexHeader.MAGIC:
                    return "INVALID FILE"

                info = HexHeader.unpack(header_data)
                stored_hash = info['stored_checksum']
                
                hasher = hashlib.sha256()
                
                # Ensure we are at the start of the body
                f.seek(HexHeader.HEADER_SIZE)
                
                # Read and hash the entire body (ciphertext)
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    hasher.update(chunk)
                
                calculated_hash = hasher.digest()
            
            if stored_hash == calculated_hash:
                return "INTEGRITY OK"
            else:
                return "CORRUPTED"
        except (IOError, OSError):
            return "ERROR READING FILE"
        except Exception:
            return "INVALID FILE"
