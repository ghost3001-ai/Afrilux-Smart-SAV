import ssl
from functools import cached_property

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend


class AfriluxSMTPEmailBackend(EmailBackend):
    @cached_property
    def ssl_context(self):
        context = super().ssl_context
        if getattr(settings, "EMAIL_RELAX_X509_STRICT", False):
            strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
            if strict_flag:
                context.verify_flags &= ~strict_flag
        return context
