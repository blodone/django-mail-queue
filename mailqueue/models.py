#---------------------------------------------#
#
# Mailer will queue up emails, Try to send them
# and keep track of if they are sent or not.
# Should be executed with a cron job.
#
#---------------------------------------------#
import datetime
import logging

logger = logging.getLogger(__name__)

from django.db import models
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from mailqueue import defaults


class MailerMessageManager(models.Manager):
    def send_queued(self, limit=None):
        if limit is None:
            limit = getattr(settings, 'MAILQUEUE_LIMIT', defaults.MAILQUEUE_LIMIT)

        for email in self.filter(sent=False)[:limit]:
            email.send()


class MailerMessage(models.Model):
    subject = models.CharField(max_length=250, blank=True, null=True)
    to_address = models.EmailField(max_length=250)
    bcc_address = models.EmailField(max_length=250, blank=True, null=True)
    from_address = models.EmailField(max_length=250)
    content = models.TextField(blank=True, null=True)
    html_content = models.TextField(blank=True, null=True)
    app = models.CharField(max_length=250, blank=True, null=True)
    sent = models.BooleanField(default=False, editable=False)
    last_attempt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True, editable=False)

    objects = MailerMessageManager()

    def __unicode__(self):
        return self.subject

    def send(self):
        if not self.sent:
            if getattr(settings, 'USE_TZ', False):
                # This change breaks SQLite usage.
                from django.utils.timezone import utc
                self.last_attempt = datetime.datetime.utcnow().replace(tzinfo=utc)
            else:
                self.last_attempt = datetime.datetime.now()
            try:
                subject, from_email, to = self.subject, self.from_address, self.to_address
                text_content = self.content
                msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
                if self.html_content:
                    html_content = self.html_content
                    msg.attach_alternative(html_content, "text/html")
                if self.bcc_address:
                    if ',' in self.bcc_address:
                        msg.bcc = [ email.strip() for email in self.bcc_address.split(',') ]
                    else:
                        msg.bcc = [self.bcc_address, ]
                msg.send()
                self.sent = True
            except Exception, e:
                logger.error('Mail Queue Exception: %s' % e)
            self.save()

@receiver(post_save, sender=MailerMessage)
def send_post_save(sender, instance, signal, *args, **kwargs):
    if getattr(settings, 'MAILQUEUE_CELERY', defaults.MAILQUEUE_CELERY):
        from mailqueue.tasks import send_mail
        send_mail.delay(instance)
    else:
        instance.send()
