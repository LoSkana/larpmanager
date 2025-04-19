# LarpManager - https://larpmanager.com
# Copyright (C) 2025 Scanagatta Mauro
#
# This file is part of LarpManager and is dual-licensed:
#
# 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
#    as published by the Free Software Foundation. You may use, modify, and
#    distribute this file under those terms.
#
# 2. Under a commercial license, allowing use in closed-source or proprietary
#    environments without the obligations of the AGPL.
#
# If you have obtained this file under the AGPL, and you make it available over
# a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary

import csv
import os
import re
import unicodedata

from django.conf import settings as conf_settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from larpmanager.models.member import Membership, Badge


def count_differences(s1, s2):
    # If the lengths of the strings are different, they can't be almost identical
    if len(s1) != len(s2):
        return False

    # Count the number of differences between the two strings
    differences = 0
    for c1, c2 in zip(s1, s2):
        if c1 != c2:
            differences += 1

    return differences


def almost_equal(s1, s2):
    # Ensure that one string has exactly one more character than the other
    if abs(len(s1) - len(s2)) != 1:
        return False

    # Identify which string is longer
    if len(s1) > len(s2):
        longer, shorter = s1, s2
    else:
        longer, shorter = s2, s1

    # Try to find the single extra character
    for i in range(len(longer)):
        # Create a new string by removing the character at index i
        modified = longer[:i] + longer[i + 1 :]
        if modified == shorter:
            return True

    return False


def calculate_fiscal_code(member):
    def calculate_consonants(s):
        return "".join([c for c in s if c.isalpha() and c not in "AEIOUÀÈÉÌÒÙ"])

    def calculate_vowels(s):
        return "".join([c for c in s if c in "AEIOU"])

    def extract_last_name(last_name):
        last_name = last_name.upper()
        consonants = calculate_consonants(last_name)
        vowels = calculate_vowels(last_name)
        return (consonants + vowels + "XXX")[:3]

    def extract_first_name(first_name):
        first_name = first_name.upper()
        consonants = calculate_consonants(first_name)
        if len(consonants) >= 4:
            consonants = consonants[0] + consonants[2] + consonants[3]
        vowels = calculate_vowels(first_name)
        return (consonants + vowels + "XXX")[:3]

    def extract_birth_date(birth_date, male):
        month_codes = "ABCDEHLMPRST"
        if not birth_date:
            return ""
        year = str(birth_date.year)[-2:]
        month = month_codes[birth_date.month - 1]
        day = birth_date.day + (40 if not male else 0)
        return f"{year}{month}{str(day).zfill(2)}"

    def clean_birth_place(birth_place):
        if not birth_place:
            return ""
        # Remove everything in parenthesis
        cleaned_birth_place = re.sub(r"\(.*?\)", "", birth_place)
        return cleaned_birth_place

    def slugify(text):
        # Remove accents
        for char in ["à", "è", "é", "ì", "ò", "ù"]:
            text = text.replace(char, "")
        # Normalize text to remove accents and convert to ASCII
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        # Convert text to lowercase
        text = text.lower()
        # Remove quotes
        text = text.replace('"', "").replace("'", "")
        # Replace any non-alphanumeric character (excluding hyphens) with a space
        text = re.sub(r"[^a-z0-9\s-]", "", text)
        # Replace any sequence of whitespace or hyphens with a single hyphen
        text = re.sub(r"[\s-]+", "-", text)
        # Strip leading and trailing hyphens
        text = text.strip("-")
        return text

    def extract_municipality_code(birth_place):
        slug = slugify(birth_place)
        # look for nations
        file_path = os.path.join(conf_settings.BASE_DIR, "../data/istat-nations.csv")
        with open(file_path, "r") as file:
            reader = csv.reader(file)
            # second pass, search something *equal*
            for row in reader:
                if slug == slugify(row[0]):
                    return row[1]

        file_path = os.path.join(conf_settings.BASE_DIR, "../data/istat-codes.csv")
        with open(file_path, "r") as file:
            reader = csv.reader(file)
            # second pass, search something *equal*
            for row in reader:
                for el in row[0].split("/"):
                    if slug == slugify(el):
                        return row[1]

            # second pass, search something *in*
            for row in reader:
                if slug in slugify(row[0]):
                    return row[1]

        # If not found
        return ""

    def calculate_check_digit(cf_without_check_digit):
        even_values = {
            "0": 0,
            "1": 1,
            "2": 2,
            "3": 3,
            "4": 4,
            "5": 5,
            "6": 6,
            "7": 7,
            "8": 8,
            "9": 9,
            "A": 0,
            "B": 1,
            "C": 2,
            "D": 3,
            "E": 4,
            "F": 5,
            "G": 6,
            "H": 7,
            "I": 8,
            "J": 9,
            "K": 10,
            "L": 11,
            "M": 12,
            "N": 13,
            "O": 14,
            "P": 15,
            "Q": 16,
            "R": 17,
            "S": 18,
            "T": 19,
            "U": 20,
            "V": 21,
            "W": 22,
            "X": 23,
            "Y": 24,
            "Z": 25,
        }

        odd_values = {
            "0": 1,
            "1": 0,
            "2": 5,
            "3": 7,
            "4": 9,
            "5": 13,
            "6": 15,
            "7": 17,
            "8": 19,
            "9": 21,
            "A": 1,
            "B": 0,
            "C": 5,
            "D": 7,
            "E": 9,
            "F": 13,
            "G": 15,
            "H": 17,
            "I": 19,
            "J": 21,
            "K": 2,
            "L": 4,
            "M": 18,
            "N": 20,
            "O": 11,
            "P": 3,
            "Q": 6,
            "R": 8,
            "S": 12,
            "T": 14,
            "U": 16,
            "V": 10,
            "W": 22,
            "X": 25,
            "Y": 24,
            "Z": 23,
        }

        total = 0
        for i, char in enumerate(cf_without_check_digit):
            if i % 2 == 1 and char in even_values:
                total += even_values[char]
            elif char in odd_values:
                total += odd_values[char]

        check_digit = chr((total % 26) + ord("A"))
        return check_digit

    def go(member, male=True):
        # Take care of legal name
        if member.legal_name:
            splitted = member.legal_name.rsplit(" ", 1)
            if len(splitted) == 2:
                member.name, member.surname = splitted
            else:
                member.name = splitted[0]

        ctx = {"membership_cf": True}

        # Constructing the fiscal code
        last_name_code = extract_last_name(member.surname)
        first_name_code = extract_first_name(member.name)
        birth_date_code = extract_birth_date(member.birth_date, male)
        cleaned_birth_place = clean_birth_place(member.birth_place)
        municipality_code = extract_municipality_code(cleaned_birth_place)
        cf_without_check_digit = f"{last_name_code}{first_name_code}{birth_date_code}{municipality_code}"
        check_digit = calculate_check_digit(cf_without_check_digit)

        ctx["calculated_cf"] = cf_without_check_digit + check_digit
        if member.fiscal_code:
            ctx["supplied_cf"] = member.fiscal_code.upper()
        else:
            ctx["supplied_cf"] = ""
        if not municipality_code:
            ctx["error_cf"] = _("Place of birth not included in the ISTAT list")

        if almost_equal(ctx["calculated_cf"], ctx["supplied_cf"]):
            ctx["error_cf"] = _("One character more or less than expected")
        elif len(ctx["supplied_cf"]) != 16:
            ctx["error_cf"] = _("Wrong number of characters")
        elif count_differences(ctx["calculated_cf"], ctx["supplied_cf"]) == 1:
            ctx["error_cf"] = _("Differing by only one character from the expected one")
        elif ctx["calculated_cf"][:6] != ctx["supplied_cf"][:6]:
            ctx["error_cf"] = _(
                "First and last name characters do not match (remember to enter the correct first "
                "and last names in legal_name)"
            )
        elif ctx["calculated_cf"][-6:-1] != ctx["supplied_cf"][-6:-1]:
            ctx["error_cf"] = _("Characters relating to place of birth do not match (check exact municipality)")
        elif ctx["calculated_cf"][6:10] != ctx["supplied_cf"][6:10]:
            ctx["error_cf"] = _("Date of birth characters do not match (check exact date)")

        ctx["correct_cf"] = ctx["calculated_cf"] == ctx["supplied_cf"]

        return ctx

    # ignore non-italian citizens
    if member.nationality and member.nationality.lower() != "it":
        return {}
    if member.fiscal_code and member.fiscal_code.lower() == "n/a":
        return {}

    first_ctx = go(member, True)

    # If the first try didn't work, try if the user has to indicate the gender female
    if not first_ctx["correct_cf"]:
        second_ctx = go(member, False)
        if second_ctx["correct_cf"]:
            return second_ctx

    return first_ctx


def leaderboard_key(a_id):
    return f"leaderboard_{a_id}"


def update_leaderboard(a_id):
    res = []
    for mb in Membership.objects.filter(assoc_id=a_id):
        el = {
            "id": mb.member_id,
            "count": mb.member.badges.filter(assoc_id=a_id).count(),
            "created": mb.created,
            "name": mb.member.display_member(),
        }
        if mb.member.profile:
            el["profile"] = mb.member.profile_thumb.url
        if el["count"] > 0:
            res.append(el)
    res = sorted(res, key=lambda x: (x["count"], x["created"]), reverse=True)
    cache.set(leaderboard_key(a_id), res)
    return res


def get_leaderboard(a_id):
    res = cache.get(leaderboard_key(a_id))
    if not res:
        res = update_leaderboard(a_id)
    return res


def assign_badge(member, cod):
    try:
        b = Badge.objects.get(cod=cod)
        b.members.add(member)
    except Exception as e:
        print(e)
