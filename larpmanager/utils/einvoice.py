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

from larpmanager.models.accounting import ElectronicInvoice, PaymentInvoice
from larpmanager.utils.tasks import background_auto


@background_auto(queue="e-invoice")
def process_payment(invoice_id):
    inv = PaymentInvoice.objects.get(pk=invoice_id)
    try:
        e_invoice = inv.electronicinvoice
    except Exception:
        e_invoice = ElectronicInvoice(inv=inv, year=datetime.now().year, assoc=inv.assoc)
        e_invoice.save()

    xml = prepare_xml(inv, e_invoice)
    e_invoice.xml = xml
    e_invoice.save()
    # Todo sends XML and track track


def prepare_xml(inv, einvoice):
    member = inv.member
    name_number = 2

    root = ET.Element("FatturaElettronica", xmlns="http://www.fatturapa.gov.it/sdi/fatturapa/v1.2.2")

    _einvoice_header(einvoice, inv, member, name_number, root)

    _einvoice_body(einvoice, inv, root)

    # Convert to XML string
    tree = ET.ElementTree(root)
    xml_bytes: IO[bytes] = io.BytesIO()
    tree.write(xml_bytes, encoding="utf-8", xml_declaration=True)
    # noinspection PyUnresolvedReferences
    xml_str = xml_bytes.getvalue().decode("utf-8")
    return xml_str


def _einvoice_header(einvoice, inv, member, name_number, root):
    """Create the header section of an electronic invoice XML structure.

    Builds transmission data and supplier/customer information according
    to Italian e-invoice standards for electronic billing compliance.

    Args:
        einvoice: Electronic invoice configuration object
        inv: Invoice instance containing billing data
        member: Member object with customer information
        name_number (str): Unique identifier for the invoice
        root: XML root element to append header data to

    Returns:
        None: Function modifies root XML element in-place
    """
    # Invoicelettronicaheader
    header = ET.SubElement(root, "FatturaElettronicaHeader")

    # Data
    dati_trasmissione = ET.SubElement(header, "DatiTrasmissione")
    id_trasmittente = ET.SubElement(dati_trasmissione, "IdTrasmittente")
    ET.SubElement(id_trasmittente, "IdPaese").text = "IT"
    ET.SubElement(id_trasmittente, "IdCodice").text = inv.assoc.get_config("einvoice_idcodice")
    ET.SubElement(dati_trasmissione, "ProgressivoInvio").text = str(einvoice.progressive).zfill(10)
    ET.SubElement(dati_trasmissione, "FormatoTrasmissione").text = "FPR12"
    ET.SubElement(dati_trasmissione, "CodiceDestinatario").text = inv.assoc.get_config("einvoice_codicedestinatario")

    # Transferor (data of the association)
    cedente_prestatore = ET.SubElement(header, "CedentePrestatore")
    dati_anagrafici = ET.SubElement(cedente_prestatore, "DatiAnagrafici")
    id_fiscale_iva = ET.SubElement(dati_anagrafici, "IdFiscaleIVA")
    ET.SubElement(id_fiscale_iva, "IdPaese").text = "IT"
    ET.SubElement(id_fiscale_iva, "IdCodice").text = inv.assoc.get_config("einvoice_partitaiva")
    anagrafica = ET.SubElement(dati_anagrafici, "Anagrafica")
    ET.SubElement(anagrafica, "Denominazione").text = inv.assoc.get_config("einvoice_denominazione")
    ET.SubElement(dati_anagrafici, "RegimeFiscale").text = inv.assoc.get_config("einvoice_regimefiscale")
    sede = ET.SubElement(cedente_prestatore, "Sede")
    ET.SubElement(sede, "Indirizzo").text = inv.assoc.get_config("einvoice_indirizzo")
    ET.SubElement(sede, "NumeroCivico").text = inv.assoc.get_config("einvoice_numerocivico")
    ET.SubElement(sede, "Cap").text = inv.assoc.get_config("einvoice_cap")
    ET.SubElement(sede, "Comune").text = inv.assoc.get_config("einvoice_comune")
    ET.SubElement(sede, "Provincia").text = inv.assoc.get_config("einvoice_provincia")
    ET.SubElement(sede, "Nazione").text = inv.assoc.get_config("einvoice_nazione")

    # Referred
    cessionario_committente = ET.SubElement(header, "CessionarioCommittente")
    dati_anagrafici = ET.SubElement(cessionario_committente, "DatiAnagrafici")
    ET.SubElement(dati_anagrafici, "CodiceFiscale").text = member.fiscal_code
    anagrafica = ET.SubElement(dati_anagrafici, "Anagrafica")
    if member.legal_name:
        splitted = member.legal_name.rsplit(" ", 1)
        if len(splitted) == name_number:
            member.name, member.surname = splitted
        else:
            member.name = splitted[0]
    ET.SubElement(anagrafica, "Nome").text = member.name
    ET.SubElement(anagrafica, "Cognome").text = member.surname
    aux = member.residence_address.split("|")
    if aux[0] == "IT":
        aux[1] = aux[1].replace("IT-", "")
    else:
        aux[1] = "ESTERO"
    sede = ET.SubElement(cessionario_committente, "Sede")
    ET.SubElement(sede, "Indirizzo").text = aux[4]
    ET.SubElement(sede, "NumeroCivico").text = aux[5]
    ET.SubElement(sede, "CAP").text = aux[3]
    ET.SubElement(sede, "Comune").text = aux[2]
    ET.SubElement(sede, "Provincia").text = aux[1]
    ET.SubElement(sede, "Nazione").text = aux[0]


def _einvoice_body(einvoice, inv, root):
    # Invoicelettronicabody
    body = ET.SubElement(root, "FatturaElettronicaBody")
    dati_generali = ET.SubElement(body, "DatiGenerali")
    dati_generali_documento = ET.SubElement(dati_generali, "DatiGeneraliDocumento")
    ET.SubElement(dati_generali_documento, "TipoDocumento").text = "TD01"
    ET.SubElement(dati_generali_documento, "Divisa").text = "EUR"
    ET.SubElement(dati_generali_documento, "Data").text = einvoice.created.strftime("%Y-%m-%d")
    ET.SubElement(dati_generali_documento, "Numero").text = "F" + str(einvoice.number).zfill(8)

    # Datibeniservizi
    beni_servizi = ET.SubElement(body, "DatiBeniServizi")
    dettaglio_linee = ET.SubElement(beni_servizi, "DettaglioLinee")
    ET.SubElement(dettaglio_linee, "NumeroLinea").text = "1"
    ET.SubElement(dettaglio_linee, "Descrizione").text = inv.causal
    ET.SubElement(dettaglio_linee, "Quantita").text = "1"
    ET.SubElement(dettaglio_linee, "PrezzoUnitario").text = f"{inv.mc_gross:.2f}"
    ET.SubElement(dettaglio_linee, "PrezzoTotale").text = f"{inv.mc_gross:.2f}"
    aliquotaiva = inv.assoc.get_config("einvoice_aliquotaiva", "")
    ET.SubElement(dettaglio_linee, "AliquotaIVA").text = aliquotaiva
    natura = inv.assoc.get_config("einvoice_natura", "")
    if natura:
        ET.SubElement(dettaglio_linee, "Natura").text = natura

    # Data
    dati_riepilogo = ET.SubElement(beni_servizi, "DatiRiepilogo")
    ET.SubElement(dati_riepilogo, "AliquotaIVA").text = aliquotaiva
    ET.SubElement(dati_riepilogo, "ImponibileImporto").text = f"{inv.mc_gross:.2f}"
    ET.SubElement(dati_riepilogo, "Imposta").text = f"{int(aliquotaiva) * float(inv.mc_gross) / 100.0:.2f}"
    if natura:
        ET.SubElement(dati_riepilogo, "Natura").text = natura
