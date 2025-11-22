# LarpManager Python File Summaries

Complete summaries of all Python files in the LarpManager repository (381 files total).

## Root Directory

**conftest.py**: Pytest configuration with fixtures for database setup, browser automation via Playwright, test isolation, and e2e test initialization. Includes database loading from SQL dumps and fixture management.

**manage.py**: Django's command-line utility entry point for administrative tasks. Sets default settings module and executes management commands.

## larpmanager/

**__init__.py**: Package initialization for the main LarpManager Django application.

**apps.py**: Django app configuration that initializes signal handlers for database events and profiler receivers for performance monitoring on application startup.

### larpmanager/accounting/

**__init__.py**: Package initialization for accounting module handling payments, invoices, and financial transactions.

**balance.py**: Member balance calculation utilities. Calculates run accounting with revenue/costs/balance, processes expenses, inflows, outflows, payments, refunds, tokens, credits, and generates association-wide financial reports.

**base.py**: Base accounting utilities and payment gateway integration. Checks registration provisional status, decrypts payment details, and handles pre-save operations for payment and collection accounting items.

**gateway.py**: Payment gateway integration for PayPal, Stripe, Redsys, SumUp, and Satispay. Handles payment form generation, webhook processing, signature verification, and transaction processing for multiple payment providers.

**invoice.py**: Invoice generation and CSV import/export utilities. Verifies payments from CSV uploads against pending invoices and processes received payments with status updates and financial detail tracking.

**member.py**: Member accounting utilities for managing membership fees and credits. Gathers comprehensive accounting info including registration history, payment status, membership fees, donations, collections, and token/credit balances.

**payment.py**: Payment processing and management utilities. Handles payment form creation, fee calculation, invoice generation, gateway integration, payment receipt processing, and accounting item creation for various payment types.

**registration.py**: Registration accounting utilities for ticket pricing and payment calculation. Handles registration fees, discounts, payment schedules, quotas, installments, cancellations, refunds, and comprehensive accounting updates.

**token_credit.py**: Token and credit balance management for member registrations. Automatically applies available tokens/credits to payments, handles overpayments, and maintains member balance tracking across the association.

**vat.py**: VAT calculation utilities for payment accounting. Computes VAT for payments by splitting between ticket and options portions, applying different VAT rates to each based on association configuration.

### larpmanager/admin/

**__init__.py**: Django admin interface configuration package. Automatically imports all admin modules for LarpManager models.

**access.py**: Django admin configuration for access control models including PermissionModule, AssociationRole, AssociationPermission, EventRole, and EventPermission with import/export functionality.

**accounting.py**: Django admin configuration for accounting and payment models. Provides admin interfaces for invoices, accounting items (payments, expenses, inflows, outflows, discounts, donations, collections, memberships, transactions), refunds, and e-invoices.

**associations.py**: Django admin configuration for association and organization models including Association, AssociationConfig, AssociationText, AssociationTranslation, and AssociationSkin with search and filtering capabilities.

**base.py**: Base admin classes for LarpManager models. Provides DefModelAdmin with import/export, CSRFTinyMCEModelAdmin for HTML fields, autocomplete filters, and admin interfaces for Feature, FeatureModule, PaymentMethod, and Log models.

**casting.py**: Django admin configuration for casting-related models including Quest, QuestType, Casting, and CastingAvoid with autocomplete fields and filtering by event, run, and member.

**character.py**: Django admin configuration for character and writing models including Character, CharacterConfig, WritingQuestion, WritingOption, WritingChoice, WritingAnswer, Relationship, AbilityPx, AbilityTypePx, and DeliveryPx with search and filtering.

**events.py**: Django admin configuration for event management models including Event, EventConfig, Run, RunConfig, EventText, PreRegistration, and ProgressStep with association and event filtering capabilities.

**larpmanager.py**: Django admin configuration for LarpManager platform models including FAQ, Tutorials, Guides, Showcase, Profiler, Discover, Reviews, Tickets, and PublisherApiKey with CSRF-aware TinyMCE editors.

**members.py**: Django admin configuration for member-related models including custom User admin, Member, MemberConfig, Membership, VolunteerRegistry, Vote, and Badge with search, filtering, and admin links between related models.

**miscellanea.py**: Django admin configuration for miscellaneous models including Contact, ChatMessage, Album, AlbumImage, Workshop modules/questions/options, HelpQuestion, Warehouse (containers, tags, items, areas, assignments), ShuttleService, Util, PlayerRelationship, Email, and OneTimeContent/Tokens.

**registrations.py**: Django admin configuration for registration-related models including Registration, RegistrationTicket, RegistrationSection, RegistrationQuestion, RegistrationOption, RegistrationChoice, RegistrationAnswer, and RegistrationCharacterRel with inline editing and filtering.

**writing.py**: Django admin configuration for writing and story models including TextVersion, Plot, PlotCharacterRel, Faction, Trait, Handout, HandoutTemplate, Prologue, PrologueType, AssignmentTrait, and SpeedLarp with event and character filtering.

### larpmanager/cache/

**__init__.py**: Package initialization for caching utilities module.

**accounting.py**: Cache utilities for accounting-related data queries and aggregations.

**association.py**: Cache functions for association data including features, config, payment methods, and organizational details.

**association_text.py**: Caching utilities for association custom text content retrieval.

**association_translation.py**: Translation cache management for association-specific i18n overrides.

**button.py**: Cache utilities for navigation button and link generation.

**character.py**: Character data caching functions for efficient retrieval.

**config.py**: Configuration value caching for association, event, run, and member-level settings with Redis support.

**event_text.py**: Event custom text caching utilities.

**feature.py**: Feature flag caching for association and event-level feature availability checks.

**fields.py**: Field metadata caching utilities.

**larpmanager.py**: Platform-level caching for LarpManager global data.

**links.py**: Link generation and caching for sidebar navigation and event links.

**permission.py**: Permission checking cache for association and event-level access control.

**registration.py**: Registration data caching for payment and status calculations.

**rels.py**: Relationship data caching utilities.

**role.py**: Role membership caching for access control.

**run.py**: Run data caching for event instance information.

**skin.py**: Theme and skin caching for visual customization.

**text_fields.py**: Text field content caching.

**wwyltd.py**: "What Would You Like To Do" menu caching utilities.

### larpmanager/forms/

**__init__.py**: Package initialization for Django forms module.

**accounting.py**: Django forms for accounting including invoice submission, payment methods, refund requests, discounts, expenses, donations, collections, and VAT management.

**association.py**: Forms for association management including settings, configurations, text customization, and organizational details.

**base.py**: Base form classes and utilities for LarpManager forms.

**character.py**: Forms for character creation, editing, and management.

**config.py**: Configuration management forms for association, event, run, and member settings.

**event.py**: Event creation and management forms including runs, tickets, registration questions, and event configurations.

**experience.py**: Forms for experience point systems, abilities, and character progression.

**feature.py**: Feature flag management forms.

**larpmanager.py**: Platform-level forms for FAQ, tutorials, guides, and support tickets.

**member.py**: Member profile, registration, and account management forms.

**miscellanea.py**: Miscellaneous forms for albums, workshops, warehouse, shuttle services, and other features.

**registration.py**: Registration forms for event sign-up, ticket selection, payment options, and registration questions.

**utils.py**: Form utility functions and CSRF-aware TinyMCE widget for rich text editing.

**warehouse.py**: Forms for warehouse inventory management.

**writing.py**: Forms for character backgrounds, plots, factions, prologues, and story elements.

### larpmanager/mail/

**__init__.py**: Package initialization for email notification module.

**accounting.py**: Email templates and sending functions for accounting-related notifications.

**base.py**: Base email utilities and template rendering functions.

**member.py**: Member-related email notifications.

**registration.py**: Registration status and payment reminder emails.

**remind.py**: Automated reminder emails for deadlines and events.

### larpmanager/management/commands/

**__init__.py**: Package initialization for Django management commands.

**assocs_mail.py**: Management command to send bulk emails to association members.

**automate.py**: Automated daily tasks including payment checks, deadline reminders, and background processing.

**backup.py**: Database and media backup management command.

**check_payments.py**: Payment verification and processing command.

**dump_test.py**: Export test database fixtures to SQL file.

**export_features.py**: Export feature flags and permissions to JSON fixtures.

**import_features.py**: Import feature flags and permissions from JSON fixtures.

**init_db.py**: Initialize database with default data and test fixtures.

**reset.py**: Reset database to test state with sample data.

**translate.py**: Update translations using DeepL API integration.

**utils.py**: Utility functions for management commands.

### larpmanager/middleware/

**__init__.py**: Package initialization for Django middleware.

**association.py**: Middleware for multi-tenant association context management.

**base.py**: Base middleware classes and utilities.

**broken.py**: Error handling middleware for broken links and missing resources.

**exception.py**: Global exception handling middleware.

**locale.py**: Locale and language detection middleware.

**profiler.py**: Performance profiling middleware for request timing.

**token.py**: Token-based authentication middleware for API access.

**translation.py**: Custom translation middleware for association-specific overrides.

**url.py**: URL access control middleware for permission checking.

### larpmanager/migrations/

All migration files from **0001_initial.py** through **0108_alter_membership_status.py**: Database migration files for Django ORM schema changes. Each migration represents a specific database schema modification including table creation, field additions/modifications, index optimization, and data migrations.

**__init__.py**: Package initialization for migrations directory.

### larpmanager/models/

**__init__.py**: Package initialization that imports all model classes for Django ORM.

**access.py**: Access control models including Feature, PermissionModule, AssociationPermission, AssociationRole, EventPermission, and EventRole for role-based permissions.

**accounting.py**: Accounting models for financial tracking including PaymentInvoice, AccountingItem types (Payment, Transaction, Expense, Outflow, Inflow, Membership, Donation, Collection, Discount, Other), Discount, RefundRequest, Collection, ElectronicInvoice, and RecordAccounting.

**association.py**: Association (organization) models including Association, AssociationConfig, AssociationText, AssociationTranslation, and AssociationSkin for multi-tenant organization management.

**base.py**: Base model classes including BaseModel, Feature, FeatureModule, PaymentMethod, and PublisherApiKey with common fields and utilities.

**casting.py**: Casting and character assignment models including Casting, CastingAvoid, Quest, QuestType, and AssignmentTrait for player-character assignments.

**event.py**: Event models including Event, EventConfig, EventText, Run, RunConfig, ProgressStep, and PreRegistration for LARP event management.

**experience.py**: Experience point system models including AbilityTypePx, AbilityPx, RulePx, and DeliveryPx for character progression tracking.

**form.py**: Dynamic form models including RegistrationQuestion, RegistrationOption, RegistrationChoice, RegistrationAnswer, WritingQuestion, WritingOption, WritingChoice, and WritingAnswer for customizable questionnaires.

**larpmanager.py**: Platform models including LarpManagerFaq, LarpManagerFaqType, LarpManagerTutorial, LarpManagerGuide, LarpManagerShowcase, LarpManagerProfiler, LarpManagerDiscover, LarpManagerReview, and LarpManagerTicket for site management.

**member.py**: Member models including Member (custom user), MemberConfig, Membership, Badge, VolunteerRegistry, Vote, and Log for user account management and organization membership tracking.

**miscellanea.py**: Miscellaneous models including Contact, ChatMessage, Album, AlbumImage, AlbumUpload, WorkshopModule, WorkshopQuestion, WorkshopOption, WorkshopMemberRel, HelpQuestion, WarehouseContainer, WarehouseTag, WarehouseItem, WarehouseArea, WarehouseItemAssignment, ShuttleService, Util, PlayerRelationship, Email, OneTimeContent, and OneTimeAccessToken.

**registration.py**: Registration models including Registration, RegistrationTicket, RegistrationSection, RegistrationCharacterRel, RegistrationInstallment, and RegistrationSurcharge for event sign-up and payment tracking.

**signals.py**: Django signal handlers for model save/delete events, cache invalidation, email notifications, and accounting updates.

**utils.py**: Model utility functions for file paths, unique code generation, and common operations.

**writing.py**: Story and character models including Character, CharacterConfig, Plot, PlotCharacterRel, Faction, Trait, Handout, HandoutTemplate, Prologue, PrologueType, SpeedLarp, TextVersion, and Relationship for narrative content management.

### larpmanager/templatetags/

**__init__.py**: Package initialization for custom Django template tags.

**show_tags.py**: Custom template tags for rendering UI elements, permissions checks, and conditional display logic.

### larpmanager/tests/

**__init__.py**: Package initialization for test suite.

**utils.py**: Test utility functions and helpers.

#### larpmanager/tests/playwright/ (E2E Tests)

**__init__.py**: Package initialization for Playwright end-to-end tests.

**ability_px_test.py**: Tests for ability and experience point system.

**additional_tickets_test.py**: Tests for additional ticket purchases.

**character_your_acc_pay_ticket_link.py**: Tests for character account payment ticket workflow.

**exe_accounting_test.py**: Tests for executive accounting features.

**exe_assoc_role_test.py**: Tests for association role management.

**exe_events_run_test.py**: Tests for event and run management.

**exe_features_all_test.py**: Tests for all executive-level features.

**exe_join_test.py**: Tests for joining associations.

**exe_membership_test.py**: Tests for membership management.

**exe_profile_test.py**: Tests for executive profile features.

**exe_template_copy_campaign.py**: Tests for campaign template copying.

**ghost_plots_secrets_factions_test.py**: Tests for plot, secret, and faction management.

**inventory.py**: Tests for inventory/warehouse system.

**mail_generation_test.py**: Tests for email generation and sending.

**mirror_test.py**: Tests for data mirroring features.

**orga_character_form_test.py**: Tests for organizer character form management.

**orga_event_role_test.py**: Tests for event role management.

**orga_features_all_test.py**: Tests for all organizer-level features.

**orga_form_writing_config.py**: Tests for writing form configuration.

**orga_manual_excel_save_external.py**: Tests for Excel export functionality.

**orga_plot_relationships_reading_test.py**: Tests for plot and relationship reading.

**orga_quest_trait.py**: Tests for quest and trait management.

**orga_reg_form_test.py**: Tests for registration form creation.

**orga_registration_form_test.py**: Tests for registration form handling.

**overpay_upload_membership_prologue.py**: Tests for overpayment handling and membership.

**permance_forms_test.py**: Performance tests for form rendering.

**signup_accounting_test.py**: Tests for signup accounting workflow.

**upload_download_test.py**: Tests for file upload and download.

**user_accounting_test.py**: Tests for user accounting features.

**user_character_form_editor_test.py**: Tests for character form editing.

**user_character_option_reg_ticket.py**: Tests for character options and tickets.

**user_new_ticket_orga_bulk.py**: Tests for bulk ticket creation.

**user_pdf_test.py**: Tests for PDF generation.

**user_registration_form_gift_test.py**: Tests for gift registration forms.

**user_search.py**: Tests for user search functionality.

**user_signup_membership_test.py**: Tests for membership signup.

**user_signup_payment_test.py**: Tests for payment during signup.

**user_signup_simple_test.py**: Tests for simple signup workflow.

**user_ticket.py**: Tests for ticket management.

#### larpmanager/tests/unit/ (Unit Tests)

**__init__.py**: Package initialization for unit tests.

**base.py**: Base test classes and utilities.

**test_accounting_functions.py**: Unit tests for accounting calculation functions.

**test_balance_functions.py**: Unit tests for balance calculation functions.

**test_cache_signals.py**: Unit tests for cache invalidation signals.

**test_common_fiscal_functions.py**: Unit tests for fiscal code and tax calculations.

**test_experience_functions.py**: Unit tests for experience point functions.

**test_gateway_signals.py**: Unit tests for payment gateway signals.

**test_mail_signals.py**: Unit tests for email notification signals.

**test_member_base_functions.py**: Unit tests for member base functions.

**test_member_text_functions.py**: Unit tests for member text processing.

**test_membership_accounting.py**: Unit tests for membership accounting.

**test_model_signals.py**: Unit tests for model signal handlers.

**test_payment_invoice_vat.py**: Unit tests for payment invoice VAT calculations.

**test_registration_functions.py**: Unit tests for registration functions.

**test_registration_signals.py**: Unit tests for registration signals.

**test_signals_basic.py**: Unit tests for basic signal functionality.

**test_text_field_signals.py**: Unit tests for text field signals.

**test_token_credit_functions.py**: Unit tests for token/credit functions.

**test_utility_signals.py**: Unit tests for utility signals.

**test_utils_functions.py**: Unit tests for utility functions.

### larpmanager/urls/

**__init__.py**: Package initialization for URL routing.

**event.py**: URL patterns for public event pages.

**exe.py**: URL patterns for executive (organization-wide) views.

**lm.py**: URL patterns for LarpManager platform pages.

**orga.py**: URL patterns for organizer (event-specific) views.

**sitemap.py**: XML sitemap generation URLs.

**user.py**: URL patterns for user-facing pages.

### larpmanager/utils/

**__init__.py**: Package initialization for utility modules.

#### larpmanager/utils/auth/

**__init__.py**: Package initialization for authentication utilities.

**adapter.py**: Django-allauth adapter for Google SSO integration.

**admin.py**: Admin authentication utilities.

**backend.py**: Custom authentication backends.

**permission.py**: Permission checking utilities and decorators.

#### larpmanager/utils/core/

**__init__.py**: Package initialization for core utilities.

**base.py**: Base utility functions for context, payment details, and common operations.

**codes.py**: Code generation utilities for unique identifiers.

**common.py**: Common utility functions for dates, text processing, and data cleaning.

**context_processors.py**: Django context processors for template rendering.

**exceptions.py**: Custom exception classes.

**paginate.py**: Pagination utilities.

**validators.py**: Custom form and field validators.

#### larpmanager/utils/io/

**__init__.py**: Package initialization for I/O utilities.

**download.py**: File download utilities.

**pdf.py**: PDF generation utilities using ReportLab.

**upload.py**: File upload handling and validation.

#### larpmanager/utils/larpmanager/

**__init__.py**: Package initialization for LarpManager-specific utilities.

**query.py**: Database query optimization utilities.

**tasks.py**: Background task utilities using django4-background-tasks.

**ticket.py**: Ticket generation and management utilities.

**tutorial.py**: Tutorial and onboarding utilities.

#### larpmanager/utils/profiler/

**__init__.py**: Package initialization for profiler utilities.

**receivers.py**: Signal receivers for performance profiling.

**signals.py**: Custom signals for profiling events.

#### larpmanager/utils/services/

**__init__.py**: Package initialization for service layer.

**association.py**: Association management services.

**bulk.py**: Bulk operation services.

**character.py**: Character management services.

**edit.py**: Content editing services.

**einvoice.py**: Electronic invoice generation services.

**event.py**: Event management services.

**experience.py**: Experience point management services.

**miscellanea.py**: Miscellaneous services.

**writing.py**: Writing and story management services.

#### larpmanager/utils/users/

**__init__.py**: Package initialization for user utilities.

**deadlines.py**: Deadline calculation and checking utilities.

**fiscal_code.py**: Italian fiscal code validation and generation.

**member.py**: Member utility functions including badge assignment.

**registration.py**: Registration utility functions.

### larpmanager/views/

**__init__.py**: Package initialization for Django views.

**api.py**: API views for external integrations.

**auth.py**: Authentication views for login, logout, signup.

**base.py**: Base view classes and mixins.

**larpmanager.py**: Platform pages views (FAQ, tutorials, guides).

**manage.py**: Management views for admin operations.

#### larpmanager/views/exe/ (Executive/Organization Views)

**__init__.py**: Package initialization for executive views.

**accounting.py**: Organization-wide accounting views.

**association.py**: Association management views.

**event.py**: Organization event management views.

**member.py**: Organization member management views.

**miscellanea.py**: Miscellaneous organization views.

#### larpmanager/views/orga/ (Organizer/Event Views)

**__init__.py**: Package initialization for organizer views.

**accounting.py**: Event-specific accounting views.

**casting.py**: Character casting and assignment views.

**character.py**: Character management views for events.

**copy.py**: Event/run copying and templating views.

**event.py**: Event editing and configuration views.

**experience.py**: Experience point management views.

**form.py**: Form builder and configuration views.

**member.py**: Event participant management views.

**miscellanea.py**: Miscellaneous event management views.

**pdf.py**: PDF generation views for event materials.

**registration.py**: Registration management views.

**writing.py**: Story and writing management views.

#### larpmanager/views/user/ (User-Facing Views)

**__init__.py**: Package initialization for user views.

**accounting.py**: User payment and balance views.

**casting.py**: User casting preference views.

**character.py**: User character views and forms.

**event.py**: Public event browsing views.

**member.py**: User profile and settings views.

**miscellanea.py**: Miscellaneous user features.

**onetime.py**: One-time content access views.

**pdf.py**: User PDF download views.

**registration.py**: Event registration and signup views.

## main/

**__init__.py**: Package initialization for Django project.

**asgi.py**: ASGI configuration for async server deployment.

**urls.py**: Root URL configuration importing all app URL patterns.

**wsgi.py**: WSGI configuration for production server deployment.

### main/settings/

**__init__.py**: Settings package initialization that loads environment-specific configuration.

**base.py**: Base Django settings shared across all environments including installed apps, middleware, database config, static files, i18n, caching, and third-party integrations.

**dev_sample.py**: Sample development settings template with debug enabled, local database, and development-specific configurations.

**prod_example.py**: Sample production settings template with security hardening, database pooling, Redis caching, and production optimizations.

**test.py**: Test environment settings with in-memory database, disabled migrations for speed, and test-specific configurations.

## scripts/

**analyze_functions.py**: Code analysis script for function complexity metrics.

**prepare_trans.py**: Prepare translation files for DeepL API processing.

**update_trans.py**: Update translation files with DeepL API results.

---

**Total Files**: 381 Python files across 32 directories

**Lines of Code**: ~90,000+ lines total

**Architecture**: Django-based multi-tenant LARP management platform with comprehensive features for events, registrations, accounting, character management, and story development.
