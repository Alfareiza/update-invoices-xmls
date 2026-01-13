from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type

from src.constants import (
    GOOGLE_TOKEN, GOOGLE_REFRESH_TOKEN, GOOGLE_TOKEN_URI, GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET, GOOGLE_SCOPES,
    FACTURAS_PDF, FACTURAS_TMP, XMLS_CAJACOPI, LOGISTICA_GOOGLE_TOKEN, LOGISTICA_GOOGLE_REFRESH_TOKEN,
    LOGISTICA_GOOGLE_CLIENT_ID, LOGISTICA_GOOGLE_CLIENT_SECRET, LOGISTICA_GOOGLE_SCOPES
)

class GoogleDriveLogistica:
    def __init__(self):
        self.creds = Credentials(
            token=LOGISTICA_GOOGLE_TOKEN,
            refresh_token=LOGISTICA_GOOGLE_REFRESH_TOKEN,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=LOGISTICA_GOOGLE_CLIENT_ID,
            client_secret=LOGISTICA_GOOGLE_CLIENT_SECRET,
            scopes=LOGISTICA_GOOGLE_SCOPES
        )
        self.service = build('drive', 'v3', credentials=self.creds)

        self.xmls = XMLS_CAJACOPI
        
    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def create_or_get_folder_id(self, folder_name: str) -> str:
        """
        Gets a folder by name or creates it if it doesn't exist.
        """
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        response = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        if files := response.get('files', []):
            return files[0].get('id')

        file_metadata = {
            'name': folder_name,
            'parents': [self.xmls],
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = self.service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

        
class GoogleDriveFevCajacopi:
    def __init__(self):
        self.creds = Credentials(
            token=GOOGLE_TOKEN,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=GOOGLE_SCOPES
        )
        self.service = build('drive', 'v3', credentials=self.creds)

        self.pdf_procesadas = FACTURAS_PDF
        self.temp = FACTURAS_TMP
        self.xmls = XMLS_CAJACOPI

    def get_facturas_mes_name(self, mes: int, ano: int):
        """"""
        return f"FacturasCajacopi_{ano}{mes:02d}"

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), retry=retry_if_not_exception_type(FileNotFoundError),
           reraise=True)
    def upload_file(self, file_path: Path, folder_id: str = None) -> dict:
        """
        Uploads a file to Google Drive.
        """
        file_metadata = {
            'name': file_path.name,
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, resumable=True)
        return (
            self.service.files()
            .create(body=file_metadata, media_body=media, fields='id')
            .execute()
        )

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def move_file(self, file_id: str, new_folder_id: str) -> dict:
        """
        Moves a file to a different folder in Google Drive.
        """
        file = self.service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        file = self.service.files().update(
            fileId=file_id,
            addParents=new_folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        return file

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def delete_file(self, file_id: str) -> None:
        """
        Deletes a file from Google Drive.
        """
        self.service.files().delete(fileId=file_id).execute()



if __name__ == '__main__':
    from src.config import BASE_DIR

    drive_client = GoogleDriveFevCajacopi()
    drive_client.upload_file(BASE_DIR / 'LGFM1574927_900073223x.zip', drive_client.temp)
