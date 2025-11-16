# LarpManager Feature Descriptions

This document provides concise descriptions of all non-placeholder features in LarpManager, based on code analysis.

## A

### Additional Tickets Feature

Allows participants to reserve extra tickets beyond their own during registration. The number of additional tickets is stored in the registration record and included in capacity calculations, enabling group organizers or parents to handle multiple registrations through a single account.

## B

### Badge Feature

Gamification system for awarding member achievements with public leaderboard. Executives manage badges (create, edit, assign members), while participants view badge catalog and leaderboard. Badges track member associations and display formatted presentations. Leaderboard shows paginated member rankings by badge scores with deterministic daily shuffle. Supports badge descriptions, images, and member collections. Encourages community engagement through visible recognition system.

### Bring Friend Feature

Discount mechanism encouraging participant referrals through the "Friend" discount type. Participants receive special discount codes to share with friends, reducing registration costs for new attendees. Links to the DiscountType.FRIEND enumeration in the discount system. Organizers can set the discount value, maximum redemptions, and track how many times each friend code is used. Helps events grow their player base through word-of-mouth marketing.

## C

### Campaign Feature

Multi-event campaign system enabling shared characters and factions across event series. Parent events copy writing elements to campaign children while maintaining independence. Automatically assigns previous campaign characters to returning participants. Supports character continuity across campaign acts with inheritable element management. Organizers configure parent-child event relationships with selective element inheritance. Enables long-term storytelling with persistent character progression across multiple events.

### Carousel Feature

Homepage carousel display using Event model fields (carousel_img, carousel_thumb, carousel_text). Shows rotating featured events with images and HTML descriptions on organization's calendar/homepage. Part of event appearance configuration to highlight upcoming events with visual appeal.

### Casting Algorithm Feature

Automated character assignment system using sophisticated optimization algorithm. Participants submit ranked character preferences with avoidance lists. Organizers filter by ticket type, membership status, payment status, and factions. Algorithm considers ticket priority, registration dates, payment dates, and configurable weighting to find optimal overall assignments. Handles mirror characters, faction restrictions, character limits per player, and preference padding with unchosen characters.

### Centauri (Easter Egg) Feature

Easter egg feature that randomly displays special content on homepage with configurable probability. When triggered for authenticated users, awards specified badge to member. Used for surprise engagement and gamification. Association configures triggering probability and badge reward. No explicit UI controls.

### Character Customization Feature

Enables participant customization of assigned character attributes including name, pronouns, public information, and other configurable fields. Organizers define which character elements participants can modify through event configuration. Supports approval workflows where customizations require organizer review before becoming visible. Allows personalization while maintaining core character integrity. Configuration accessible via config/custom_character with approval toggle for quality control.

### Character Feature

Manages player characters with comprehensive workflow support. Organizers create/edit characters with name, title, presentation (teaser), and private text. Supports player assignment, status tracking (creation→proposed→review→approved), mirror characters for secret identities, cover images, and faction/plot assignments. Includes customizable writing questions/forms for character creation, external access via secret URLs, and character approval workflows. Characters integrate with plots, factions, relationships, and registration systems. Provides list/edit/view interfaces with version history tracking.

### Chat Feature

Private messaging system enabling participant-to-participant communication without revealing email addresses. Creates bidirectional contact relationships with unread message tracking and last message timestamps. Messages are organized by channel (unique conversation thread) and sorted chronologically. Prevents self-messaging, automatically updates contact records, and maintains message history within association context. Provides simple text-based communication with success notifications.

### Collection Feature

Crowdfunding tool for organizing monetary gifts for members or special purposes. Features two unique codes: contribute_code (for donors) and redeem_code (for recipients). Tracks collection status (Open, Close, Delivered), total amount, organizer, and optional recipient member. Managed via exe_collections. Contributions create AccountingItemCollection entries. Useful for birthday gifts, farewell presents, or community support initiatives within the LARP organization.

### Copy Feature

Allows copying any event element from another event in the same organization. Supports copying event settings, appearance, navigation, features, roles, tickets, registration questions/discounts/quotas/installments/surcharges, characters, factions, quests, prologues, speed larps, plots, handouts, and workshops. Automatically corrects relationships and IDs during copy.

## D

### Deadlines Feature

Provides a centralized dashboard showing all upcoming deadlines across the organization, including payment installments, membership renewals, form submissions, and casting deadlines. Available at both organization-level (exe_deadlines) and event-level (orga_deadlines) views for tracking participant compliance.

### Delegated Accounts Feature

Parent-child account management system enabling users to create fully-managed delegated accounts without separate credentials (e.g., children, multiple personas). Parents can create delegated profiles, switch between accounts bidirectionally, and manage accounting for each. Delegated accounts use generated credentials and link to parent profiles. Supports family memberships while maintaining separate registration tracking. Temporarily disables last-login tracking during account switching.

### Diet Feature

Manages dietary preference collection and display for event participants. Retrieves diet information from non-cancelled registrations exceeding minimum length (3 characters), associates each participant with their assigned characters, and displays formatted character assignments (#number name). Data is sorted alphabetically by participant display name. Helps organizers plan food accommodations by providing comprehensive dietary requirement lists with character context.

### Discount Feature

Flexible discount code system for event registrations. Supports multiple discount types: Standard, Play Again (for returning players), Friend (referral discounts), Influencer, and Gift. Each discount has a unique code, value amount, maximum redemption limit, visibility settings, and optional run restrictions. Organizers can create unlimited-use or limited-quantity discounts, control whether they apply only to new registrations or existing ones, and track usage through orga_discounts view.

### Donation Feature

Organization-wide donation tracking system for monetary contributions outside event registrations. Managed through AccountingItemDonation model with member attribution, description, value, and timestamps. Accessible via exe_donations view for organization executives. Integrates into annual balance calculations and financial reporting. Donations use PaymentType.DONATE classification and can be linked to payment invoices. Supports event funding and general operational expenses.

### Dynamic Rates Feature

Implements a dynamic installment system where the total registration fee is automatically split into multiple payments. The number of quotas and surcharges are calculated based on days remaining until the event, with availability thresholds determining when each rate tier becomes active.

## E

### Event Feature

Organization-wide event management dashboard providing event/run creation, editing, template management, pre-registration tracking, and deadline monitoring. Displays registration status and participant counts for all events. Automatically assigns creators as organizers (EventRole #1), supports quick setup wizard for new events, enables template configuration with role copying, and aggregates pre-registration data across events with preference-based or simple counting.

### Experience Points (PX) Feature

Comprehensive experience point management system for character progression. Organizers define ability types, abilities with prerequisites/requirements, delivery methods, rules, and modifiers. Participants earn PX and purchase abilities for characters. Supports complex prerequisite chains, bulk ability operations, PDF generation, and export functionality. Ability types categorize skills, deliveries track distribution, rules establish earning mechanisms, modifiers adjust values.

### Expense Feature

Reimbursement request system for event collaborators to submit and track expenses. Supports categorized expenses (set design, costumes, props, electronics, promotion, transportation, kitchen, location, secretarial, other) with balance sheet allocation. Requires invoice upload, description, and value. Features approval workflow: orga_expenses for event-level approval, exe_expenses for organization-level approval. Tracks approval status via is_approved field and can be disabled per organization via expense_disable_orga config.

### External Mail Server Feature

Allows configuration of external SMTP mail server instead of the default one. Organizations can specify custom server settings including host, port, username, password, and TLS configuration. Enables branded email communications from organization's own domain for professional messaging.

### External Registration Feature

Redirects users to an external registration tool instead of using the internal registration form. When enabled, unregistered users are sent to the specified external link, while already-registered users retain normal access to event content and features.

## F

### Faction Feature

Organizes characters into groups with three types: Primary (main allegiance), Transversal (cross-cutting), and Secret (hidden). Each faction has name, presentation, private text, optional cover image/logo, and many-to-many character assignments. Factions can be marked selectable to allow participant choice during registration. Character sheets display faction logos. Supports ordering, version history, and PDF generation. Faction text can reference characters by number using @N notation with automatic name substitution when enabled.

### Filler Feature

Enables simplified "filler" character tickets for participants willing to replace last-minute dropouts. Filler tickets have separate capacity limits from main participants and grant access to streamlined character sheets, making them ideal for backup or supporting roles with less preparation required.

### Fiscal Budget Feature

Annual balance sheet reporting for Italian organizations. Generates comprehensive financial reports showing memberships, donations, ticket revenue (net of transaction fees), inflows, and expenditures by category. Proportionally distributes reimbursements across expense categories. Specific to Italian accounting requirements with year-based filtering.

### Fiscal Code Check Feature

Italian fiscal code validation and calculation system. Automatically computes expected fiscal code from member name, surname, birth date, birth place, and gender. Displays calculated code alongside member-provided code during membership evaluation to verify identity and prevent errors.

### Fixed Instalments Feature

Enables organizers to define fixed payment installments for registration fees. Allows creating multiple due dates with specific amounts, each with either a fixed deadline date or a deadline calculated in days from enrollment. Installments can be configured per ticket type and support partial payments over time.

## G

### Gift Feature

Ticket gifting system allowing participants to purchase registrations for others. Tickets marked as giftable=True can be transferred using redeem codes. The recipient uses the redeem_code during registration to claim the gifted ticket. Gift discounts (DiscountType.GIFT) are also supported. Gifted registrations are excluded from standard discount calculations. Useful for introducing new players, birthday presents, or sponsored attendance. Tracked via Registration.redeem_code field.

## H

### Handout Feature

Generates printable game materials using template-based system. Organizers create handout templates with custom CSS styling, then create individual handouts with content. Each handout has unique access code, presentation, text, and links to a template. Supports PDF generation for printing physical materials, test preview mode, and version history. Handouts integrate with bulk PDF export. Requires at least one template before creating handouts. Used for physical props, letters, documents, and other in-game materials distributed to players.

### Help Feature

Provides a question-and-answer system for participant support. Participants can submit help questions to organizers through forms, which appear in organized queues (open/closed). Organizers can view member details, character assignments, and conversation history when answering questions. Supports both event-specific (orga_questions) and organization-wide (exe_questions) help management. Questions can be answered with text and file attachments, then marked as closed. Integrates with character cache to display participant assignments.

## I

### Inflow Feature

Manual cash inflow tracking for non-registration revenue. Records external money received with description, value, payment date, run association, and optional invoice attachment via AccountingItemInflow. Managed through orga_inflows and exe_inflows views. Common uses include sponsorships, grants, merchandise sales, or event-specific income. Integrates into run accounting breakdowns and annual balance calculations. Provides complete audit trail with downloadable invoice documentation.

## L

### LAOG Feature

Treats events as digital/online occurrences that don't require in-person registration. Changes event behavior for virtual/remote participation scenarios. No specific UI but modifies registration flow and validation logic to accommodate online-only events without physical attendance requirements.

### Legal Notice Feature

No explicit permission - this is part of event appearance configuration. The carousel feature uses Event model fields (carousel_img, carousel_text) to display featured events on the organization's homepage with images and descriptions. Legal notices are configured through association settings.

### Lottery Feature

Creates unlimited free lottery tickets that users can request. Organizers later run a random draw to convert a specified number of lottery registrations into standard tickets. The lottery draw shuffles all lottery registrations and upgrades the selected quantity to the configured ticket tier.

## M

### Membership Feature

Comprehensive association membership management including application submission, executive approval workflows, membership fee tracking, document uploads, card number assignment, and fiscal code validation. Generates membership registries and enrollment lists. Tracks membership status (submitted, accepted, uploaded), validates duplicates, automatically updates registration payments upon approval, and provides membership fee collection with invoice generation. Supports volunteer registry for RUNTS compliance.

## N

### New Player Feature

Reserves special tickets exclusively for users who have never participated in any organization event before. The system automatically checks participant history across all events to enforce eligibility, helping organizations attract and welcome first-time participants with potentially discounted or priority access.

### Newsletter Feature

Multi-faceted communication management system with four components: orga_newsletter displays email lists of non-cancelled/non-waiting participants; orga_spam shows members eligible for promotional emails grouped by language; orga_persuade identifies persuadable members with pre-registration status and event history; exe_newsletter manages organization-wide mailing lists by language and subscription preference. Enables targeted communication campaigns.

## O

### One-Time Content Feature

Secure media streaming system for video/audio files via cryptographically-secure one-time access tokens. Each token tracks usage (who accessed, when, IP address, user agent). Supports MP4, WebM, MP3, OGG formats. Organizers generate tokens with notes, view statistics (total/used/unused), and content remains inaccessible after token use.

### Opening Date Feature

Allows organizers to specify an exact date and time when registration will open. Displays a countdown message to users before this time, preventing early registrations. Once the opening datetime is reached, registration becomes available automatically without manual intervention.

### Organisation Tax Feature

Tax configuration and balance sheet categorization system. Works with BalanceChoices to classify expenses into tax-deductible categories: raw materials, services, third-party assets, personal, miscellaneous. Integrates with exe_balance view for annual tax reporting. Expenses and outflows are allocated to balance categories during entry. Annual balance calculations aggregate by category for simplified tax filing. Supports compliance with local tax regulations and financial transparency requirements.

### Outflow Feature

Manual cash outflow recording for expenses not submitted via reimbursement workflow. Tracks spending with categorization (ExpenseChoices), balance sheet allocation (BalanceChoices), description, payment date, and invoice upload via AccountingItemOutflow. Managed through orga_outflows and exe_outflows. Used for direct organizational expenses, vendor payments, or location costs. Differentiates from expense feature by representing actual payments made rather than reimbursement requests. Includes downloadable invoice documentation.

## P

### Participant Cancellation Feature

Self-service registration cancellation system allowing participants to cancel their event registrations at any time without organizer intervention. Provides autonomy for participants to manage attendance commitments. Configuration is simple with no additional settings required (after_text and after_link are empty). Enables flexible participation management while maintaining registration tracking and financial record integrity. Reduces administrative overhead for organizers.

### Patron and Reduced Feature

Links patron and reduced ticket availability in a ratio-based system. Each patron ticket purchased makes reduced-price tickets available based on a configurable ratio (default 1:1). The system calculates remaining reduced slots dynamically as patron tickets are sold.

### Pay What You Want Feature

Optional registration field allowing participants to add a voluntary contribution on top of their ticket price. Integrates seamlessly into registration fee calculations through the pay_what field on Registration model. Participants can specify any additional amount they wish to contribute during signup. This amount is added to the total registration cost (tot_iscr) and appears in accounting breakdowns. Commonly used for sliding-scale pricing or supporting events financially.

### Payment Feature

Comprehensive payment management system supporting multiple gateways (PayPal, Stripe, Redsys, Satispay, SumUp). Tracks payment invoices with statuses (Created, Submitted, Confirmed, Checked), transaction fees, and payment methods. Event organizers can view and confirm pending payments via orga_payments/orga_invoices, while organization executives manage all payments through exe_payments/exe_invoices. Includes verification workflow, gross/net calculations, and detailed payment history. Links payments to registrations, memberships, donations, or collections.

### PDF Generation Feature

Generates professional PDF exports for characters, factions, and event materials. Provides bulk PDF generation with configurable options, individual character sheets (full and friendly versions), relationship sheets, faction sheets, handouts, character gallery, and profile pages. Supports batch regeneration for future event runs, PDF preview/test modes, and ZIP download of multiple PDFs. Organizers configure PDF settings per event including layout, fonts, and included sections. Essential for preparing printed materials for in-person LARP events.

### Player Editor Feature

Player-driven character creation and editing system enabling participants to build characters freely within organizer-defined constraints. Supports custom forms, character sheets, element fields, relationships, and ability selections. Organizers configure editing permissions, approval requirements, visibility rules, and external access tokens. Integrates with experience points (PX) system for ability purchases. Provides full character sheet access with contextual data based on permissions.

### Plot Feature

Creates story threads linking multiple characters through plot-character relationships. Each plot has name, presentation, text, and connects to characters via PlotCharacterRel allowing custom per-character text snippets. Supports ordering, staff assignment, progress tracking, and version history. Plots integrate with character sheets and the "check" tool validates plot-character consistency. Plot text supports character references (@N notation) with automatic name substitution. Can be hidden from participants and assigned to specific staff members.

### Pre-Registration Feature

Enables free pre-registration before full registration opens, allowing users to express interest in events. Supports optional preference ordering and additional information collection. Pre-registrations are tracked organization-wide and per-event, with views for both participants and organizers to monitor interest levels.

### Problems Feature

Event problem tracking system using severity levels (RED/ORANGE/YELLOW/GREEN) and status (OPEN/WORKING/CLOSED). Tracks where, when, what, and who for each issue with detailed descriptions. Problems are numbered, assigned to specific staff members, and ordered by status and severity for prioritized resolution during event organization.

### Progress Feature

Tracks writing workflow status using customizable progress steps. Organizers define ordered progress steps (e.g., "Draft", "Review", "Complete") that can be assigned to any writing element (characters, plots, factions, etc.). Steps have number, name, and order for display. Helps manage large-scale writing projects by tracking which elements need attention. Staff can filter/sort writing elements by progress status. Supports reordering and is commonly used for tracking character development, plot completion, and faction refinement during event preparation.

### Prologue Feature

The Prologue feature allows organizers to create introductory texts for each act that appear in character sheets. Using `orga_prologue_types`, organizers first define prologue types (e.g., "Act 1", "Act 2"). Then via `orga_prologues`, they create prologue content linked to a type and assign it to characters through a many-to-many relationship. When participants view their character sheet, prologues are displayed ordered by type number, with a warning not to read ahead. The system validates that at least one prologue type exists before allowing prologue creation.

### Publication Feature

Makes upcoming events visible to external sites through public API endpoints. Organizations enable publication of their event calendar data for aggregation on third-party platforms or event discovery services. Uses PublisherApiKey for secure API access with IP tracking and logging.

## Q

### Quests and Traits Feature

The questbuilder feature introduces a hierarchical system for organizing character sheet content. **QuestType** categorizes quests, **Quest** models (belonging to a QuestType) contain multiple **Trait** objects. Traits can reference other traits using #number syntax and maintain many-to-many relationships. **AssignmentTrait** links traits to specific characters via Members and Runs. Four permissions manage the system: `orga_quest_types`, `orga_quests`, `orga_traits`, and `orga_assignments`. Character sheets display assigned traits with quest context.

## R

### Receipt Feature

Invoice and receipt generation system for payment confirmations. Links to PaymentInvoice model storing payment documentation. Supports electronic invoice generation (ElectronicInvoice with progressive numbering and XML export). Provides downloadable receipt access via get_details() method. Integrates with payment gateways for automatic receipt creation. Manual payments support receipt upload. Critical for participant records, tax documentation, and financial auditing. Receipts track gross amount, fees, transaction IDs, and payment method details.

### Record Accounting Feature

Financial snapshot system creating periodic accounting records via RecordAccounting model. Captures global_sum and bank_sum at specific points in time for organization-level tracking. Managed through exe_accounting_rec view. Automatically created via check_accounting() when accessed if none exist. Provides historical financial data, enables trend analysis, and supports audit requirements. Tracks date ranges between first and last records for temporal financial reporting.

### Refund Feature

Refund request management for participants seeking reimbursement. Members submit RefundRequest with payment details (IBAN, PayPal, etc.), requested amount, and status (Request/Delivered). Organization executives review via exe_refunds and mark as delivered when processed. Displays remaining credits alongside refund amount. Does not automatically process payments—requires manual external transaction. Tracks refund history and integrates with member balance calculations for complete financial oversight.

### Relationships Feature

Manages directional character-to-character relationships with rich text descriptions. Each relationship links source character to target character with HTML-formatted text describing their connection. Supports TinyMCE editor, inverse relationship tracking (shows both directions), and PDF export. Integrated into character editing workflow with inline editing. The "check" tool validates relationship symmetry, flagging missing reciprocal relationships. Relationships appear on character sheets and can be exported as separate PDF documents for player reference.

### Reminder Feature

Performs automated daily checks for approaching payment deadlines and sends reminder emails to participants with outstanding balances. The system tracks installment due dates and registration payment status, triggering notifications based on configured timing thresholds to reduce late payments and cancellations.

## S

### Safety Feature

Displays safety information submitted by registered event participants for organizer review. Collects safety data from non-cancelled registrations with entries exceeding minimum length (3 characters). Associates each participant's safety information with their assigned characters, showing character numbers and names. Data is sorted alphabetically by participant name and includes character assignments for comprehensive safety management during events.

### Secret Link Feature

Generates a special hidden URL that bypasses registration closure restrictions. Enables specific groups to register even when general registration is closed, useful for early access, VIP registration, or late additions. The secret code is embedded in the registration URL.

### Sections Feature

Organizes lengthy registration forms by grouping questions into logical sections. Each section has a name and optional description displayed at the beginning, improving form clarity and user experience. Sections are ordered and displayed sequentially during registration.

### Shuttle Feature

Transportation request management system where participants submit pickup requests with passenger count, address, date/time, and special information. Staff members can claim requests, update status (waiting/coming/arrived), add notes about car details or arrival times. Shows active requests and recent completed shuttles (last 5 days).

### Speed Larp Feature

Manages pre-event mini-scenes with type and station assignments. Organizers create numbered speed larps, assign characters to avoid scheduling conflicts, and track progression. Includes versioning support for iterative development. Participants can be scheduled across multiple scenes with automated conflict detection.

### Surcharge Feature

Date-based automatic price increases for late registrations. Organizers define surcharge amounts and effective dates through RegistrationSurcharge model. The system automatically calculates and applies cumulative surcharges based on when participants register via get_date_surcharge(). Surcharges are exempt for waiting list, staff, and NPC ticket tiers. Managed through orga_registration_surcharges view with full CRUD operations. Encourages early registration and covers increased organizational costs.

## T

### Taxes (VAT) Feature

Value-Added Tax calculation system for tax compliance. Computes VAT on ticket prices (vat_ticket) and registration options (vat_options) when vat feature is enabled. Calculations occur during payment processing via compute_vat_payment(). Only applies to money payments (not tokens/credits). Integrates with balance sheet generation and financial reporting. Displays VAT columns in payment views when enabled. Essential for organizations in jurisdictions requiring VAT collection and reporting.

### Template Feature

Event template management system for reusable event configurations. Templates are events marked as templates with associated roles. Organizations create template events with predefined features, configs, roles, and permissions. New events can inherit from templates for consistent event setup and reduced configuration time.

### Token Credit Feature

Alternative payment currencies allowing participants to use tokens or credits instead of money. Managed through AccountingItemOther with OtherChoices (CREDIT/TOKEN). Credits typically represent monetary value from refunds/cancellations, while tokens are event-specific currency. Assigned via orga_tokens/orga_credits and exe_tokens/exe_credits views. Supports bonus assignments for additional tickets, cancellation refunds, and flexible payment combinations. Automatically handled in registration accounting calculations.

### Translation Feature

Organization-specific translation override system. Allows fine-tuning of word and phrase translations beyond default localizations. Administrators define custom translations for their organization's space, enabling terminology adjustments, regional language preferences, or specialized LARP vocabulary customization.

### Treasurer Feature

Permission and role designation for financial management. Likely controls access to accounting views and sensitive financial operations. Integrates with the feature-based permission system (AssociationPermission/EventPermission). Treasurer role would typically have access to exe_accounting, exe_balance, exe_verification, payment management, and financial reporting. Enables delegation of financial responsibilities while maintaining security and audit controls. Part of the broader role-based access control architecture.

## U

### URL Shortener Feature

Organization-wide URL shortening service with custom short codes. Creates memorable short links for long URLs with tracking via unique 5-character codes. Each entry has number, name, code, and target URL. Accessible through public short URL redirects for marketing and participant communication.

### Utility Feature

File hosting system that lets organizers upload and manage files directly on the platform. Files can be made available to staff or participants via secret external links with unique codes. Each utility has a number, name, code, and downloadable file attachment for secure distribution of event materials.

## V

### Verification Payments Feature

Payment invoice verification system ensuring payment authenticity. Electronic gateways (PayPal, Stripe, Redsys, Satispay, SumUp) auto-verify. Manual methods require verification via exe_verification. Supports bulk upload verification and manual confirmation per invoice. Tracks verified status on PaymentInvoice. Displays pending verifications with registration codes for easy matching. Critical for bank transfer payments where organizers must match bank statements to registrations before confirming payment.

### Volunteer Registry Feature

Manages volunteer service records with member information, start/end dates, and role descriptions. Displays registry list ordered by start date and surname. Generates printable PDF reports for legal compliance. Supports volunteer hour tracking and organizational record-keeping for Italian associations.

### Vote Feature

Election management system for executive committee voting. Organization executives can configure candidates, vote minimums/maximums, and opening status. Members cast votes for configured candidates with randomized ordering to prevent position bias. Validates membership fee payment before voting. Tracks votes by year and displays tallies. Participants see candidate lists and submit ballot selections. Prevents duplicate voting within same year.

## W

### Waiting List Feature

Activates waiting list tickets that become available only when all primary tickets are sold out. Supports both limited capacity and unlimited waiting spots. When primary tickets free up, waiting list participants can be manually upgraded by organizers.

### Warehouse Feature

Enables comprehensive warehouse management for organizations. Allows creation of containers, items with photos and tags, movement tracking, and event-specific area assignments. Supports quantity tracking with manifest generation and one-time quantity commits when loading items for events. Includes loaded/deployed status tracking for event logistics.

### Workshop Feature

Quiz-style workshop system with modules, questions, and multiple-choice options. Participants complete workshops by answering questions correctly, with immediate feedback. Tracks completion within 365 days. Organizers define modules, questions with correct answers, and participant progress. Supports pre-event educational requirements with automated tracking.

---

**Total Features Documented:** 77
