# Tutorial Screenshot Manifest

What each screenshot in the tutorials shows, so it can be retaken with the current interface.
Numbering is the order of `<img>` tags inside the tutorial `descr`. "Player" = logged in as the
test user on the public event pages; otherwise logged in as organizer on the manage side.
Crop = the part of the page to keep (see **Screenshots** in `SKILL.md` for general rules).

Status (2026-09-26): all tutorials are captured by the Playwright scripts in `playwright/` (see **Taking them** in
`SKILL.md`). Output goes to `tutorial_screenshots/<order>_<slug>_<nn>.png`, where `<nn>` is the image number below,
plus `<order>_<slug>.json` with CSS width/height and alt text for each image. The tutorial HTML references them as
`/media/tutorial_screenshots/<file>` (manage-events #2 reuses `170_characters_03.png`).

Images not recaptured, and why (the tutorial HTML is already updated: dropped images are removed and the sentence
before them names the field instead):

| Tutorial | Images | Reason |
|---|---|---|
| 1 create-organization | 1 | Main-site page, not reachable from the test server: keep the existing one |
| 90 registrations | 4, 6 | Single field: drop, the bold field name in the text is enough |
| 100 manage-ticket | 5, 7, 9, 11 | Merged into 3 (tier list shows every enabled tier): drop |
| 100 manage-ticket | 8, 10 | Single field: drop |
| 110 registration-form | 9 | Single select: drop |
| 130 registration-accounting | 1, 8, 10 | Single field / single icon: drop |
| 170 characters | 5, 6, 7, 8 | Editor popups and hover states: keep the existing ones (already in the new style) |
| 170 characters | 10, 14 | Merged into 9 and 13: drop |
| 190 character-form | 5, 7, 8, 9 | Single field: drop |
| 200 character-creation | 4, 7 | Single field: drop |
| 205 xp | 8 | Single checkbox: drop |
| 210 factions | 3, 4 | Single field: drop; new image 5 (gallery grouped by faction) |
| 215 ensemble | 1, 2 | Photo and illustration: keep |
| 230 casting | 7, 12, 13 | Single cell / field: drop |
| 230 casting | 11 | Avoid column now visible in 6: drop |
| 260 users | 1, 9 | Footer link and user menu entry: described in the text |
| 270 membership | 4, 7 | Needs uploaded documents / buttons now visible in 5: described in the text |
| 300 accounting | 1 | Topbar link: describe in text |


## 1 create-organization

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | Landing "Get started" (`/debug`-free main site) | "Create your organization" form |
| 2 | Manage, topbar | Context pills: organization + event |
| 3 | Manage, topbar | User / Admin switch |
| 4 | `manage/` | Sidebar: Home, Dashboard, Preferences, Organization, Roles, Configuration, Features, Events |
| 5 | `manage/`, mobile viewport | Mobile bar: menu button, org name, context button |
| 6 | `manage/` | Sidebar bottom links: Discord, Guides, Tutorials |

## 10 player-information

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/profile/` | Profile fields with Hidden/Optional/Mandatory selects |
| 2 | `event/manage/sensitive/` | Users data table with one participant |
| 3 | `event/manage/registrations/` | Participant row with the eye icon (sensitive data popup) |

## 20 organization-roles

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/roles/` | Roles list with Admin role (old shot wrongly shows the event roles page) |
| 2 | `manage/roles/` > New | Role form: Name, Members, permission groups |

## 30 organization-appearance

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/appearance/` | Theme select with help, custom title font |
| 2 | `manage/texts/` > New | Text form: Text, Type, Language |
| 3 | `manage/config/interface/` | Interface section checkboxes |

## 40 advanced-features (tutorial removed: images used by create-organization and manage-events)

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/features/` | Organization features grouped by module |
| 2 | `event/manage/features/` | Event features grouped by module |

## 50 manage-events

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/events/` > New event | Event form: name, URL identifier, description |
| 2 | Event form | Characters visibility row: Name / Presentation / Text |
| 3 | `event/manage/` | Dashboard "Event" card: name, dates, status, registrations |
| 4 | `manage/events/` > New session | Session form: Event, Start/End date, Status cards |
| 5 | `manage/template/` > New | Template form: name + feature checkboxes |
| 6 | `manage/template/` | Template list with roles / configuration links |
| 7 | `event/manage/event/` (Campaign on) | Parent campaign field |
| 8 | Newcomer, organization home `/` | Upcoming sessions: event card with dates and registration status |
| 9 | Newcomer, event page `test/` | Registration box, dates, description |
| 10 | Newcomer, `test/register/` | Ticket choice on the registration page |

## 70 event-roles

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/roles/` | Roles list with Organizer role |
| 2 | `event/manage/roles/` > New | Role form: Name, Members, permission groups |

## 80 event-appearance

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/appearance/` | Theme, cover image, custom title font |
| 2 | `event/manage/texts/` > New | Text form with Type "Character sheet intro" |
| 3 | `event/manage/buttons/` > New | Navigation form: Name, Tooltip, Link, Icon |
| 4 | Player, event page | Event sidebar with the custom navigation entry |
| 5 | `event/manage/config/gallery/` | Gallery section: Require login/registration, Hide unassigned characters/participants |

## 85 promotion

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/config/publication/` | Promotion section: publish staff/players, ILDB key and team ID |
| 2 | `event/manage/promotion/` | Promotion page with location search and map |

## 90 registrations

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/registrations/` | Toolbar, column toggles, one participant row |
| 2 | Registrations > edit | Member + Character fields |
| 3 | `event/manage/cancellations/` | Cancellations table with one row |
| 4 | Player, registration form (Additional tickets on) | "Additional" field |
| 5 | `event/manage/event/` | Registration status cards (Pre-registration selected) |
| 6 | `event/manage/event/` (Secret link on) | Secret registration code field |
| 7 | `event/manage/` | Dashboard "Registrations" card with secret link copy button |

## 100 manage-ticket

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/tickets/` > New | Ticket form: Name, Description, Price |
| 2 | `event/manage/config/tickets/` | Tickets section: Staff, NPC, Collaborator, Seller, Show sold tickets |
| 3 | Ticket form | Tier select open: Standard / Staff |
| 4 | Player, registration form | Ticket card with price and availability |
| 5 | Ticket form (Patron and Reduced on) | Tier select open: Standard / Reduced / Patron |
| 6 | `event/manage/config/reduced/` | Patron / Reduced section: Ratio |
| 7 | Ticket form (Reserve on) | Tier select open with Reserve |
| 8 | `event/manage/event/` | Maximum reserves field |
| 9 | Ticket form (Waiting list on) | Tier select open with Waiting |
| 10 | `event/manage/event/` | Maximum waiting list field |
| 11 | Ticket form (Lottery on) | Tier select open with Lottery |
| 12 | `event/manage/config/lottery/` | Lottery section: Number of extractions, Conversion ticket |

## 110 registration-form

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/form/` > New | Question form: Type, Name, Description, Status |
| 2 | Player, registration form | Single-line text question |
| 3 | Player, registration form | Multi-line text question |
| 4 | Player, registration form | Advanced text editor question (shown) |
| 5 | Player, registration form | Likert scale question |
| 6 | Question form, single choice | Inline options editor with three options |
| 7 | Player, registration form | Choice question as option cards (price, availability) |
| 8 | `event/manage/sections/` > New | Section form: Name, Description |
| 9 | Question form (Sections on) | Section select open |
| 10 | Player, registration form | Collapsible section with its question |
| 11 | `event/manage/config/registrations/` | Registrations section checkboxes |
| 12 | Player, signup (request mode) | "Request to signup" form |
| 13 | `event/manage/registrations/requests/` | Requests table with Approve / Reject |

## 130 registration-accounting

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | Player, registration form | Pay what you want field |
| 2 | `event/manage/installments/` > New | Fixed instalment form: Amount, Days deadline, Date deadline |
| 3 | `event/manage/quotas/` > New (Dynamic rates) | Quota form: Quotas, Days available, Surcharge |
| 4 | `event/manage/quotas/` | Quotas table with three rows |
| 5 | `event/manage/surcharges/` > New | Surcharge form: Amount, Date |
| 6 | `event/manage/discounts/` > New | Discount form: Name, Sessions, Value, Max redeem, Code |
| 7 | Player, registration form | Discounts code field |
| 8 | Ticket form (Gift on) | Giftable checkbox |
| 9 | Player, gift page | Gift page with Add new |
| 10 | `event/manage/registrations/` | Registration row with gift icon |

## 150 payments

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/methods/` | Payment methods checkboxes |
| 2 | `manage/methods/` (Wire checked) | Wire section fields |
| 3 | `manage/config/payment/` | Payments section (organization) |
| 4 | `event/manage/config/payment/` | Payments section (event) |

## 170 characters

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/characters/` > New | Character form: Name, Presentation, Text |
| 2 | `event/manage/config/writing/` | Characters section: Title, Number, Cover, File, Hide |
| 3 | `event/manage/event/` | Characters visibility row: Name / Presentation / Text |
| 4 | Character form | Text editor containing a "#1" reference |
| 5 | Player, character page | Rendered reference with hover popup |
| 6 | Character form | Reference insert popup ("#XX") with character list |
| 7 | Character form | Highlighted "#1" showing the name popup |
| 8 | `event/manage/characters/` | Double-click inline edit popup |
| 9 | Character form (Relationships on) | Relationships select |
| 10 | Character form | Relationship row: Direct / Inverse |
| 11 | `event/manage/config/custom_character/` | Character customisation section |
| 12 | Player, character sidebar | "Customize" entry |
| 13 | `event/manage/pdf/` | PDF page links (unused: moved to 180 pdf-generation) |
| 14 | `event/manage/pdf/` | "Try the sheet generation" row |
| 15 | `event/manage/check/` | Relationship check table |
| new | Player, gallery | Gallery with characters grouped by faction + Registrants (section "Gallery and Search") |
| new | Player, search | Search page with a faction filter included and results (section "Gallery and Search") |

## 175 character-references

Reuses `170_characters_04.png` (reference in a text) and `170_characters_15.png` (check page), plus the three kept
editor screenshots (hover popup, character finder, highlighted reference; formerly characters #5-7).

## 180 pdf-generation

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/pdf/` | Download links and "Try the sheet generation" |
| 2 | `event/manage/pdf/` | PDF options form |
| 3 | `event/manage/characters/<uuid>/pdf/sheet/test/` | Complete sheet with header, footer and brown colors |

## 190 character-form

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/writing/form/` > New | Field form: Type, Name, Description, Visibility |
| 2 | Field form (Character creation on) | Status select with help |
| 3 | Field form, single choice | Option editor with one expanded option |
| 4 | `event/manage/config/char_form/` | Character sheet section checkboxes |
| 5 | Character form (Title on) | Title field filled |
| 6 | Player, gallery | Character card with title |
| 7 | Character form (Cover on) | Cover file field |
| 8 | Character form (Assigned on) | Assigned select |
| 9 | Character form (Progress on) | Progress select |
| 10 | `event/manage/characters/` | Toolbar: New, Progress, Assignments, Progress - Assignments |

## 200 character-creation

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/config/user_character/` | Character creation section: Maximum number, Approval |
| 2 | Player, event page | "Create the character you will play" banner |
| 3 | Player, character sidebar | Character + Edit entries |
| 4 | Character form (Approval on) | Status select |
| 5 | Player, character page | "Confirm your character is ready" banner |
| 6 | Field form (Approval on) | Editable: Creation / Proposed / Revision / Approved |
| 7 | Character form (Campaign on) | Active checkbox |
| 8 | Player, character sidebar | "Relationships" entry |
| 9 | Player, relationship > New | Relationship form: Character, Text |

## 202 character-inventory

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | Character inventory page | Currencies and materials with transfer controls |
| 2 | Character inventory page | Transfer log with two rows |

## 205 xp

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/experience/abilities/` > New | Ability form: Name, Type, Cost, Description |
| 2 | `event/manage/experience/awards/` > New | Award form: Name, Amount, Characters dual list |
| 3 | `event/manage/experience/awards/` | Toolbar with "Load characters" dropdown open |
| 4 | `event/manage/config/experience/` | Experience points section |
| 5 | Player, character sidebar | "Abilities" entry |
| 6 | Player, abilities page | Obtain ability picker + XP counters |
| 7 | Player, abilities page | Owned abilities with remove (undo) control |
| 8 | Ability form | Visible checkbox |
| 9 | `event/manage/writing/form/` > New | Type select open on "Computed" |
| 10 | `event/manage/experience/rules/` > New | Rule form |
| 11 | `event/manage/experience/modifiers/` > New | Modifier form |

## 210 factions

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/factions/` > New | Faction form: Type (Primary selected, help text visible), Name, Presentation, Text, Characters |
| 2 | `event/manage/event/` | "Factions" row of the gallery visibility fields: Name / Presentation / Text checkboxes |
| 3 | `event/manage/factions/` > New (Character creation active) | Only the "Selectable" checkbox row |
| 4 | Player, character edit/create | "Faction" selector field of the character form |

## 215 ensemble

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | - | Photo of printed character cards and booklet (not UI, keep) |
| 2 | - | Workflow illustration (not UI, keep) |
| 3 | Player, event page | Event navigation bar with the "Ensemble" button highlighted |

## 217 guilds

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/config/guild/` | Guilds section: Maximum number, Maximum members |
| 2 | Player, event page | "Guilds" entry in the event menu |
| 3 | Player, `guilds/` | Guild list with create and invites links |
| 4 | Player, `guilds/new/` | New guild form |
| 5 | Player, guild page (admin) | Members, admin star, edit and invite |
| 6 | Player, `guilds/invites/` | Pending invite with accept/decline |
| 7 | Player, gallery | Guild section of the gallery |
| 8 | `event/manage/guilds/` | Guilds list for organizers |

## 220 plots

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/plots/` > New | Plot form: Name, Concept, Text, Characters |
| 2 | Plot form, one character added | Characters field with "#1 Test Character" plus its personal-text editor ("Personal text") |
| 3 | `event/manage/characters/` > edit Test Character | Plot row "#1 Test plot": general text box + personal text editor |
| 4 | Player, character sheet | "Test plot" section showing General text then Personal text |

## 223 writing-extras

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/prologue_types/new/` | New prologue type |
| 2 | `event/manage/prologues/new/` | New prologue (after a type exists) |
| 3 | `event/manage/handout_templates/new/` | New handout model (name, CSS) |
| 4 | `event/manage/handouts/new/` | New handout (after a model exists) |
| 5 | `event/manage/speedlarps/new/` | New speed larp scene |
| 6 | `event/manage/workshops/modules/new/` | New workshop module |

## 225 matchmaker

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/form/matchmaker/` | Matchmaker form with three questions (incl. automatic faction preference) |
| 2 | Player, event page | "Matchmaker" entry in the event menu |
| 3 | Player, `matchmaker/` | Matchmaker form with faction ranking |
| 4 | `event/manage/matchmaker/` | Answers table |
| 5 | `event/manage/matchmaker/` | Likert chart |

## 230 casting

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/config/casting/` | First half: Minimum / Maximum / Additional preferences, Field for exclusions, Assignments |
| 2 | `event/manage/config/casting/` | Second half: Mirror, Show statistics, Show history, Registration priority, Payment priority |
| 3 | Player, casting page | Event nav with "Casting", signup status line, preference table (#1-#4, Faction + Character selects) |
| 4 | Player, character page (Show statistics on) | Casting preferences total + bar graph |
| 5 | `event/manage/casting/` | Filter bar: Tier (ticket), Payment status, Factions checkboxes, Update |
| 6 | `event/manage/casting/` | Preference table row: Player, Priority, Pref 1, Pref 2 (YES) |
| 7 | `event/manage/casting/` | Single blocked preference cell: "#1 Test Character - NO" |
| 8 | `event/manage/casting/` | "Start algorithm" button with its note |
| 9 | `event/manage/casting/` after run | Result block: Upload button, warning, proposed assignment |
| 10 | Player, casting page (Field for exclusions on) | "Indicate here any element you wish to avoid" field |
| 11 | `event/manage/casting/` | Preference table with the "Avoid" column filled |
| 12 | `event/manage/tickets/` > edit ticket | "Casting priority" field |
| 13 | `event/manage/characters/` > edit (Mirror on) | "Mirror" select field |

## 240 quests

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/quest_types/` > New | Quest type form: Name, Presentation |
| 2 | `event/manage/quests/` > New | Quest form: Type (Past Occupations), Name, Presentation, Text |
| 3 | `event/manage/traits/` > New | Trait form: Quest (Heist), Name, Presentation, Text |
| 4 | Player, quest list | Event nav with "Quest", table of quest types and quests |
| 5 | Player, quest "Heist" | Presentation + Traits list (Mind / Muscle / Face) |
| 6 | Player, casting for quest type | Casting page with Quest + Trait preference selects |
| 7 | `event/manage/casting/` (quest type) | Start algorithm, legend, preference table with traits |
| 8 | `event/manage/registrations/` > edit | Quest type select opened, showing traits ("Q1 Heist - T1 Mind", ...) |

## 250 deadlines

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/config/deadlines/` | Deadline section: Tolerance, Frequency |
| 2 | `event/manage/deadlines/` | Deadlines table: cancellation for missing payment, membership overdue, delay in payment |
| 3 | `manage/config/remind/` | Reminder section: Frequency, Holidays |
| 4 | `manage/texts/` > New | Text form with Type select opened on "Reminder payment" |

## 260 users

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | Player, any page | Footer links: "Need help?", Privacy Policy, Technical Support |
| 2 | Player, help page | "Submit a new question" form: Text, Attachment, Event, Confirm |
| 3 | Player, help page | Communications list with one question |
| 4 | `manage/questions/` | Questions table with one open question (Answer / Close) |
| 5 | `event/manage/safety/` | Safety table with one participant |
| 6 | `event/manage/diet/` | Diet table with one participant |
| 7 | Player, user profile from gallery | Profile card with "Private message: Chat" link |
| 8 | `manage/newsletter/` | Newsletter lists grouped by language and preference |
| 9 | Player, user menu | Menu with "Delegated users" entry |
| 10 | Player, delegated users page | Delegated accounts table with Login + Add new |

## 265 user-flags

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/config/users/` | Users section with the User flags option |
| 2 | `manage/member_flags/` > New | Flag type form: Name, Description, Annual |
| 3 | `manage/member_flags/` | Flag types list |
| 4 | `manage/members_flags/` | Users with their flags |
| 5 | `manage/members_flags/` > edit | Edit flags popup |
| 6 | `event/manage/registrations/` > eye | Participant details with flags |

## 270 membership

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/config/membership/` | Members section: Age, Annual fee, Start day, Months free quota |
| 2 | `manage/texts/` > New | Text form with Type select opened on "Membership" |
| 3 | Player, membership page | "You are not yet a member" upload form (Request signed, Photo of an ID) |
| 4 | Player, membership confirmation | Confirmation checklist with uploaded documents |
| 5 | `manage/membership/` | Members list with one pending request (Details / Member / Request) |
| 6 | `manage/membership/` > Request | Request review: Is approved, Response, Confirm |
| 7 | `manage/membership/` | Header with "Upload membership document" / "Upload membership fee" buttons |
| 8 | `event/manage/registrations/` | Registrations list with "member" column active showing status |
| 9 | `manage/deadlines/` | Deadlines table: "Delay in organization registration" row |

## 300 accounting

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | Player, topbar | "Accounting" link in the user menu/topbar |
| 2 | Player, accounting page | Registration history for Test Event + History link |
| 3 | `manage/accounting/` | Organization accounting summary (balances, inflows, outflows) |
| 4 | `event/manage/accounting/` | Event accounting: total revenue + breakdown table |
| 5 | Player, accounting page | "Donation" section |
| 6 | `event/manage/upload_expenses/` > New | Expense form: Value, Invoice, Descr, Type |
| 7 | `manage/expenses/` | Expenses table with one row (Download / Approve) |
| 8 | Player, accounting page | "Collection" section |
| 9 | Player, collection page | Active collection with participate / close links |
| 10 | Player, accounting page | "Credits" section with refund request link |
| 11 | `manage/refunds/` | Refund requests table (Request / Delivered) |
| 12 | `manage/inflows/` > New | Inflow form: Value, Run, Description, Invoice, Payment date |
| 13 | `manage/outflows/` > New | Outflow form: Value, Run, Description, Invoice, Payment date, Type |
| 14 | `manage/config/vat/` | VAT section: Ticket, Options |
| 15 | `manage/payments/` | Payments table showing the VAT column |
| 16 | `manage/verification/` | Payment verification: upload form + list of payments to verify |
| 17 | `manage/config/organization_tax/` | Organizational fee section: Percentage |
| 18 | `event/manage/accounting/` | Event accounting header with the "Organization tax" line |

## 400 checkin

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | - | Features panel: dropped, the activation link is enough |
| 2 | Player, event page | Registration card with the check-in QR code |
| 3 | `event/manage/checkin/` | Search, scan button, participant list and summary (two already present) |
| 4 | `event/manage/checkin/` > Scan QR code | Scanner popup after reading the player's QR ("Checked in: ...") |
| 5 | `event/manage/checkin/` > Sign in | Manual check-in confirmation popup |
| 6 | `event/manage/checkin/` offline | Status bar: Offline, Pending sync: 1 |
| 7 | `event/manage/experience/awards/` | Load characters menu with "From checked-in participants" |

## 410 debrief

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/form/debrief/` | Debrief form page with three questions (rating, best moment, next edition) |
| 2 | Player, event page | "Debrief" entry in the event menu |
| 3 | Player, `debrief/` | Debrief form with the three questions |
| 4 | `event/manage/debrief/` | Answers table for three participants |
| 5 | `event/manage/debrief/` | Likert chart of the overall rating |
| 6 | `event/manage/deadlines/` (session over) | "Debrief not yet compiled" row |
| 7 | `event/manage/experience/awards/` | Load characters menu with "From participants who filled the debrief" |

## 415 event-tools

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `event/manage/problems/new/` | New problem |
| 2 | `event/manage/milestones/new/` | New milestone |
| 3 | `event/manage/utils/new/` | New hosted file |
| 4 | `event/manage/onetimes/content/new/` | New one-time content |
| 5 | `event/manage/copy/` | Copy from another event |

## 420 organization-tools

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/urlshortner/new/` | New short URL |
| 2 | `manage/warehouse/containers/new/` | New container |
| 3 | `manage/warehouse/items/new/` | New item |
| 4 | `manage/config/app_integration/` | App integration section |
| 5 | Participant, `shuttle/new/` | Shuttle request form |
| 6 | `manage/logs/` | Activity log |

## 900 sections (images used by sections of existing tutorials)

| # | Tutorial | Page | What it shows |
|---|---|---|---|
| 1 | registration-accounting | `event/manage/config/bring_friend/` | Bring a friend discounts |
| 2 | accounting | `manage/config/treasurer/` | Treasury appointees |
| 3 | organization-appearance | `manage/translations/new/` | New custom translation |
| 4 | users | `manage/badges/new/` | New badge |
| 5 | users | `manage/config/vote/` | Voting section |

## 995 italian-associations

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/config/receipts/` | Receipts section |
| 2 | `manage/volunteer_registry/` | Register of volunteers |
| 3 | `manage/config/centauri/` | Easter egg section |

## 999 manage-mails

| # | Page | Crop / what it shows |
|---|---|---|
| 1 | `manage/config/email/` | Email notifications section: Carbon copy, New signup, Signup update, Signup cancellation, Payments received |
| 2 | `manage/config/custom_mail_server/` | Customised mail server section (old shot shows the outdated "Mail server" title) |
| 3 | `event/manage/config/custom_mail_server/` | Same section at event level |
| 4 | `manage/preferences/` | Interface section with the personal Notifications digest |
