import base64
import ssl
from datetime import datetime
from email.utils import formataddr
from pathlib import Path
from typing import List, Dict, Any, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from tenacity import retry, stop_after_attempt, wait_fixed

from src.config import CONFIG, BASE_DIR
from src.constants import LOGI_NIT, GOOGLE_TOKEN, GOOGLE_SCOPES, GOOGLE_REFRESH_TOKEN, GOOGLE_TOKEN_URI, \
    GOOGLE_CLIENT_ID, \
    GOOGLE_CLIENT_SECRET
from src.models.google import EmailMessage


class GmailAPIReader:
    """A class to interact with the Gmail API."""

    def __init__(self) -> None:
        """Initializes the GmailAPIReader with credentials from environment variables."""
        self.creds = Credentials(
            token=GOOGLE_TOKEN,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            # scopes=[scope for scope in GOOGLE_SCOPES if 'gmail' in scope]
            scopes=GOOGLE_SCOPES
        )
        self.service = build('gmail', 'v1', credentials=self.creds)

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def _list_messages(self, query: str, next_page_token: str = None) -> Dict[str, Any]:
        """Lists messages from the user's mailbox."""
        return self.service.users().messages().list(userId='me', q=query, pageToken=next_page_token).execute()

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def _get_message(self, message_id: str, msg_format: str) -> Dict[str, Any]:
        """Gets a specific message from the user's mailbox."""
        return self.service.users().messages().get(userId='me', id=message_id, format=msg_format).execute()

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def _get_attachment(self, message_id: str, attachment_id: str) -> Dict[str, Any]:
        """Gets a specific attachment from a message."""
        return self.service.users().messages().attachments().get(
            userId='me', messageId=message_id, id=attachment_id).execute()

    def read_inbox(self, limit: int) -> List[EmailMessage]:
        """Reads the inbox and returns a list of EmailMessage objects."""
        all_messages = []
        next_page_token = None
        while len(all_messages) < limit:
            results = self._list_messages(
                query=f'is:unread subject:"{LOGI_NIT};LOGIFARMA SAS;"',
                next_page_token=next_page_token
            )
            messages = results.get('messages', [])
            all_messages.extend([EmailMessage(**message) for message in messages])
            next_page_token = results.get('nextPageToken')
            if not next_page_token:
                break
        return all_messages[::-1][:limit]

    def fetch_email_details(self, message: EmailMessage) -> None:
        """Fetches the details of an email and updates the EmailMessage object."""
        msg = self._get_message(message_id=message.id, msg_format='full')
        payload = msg.get('payload', {})
        headers = payload.get('headers', [])

        for header in headers:
            if header['name'] == 'Subject':
                message.subject = header['value']
            if header['name'] == 'To':
                message.recipient = header['value']
            if header['name'] == 'Date':
                message.received_at = datetime.strptime(header['value'], '%a, %d %b %Y %H:%M:%S %z')

        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/html':
                    data = part['body']['data']
                    message.body_html = base64.urlsafe_b64decode(data).decode('utf-8')

    def download_attachment(self, message: EmailMessage) -> Optional[Path]:
        """Downloads the attachment of an email."""
        msg = self._get_message(message_id=message.id, msg_format='full')
        for part in msg['payload']['parts']:
            if part.get('body') and part.get('body').get('attachmentId'):
                attachment = self._get_attachment(message_id=message.id, attachment_id=part['body']['attachmentId'])
                file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
                if message.zip_name:
                    message.attachment_path = CONFIG.DIRECTORIES.TEMP / message.zip_name
                    if message.attachment_path.exists():
                        continue
                    with open(message.attachment_path, 'wb') as f:
                        f.write(file_data)
                    return message.attachment_path
        return None

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def mark_as_read(self, message_id: str) -> None:
        """Marks an email as read."""
        self.service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(1), reraise=True)
    def send(self, body) -> None:
        """"Perform the sent of the email."""
        self.service.users().messages().send(userId="me", body=body).execute()

    def send_email(self, to: str, subject: str, body_vars: Dict[str, Any], cc: Optional[str] = None, bcc: Optional[str] = None, template_path: Optional[str] = None, attachment_file: Optional[Path] = None) -> None:
        """
        Sends an email using a rendered HTML template.

        Args:
            to (str): Recipient email address.
            subject (str): Subject of the email.
            body_vars (Dict[str, Any]): Variables to render in the HTML template.
            cc (Optional[str], optional): CC recipient(s). Defaults to None.
            bcc (Optional[str], optional): BCC recipient(s). Defaults to None.
            template_path (Optional[str], optional): Path to the HTML template. Defaults to a constant if not provided.
            attachment_file (Optional[Path], optional): Path to the attachment file. Defaults to None.

        Raises:
            FileNotFoundError: If the template file does not exist.
            Exception: If sending the email fails.
        """
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        import re

        if template_path is None:
            template_path = BASE_DIR / "src" / "resources" / "error_con_factura.html"

        # if bcc is None:
        #     bcc = Emails.LOGIFARMA_DEV

        template_file = Path(template_path)
        if not template_file.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")
        html_content = template_file.read_text(encoding="utf-8")
        def replace_var(match):
            var_name = match.group(1)
            return str(body_vars.get(var_name, f"${{{var_name}}}"))
        html_body = re.sub(r"\$\{([a-zA-Z0-9_]+)\}", replace_var, html_content)

        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        # message["From"] = formataddr(("Facturas a Mutualser", "fevmutualser@logifarma.co"))
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        message.attach(MIMEText(html_body, "html"))

        if attachment_file.exists():
            from email.mime.application import MIMEApplication
            with open(attachment_file, 'rb') as f:
                part = MIMEApplication(f.read(), Name=attachment_file.name)
            part['Content-Disposition'] = f'attachment; filename="{attachment_file.name}"'
            message.attach(part)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {"raw": raw_message}

        self.send(body)


if __name__ == '__main__':
    gmail_reader = GmailAPIReader()
    if email_messages := gmail_reader.read_inbox(1):
        for email_message in email_messages:
            gmail_reader.fetch_email_details(email_message)
            if not email_message.is_email_before_30_nov_2025:
                continue
            print(f"Processing message ID: {email_message.id}")
            if email_message.soup:
                print("Email body converted to BeautifulSoup object.")

    else:
        print("No new messages found.")

            # attachment_path = gmail_reader.download_attachment(email_message)
            # if attachment_path:
            #     print(f"Attachment downloaded to: {attachment_path}")
