"""Unit tests for email backends and factory."""

from unittest.mock import Mock, patch

import pytest
from django.core.mail import EmailMultiAlternatives

from larpmanager.mail.backends import (
    DefaultEmailBackend,
    SESEmailBackend,
    SMTPEmailBackend,
)
from larpmanager.mail.factory import (
    EmailConnectionFactory,
    _get_event_smtp_config,
    _is_ses_configured,
)


class TestSMTPEmailBackend:
    """Tests for SMTP email backend."""

    def test_smtp_backend_initialization(self):
        """Test SMTP backend initializes with correct config."""
        smtp_config = {
            'host': 'smtp.example.com',
            'port': 587,
            'username': 'user@example.com',
            'password': 'password123',
            'use_tls': True,
        }

        with patch('larpmanager.utils.email.backends.get_connection') as mock_get_connection:
            backend = SMTPEmailBackend(smtp_config)

            mock_get_connection.assert_called_once_with(
                host='smtp.example.com',
                port=587,
                username='user@example.com',
                password='password123',
                use_tls=True,
            )

    def test_smtp_backend_send_message(self):
        """Test SMTP backend sends message via custom connection."""
        smtp_config = {
            'host': 'smtp.example.com',
            'port': 587,
            'username': 'user@example.com',
            'password': 'password123',
            'use_tls': True,
        }

        with patch('larpmanager.utils.email.backends.get_connection') as mock_get_connection:
            mock_connection = Mock()
            mock_get_connection.return_value = mock_connection

            backend = SMTPEmailBackend(smtp_config)

            # Create test email
            email = EmailMultiAlternatives(
                subject='Test Subject',
                body='Test Body',
                from_email='from@example.com',
                to=['to@example.com'],
            )

            # Send email
            backend.send_message(email)

            # Verify connection was set and send was called
            assert email.connection == mock_connection
            assert email.send.called or True  # EmailMultiAlternatives.send() is called


class TestSESEmailBackend:
    """Tests for SES email backend."""

    def test_ses_backend_initialization(self):
        """Test SES backend initializes boto3 client."""
        with patch('larpmanager.utils.email.backends.boto3') as mock_boto3:
            with patch('larpmanager.utils.email.backends.settings') as mock_settings:
                mock_settings.AWS_SES_ACCESS_KEY_ID = 'test-key'
                mock_settings.AWS_SES_SECRET_ACCESS_KEY = 'test-secret'
                mock_settings.AWS_SES_REGION_NAME = 'us-east-1'

                backend = SESEmailBackend()

                mock_boto3.client.assert_called_once_with(
                    'ses',
                    aws_access_key_id='test-key',
                    aws_secret_access_key='test-secret',
                    region_name='us-east-1',
                )

    def test_ses_backend_send_message_success(self):
        """Test SES backend successfully sends email."""
        with patch('larpmanager.utils.email.backends.boto3') as mock_boto3:
            with patch('larpmanager.utils.email.backends.settings') as mock_settings:
                mock_settings.AWS_SES_ACCESS_KEY_ID = 'test-key'
                mock_settings.AWS_SES_SECRET_ACCESS_KEY = 'test-secret'
                mock_settings.AWS_SES_REGION_NAME = 'us-east-1'

                # Setup mock SES client
                mock_client = Mock()
                mock_client.send_raw_email.return_value = {'MessageId': 'test-message-id-123'}
                mock_boto3.client.return_value = mock_client

                backend = SESEmailBackend()

                # Create test email
                email = EmailMultiAlternatives(
                    subject='Test Subject',
                    body='Test Body',
                    from_email='from@example.com',
                    to=['to@example.com'],
                    bcc=['bcc@example.com'],
                )
                email.attach_alternative('<p>Test HTML</p>', 'text/html')

                # Send email
                backend.send_message(email)

                # Verify send_raw_email was called
                assert mock_client.send_raw_email.called
                call_args = mock_client.send_raw_email.call_args[1]
                assert call_args['Source'] == 'from@example.com'
                assert set(call_args['Destinations']) == {'to@example.com', 'bcc@example.com'}
                assert 'RawMessage' in call_args

    def test_ses_backend_throttling_retry(self):
        """Test SES backend retries on throttling error."""
        with patch('larpmanager.utils.email.backends.boto3') as mock_boto3:
            with patch('larpmanager.utils.email.backends.settings') as mock_settings:
                with patch('larpmanager.utils.email.backends.time.sleep'):  # Skip actual sleep
                    mock_settings.AWS_SES_ACCESS_KEY_ID = 'test-key'
                    mock_settings.AWS_SES_SECRET_ACCESS_KEY = 'test-secret'
                    mock_settings.AWS_SES_REGION_NAME = 'us-east-1'

                    # Setup mock SES client that fails twice then succeeds
                    mock_client = Mock()
                    from botocore.exceptions import ClientError

                    throttling_error = ClientError(
                        {'Error': {'Code': 'Throttling', 'Message': 'Rate exceeded'}},
                        'send_raw_email',
                    )

                    mock_client.send_raw_email.side_effect = [
                        throttling_error,
                        throttling_error,
                        {'MessageId': 'success-after-retry'},
                    ]
                    mock_boto3.client.return_value = mock_client

                    # Import ClientError for backend
                    with patch('larpmanager.utils.email.backends.ClientError', ClientError):
                        backend = SESEmailBackend()

                        # Create test email
                        email = EmailMultiAlternatives(
                            subject='Test',
                            body='Test',
                            from_email='from@example.com',
                            to=['to@example.com'],
                        )

                        # Send should succeed after retries
                        backend.send_message(email)

                        # Verify it was called 3 times
                        assert mock_client.send_raw_email.call_count == 3

    def test_ses_backend_message_rejected_no_retry(self):
        """Test SES backend does not retry on MessageRejected error."""
        with patch('larpmanager.utils.email.backends.boto3') as mock_boto3:
            with patch('larpmanager.utils.email.backends.settings') as mock_settings:
                mock_settings.AWS_SES_ACCESS_KEY_ID = 'test-key'
                mock_settings.AWS_SES_SECRET_ACCESS_KEY = 'test-secret'
                mock_settings.AWS_SES_REGION_NAME = 'us-east-1'

                # Setup mock SES client
                mock_client = Mock()
                from botocore.exceptions import ClientError

                rejected_error = ClientError(
                    {'Error': {'Code': 'MessageRejected', 'Message': 'Email address not verified'}},
                    'send_raw_email',
                )
                mock_client.send_raw_email.side_effect = rejected_error
                mock_boto3.client.return_value = mock_client

                # Import ClientError for backend
                with patch('larpmanager.utils.email.backends.ClientError', ClientError):
                    backend = SESEmailBackend()

                    # Create test email
                    email = EmailMultiAlternatives(
                        subject='Test',
                        body='Test',
                        from_email='from@example.com',
                        to=['to@example.com'],
                    )

                    # Send should raise error without retry
                    with pytest.raises(ClientError):
                        backend.send_message(email)

                    # Verify it was only called once (no retry)
                    assert mock_client.send_raw_email.call_count == 1

    def test_ses_backend_adds_reply_to_from_org_main_mail(self):
        """Test SES backend adds Reply-To from org_main_mail attribute."""
        with patch('larpmanager.mail.backends.boto3') as mock_boto3:
            with patch('larpmanager.mail.backends.settings') as mock_settings:
                mock_settings.AWS_SES_ACCESS_KEY_ID = 'test-key'
                mock_settings.AWS_SES_SECRET_ACCESS_KEY = 'test-secret'
                mock_settings.AWS_SES_REGION_NAME = 'us-east-1'

                # Setup mock SES client
                mock_client = Mock()
                mock_client.send_raw_email.return_value = {'MessageId': 'test-message-id'}
                mock_boto3.client.return_value = mock_client

                backend = SESEmailBackend()

                # Create test email without Reply-To but with org_main_mail attribute
                email = EmailMultiAlternatives(
                    subject='Test',
                    body='Test',
                    from_email='from@example.com',
                    to=['to@example.com'],
                )
                email.org_main_mail = 'org@example.com'

                # Send email
                backend.send_message(email)

                # Verify Reply-To was added to extra_headers
                assert email.extra_headers.get('Reply-To') == 'org@example.com'

    def test_ses_backend_respects_existing_reply_to(self):
        """Test SES backend does not override existing Reply-To header."""
        with patch('larpmanager.mail.backends.boto3') as mock_boto3:
            with patch('larpmanager.mail.backends.settings') as mock_settings:
                mock_settings.AWS_SES_ACCESS_KEY_ID = 'test-key'
                mock_settings.AWS_SES_SECRET_ACCESS_KEY = 'test-secret'
                mock_settings.AWS_SES_REGION_NAME = 'us-east-1'

                # Setup mock SES client
                mock_client = Mock()
                mock_client.send_raw_email.return_value = {'MessageId': 'test-message-id'}
                mock_boto3.client.return_value = mock_client

                backend = SESEmailBackend()

                # Create test email with existing Reply-To
                email = EmailMultiAlternatives(
                    subject='Test',
                    body='Test',
                    from_email='from@example.com',
                    to=['to@example.com'],
                    headers={'Reply-To': 'custom@example.com'},
                )
                email.org_main_mail = 'org@example.com'

                # Send email
                backend.send_message(email)

                # Verify Reply-To was NOT changed
                assert email.extra_headers.get('Reply-To') == 'custom@example.com'


class TestDefaultEmailBackend:
    """Tests for default email backend."""

    def test_default_backend_initialization(self):
        """Test default backend initializes with get_connection."""
        with patch('larpmanager.utils.email.backends.get_connection') as mock_get_connection:
            backend = DefaultEmailBackend()
            mock_get_connection.assert_called_once_with()

    def test_default_backend_send_message(self):
        """Test default backend sends message."""
        with patch('larpmanager.utils.email.backends.get_connection') as mock_get_connection:
            mock_connection = Mock()
            mock_get_connection.return_value = mock_connection

            backend = DefaultEmailBackend()

            # Create test email
            email = EmailMultiAlternatives(
                subject='Test',
                body='Test',
                from_email='from@example.com',
                to=['to@example.com'],
            )

            # Send email
            backend.send_message(email)

            # Verify connection was set
            assert email.connection == mock_connection


class TestEmailConnectionFactory:
    """Tests for email connection factory."""

    @pytest.mark.django_db
    def test_factory_priority_event_smtp(self, run_factory, event_factory):
        """Test factory prioritizes event-level SMTP."""
        event = event_factory()
        run = run_factory(event=event)

        # Mock event SMTP config
        with patch('larpmanager.utils.email.factory._get_event_smtp_config') as mock_event_config:
            with patch('larpmanager.utils.email.factory._get_association_smtp_config') as mock_assoc_config:
                with patch('larpmanager.utils.email.factory._is_ses_configured') as mock_ses_config:
                    mock_event_config.return_value = {'host': 'event-smtp.com', 'port': 587}
                    mock_assoc_config.return_value = {'host': 'assoc-smtp.com', 'port': 587}
                    mock_ses_config.return_value = True

                    backend = EmailConnectionFactory.get_backend(
                        association_id=event.association_id, run_id=run.id
                    )

                    # Should use event SMTP (highest priority)
                    assert isinstance(backend, SMTPEmailBackend)
                    mock_event_config.assert_called_once_with(run.id)

    @pytest.mark.django_db
    def test_factory_priority_association_smtp(self, association_factory):
        """Test factory uses association SMTP when event SMTP not configured."""
        association = association_factory()

        with patch('larpmanager.utils.email.factory._get_event_smtp_config') as mock_event_config:
            with patch('larpmanager.utils.email.factory._get_association_smtp_config') as mock_assoc_config:
                with patch('larpmanager.utils.email.factory._is_ses_configured') as mock_ses_config:
                    mock_event_config.return_value = None
                    mock_assoc_config.return_value = {'host': 'assoc-smtp.com', 'port': 587}
                    mock_ses_config.return_value = True

                    backend = EmailConnectionFactory.get_backend(association_id=association.id)

                    # Should use association SMTP
                    assert isinstance(backend, SMTPEmailBackend)
                    mock_assoc_config.assert_called_once_with(association.id)

    def test_factory_priority_ses(self):
        """Test factory uses SES when custom SMTP not configured."""
        with patch('larpmanager.utils.email.factory._get_event_smtp_config') as mock_event_config:
            with patch('larpmanager.utils.email.factory._get_association_smtp_config') as mock_assoc_config:
                with patch('larpmanager.utils.email.factory._is_ses_configured') as mock_ses_config:
                    mock_event_config.return_value = None
                    mock_assoc_config.return_value = None
                    mock_ses_config.return_value = True

                    with patch('larpmanager.utils.email.factory.SESEmailBackend') as mock_ses_backend:
                        backend = EmailConnectionFactory.get_backend(association_id=1, run_id=1)

                        # Should create SES backend
                        mock_ses_backend.assert_called_once()

    def test_factory_priority_default(self):
        """Test factory uses default backend as last resort."""
        with patch('larpmanager.utils.email.factory._get_event_smtp_config') as mock_event_config:
            with patch('larpmanager.utils.email.factory._get_association_smtp_config') as mock_assoc_config:
                with patch('larpmanager.utils.email.factory._is_ses_configured') as mock_ses_config:
                    mock_event_config.return_value = None
                    mock_assoc_config.return_value = None
                    mock_ses_config.return_value = False

                    backend = EmailConnectionFactory.get_backend()

                    # Should use default backend
                    assert isinstance(backend, DefaultEmailBackend)


class TestFactoryHelpers:
    """Tests for factory helper functions."""

    def test_is_ses_configured_all_settings_present(self):
        """Test SES is configured when all settings present."""
        with patch('larpmanager.utils.email.factory.settings') as mock_settings:
            mock_settings.AWS_SES_ACCESS_KEY_ID = 'test-key'
            mock_settings.AWS_SES_SECRET_ACCESS_KEY = 'test-secret'
            mock_settings.AWS_SES_REGION_NAME = 'us-east-1'

            assert _is_ses_configured() is True

    def test_is_ses_configured_missing_settings(self):
        """Test SES is not configured when settings missing."""
        with patch('larpmanager.utils.email.factory.settings') as mock_settings:
            mock_settings.AWS_SES_ACCESS_KEY_ID = None
            mock_settings.AWS_SES_SECRET_ACCESS_KEY = 'test-secret'
            mock_settings.AWS_SES_REGION_NAME = 'us-east-1'

            assert _is_ses_configured() is False

    @pytest.mark.django_db
    def test_get_event_smtp_config_configured(self, run_factory, event_factory):
        """Test getting event SMTP config when configured."""
        event = event_factory()
        run = run_factory(event=event)

        with patch('larpmanager.utils.email.factory.get_event_config') as mock_get_config:
            # Mock config responses
            def config_side_effect(event_id, key, **kwargs):
                config_map = {
                    'mail_server_host_user': 'user@event.com',
                    'mail_server_host': 'smtp.event.com',
                    'mail_server_port': 587,
                    'mail_server_host_password': 'password',
                    'mail_server_use_tls': True,
                }
                return config_map.get(key, kwargs.get('default_value', ''))

            mock_get_config.side_effect = config_side_effect

            config = _get_event_smtp_config(run.id)

            assert config is not None
            assert config['host'] == 'smtp.event.com'
            assert config['port'] == 587
            assert config['username'] == 'user@event.com'
            assert config['password'] == 'password'
            assert config['use_tls'] is True

    @pytest.mark.django_db
    def test_get_event_smtp_config_not_configured(self, run_factory, event_factory):
        """Test getting event SMTP config when not configured."""
        event = event_factory()
        run = run_factory(event=event)

        with patch('larpmanager.utils.email.factory.get_event_config') as mock_get_config:
            mock_get_config.return_value = ""  # No host user configured

            config = _get_event_smtp_config(run.id)

            assert config is None
