import os
import shutil
import glob
from typing import Dict, Any, Union, List, Optional

class VaultManager:
    """
    Manages the storage, movement, and organization of encrypted and decrypted files.
    
    This class handles the file system operations required to move files into the 
    secure vault directory and export them back to the user's workspace upon decryption.
    """
    
    VAULT_DIR: str = "HEX_VAULT"
    EXPORT_DIR: str = "HEX_EXPORTS"

    def __init__(self, vault_dir: Optional[str] = None) -> None:
        """
        Initialize the VaultManager.

        Args:
            vault_dir (str, optional): Custom path for the vault directory. 
                                       Defaults to local 'HEX_VAULT'.
        """
        if vault_dir:
            self.VAULT_DIR = vault_dir
        
        # Ensure the vault directory exists to prevent IO errors later
        try:
            os.makedirs(self.VAULT_DIR, exist_ok=True)
        except OSError as e:
            print(f"CRITICAL: Failed to create vault directory: {e}")

    def encrypt_and_store(
        self, 
        original_path: str, 
        engine: Any, 
        password: str, 
        algo_id: int = 0, 
        delete_original: bool = True
    ) -> str:
        """
        Encrypt a file and move the result to the vault.

        Args:
            original_path: Path to the plaintext file.
            engine: The encryption engine instance.
            password: The credentials for encryption.
            algo_id: The algorithm identifier (0=AES, 1=ChaCha20).
            delete_original: Whether to shred the plaintext file after success.

        Returns:
            str: A status message indicating success or specific failure reason.
        """
        # 1. Input Validation
        if not os.path.exists(original_path):
            return "ERROR: File does not exist."
        
        # Security Check: Prevent recursive encryption of the vault itself
        abs_src = os.path.abspath(original_path)
        abs_vault = os.path.abspath(self.VAULT_DIR)
        if abs_src.startswith(abs_vault):
            return "ERROR: File is already in the Vault."

        try:
            # 2. Perform Encryption
            # The engine creates 'filename.ext.hxc' in the same directory as the source.
            encrypted_path = engine.encrypt_file(original_path, password, algo_id)

            # Check for error flags returned by the engine (Legacy API support)
            if encrypted_path.startswith("ERROR:") or encrypted_path.startswith("ENCRYPTION FAILED:"):
                return encrypted_path 

            # 3. Move to Vault
            filename = os.path.basename(encrypted_path)
            dest_path = os.path.join(self.VAULT_DIR, filename)

            # If a file with the same name exists in the vault, overwrite it.
            if os.path.exists(dest_path):
                os.remove(dest_path)
            
            shutil.move(encrypted_path, dest_path)

            # 4. Cleanup Plaintext
            if delete_original:
                try:
                    os.remove(original_path)
                except OSError:
                    return "SUCCESS: Encrypted, but failed to delete original."

            return "SUCCESS: File Encrypted & Moved to Vault"

        except Exception as e:
            return f"VAULT ERROR: {str(e)}"

    def decrypt_vault(
        self, 
        engine: Any, 
        password: str, 
        delete_encrypted: bool = True
    ) -> Union[str, Dict[str, Any]]:
        """
        Batch decrypt all files in the vault.

        Args:
            engine: The encryption engine instance.
            password: The credentials for decryption.
            delete_encrypted: Whether to remove the encrypted file from the vault on success.

        Returns:
            Union[str, Dict]: Error string if empty, otherwise a stats dictionary.
        """
        # Ensure export directory exists
        os.makedirs(self.EXPORT_DIR, exist_ok=True)

        results = {
            "success": 0,
            "failed": 0,
            "errors": []
        }

        vault_files = glob.glob(os.path.join(self.VAULT_DIR, "*.hxc"))

        if not vault_files:
            return "VAULT IS EMPTY"

        for encrypted_file in vault_files:
            try:
                # 1. Decrypt (In-Place)
                # The engine decrypts 'file.hxc' to 'file' in the same directory (the vault).
                status = engine.decrypt_file(encrypted_file, password)

                # Determine expected plaintext filename
                plaintext_path = encrypted_file
                if plaintext_path.endswith(".hxc"):
                    plaintext_path = plaintext_path[:-4]
                
                filename = os.path.basename(plaintext_path)

                if status == "SUCCESS":
                    # 2. Move Plaintext to Export Folder
                    if os.path.exists(plaintext_path):
                        target_path = os.path.join(self.EXPORT_DIR, filename)
                        
                        # Handle filename collisions in the export folder
                        counter = 1
                        base_name, ext = os.path.splitext(filename)
                        while os.path.exists(target_path):
                            target_path = os.path.join(self.EXPORT_DIR, f"{base_name}_{counter}{ext}")
                            counter += 1

                        shutil.move(plaintext_path, target_path)
                        
                        # 3. Cleanup Encrypted File
                        if delete_encrypted:
                            os.remove(encrypted_file)
                            
                        results["success"] += 1
                    else:
                        # Edge case: Engine reported success but file wasn't found
                        results["failed"] += 1
                        results["errors"].append(f"Decryption success but file missing: {filename}")
                else:
                    # Engine reported specific failure (e.g., Wrong Password)
                    results["failed"] += 1
                    results["errors"].append(f"{os.path.basename(encrypted_file)}: {status}")

            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Crash on {os.path.basename(encrypted_file)}: {str(e)}")

        return results