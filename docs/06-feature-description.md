# Prologue Feature

The Prologue feature allows organizers to create introductory texts for each act that appear in character sheets. Using `orga_prologue_types`, organizers first define prologue types (e.g., "Act 1", "Act 2"). Then via `orga_prologues`, they create prologue content linked to a type and assign it to characters through a many-to-many relationship. When participants view their character sheet, prologues are displayed ordered by type number, with a warning not to read ahead. The system validates that at least one prologue type exists before allowing prologue creation.
