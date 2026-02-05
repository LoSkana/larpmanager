"""Integration tests for email sending system."""

from unittest.mock import Mock, patch

import pytest

from larpmanager.utils.email import EmailConnectionFactory, SESEmailBackend, SMTPEmailBackend
from larpmanager.utils.larpmanager.tasks import (
    _build_email_message,
    _prepare_email_metadata,
    my_send_simple_mail,
)


class TestEmailMetadataPreparation:
    """Tests for email metadata extraction."""

    @pytest.mark.django_db
    def test_prepare_metadata_default(self):
        """Test metadata preparation with no config."""
        metadata = _prepare_email_metadata(None, None, None)

        assert metadata['sender_email'] == 'info@larpmanager.com'
        assert metadata['sender_name'] == 'LarpManager'
        assert metadata['headers']['List-Unsubscribe'] == '<mailto:info@larpmanager.com>'
        assert metadata['bcc_recipients'] == []

    @pytest.mark.django_db
    def test_prepare_metadata_with_reply_to(self):
        """Test metadata preparation with reply-to header."""
        metadata = _prepare_email_metadata(None, None, 'reply@example.com')

        assert metadata['headers']['Reply-To'] == 'reply@example.com'
        assert metadata['headers']['List-Unsubscribe'] == '<mailto:info@larpmanager.com>'

    @pytest.mark.django_db
    def test_prepare_metadata_with_association(self, association_factory):
        """Test metadata preparation with association config."""
        association = association_factory(slug='testassoc', name='Test Association')

        metadata = _prepare_email_metadata(association.id, None, None)

        # Should use association subdomain
        assert metadata['sender_email'] == 'testassoc@larpmanager.com'
        assert metadata['sender_name'] == 'Test Association'
        assert 'testassoc@larpmanager.com' in metadata['headers']['List-Unsubscribe']

    @pytest.mark.django_db
    def test_prepare_metadata_with_association_bcc(self, association_factory):
        """Test metadata includes BCC when association has mail_cc enabled."""
        association = association_factory(slug='testassoc', main_mail='admin@testassoc.com')

        # Mock the config to return True for mail_cc
        with patch.object(association, 'get_config', return_value=True):
            metadata = _prepare_email_metadata(association.id, None, None)

            assert 'admin@testassoc.com' in metadata['bcc_recipients']

    @pytest.mark.django_db
    def test_prepare_metadata_stores_org_main_mail(self, association_factory):
        """Test metadata stores organization main_mail for SES backend."""
        association = association_factory(slug='testassoc', name='Test Org', main_mail='contact@testassoc.com')

        metadata = _prepare_email_metadata(association.id, None, None)

        # Should store org_main_mail in metadata (for SES to use)
        assert metadata.get('org_main_mail') == 'contact@testassoc.com'
        # Should NOT have Reply-To in headers yet (SES will add it)
        assert 'Reply-To' not in metadata['headers']

    @pytest.mark.django_db
    def test_prepare_metadata_custom_reply_to_in_headers(self, association_factory):
        """Test custom reply_to is added to headers."""
        association = association_factory(slug='testassoc', main_mail='contact@testassoc.com')

        metadata = _prepare_email_metadata(association.id, None, 'custom@example.com')

        # Custom reply_to should be in headers
        assert metadata['headers']['Reply-To'] == 'custom@example.com'

    @pytest.mark.django_db
    def test_prepare_metadata_event_overrides_association(self, run_factory, event_factory, association_factory):
        """Test event metadata overrides association metadata."""
        association = association_factory(slug='assoc', name='Association')
        event = event_factory(association=association, name='Test Event')
        run = run_factory(event=event)

        # Mock event config to return SMTP user
        with patch('larpmanager.utils.larpmanager.tasks.get_event_config') as mock_get_config:
            mock_get_config.return_value = 'event@example.com'

            metadata = _prepare_email_metadata(association.id, run.id, None)

            # Should use event sender, not association
            assert metadata['sender_email'] == 'event@example.com'
            assert metadata['sender_name'] == 'Test Event'


class TestEmailMessageBuilding:
    """Tests for email message construction."""

    def test_build_email_message_basic(self):
        """Test building basic email message."""
        metadata = {
            'sender_email': 'from@example.com',
            'sender_name': 'Test Sender',
            'headers': {'Reply-To': 'reply@example.com'},
            'bcc_recipients': [],
        }

        message = _build_email_message(
            subj='Test Subject', body='<p>Test HTML</p>', m_email='to@example.com', metadata=metadata
        )

        assert message.subject == 'Test Subject'
        assert message.to == ['to@example.com']
        assert 'from@example.com' in message.from_email
        assert 'Test Sender' in message.from_email
        assert message.extra_headers['Reply-To'] == 'reply@example.com'
        assert len(message.alternatives) == 1  # HTML alternative

    def test_build_email_message_with_bcc(self):
        """Test building email message with BCC recipients."""
        metadata = {
            'sender_email': 'from@example.com',
            'sender_name': 'Test Sender',
            'headers': {},
            'bcc_recipients': ['bcc1@example.com', 'bcc2@example.com'],
        }

        message = _build_email_message(subj='Test', body='<p>Test</p>', m_email='to@example.com', metadata=metadata)

        assert message.bcc == ['bcc1@example.com', 'bcc2@example.com']

    def test_build_email_message_multipart(self):
        """Test email message has both plain text and HTML versions."""
        metadata = {
            'sender_email': 'from@example.com',
            'sender_name': 'Test',
            'headers': {},
            'bcc_recipients': [],
        }

        html_body = '<p>This is <strong>HTML</strong> content</p>'
        message = _build_email_message(subj='Test', body=html_body, m_email='to@example.com', metadata=metadata)

        # Check plain text body (should have HTML tags removed)
        assert '<p>' not in message.body
        assert '<strong>' not in message.body

        # Check HTML alternative exists
        assert len(message.alternatives) == 1
        assert message.alternatives[0][1] == 'text/html'
        assert html_body in message.alternatives[0][0]

    def test_build_email_message_with_org_main_mail(self):
        """Test email message stores org_main_mail attribute for SES."""
        metadata = {
            'sender_email': 'from@example.com',
            'sender_name': 'Test',
            'headers': {},
            'bcc_recipients': [],
            'org_main_mail': 'org@example.com',
        }

        message = _build_email_message(subj='Test', body='<p>Test</p>', m_email='to@example.com', metadata=metadata)

        # Check org_main_mail attribute is stored
        assert hasattr(message, 'org_main_mail')
        assert message.org_main_mail == 'org@example.com'

    def test_build_email_message_without_org_main_mail(self):
        """Test email message without org_main_mail doesn't have attribute."""
        metadata = {
            'sender_email': 'from@example.com',
            'sender_name': 'Test',
            'headers': {},
            'bcc_recipients': [],
        }

        message = _build_email_message(subj='Test', body='<p>Test</p>', m_email='to@example.com', metadata=metadata)

        # Check org_main_mail attribute is not set
        assert not hasattr(message, 'org_main_mail')


class TestMySendSimpleMail:
    """Integration tests for my_send_simple_mail function."""

    @pytest.mark.django_db
    def test_send_simple_mail_with_default_backend(self):
        """Test sending email with default backend."""
        with patch.object(EmailConnectionFactory, 'get_backend') as mock_get_backend:
            mock_backend = Mock()
            mock_get_backend.return_value = mock_backend

            my_send_simple_mail(
                subj='Test Subject', body='<p>Test Body</p>', m_email='test@example.com', association_id=None, run_id=None
            )

            # Verify backend was retrieved and send was called
            mock_get_backend.assert_called_once_with(None, None)
            mock_backend.send_message.assert_called_once()

            # Verify message properties
            sent_message = mock_backend.send_message.call_args[0][0]
            assert sent_message.subject == 'Test Subject'
            assert sent_message.to == ['test@example.com']

    @pytest.mark.django_db
    def test_send_simple_mail_with_ses_backend(self):
        """Test sending email via SES backend."""
        with patch.object(EmailConnectionFactory, 'get_backend') as mock_get_backend:
            mock_backend = Mock(spec=SESEmailBackend)
            mock_get_backend.return_value = mock_backend

            my_send_simple_mail(subj='Test', body='<p>Test</p>', m_email='test@example.com')

            # Verify SES backend was used
            mock_backend.send_message.assert_called_once()

    @pytest.mark.django_db
    def test_send_simple_mail_custom_smtp_priority(self, association_factory):
        """Test custom SMTP takes priority over SES."""
        association = association_factory()

        # Mock factory to return SMTP backend
        with patch.object(EmailConnectionFactory, 'get_backend') as mock_get_backend:
            mock_smtp_backend = Mock(spec=SMTPEmailBackend)
            mock_get_backend.return_value = mock_smtp_backend

            my_send_simple_mail(
                subj='Test', body='<p>Test</p>', m_email='test@example.com', association_id=association.id
            )

            # Verify backend was called with association_id
            mock_get_backend.assert_called_once_with(association.id, None)
            mock_smtp_backend.send_message.assert_called_once()

    @pytest.mark.django_db
    def test_send_simple_mail_with_reply_to(self):
        """Test email includes Reply-To header."""
        with patch.object(EmailConnectionFactory, 'get_backend') as mock_get_backend:
            mock_backend = Mock()
            mock_get_backend.return_value = mock_backend

            my_send_simple_mail(
                subj='Test', body='<p>Test</p>', m_email='test@example.com', reply_to='reply@example.com'
            )

            # Verify message has Reply-To header
            sent_message = mock_backend.send_message.call_args[0][0]
            assert sent_message.extra_headers['Reply-To'] == 'reply@example.com'

    @pytest.mark.django_db
    def test_send_simple_mail_ses_adds_org_reply_to(self, association_factory):
        """Test SES backend adds org main_mail as Reply-To."""
        association = association_factory(slug='testorg', main_mail='contact@testorg.com')

        with patch.object(EmailConnectionFactory, 'get_backend') as mock_get_backend:
            mock_ses_backend = Mock(spec=SESEmailBackend)
            mock_get_backend.return_value = mock_ses_backend

            my_send_simple_mail(
                subj='Test', body='<p>Test</p>', m_email='test@example.com', association_id=association.id
            )

            # Verify message has org_main_mail attribute
            sent_message = mock_ses_backend.send_message.call_args[0][0]
            assert hasattr(sent_message, 'org_main_mail')
            assert sent_message.org_main_mail == 'contact@testorg.com'

    @pytest.mark.django_db
    def test_send_simple_mail_ses_custom_reply_to_overrides(self, association_factory):
        """Test custom Reply-To overrides org main_mail even with SES."""
        association = association_factory(slug='testorg', main_mail='contact@testorg.com')

        with patch.object(EmailConnectionFactory, 'get_backend') as mock_get_backend:
            mock_ses_backend = Mock(spec=SESEmailBackend)
            mock_get_backend.return_value = mock_ses_backend

            my_send_simple_mail(
                subj='Test',
                body='<p>Test</p>',
                m_email='test@example.com',
                association_id=association.id,
                reply_to='custom@example.com',
            )

            # Verify custom Reply-To is in headers (SES won't override it)
            sent_message = mock_ses_backend.send_message.call_args[0][0]
            assert sent_message.extra_headers['Reply-To'] == 'custom@example.com'

    @pytest.mark.django_db
    def test_send_simple_mail_error_handling(self):
        """Test error handling in send_simple_mail."""
        with patch.object(EmailConnectionFactory, 'get_backend') as mock_get_backend:
            # Mock backend that raises exception
            mock_backend = Mock()
            mock_backend.send_message.side_effect = Exception('SMTP Error')
            mock_get_backend.return_value = mock_backend

            # Mock mail_error function
            with patch('larpmanager.utils.larpmanager.tasks.mail_error') as mock_mail_error:
                with pytest.raises(Exception, match='SMTP Error'):
                    my_send_simple_mail(subj='Test', body='<p>Test</p>', m_email='test@example.com')

                # Verify error handler was called
                mock_mail_error.assert_called_once()


class TestBackendSelection:
    """Integration tests for backend selection logic."""

    @pytest.mark.django_db
    def test_backend_selection_priority_order(self, run_factory, event_factory, association_factory):
        """Test backend selection follows priority order."""
        association = association_factory()
        event = event_factory(association=association)
        run = run_factory(event=event)

        # Test with event SMTP configured
        with patch('larpmanager.utils.email.factory._get_event_smtp_config') as mock_event:
            with patch('larpmanager.utils.email.factory._get_association_smtp_config') as mock_assoc:
                with patch('larpmanager.utils.email.factory._is_ses_configured') as mock_ses:
                    mock_event.return_value = {'host': 'event.smtp.com'}
                    mock_assoc.return_value = {'host': 'assoc.smtp.com'}
                    mock_ses.return_value = True

                    backend = EmailConnectionFactory.get_backend(association.id, run.id)

                    # Should select event SMTP (highest priority)
                    assert isinstance(backend, SMTPEmailBackend)

        # Test with only association SMTP configured
        with patch('larpmanager.utils.email.factory._get_event_smtp_config') as mock_event:
            with patch('larpmanager.utils.email.factory._get_association_smtp_config') as mock_assoc:
                with patch('larpmanager.utils.email.factory._is_ses_configured') as mock_ses:
                    mock_event.return_value = None
                    mock_assoc.return_value = {'host': 'assoc.smtp.com'}
                    mock_ses.return_value = True

                    backend = EmailConnectionFactory.get_backend(association.id, run.id)

                    # Should select association SMTP
                    assert isinstance(backend, SMTPEmailBackend)

        # Test with only SES configured
        with patch('larpmanager.utils.email.factory._get_event_smtp_config') as mock_event:
            with patch('larpmanager.utils.email.factory._get_association_smtp_config') as mock_assoc:
                with patch('larpmanager.utils.email.factory._is_ses_configured') as mock_ses:
                    mock_event.return_value = None
                    mock_assoc.return_value = None
                    mock_ses.return_value = True

                    with patch('larpmanager.utils.email.factory.SESEmailBackend') as mock_ses_backend:
                        backend = EmailConnectionFactory.get_backend(association.id, run.id)

                        # Should create SES backend
                        mock_ses_backend.assert_called_once()
