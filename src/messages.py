import contextlib
import email.message
import email.mime.text
import email.utils
import uuid

from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import deferred, undefer_group

from .db import db
from .settings import Settings
from .utils import as_bytes
from .base import BaseModel, BaseEnum

class EmailProviders(BaseEnum):
    """Enum representing our available email providers to send emails with"""
    sendgrid = 'sendgrid'
    smtp = 'smtp'


class EmailStatuses(BaseEnum):
    """Enum representing our available email statuses"""
    queued = 'queued'
    sent = 'sent'
    processing = 'processing'
    failed = 'failed'

class RecipientTypes(BaseEnum):
    """Enum representing the available types of recipients of an Message"""
    to = 'to'
    cc = 'cc'
    bcc = 'bcc'

class Message(db.Model, BaseModel):
    """Database representation of a single email message"""

    # Unique id in our data for this email, UUIDv4
    # Example:
    # >>> uuid.uuid4()
    # UUID('64d9a533-888a-4dac-865e-7909025847e3')
    id = db.Column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True)

    # Email message line length limits:
    #   https://tools.ietf.org/html/rfc2822.html#section-2.1.1
    # Max of 998 characters, but recommended at 78 characters to ensure compatibility with email clients UI

    # Email message id, used for `Message-ID:` headers
    # Example:
    # >>> email.utils.make_msgid(domain='workstride.com')
    # '<152537373666.26579.17277507593390454674@workstride.com>'
    msgid = db.Column(db.String(length=128), nullable=False, unique=True)

    # Email message subject line
    subject = db.Column(db.String(length=200), nullable=False)

    # Email provider used to send the email
    # e.g. `sendgrid`, `smtp`, etc
    provider = db.Column(ENUM(EmailProviders), nullable=False)

    # Whether this is a test email that should not actually be sent
    sandbox = db.Column(db.Boolean(), default=False, nullable=False)

    # Email message content, at least one of text or html should be set, both is also acceptable
    # TODO: How do we enforce that at least one of these is set before model persistence
    text = deferred(db.Column(db.Text(), nullable=True), group='content')
    html = deferred(db.Column(db.Text(), nullable=True), group='content')

    from_email = db.Column(db.Integer, db.ForeignKey('address.address_id'), nullable=False)
    from_ = db.relationship('Address')

    # The time the message was successfully sent
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Current email status
    # e.g. `queued`, `sent`
    status = db.Column(ENUM(EmailStatuses), nullable=False)

    # Processing/locking
    locked_by = db.Column(UUID(as_uuid=True), default=None, nullable=True)

    company_id = db.Column(db.Integer(), nullable=True)

    entity_id = db.Column(db.String(length=256), nullable=True)
    entity_type = db.Column(db.String(length=256), nullable=True)
    migration_info = db.Column(db.String(length=100), nullable=True)
    id_old = db.Column(db.Integer(), nullable=True)

    # The files attached to this email
    attachments = db.relationship('Attachment', back_populates='message', cascade='save-update, merge, delete')

    # The email addresses who should receive this email
    # DEV: This is a list of all recipients (`to`, `cc`, `bcc`) merged together
    _recipients = db.relationship('Recipient', back_populates='message', cascade='save-update, merge, delete')

    # TODO: add the following columns
    #   - tags - mapping? list?

    def __init__(self, id=None, msgid=None, *args, **kwargs):
        """Constructor used to ensure sane default/required values are configured"""
        if id is None:
            id = uuid.uuid4()

        if msgid is None:
            # >>> email.utils.make_msgid(domain='workstride.com')
            # '<152537373666.26579.17277507593390454674@workstride.com>'
            msgid = email.utils.make_msgid(domain=Settings.EMAIL_MSGID_DOMAIN)
        super(Message, self).__init__(id=id, msgid=msgid, *args, **kwargs)

    def add_recipient(self, recipient):
        existing = [r for r in self._recipients if r.type_ == recipient.type_ and r.address == recipient.address]
        if len(existing) == 0:
            self._recipients.append(recipient)

    @property
    def to(self):
        return [r.address for r in self._recipients if r.type_ == RecipientTypes.to]

    @property
    def cc(self):
        return [r.address for r in self._recipients if r.type_ == RecipientTypes.cc]

    @property
    def bcc(self):
        return [r.address for r in self._recipients if r.type_ == RecipientTypes.bcc]

    def get_size(self):
        msg = self.as_email_message()
        return len(as_bytes(msg))

    def as_light_dict(self):
        data = dict(
            id=self.id,
            status=self.status.value,
        )

        return data


    def as_dict(self, include_attachment_data=False, include_content=True):
        """Helper method to get this Message as a dict"""
        data = dict(
            id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            bcc=[a.as_dict() for a in self.bcc],
            cc=[a.as_dict() for a in self.cc],
            msgid=self.msgid,
            provider=self.provider.value,
            sent_at=self.sent_at,
            status=self.status.value,
            subject=self.subject,
            to=[a.as_dict() for a in self.to],
            sandbox=self.sandbox,
            attachments=[
                attachment.as_dict(include_data=include_attachment_data)
                for attachment in self.attachments
            ],
            entity_id=self.entity_id,
            entity=self.entity_type,
            company_id=self.company_id,
        )
        data['from'] = self.from_.as_dict()

        # Only include text/html data if we requested it
        if include_content:
            data['content'] = dict(
                text=self.text,
                html=self.html,
            )

        return data

    def as_email_message(self):
        """Helper method to get this Message as an email.message.EmailMessage"""
        msg = email.message.EmailMessage()
        msg.make_alternative()
        msg['Message-ID'] = self.msgid
        msg['Subject'] = self.subject
        msg['To'] = [addr.as_header() for addr in self.to]
        msg['Cc'] = [addr.as_header() for addr in self.cc]
        msg['Bcc'] = [addr.as_header() for addr in self.bcc]
        msg['From'] = self.from_.as_header()

        if self.text:
            msg.attach(email.mime.text.MIMEText(self.text, 'plain'))
        if self.html:
            msg.attach(email.mime.text.MIMEText(self.html, 'html'))

        for attachment in self.attachments:
            maintype, _, subtype = attachment.content_type.partition('/')
            part = email.mime.base.MIMEBase(maintype, subtype)
            part.set_payload(attachment.get_data())
            email.encoders.encode_base64(part)
            part.add_header('Content-Disposition', attachment.content_disposition)
            msg.attach(part)

        return msg

    @contextlib.contextmanager
    def lock(self):
        """
        Helper method to obtain a lock on this message for processing

        Example:

          with message.lock():
              # process the message
        """
        lock_id = uuid.uuid4()

        # Try to obtain the lock on this message
        #   - Set locked_by to our `lock_id`
        #   - If there isn't already a lock on this message
        #   - Return the lock id we set to ensure it is ours
        row = db.engine.execute(
            ('UPDATE message '
             f'SET locked_by = \'{str(lock_id)}\' '
             f'WHERE id = \'{str(self.id)}\' AND locked_by IS NULL '
             'RETURNING locked_by'),
        ).fetchone()
        if not row or len(row) != 1:
            raise TypeError(f'Expected Message.lock response to be a single item tuple, instead got {row!r}')

        if row[0] != lock_id:
            raise Exception(f'Could not obtain lock on message {str(self.id)!r}')

        try:
            # Set `locked_by` for this instance.
            # DEV: We don't need to commit, because it is already set from query above
            self.locked_by = lock_id

            # Yield to the caller
            yield
        finally:
            # Release the lock
            db.engine.execute(f'UPDATE message SET locked_by = NULL WHERE id = \'{str(self.id)}\'')

    @classmethod
    def find_by_id(cls, id, include_content=True):
        """
        Helper for finding a specific Message by id

        This helper is a wrapper around Message.query.get(<id>) but we test to ensure
        the id is a valid UUID first, otherwise we will get a SQL error
        """
        # Attempt to convert the id to a `uuid.UUID` if it is not already
        if not isinstance(id, uuid.UUID):
            try:
                id = uuid.UUID(id)
            except ValueError:
                return None

        query = cls.query
        # Only fetch 'html' and 'text' columns if requested
        if include_content:
            query = query.options(undefer_group('content'))
        return query.get(id)
