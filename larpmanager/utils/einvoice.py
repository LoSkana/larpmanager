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
    transmission_data = ET.SubElement(header, "DatiTrasmissione")
    transmitter_id = ET.SubElement(transmission_data, "IdTrasmittente")
    # Set Italy as default country code for electronic invoicing
    ET.SubElement(transmitter_id, "IdPaese").text = "IT"
    ET.SubElement(transmitter_id, "IdCodice").text = get_assoc_config(
        inv.assoc_id, "einvoice_idcodice", None, config_holder
    )
    # Progressive invoice number padded to 10 digits
    ET.SubElement(transmission_data, "ProgressivoInvio").text = str(einvoice.progressive).zfill(10)
    # Standard format for private entities
    ET.SubElement(transmission_data, "FormatoTrasmissione").text = "FPR12"
    ET.SubElement(transmission_data, "CodiceDestinatario").text = get_assoc_config(
        inv.assoc_id, "einvoice_codicedestinatario", None, config_holder
    )

    # Build supplier section - association information as service provider
    supplier_provider = ET.SubElement(header, "CedentePrestatore")
    supplier_registry_data = ET.SubElement(supplier_provider, "DatiAnagrafici")
    # Add VAT identification details
    vat_fiscal_id = ET.SubElement(supplier_registry_data, "IdFiscaleIVA")
    ET.SubElement(vat_fiscal_id, "IdPaese").text = "IT"
    ET.SubElement(vat_fiscal_id, "IdCodice").text = get_assoc_config(
        inv.assoc_id, "einvoice_partitaiva", None, config_holder
    )
    # Add association name and tax regime
    supplier_registry = ET.SubElement(supplier_registry_data, "Anagrafica")
    ET.SubElement(supplier_registry, "Denominazione").text = get_assoc_config(
        inv.assoc_id, "einvoice_denominazione", None, config_holder
    )
    ET.SubElement(supplier_registry_data, "RegimeFiscale").text = get_assoc_config(
        inv.assoc_id, "einvoice_regimefiscale", None, config_holder
    )
    # Add association registered address
    supplier_address = ET.SubElement(supplier_provider, "Sede")
    ET.SubElement(supplier_address, "Indirizzo").text = get_assoc_config(
        inv.assoc_id, "einvoice_indirizzo", None, config_holder
    )
    ET.SubElement(supplier_address, "NumeroCivico").text = get_assoc_config(
        inv.assoc_id, "einvoice_numerocivico", None, config_holder
    )
    ET.SubElement(supplier_address, "Cap").text = get_assoc_config(inv.assoc_id, "einvoice_cap", None, config_holder)
    ET.SubElement(supplier_address, "Comune").text = get_assoc_config(
        inv.assoc_id, "einvoice_comune", None, config_holder
    )
    ET.SubElement(supplier_address, "Provincia").text = get_assoc_config(
        inv.assoc_id, "einvoice_provincia", None, config_holder
    )
    ET.SubElement(supplier_address, "Nazione").text = get_assoc_config(
        inv.assoc_id, "einvoice_nazione", None, config_holder
    )

    # Build customer section - member receiving the invoice
    customer_recipient = ET.SubElement(header, "CessionarioCommittente")
    customer_registry_data = ET.SubElement(customer_recipient, "DatiAnagrafici")
    ET.SubElement(customer_registry_data, "CodiceFiscale").text = member.fiscal_code
    # Parse member name from legal name if available
    customer_registry = ET.SubElement(customer_registry_data, "Anagrafica")
    if member.legal_name:
        name_parts = member.legal_name.rsplit(" ", 1)
        # Split into first and last name if exactly 2 parts
        if len(name_parts) == name_number:
            member.name, member.surname = name_parts
        else:
            member.name = name_parts[0]
    ET.SubElement(customer_registry, "Nome").text = member.name
    ET.SubElement(customer_registry, "Cognome").text = member.surname
    # Parse residence address from pipe-separated format: Country|Province|City|ZIP|Street|Number
    address_components = member.residence_address.split("|")
    # Handle Italian vs foreign addresses differently
    if address_components[0] == "IT":
        address_components[1] = address_components[1].replace("IT-", "")
    else:
        # Foreign addresses use special province code
        address_components[1] = "ESTERO"
    # Add customer address details
    customer_address = ET.SubElement(customer_recipient, "Sede")
    ET.SubElement(customer_address, "Indirizzo").text = address_components[4]
    ET.SubElement(customer_address, "NumeroCivico").text = address_components[5]
    ET.SubElement(customer_address, "CAP").text = address_components[3]
    ET.SubElement(customer_address, "Comune").text = address_components[2]
    ET.SubElement(customer_address, "Provincia").text = address_components[1]
    ET.SubElement(customer_address, "Nazione").text = address_components[0]


def _einvoice_body(einvoice, invoice, xml_root) -> None:
    """
    Build the body section of electronic invoice XML structure.

    Args:
        einvoice: Electronic invoice instance containing creation date and number
        invoice: Invoice data object with causal, mc_gross, and assoc_id attributes
        xml_root: XML root element to append body to

    Returns:
        None: Modifies xml_root element in place by adding FatturaElettronicaBody
    """
    # Create main body element and general data section
    invoice_body = ET.SubElement(xml_root, "FatturaElettronicaBody")
    general_data = ET.SubElement(invoice_body, "DatiGenerali")
    general_document_data = ET.SubElement(general_data, "DatiGeneraliDocumento")

    # Set document metadata: type, currency, date, and invoice number
    ET.SubElement(general_document_data, "TipoDocumento").text = "TD01"
    ET.SubElement(general_document_data, "Divisa").text = "EUR"
    ET.SubElement(general_document_data, "Data").text = einvoice.created.strftime("%Y-%m-%d")
    ET.SubElement(general_document_data, "Numero").text = "F" + str(einvoice.number).zfill(8)

    # Create goods/services section and line item details
    goods_services = ET.SubElement(invoice_body, "DatiBeniServizi")
    line_details = ET.SubElement(goods_services, "DettaglioLinee")
    ET.SubElement(line_details, "NumeroLinea").text = "1"

    # Set line item data: description, quantity, unit price, and total
    ET.SubElement(line_details, "Descrizione").text = invoice.causal
    ET.SubElement(line_details, "Quantita").text = "1"
    ET.SubElement(line_details, "PrezzoUnitario").text = f"{invoice.mc_gross:.2f}"
    ET.SubElement(line_details, "PrezzoTotale").text = f"{invoice.mc_gross:.2f}"

    config_holder = {}

    # Get VAT rate and nature configuration from association settings
    vat_rate = get_assoc_config(invoice.assoc_id, "einvoice_aliquotaiva", "", config_holder)
    ET.SubElement(line_details, "AliquotaIVA").text = vat_rate
    vat_nature = get_assoc_config(invoice.assoc_id, "einvoice_natura", "", config_holder)
    if vat_nature:
        ET.SubElement(line_details, "Natura").text = vat_nature

    # Create summary data section with VAT calculations
    summary_data = ET.SubElement(goods_services, "DatiRiepilogo")
    ET.SubElement(summary_data, "AliquotaIVA").text = vat_rate
    ET.SubElement(summary_data, "ImponibileImporto").text = f"{invoice.mc_gross:.2f}"

    # Calculate and set VAT amount based on rate and gross amount
    ET.SubElement(summary_data, "Imposta").text = f"{int(vat_rate) * float(invoice.mc_gross) / 100.0:.2f}"
    if vat_nature:
        ET.SubElement(summary_data, "Natura").text = vat_nature
