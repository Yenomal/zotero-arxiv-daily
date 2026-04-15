from .base import BaseSink
from ..construct_email import render_email
from ..utils import send_email


class EmailSink(BaseSink):
    def deliver(self, papers):
        email_content = render_email(papers)
        send_email(self.config, email_content)
