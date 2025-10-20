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

import io
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import IO

from larpmanager.cache.config import get_assoc_config
from larpmanager.models.accounting import ElectronicInvoice, PaymentInvoice
from larpmanager.models.member import Member
from larpmanager.utils.tasks import background_auto


@background_auto(queue="e-invoice")
def process_payment(invoice_id: int) -> None:
    """Process payment by generating electronic invoice XML.

    Args:
        invoice_id: Primary key of the PaymentInvoice to process

    Note:
        Creates ElectronicInvoice if it doesn't exist, then generates and saves XML.
    """
    # Retrieve the payment invoice by ID
    inv = PaymentInvoice.objects.get(pk=invoice_id)

    # Get or create electronic invoice record
    try:
        e_invoice = inv.electronicinvoice
    except Exception:
        # Create new electronic invoice if none exists
        e_invoice = ElectronicInvoice(inv=inv, year=datetime.now().year, assoc=inv.assoc)
        e_invoice.save()

    # Generate XML content for the electronic invoice
    xml = prepare_xml(inv, e_invoice)

    # Save the generated XML to the electronic invoice
    e_invoice.xml = xml
    e_invoice.save()
    # Todo sends XML and track track


def prepare_xml(inv, einvoice) -> str:
    """Generate XML structure for Italian electronic invoice.

    This function creates a compliant XML structure according to the Italian
    Sistema di Interscambio (SDI) standards for electronic invoicing.

    Args:
        inv: Invoice instance containing billing data and member information
        einvoice: Electronic invoice configuration object with header settings

    Returns:
        str: XML string formatted according to Italian e-invoice standards
            (FatturaPA v1.2.2 specification)

    Note:
        The generated XML includes both header and body sections required
        for Italian electronic invoice submission to the SDI system.
    """
    # Extract member data from invoice
    member = inv.member
    name_number = 2

    # Create root XML element with namespace declaration
    root = ET.Element("FatturaElettronica", xmlns="http://www.fatturapa.gov.it/sdi/fatturapa/v1.2.2")

    # Generate invoice header section with sender/receiver data
    _einvoice_header(einvoice, inv, member, name_number, root)

    # Generate invoice body section with line items and totals
    _einvoice_body(einvoice, inv, root)

    # Convert XML tree to string representation
    tree = ET.ElementTree(root)
    xml_bytes: IO[bytes] = io.BytesIO()

    # Write XML with UTF-8 encoding and declaration
    tree.write(xml_bytes, encoding="utf-8", xml_declaration=True)

    # Decode bytes to string for return
    # noinspection PyUnresolvedReferences
    xml_str = xml_bytes.getvalue().decode("utf-8")
    return xml_str


def _einvoice_header(
    einvoice: "ElectronicInvoice", inv: PaymentInvoice, member: Member, name_number: int, root: ET.Element
) -> None:
    """Create the header section of an electronic invoice XML structure.

    Builds transmission data and supplier/customer information according
    to Italian e-invoice standards for electronic billing compliance.

    Args:
        einvoice: Electronic invoice configuration object with progressive number
        inv: Invoice instance containing billing data and association ID
        member: Member object with customer information and residence
        name_number: Expected number of name components (typically 2)
        root: XML root element to append header data to

    Side effects:
        Modifies root XML element in-place by adding FatturaElettronicaHeader
        with transmission data, supplier (association), and customer (member) details
    """
    # Create config holder to optimize repeated calls
    config_holder = {}

    # Create main invoice header element
    header = ET.SubElement(root, "FatturaElettronicaHeader")

    # Build transmission data section with sender and destination identifiers
    dati_trasmissione = ET.SubElement(header, "DatiTrasmissione")
    id_trasmittente = ET.SubElement(dati_trasmissione, "IdTrasmittente")
    # Set Italy as default country code for electronic invoicing
    ET.SubElement(id_trasmittente, "IdPaese").text = "IT"
    ET.SubElement(id_trasmittente, "IdCodice").text = get_assoc_config(
        inv.assoc_id, "einvoice_idcodice", None, config_holder
    )
    # Progressive invoice number padded to 10 digits
    ET.SubElement(dati_trasmissione, "ProgressivoInvio").text = str(einvoice.progressive).zfill(10)
    # Standard format for private entities
    ET.SubElement(dati_trasmissione, "FormatoTrasmissione").text = "FPR12"
    ET.SubElement(dati_trasmissione, "CodiceDestinatario").text = get_assoc_config(
        inv.assoc_id, "einvoice_codicedestinatario", None, config_holder
    )

    # Build supplier section - association information as service provider
    cedente_prestatore = ET.SubElement(header, "CedentePrestatore")
    dati_anagrafici = ET.SubElement(cedente_prestatore, "DatiAnagrafici")
    # Add VAT identification details
    id_fiscale_iva = ET.SubElement(dati_anagrafici, "IdFiscaleIVA")
    ET.SubElement(id_fiscale_iva, "IdPaese").text = "IT"
    ET.SubElement(id_fiscale_iva, "IdCodice").text = get_assoc_config(
        inv.assoc_id, "einvoice_partitaiva", None, config_holder
    )
    # Add association name and tax regime
    anagrafica = ET.SubElement(dati_anagrafici, "Anagrafica")
    ET.SubElement(anagrafica, "Denominazione").text = get_assoc_config(
        inv.assoc_id, "einvoice_denominazione", None, config_holder
    )
    ET.SubElement(dati_anagrafici, "RegimeFiscale").text = get_assoc_config(
        inv.assoc_id, "einvoice_regimefiscale", None, config_holder
    )
    # Add association registered address
    sede = ET.SubElement(cedente_prestatore, "Sede")
    ET.SubElement(sede, "Indirizzo").text = get_assoc_config(inv.assoc_id, "einvoice_indirizzo", None, config_holder)
    ET.SubElement(sede, "NumeroCivico").text = get_assoc_config(
        inv.assoc_id, "einvoice_numerocivico", None, config_holder
    )
    ET.SubElement(sede, "Cap").text = get_assoc_config(inv.assoc_id, "einvoice_cap", None, config_holder)
    ET.SubElement(sede, "Comune").text = get_assoc_config(inv.assoc_id, "einvoice_comune", None, config_holder)
    ET.SubElement(sede, "Provincia").text = get_assoc_config(inv.assoc_id, "einvoice_provincia", None, config_holder)
    ET.SubElement(sede, "Nazione").text = get_assoc_config(inv.assoc_id, "einvoice_nazione", None, config_holder)

    # Build customer section - member receiving the invoice
    cessionario_committente = ET.SubElement(header, "CessionarioCommittente")
    dati_anagrafici = ET.SubElement(cessionario_committente, "DatiAnagrafici")
    ET.SubElement(dati_anagrafici, "CodiceFiscale").text = member.fiscal_code
    # Parse member name from legal name if available
    anagrafica = ET.SubElement(dati_anagrafici, "Anagrafica")
    if member.legal_name:
        splitted = member.legal_name.rsplit(" ", 1)
        # Split into first and last name if exactly 2 parts
        if len(splitted) == name_number:
            member.name, member.surname = splitted
        else:
            member.name = splitted[0]
    ET.SubElement(anagrafica, "Nome").text = member.name
    ET.SubElement(anagrafica, "Cognome").text = member.surname
    # Parse residence address from pipe-separated format: Country|Province|City|ZIP|Street|Number
    aux = member.residence_address.split("|")
    # Handle Italian vs foreign addresses differently
    if aux[0] == "IT":
        aux[1] = aux[1].replace("IT-", "")
    else:
        # Foreign addresses use special province code
        aux[1] = "ESTERO"
    # Add customer address details
    sede = ET.SubElement(cessionario_committente, "Sede")
    ET.SubElement(sede, "Indirizzo").text = aux[4]
    ET.SubElement(sede, "NumeroCivico").text = aux[5]
    ET.SubElement(sede, "CAP").text = aux[3]
    ET.SubElement(sede, "Comune").text = aux[2]
    ET.SubElement(sede, "Provincia").text = aux[1]
    ET.SubElement(sede, "Nazione").text = aux[0]


def _einvoice_body(einvoice, inv, root) -> None:
    """
    Build the body section of electronic invoice XML structure.

    Args:
        einvoice: Electronic invoice instance containing creation date and number
        inv: Invoice data object with causal, mc_gross, and assoc_id attributes
        root: XML root element to append body to

    Returns:
        None: Modifies root element in place by adding FatturaElettronicaBody
    """
    # Create main body element and general data section
    body = ET.SubElement(root, "FatturaElettronicaBody")
    dati_generali = ET.SubElement(body, "DatiGenerali")
    dati_generali_documento = ET.SubElement(dati_generali, "DatiGeneraliDocumento")

    # Set document metadata: type, currency, date, and invoice number
    ET.SubElement(dati_generali_documento, "TipoDocumento").text = "TD01"
    ET.SubElement(dati_generali_documento, "Divisa").text = "EUR"
    ET.SubElement(dati_generali_documento, "Data").text = einvoice.created.strftime("%Y-%m-%d")
    ET.SubElement(dati_generali_documento, "Numero").text = "F" + str(einvoice.number).zfill(8)

    # Create goods/services section and line item details
    beni_servizi = ET.SubElement(body, "DatiBeniServizi")
    dettaglio_linee = ET.SubElement(beni_servizi, "DettaglioLinee")
    ET.SubElement(dettaglio_linee, "NumeroLinea").text = "1"

    # Set line item data: description, quantity, unit price, and total
    ET.SubElement(dettaglio_linee, "Descrizione").text = inv.causal
    ET.SubElement(dettaglio_linee, "Quantita").text = "1"
    ET.SubElement(dettaglio_linee, "PrezzoUnitario").text = f"{inv.mc_gross:.2f}"
    ET.SubElement(dettaglio_linee, "PrezzoTotale").text = f"{inv.mc_gross:.2f}"

    config_holder = {}

    # Get VAT rate and nature configuration from association settings
    aliquotaiva = get_assoc_config(inv.assoc_id, "einvoice_aliquotaiva", "", config_holder)
    ET.SubElement(dettaglio_linee, "AliquotaIVA").text = aliquotaiva
    natura = get_assoc_config(inv.assoc_id, "einvoice_natura", "", config_holder)
    if natura:
        ET.SubElement(dettaglio_linee, "Natura").text = natura

    # Create summary data section with VAT calculations
    dati_riepilogo = ET.SubElement(beni_servizi, "DatiRiepilogo")
    ET.SubElement(dati_riepilogo, "AliquotaIVA").text = aliquotaiva
    ET.SubElement(dati_riepilogo, "ImponibileImporto").text = f"{inv.mc_gross:.2f}"

    # Calculate and set VAT amount based on rate and gross amount
    ET.SubElement(dati_riepilogo, "Imposta").text = f"{int(aliquotaiva) * float(inv.mc_gross) / 100.0:.2f}"
    if natura:
        ET.SubElement(dati_riepilogo, "Natura").text = natura
